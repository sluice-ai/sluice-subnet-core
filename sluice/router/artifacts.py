from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from sluice.models import PrivacyTier, RouterArtifactFormat, RouterArtifactManifest


CHUNK_SIZE = 1024 * 1024


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_directory(path: Path) -> str:
    hasher = hashlib.sha256()
    root = path.resolve()

    for child in sorted(root.rglob("*")):
        relative = child.relative_to(root).as_posix()
        if child.is_symlink():
            raise ValueError(f"Symlinks are not supported in router artifacts: {relative}")
        if child.is_dir():
            hasher.update(f"dir:{relative}\n".encode("utf-8"))
            continue
        hasher.update(f"file:{relative}\n".encode("utf-8"))
        with child.open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        hasher.update(b"\n")

    return hasher.hexdigest()


def compute_artifact_sha256(path: Path, artifact_format: RouterArtifactFormat | str) -> str:
    normalized_format = (
        artifact_format
        if isinstance(artifact_format, RouterArtifactFormat)
        else RouterArtifactFormat(artifact_format)
    )
    if normalized_format == RouterArtifactFormat.directory:
        return sha256_directory(path)
    return sha256_file(path)


def load_manifest_file(path: str | Path) -> RouterArtifactManifest:
    manifest_path = Path(path)
    return RouterArtifactManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )


def write_manifest_file(path: str | Path, manifest: RouterArtifactManifest) -> Path:
    manifest_path = Path(path)
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def create_router_archive(
    source_dir: str | Path,
    destination: str | Path,
    *,
    artifact_format: RouterArtifactFormat = RouterArtifactFormat.tar_gz,
) -> Path:
    root = Path(source_dir).resolve()
    output_path = Path(destination).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if artifact_format == RouterArtifactFormat.directory:
        raise ValueError("create_router_archive() does not support directory artifacts.")

    files = sorted(path for path in root.rglob("*") if path.is_file())
    if artifact_format in (RouterArtifactFormat.tar, RouterArtifactFormat.tar_gz):
        mode = "w:gz" if artifact_format == RouterArtifactFormat.tar_gz else "w"
        with tarfile.open(output_path, mode) as archive:
            for file_path in files:
                relative = file_path.relative_to(root).as_posix()
                info = archive.gettarinfo(str(file_path), arcname=relative)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                with file_path.open("rb") as handle:
                    archive.addfile(info, handle)
        return output_path

    if artifact_format == RouterArtifactFormat.zip:
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in files:
                relative = file_path.relative_to(root).as_posix()
                info = zipfile.ZipInfo(filename=relative)
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, file_path.read_bytes())
        return output_path

    raise ValueError(f"Unsupported artifact format: {artifact_format}")


def manifest_from_source(
    *,
    source_dir: str | Path,
    artifact_uri: str,
    artifact_format: RouterArtifactFormat,
    entrypoint_path: str = "agent.py",
    entrypoint_callable: str = "agent_main",
    router_name: str = "sluice-router",
    router_version: str = "0.1.0",
    supported_capabilities: list[str] | None = None,
    supported_privacy_tiers: list[str] | None = None,
    description: str = "",
    metadata: dict | None = None,
) -> RouterArtifactManifest:
    source_root = Path(source_dir).resolve()
    if artifact_format == RouterArtifactFormat.directory:
        artifact_path = source_root
        artifact_size_bytes = None
    else:
        parsed = urlparse(artifact_uri)
        if parsed.scheme == "file":
            artifact_path = Path(unquote(parsed.path)).resolve()
        elif parsed.scheme == "":
            artifact_path = Path(artifact_uri).expanduser().resolve()
        else:
            raise ValueError(
                "manifest_from_source() only supports local artifact URIs when computing hashes."
            )
        artifact_size_bytes = artifact_path.stat().st_size

    return RouterArtifactManifest(
        artifact_uri=artifact_uri,
        sha256=compute_artifact_sha256(artifact_path, artifact_format),
        artifact_format=artifact_format,
        entrypoint_path=entrypoint_path,
        entrypoint_callable=entrypoint_callable,
        router_name=router_name,
        router_version=router_version,
        supported_capabilities=supported_capabilities or [],
        supported_privacy_tiers=supported_privacy_tiers or [PrivacyTier.public.value],
        description=description,
        artifact_size_bytes=artifact_size_bytes,
        metadata=metadata or {},
    )
