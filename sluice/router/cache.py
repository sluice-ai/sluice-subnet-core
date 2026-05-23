from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from sluice.models import RouterArtifactFormat, RouterArtifactManifest
from sluice.router.artifacts import compute_artifact_sha256, sha256_directory


@dataclass
class CachedArtifact:
    manifest: RouterArtifactManifest
    cache_dir: Path
    artifact_root: Path
    entrypoint_path: Path


class ArtifactCache:
    def __init__(self, cache_dir: str | Path | None = None):
        default_root = Path(
            os.getenv("SLUICE_ARTIFACT_CACHE_DIR", "~/.cache/sluice/router-artifacts")
        ).expanduser()
        self.cache_dir = Path(cache_dir or default_root).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def materialize(self, manifest: RouterArtifactManifest) -> CachedArtifact:
        artifact_root = self.cache_dir / manifest.sha256
        entrypoint_path = artifact_root / "artifact" / manifest.entrypoint_path

        if entrypoint_path.exists():
            return CachedArtifact(
                manifest=manifest,
                cache_dir=self.cache_dir,
                artifact_root=artifact_root / "artifact",
                entrypoint_path=entrypoint_path,
            )

        with tempfile.TemporaryDirectory(dir=self.cache_dir, prefix=f"{manifest.sha256}-") as temp_dir:
            staging_root = Path(temp_dir)
            unpacked_root = staging_root / "artifact"
            unpacked_root.mkdir(parents=True, exist_ok=True)

            if manifest.artifact_format == RouterArtifactFormat.directory:
                source_dir = self._resolve_local_directory(manifest.artifact_uri)
                actual_sha = sha256_directory(source_dir)
                if actual_sha != manifest.sha256:
                    raise ValueError(
                        f"Directory artifact digest mismatch for {manifest.router_name}: "
                        f"expected {manifest.sha256}, got {actual_sha}"
                    )
                self._copy_directory(source_dir, unpacked_root)
            else:
                raw_artifact = staging_root / f"artifact{self._artifact_suffix(manifest.artifact_format)}"
                self._fetch_to_path(manifest.artifact_uri, raw_artifact)
                actual_sha = compute_artifact_sha256(raw_artifact, manifest.artifact_format)
                if actual_sha != manifest.sha256:
                    raise ValueError(
                        f"Artifact digest mismatch for {manifest.router_name}: "
                        f"expected {manifest.sha256}, got {actual_sha}"
                    )
                self._extract_archive(raw_artifact, unpacked_root, manifest.artifact_format)

            entrypoint = unpacked_root / manifest.entrypoint_path
            if not entrypoint.exists():
                raise FileNotFoundError(
                    f"Entrypoint {manifest.entrypoint_path} is missing from artifact {manifest.router_name}"
                )

            metadata_path = staging_root / "manifest.json"
            metadata_path.write_text(
                json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            try:
                if artifact_root.exists():
                    shutil.rmtree(artifact_root)
                shutil.move(str(staging_root), str(artifact_root))
            except FileExistsError:
                pass
            except FileNotFoundError:
                pass

        if not entrypoint_path.exists():
            raise FileNotFoundError(
                f"Cached artifact entrypoint missing after materialization: {entrypoint_path}"
            )

        return CachedArtifact(
            manifest=manifest,
            cache_dir=self.cache_dir,
            artifact_root=artifact_root / "artifact",
            entrypoint_path=artifact_root / "artifact" / manifest.entrypoint_path,
        )

    def _resolve_local_directory(self, artifact_uri: str) -> Path:
        candidate = self._local_path_from_uri(artifact_uri)
        if candidate is None or not candidate.exists() or not candidate.is_dir():
            raise FileNotFoundError(f"Directory artifact not found: {artifact_uri}")
        return candidate.resolve()

    def _fetch_to_path(self, artifact_uri: str, destination: Path) -> None:
        local_path = self._local_path_from_uri(artifact_uri)
        if local_path is not None:
            if not local_path.exists() or not local_path.is_file():
                raise FileNotFoundError(f"Artifact file not found: {artifact_uri}")
            shutil.copy2(local_path, destination)
            return

        parsed = urlparse(artifact_uri)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported artifact URI: {artifact_uri}")

        with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            with client.stream("GET", artifact_uri) as response:
                response.raise_for_status()
                with destination.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        if chunk:
                            handle.write(chunk)

    @staticmethod
    def _local_path_from_uri(artifact_uri: str) -> Path | None:
        parsed = urlparse(artifact_uri)
        if parsed.scheme == "file":
            return Path(unquote(parsed.path))
        if parsed.scheme == "":
            return Path(artifact_uri).expanduser()
        return None

    @staticmethod
    def _copy_directory(source_dir: Path, destination: Path) -> None:
        for child in source_dir.rglob("*"):
            relative = child.relative_to(source_dir)
            target = destination / relative
            if child.is_symlink():
                raise ValueError(f"Symlinks are not supported in router artifacts: {relative}")
            if child.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)

    @staticmethod
    def _artifact_suffix(artifact_format: RouterArtifactFormat) -> str:
        return {
            RouterArtifactFormat.tar: ".tar",
            RouterArtifactFormat.tar_gz: ".tar.gz",
            RouterArtifactFormat.zip: ".zip",
        }[artifact_format]

    def _extract_archive(
        self,
        artifact_path: Path,
        destination: Path,
        artifact_format: RouterArtifactFormat,
    ) -> None:
        if artifact_format in (RouterArtifactFormat.tar, RouterArtifactFormat.tar_gz):
            self._extract_tar(artifact_path, destination)
            return
        if artifact_format == RouterArtifactFormat.zip:
            self._extract_zip(artifact_path, destination)
            return
        raise ValueError(f"Unsupported archive format: {artifact_format}")

    @staticmethod
    def _safe_target(destination: Path, member_name: str) -> Path:
        relative = Path(member_name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe archive member path: {member_name}")
        return destination / relative

    def _extract_tar(self, artifact_path: Path, destination: Path) -> None:
        with tarfile.open(artifact_path, "r:*") as archive:
            for member in archive.getmembers():
                if member.issym() or member.islnk():
                    raise ValueError(f"Symlinks are not supported in router artifacts: {member.name}")
                target = self._safe_target(destination, member.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ValueError(f"Failed to extract archive member: {member.name}")
                with target.open("wb") as handle:
                    shutil.copyfileobj(extracted, handle)

    def _extract_zip(self, artifact_path: Path, destination: Path) -> None:
        with zipfile.ZipFile(artifact_path) as archive:
            for member in archive.infolist():
                target = self._safe_target(destination, member.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                with archive.open(member, "r") as source, target.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
