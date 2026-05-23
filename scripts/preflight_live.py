from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sluice.models import RouterArtifactManifest
from sluice.router import load_manifest_file


def _merge_env(path: Path) -> dict[str, str]:
    values = {key: value for key, value in dotenv_values(path).items() if value is not None}
    for key, value in os.environ.items():
        values[key] = value
    return values


def _ok(message: str) -> tuple[bool, str]:
    return True, f"OK: {message}"


def _fail(message: str) -> tuple[bool, str]:
    return False, f"FAIL: {message}"


def _warn(message: str) -> tuple[bool, str]:
    return True, f"WARN: {message}"


def _check_command(command: str) -> tuple[bool, str]:
    path = shutil.which(command)
    if path is None:
        sibling = Path(sys.executable).parent / command
        if sibling.exists():
            return _ok(f"`{command}` found at {sibling}")
        return _fail(f"`{command}` is not on PATH")
    return _ok(f"`{command}` found at {path}")


def _check_host_docker_cli() -> tuple[bool, str]:
    if shutil.which("flatpak-spawn") is None:
        return _fail("SLUICE_USE_HOST_DOCKER_CLI=1 but `flatpak-spawn` is not on PATH")

    result = subprocess.run(
        ["flatpak-spawn", "--host", "docker", "info", "--format", "{{.ServerVersion}}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return _fail(f"host Docker daemon is not reachable via flatpak-spawn: {detail}")
    return _ok(f"host Docker daemon reachable via flatpak-spawn, server={result.stdout.strip()}")


def _check_docker(env: dict[str, str]) -> tuple[bool, str]:
    if env.get("SLUICE_USE_HOST_DOCKER_CLI", "0").strip() == "1":
        return _check_host_docker_cli()

    if shutil.which("docker") is None:
        return _fail("Docker is not installed or not on PATH")

    result = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return _fail(f"Docker daemon is not reachable: {detail}")
    return _ok(f"Docker daemon reachable, server={result.stdout.strip()}")


def _manifest_from_env(env: dict[str, str]) -> RouterArtifactManifest | None:
    manifest_path = env.get("ROUTER_MANIFEST_PATH", "").strip()
    if manifest_path:
        return load_manifest_file(manifest_path)

    artifact_uri = env.get("ROUTER_ARTIFACT_URI", "").strip()
    artifact_sha256 = env.get("ROUTER_ARTIFACT_SHA256", "").strip()
    if not artifact_uri or not artifact_sha256:
        return None

    return RouterArtifactManifest(
        artifact_uri=artifact_uri,
        sha256=artifact_sha256,
        artifact_format=env.get("ROUTER_ARTIFACT_FORMAT", "tar.gz").strip(),
        entrypoint_path=env.get("ROUTER_ENTRYPOINT_PATH", "agent.py").strip(),
        entrypoint_callable=env.get("ROUTER_ENTRYPOINT_CALLABLE", "agent_main").strip(),
        router_name=env.get("ROUTER_LABEL", "sluice-router").strip(),
        router_version=env.get("ROUTER_VERSION", "0.1.0").strip(),
        supported_capabilities=[
            item.strip().lower()
            for item in env.get("ROUTER_SUPPORTED_CAPABILITIES", "").split(",")
            if item.strip()
        ],
        supported_privacy_tiers=[
            item.strip().lower()
            for item in env.get("ROUTER_SUPPORTED_PRIVACY_TIERS", "public").split(",")
            if item.strip()
        ],
        description=env.get("ROUTER_SUMMARY", "").strip(),
    )


def _check_miner(env: dict[str, str], allow_local_artifact: bool) -> list[tuple[bool, str]]:
    checks: list[tuple[bool, str]] = []
    try:
        manifest = _manifest_from_env(env)
    except Exception as exc:
        return [_fail(f"Miner manifest is invalid: {exc}")]

    if manifest is None:
        return [_fail("Set ROUTER_MANIFEST_PATH or ROUTER_ARTIFACT_URI plus ROUTER_ARTIFACT_SHA256")]

    parsed = urlparse(manifest.artifact_uri)
    if parsed.scheme in {"http", "https"}:
        if parsed.scheme == "https":
            checks.append(_ok(f"miner artifact URI is public HTTPS: {manifest.artifact_uri}"))
        else:
            checks.append(_warn(f"miner artifact URI is HTTP; HTTPS is preferred: {manifest.artifact_uri}"))
    elif allow_local_artifact:
        checks.append(_warn(f"local artifact URI allowed by flag: {manifest.artifact_uri}"))
    else:
        checks.append(
            _fail(
                "miner artifact URI is local. Upload the artifact and build the manifest "
                f"with --artifact-uri. Current URI: {manifest.artifact_uri}"
            )
        )

    if not manifest.supported_capabilities:
        checks.append(_warn("miner manifest has no supported_capabilities"))
    else:
        checks.append(_ok(f"miner capabilities={','.join(manifest.supported_capabilities)}"))

    return checks


def _check_validator(env: dict[str, str]) -> list[tuple[bool, str]]:
    checks: list[tuple[bool, str]] = []
    if env.get("SLUICE_LOCAL_DEV_EXECUTION", "0").strip() == "1":
        checks.append(_fail("SLUICE_LOCAL_DEV_EXECUTION=1; live validators must use Docker sandboxing"))
    else:
        checks.append(_ok("SLUICE_LOCAL_DEV_EXECUTION is disabled"))

    if env.get("SLUICE_SKIP_SANDBOX_BUILD", "0").strip() == "1":
        checks.append(_warn("SLUICE_SKIP_SANDBOX_BUILD=1; make sure the sandbox image already exists"))
    else:
        checks.append(_ok("validator will build the sandbox image on startup"))

    checks.append(_check_docker(env))
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check live Sluice subnet readiness.")
    parser.add_argument(
        "--role",
        choices=["miner", "validator", "both"],
        default="both",
        help="Which side to check.",
    )
    parser.add_argument("--miner-env", default=".env.miner")
    parser.add_argument("--validator-env", default=".env.validator")
    parser.add_argument(
        "--allow-local-artifact",
        action="store_true",
        help="Allow file:// artifacts. Use only for local or single-machine testing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks: list[tuple[bool, str]] = [_check_command("btcli")]

    if args.role in {"miner", "both"}:
        checks.extend(_check_miner(_merge_env(ROOT / args.miner_env), args.allow_local_artifact))

    if args.role in {"validator", "both"}:
        checks.extend(_check_validator(_merge_env(ROOT / args.validator_env)))

    for passed, message in checks:
        print(message)

    return 0 if all(passed for passed, _message in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
