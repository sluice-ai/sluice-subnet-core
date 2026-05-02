from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import bittensor as bt
from pydantic import ValidationError

from sluice.agent_screener import screen_agent
from sluice.models import RoutingExecutionReport, RoutingTask

try:
    import docker
except ImportError:  # pragma: no cover
    docker = None


class SandboxRunner:
    IMAGE_NAME = os.getenv("SLUICE_SANDBOX_IMAGE", "sluice-router-agent:latest")
    CLONE_TIMEOUT_S = int(os.getenv("SLUICE_CLONE_TIMEOUT", "45"))
    SANDBOX_TIMEOUT_S = int(os.getenv("SANDBOX_TIMEOUT", "45"))
    MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_SANDBOXES", "4"))
    AGENT_CANDIDATE_PATHS = (
        "agent.py",
        "agent/agent.py",
        "router.py",
        "src/agent.py",
    )

    def __init__(self):
        self.client = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    def _get_client(self):
        if docker is None:
            raise RuntimeError(
                "The docker Python package is not installed. Install dependencies from requirements.txt."
            )
        if self.client is None:
            self.client = docker.from_env()
        return self.client

    def build_image(self, dockerfile_dir: str = "agent") -> None:
        bt.logging.info(f"Building Sluice sandbox image from {dockerfile_dir}")
        self._get_client().images.build(path=str(dockerfile_dir), tag=self.IMAGE_NAME, rm=True)

    async def run_all(
        self,
        repo_urls: list[Optional[str]],
        task: RoutingTask,
    ) -> list[Optional[RoutingExecutionReport]]:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)

        results: list[Optional[RoutingExecutionReport]] = [None] * len(repo_urls)
        loop = asyncio.get_running_loop()

        async def run_one(index: int, repo_url: str) -> None:
            async with self._semaphore:
                results[index] = await loop.run_in_executor(
                    None, self._run_sync, index, repo_url, task
                )

        await asyncio.gather(
            *[
                run_one(index, repo_url)
                for index, repo_url in enumerate(repo_urls)
                if repo_url
            ]
        )
        return results

    def _run_sync(
        self,
        index: int,
        repo_url: str,
        task: RoutingTask,
    ) -> Optional[RoutingExecutionReport]:
        tag = f"miner-{index}"
        container = None

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_dir = root / "repo"
            task_dir = root / "challenge"
            task_dir.mkdir()

            if not self._clone_repo(tag, repo_url, repo_dir):
                return None

            agent_path = self._find_agent_entry(repo_dir)
            if agent_path is None:
                bt.logging.warning(f"{tag}: no routing agent found in {repo_url}")
                return None

            is_safe, screening_report = screen_agent(str(agent_path))
            if not is_safe:
                bt.logging.warning(f"{tag}: screener rejected router repo\n{screening_report}")
                return None

            (task_dir / "task.json").write_text(
                task.model_dump_json(indent=2),
                encoding="utf-8",
            )

            try:
                container = self._run_container(
                    repo_dir=repo_dir,
                    task_dir=task_dir,
                    relative_agent_path=agent_path.relative_to(repo_dir).as_posix(),
                )
                container.wait(timeout=self.SANDBOX_TIMEOUT_S)
                return self._extract_report(container)
            except Exception as exc:
                bt.logging.warning(f"{tag}: sandbox execution failed: {exc}")
                return None
            finally:
                if container is not None:
                    self._cleanup(container)

    def _clone_repo(self, tag: str, repo_url: str, dest: Path) -> bool:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--single-branch", repo_url, str(dest)],
                check=True,
                timeout=self.CLONE_TIMEOUT_S,
                capture_output=True,
                text=True,
            )
            bt.logging.info(f"{tag}: cloned router repo {repo_url}")
            return True
        except subprocess.TimeoutExpired:
            bt.logging.warning(f"{tag}: clone timed out for {repo_url}")
        except subprocess.CalledProcessError as exc:
            bt.logging.warning(f"{tag}: clone failed for {repo_url}: {exc.stderr.strip()}")
        return False

    def _find_agent_entry(self, repo_dir: Path) -> Optional[Path]:
        for relative_path in self.AGENT_CANDIDATE_PATHS:
            candidate = repo_dir / relative_path
            if candidate.exists():
                return candidate
        return None

    def _run_container(
        self,
        repo_dir: Path,
        task_dir: Path,
        relative_agent_path: str,
    ):
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
            environment={"AGENT_RELATIVE_PATH": relative_agent_path},
            volumes={
                str(repo_dir): {"bind": "/miner_agent", "mode": "ro"},
                str(task_dir): {"bind": "/challenge", "mode": "ro"},
            },
        )

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
