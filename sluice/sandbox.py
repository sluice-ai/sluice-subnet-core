from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import bittensor as bt
from pydantic import ValidationError

from sluice.agent_screener import screen_agent
from sluice.models import RouterArtifactManifest, RoutingExecutionReport, RoutingTask
from sluice.router.cache import ArtifactCache

try:
    import docker
except ImportError:  # pragma: no cover
    docker = None


@dataclass
class HostDockerContainer:
    runner: "SandboxRunner"
    container_id: str

    def wait(self, timeout: int) -> None:
        self.runner._host_docker_wait(self.container_id, timeout)

    def logs(self, stdout: bool = True, stderr: bool = False) -> bytes:
        return self.runner._host_docker_logs(
            self.container_id, stdout=stdout, stderr=stderr
        )

    def remove(self, force: bool = True) -> None:
        self.runner._host_docker_remove(self.container_id, force=force)


class SandboxRunner:
    IMAGE_NAME = os.getenv("SLUICE_SANDBOX_IMAGE", "sluice-router-agent:latest")
    SANDBOX_TIMEOUT_S = int(os.getenv("SANDBOX_TIMEOUT", "45"))
    MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_SANDBOXES", "4"))
    HOST_RUNTIME_ROOT = Path(
        os.getenv(
            "SLUICE_HOST_RUNTIME_ROOT",
            "~/.cache/sluice/host-runtime",
        )
    ).expanduser()

    def __init__(self, artifact_cache: ArtifactCache | None = None):
        self.client = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self.artifact_cache = artifact_cache or ArtifactCache()
        self.local_dev_execution = os.getenv("SLUICE_LOCAL_DEV_EXECUTION", "0") == "1"
        self._host_docker_checked = False
        self._host_docker_available = False
        self._use_host_docker_cli = (
            os.getenv("SLUICE_USE_HOST_DOCKER_CLI", "0") == "1"
        )
        self.HOST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

    def _temporary_runtime_dir(self):
        return tempfile.TemporaryDirectory(
            dir=self.HOST_RUNTIME_ROOT,
            prefix="sandbox-",
        )

    def _host_docker_command_prefix(self) -> list[str]:
        return ["flatpak-spawn", "--host", "docker"]

    def _check_host_docker_cli(self) -> bool:
        if self._host_docker_checked:
            return self._host_docker_available

        self._host_docker_checked = True
        if shutil.which("flatpak-spawn") is None:
            self._host_docker_available = False
            return False

        try:
            result = subprocess.run(
                [*self._host_docker_command_prefix(), "version"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except Exception:
            self._host_docker_available = False
            return False

        self._host_docker_available = result.returncode == 0
        return self._host_docker_available

    def _run_host_docker(
        self,
        args: list[str],
        *,
        check: bool = True,
        timeout: int | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [*self._host_docker_command_prefix(), *args],
            check=check,
            timeout=timeout,
            text=False,
            capture_output=capture_output,
        )

    def _get_client(self):
        if self._use_host_docker_cli:
            return None
        if docker is None:
            if self._check_host_docker_cli():
                bt.logging.warning(
                    "Docker SDK unavailable inside the current sandbox; "
                    "falling back to host Docker via flatpak-spawn."
                )
                self._use_host_docker_cli = True
                return None
            raise RuntimeError(
                "The docker Python package is not installed. Install dependencies from requirements.txt."
            )
        if self.client is None:
            try:
                self.client = docker.from_env()
                self.client.ping()
            except Exception:
                if self._check_host_docker_cli():
                    bt.logging.warning(
                        "Docker socket is not reachable from the current sandbox; "
                        "falling back to host Docker via flatpak-spawn."
                    )
                    self._use_host_docker_cli = True
                    self.client = None
                    return None
                raise
        return self.client

    def build_image(self, dockerfile_dir: str = "agent") -> None:
        bt.logging.info(f"Building Sluice sandbox image from {dockerfile_dir}")
        client = self._get_client()
        if self._use_host_docker_cli:
            self._run_host_docker(
                ["build", "--rm", "-t", self.IMAGE_NAME, str(dockerfile_dir)],
                timeout=max(300, self.SANDBOX_TIMEOUT_S),
            )
            return

        client.images.build(path=str(dockerfile_dir), tag=self.IMAGE_NAME, rm=True)

    async def run_all(
        self,
        manifests: list[Optional[RouterArtifactManifest]],
        task: RoutingTask,
    ) -> list[Optional[RoutingExecutionReport]]:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)

        results: list[Optional[RoutingExecutionReport]] = [None] * len(manifests)
        loop = asyncio.get_running_loop()

        async def run_one(index: int, manifest: RouterArtifactManifest) -> None:
            async with self._semaphore:
                results[index] = await loop.run_in_executor(
                    None, self._run_sync, index, manifest, task
                )

        await asyncio.gather(
            *[
                run_one(index, manifest)
                for index, manifest in enumerate(manifests)
                if manifest is not None
            ]
        )
        return results

    def _run_sync(
        self,
        index: int,
        manifest: RouterArtifactManifest,
        task: RoutingTask,
    ) -> Optional[RoutingExecutionReport]:
        tag = (
            f"miner-{index} router={manifest.router_name} "
            f"version={manifest.router_version} sha={manifest.sha256[:12]}"
        )
        container = None

        with self._temporary_runtime_dir() as temp_dir:
            root = Path(temp_dir)
            task_dir = root / "challenge"
            task_dir.mkdir()

            try:
                cached_artifact = self.artifact_cache.materialize(manifest)
            except Exception as exc:
                bt.logging.warning(f"{tag}: artifact materialization failed: {exc}")
                return None

            agent_path = cached_artifact.entrypoint_path

            is_safe, screening_report = screen_agent(str(agent_path))
            if not is_safe:
                bt.logging.warning(f"{tag}: screener rejected router artifact\n{screening_report}")
                return None

            (task_dir / "task.json").write_text(
                task.model_dump_json(indent=2),
                encoding="utf-8",
            )

            try:
                if self.local_dev_execution:
                    bt.logging.warning(
                        f"{tag}: using local dev execution path without Docker sandbox"
                    )
                    return self._run_local(
                        artifact_dir=cached_artifact.artifact_root,
                        relative_agent_path=agent_path.relative_to(
                            cached_artifact.artifact_root
                        ).as_posix(),
                        entrypoint_callable=manifest.entrypoint_callable,
                        task=task,
                    )

                container = self._run_container(
                    artifact_dir=cached_artifact.artifact_root,
                    task_dir=task_dir,
                    relative_agent_path=agent_path.relative_to(
                        cached_artifact.artifact_root
                    ).as_posix(),
                    entrypoint_callable=manifest.entrypoint_callable,
                )
                container.wait(timeout=self.SANDBOX_TIMEOUT_S)
                return self._extract_report(container)
            except Exception as exc:
                bt.logging.warning(f"{tag}: sandbox execution failed: {exc}")
                return None
            finally:
                if container is not None:
                    self._cleanup(container)

    def _run_local(
        self,
        *,
        artifact_dir: Path,
        relative_agent_path: str,
        entrypoint_callable: str,
        task: RoutingTask,
    ) -> Optional[RoutingExecutionReport]:
        runner_path = Path(__file__).resolve().parent.parent / "agent" / "runner.py"
        task_id = task.task_id
        with self._temporary_runtime_dir() as temp_dir:
            task_dir = Path(temp_dir)
            task_file = task_dir / "task.json"
            task_file.write_text(task.model_dump_json(indent=2), encoding="utf-8")

            spec = importlib.util.spec_from_file_location("sluice_dev_runner", str(runner_path))
            if spec is None or spec.loader is None:
                raise RuntimeError("Failed to load agent runner module for local dev execution.")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            module.MINER_ROOT = artifact_dir
            module.TASK_FILE = task_file
            module.AGENT_RELATIVE_PATH = relative_agent_path
            module.AGENT_ENTRYPOINT_CALLABLE = entrypoint_callable

            try:
                agent_module = module.load_agent()
                result = module.call_agent_with_deadline(agent_module, task.model_dump(mode="json"))
            except Exception as exc:
                bt.logging.warning(f"local dev runner failed for task={task_id}: {exc}")
                result = module.error_report(task_id, f"{type(exc).__name__}: {exc}")

            return RoutingExecutionReport.model_validate(result)

    def _run_container(
        self,
        artifact_dir: Path,
        task_dir: Path,
        relative_agent_path: str,
        entrypoint_callable: str,
    ):
        client = self._get_client()
        if self._use_host_docker_cli:
            command = [
                "run",
                "-d",
                "--network",
                "none",
                "--read-only",
                "--memory",
                "512m",
                "--cpus",
                "1.0",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=128m",
                "-e",
                f"AGENT_RELATIVE_PATH={relative_agent_path}",
                "-e",
                f"AGENT_ENTRYPOINT_CALLABLE={entrypoint_callable}",
                "-v",
                f"{artifact_dir}:/miner_agent:ro",
                "-v",
                f"{task_dir}:/challenge:ro",
                self.IMAGE_NAME,
            ]
            result = self._run_host_docker(
                command,
                capture_output=True,
            )
            container_id = result.stdout.decode("utf-8", errors="ignore").strip()
            if not container_id:
                raise RuntimeError("Host Docker run did not return a container id.")
            return HostDockerContainer(runner=self, container_id=container_id)

        return self._get_client().containers.run(
            self.IMAGE_NAME,
            detach=True,
            network_disabled=True,
            read_only=True,
            mem_limit="512m",
            nano_cpus=1_000_000_000,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=128m"},
            environment={
                "AGENT_RELATIVE_PATH": relative_agent_path,
                "AGENT_ENTRYPOINT_CALLABLE": entrypoint_callable,
            },
            volumes={
                str(artifact_dir): {"bind": "/miner_agent", "mode": "ro"},
                str(task_dir): {"bind": "/challenge", "mode": "ro"},
            },
        )

    def _host_docker_wait(self, container_id: str, timeout: int) -> None:
        self._run_host_docker(
            ["wait", container_id],
            timeout=timeout,
        )

    def _host_docker_logs(
        self, container_id: str, *, stdout: bool = True, stderr: bool = False
    ) -> bytes:
        command = ["logs", container_id]
        result = self._run_host_docker(
            command,
            capture_output=True,
            check=False,
        )
        return result.stdout

    def _host_docker_remove(self, container_id: str, force: bool = True) -> None:
        command = ["rm"]
        if force:
            command.append("-f")
        command.append(container_id)
        self._run_host_docker(command, check=False)

    def _extract_report(self, container) -> Optional[RoutingExecutionReport]:
        raw_logs = container.logs(stdout=True, stderr=False).decode("utf-8", errors="ignore").strip()
        if not raw_logs:
            return None

        for line in reversed(raw_logs.splitlines()):
            candidate = line.strip()
            if not candidate:
                continue
            try:
                return RoutingExecutionReport.model_validate(json.loads(candidate))
            except (ValidationError, json.JSONDecodeError):
                continue
        return None

    def _cleanup(self, container) -> None:
        try:
            container.remove(force=True)
        except Exception:
            pass
