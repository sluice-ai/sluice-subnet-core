from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sluice.router.artifacts import (
    compute_artifact_sha256,
    load_manifest_file,
    write_manifest_file,
)


DEFAULT_HF_ENDPOINT = "https://huggingface.co"
SUPPORTED_HF_REPO_TYPES = {"model", "dataset", "space"}


@dataclass(frozen=True)
class PublishedHuggingFaceArtifact:
    repo_id: str
    repo_type: str
    artifact_path_in_repo: str
    manifest_path_in_repo: str
    artifact_url: str
    manifest_url: str
    artifact_commit: str | None
    manifest_commit: str | None


def normalize_hf_repo_type(repo_type: str | None) -> str:
    normalized = (repo_type or "model").strip().lower()
    if normalized not in SUPPORTED_HF_REPO_TYPES:
        raise ValueError(
            "Hugging Face repo type must be one of: model, dataset, space."
        )
    return normalized


def repo_type_for_hf_api(repo_type: str | None) -> str | None:
    normalized = normalize_hf_repo_type(repo_type)
    return None if normalized == "model" else normalized


def clean_hf_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("Hugging Face repository path must not be empty.")
    if normalized.startswith("/"):
        raise ValueError("Hugging Face repository path must be relative.")

    parts = [part for part in normalized.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"Unsafe Hugging Face repository path: {path}")
    return "/".join(parts)


def join_hf_path(path_prefix: str | None, filename: str) -> str:
    clean_filename = clean_hf_path(filename)
    if not path_prefix or not path_prefix.strip():
        return clean_filename
    return clean_hf_path(f"{path_prefix.strip('/')}/{clean_filename}")


def huggingface_resolve_url(
    *,
    repo_id: str,
    path_in_repo: str,
    repo_type: str | None = "model",
    revision: str = "main",
    endpoint: str | None = None,
) -> str:
    normalized_repo_type = normalize_hf_repo_type(repo_type)
    clean_repo_id = repo_id.strip().strip("/")
    clean_path = clean_hf_path(path_in_repo)
    clean_revision = (revision or "main").strip()
    if not clean_repo_id:
        raise ValueError("Hugging Face repo_id must not be empty.")
    if not clean_revision:
        raise ValueError("Hugging Face revision must not be empty.")

    repo_prefix = {
        "model": "",
        "dataset": "datasets",
        "space": "spaces",
    }[normalized_repo_type]
    base_url = (endpoint or os.getenv("HF_ENDPOINT") or DEFAULT_HF_ENDPOINT).rstrip("/")
    encoded_repo = "/".join(quote(part, safe="") for part in clean_repo_id.split("/"))
    encoded_path = "/".join(quote(part, safe="") for part in clean_path.split("/"))
    encoded_revision = quote(clean_revision, safe="")

    if repo_prefix:
        return (
            f"{base_url}/{repo_prefix}/{encoded_repo}/resolve/"
            f"{encoded_revision}/{encoded_path}"
        )
    return f"{base_url}/{encoded_repo}/resolve/{encoded_revision}/{encoded_path}"


def _commit_oid(upload_result: Any) -> str | None:
    for attribute in ("oid", "commit_hash"):
        value = getattr(upload_result, attribute, None)
        if value:
            return str(value)
    return None


def _build_api(endpoint: str | None):
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:  # pragma: no cover - exercised through CLI usage.
        raise RuntimeError(
            "Install huggingface-hub to publish router artifacts: "
            "`python -m pip install huggingface-hub`."
        ) from exc

    if endpoint:
        return HfApi(endpoint=endpoint)
    return HfApi()


def publish_router_artifact_to_huggingface(
    *,
    artifact_path: str | Path,
    manifest_path: str | Path,
    repo_id: str,
    repo_type: str | None = "model",
    path_prefix: str = "routers",
    artifact_path_in_repo: str | None = None,
    manifest_path_in_repo: str | None = None,
    revision: str = "main",
    private: bool = False,
    create_repo: bool = True,
    token: str | None = None,
    endpoint: str | None = None,
) -> PublishedHuggingFaceArtifact:
    artifact_file = Path(artifact_path).resolve()
    manifest_file = Path(manifest_path).resolve()
    if not artifact_file.is_file():
        raise FileNotFoundError(f"Router artifact file not found: {artifact_file}")
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Router manifest file not found: {manifest_file}")

    manifest = load_manifest_file(manifest_file)
    actual_sha = compute_artifact_sha256(artifact_file, manifest.artifact_format)
    if actual_sha != manifest.sha256:
        raise ValueError(
            f"Artifact digest mismatch before upload: manifest has {manifest.sha256}, "
            f"but {artifact_file} is {actual_sha}."
        )

    normalized_repo_type = normalize_hf_repo_type(repo_type)
    api_repo_type = repo_type_for_hf_api(normalized_repo_type)
    artifact_repo_path = (
        clean_hf_path(artifact_path_in_repo)
        if artifact_path_in_repo
        else join_hf_path(path_prefix, artifact_file.name)
    )
    manifest_repo_path = (
        clean_hf_path(manifest_path_in_repo)
        if manifest_path_in_repo
        else join_hf_path(path_prefix, manifest_file.name)
    )

    api = _build_api(endpoint)
    if create_repo:
        api.create_repo(
            repo_id=repo_id,
            repo_type=api_repo_type,
            private=private,
            exist_ok=True,
            token=token,
        )

    artifact_upload = api.upload_file(
        path_or_fileobj=str(artifact_file),
        path_in_repo=artifact_repo_path,
        repo_id=repo_id,
        repo_type=api_repo_type,
        revision=revision,
        token=token,
        commit_message=(
            f"Upload Sluice router artifact "
            f"{manifest.router_name} {manifest.router_version}"
        ),
    )
    artifact_commit = _commit_oid(artifact_upload)
    artifact_url = huggingface_resolve_url(
        repo_id=repo_id,
        repo_type=normalized_repo_type,
        path_in_repo=artifact_repo_path,
        revision=artifact_commit or revision,
        endpoint=endpoint,
    )

    metadata = dict(manifest.metadata)
    metadata["huggingface"] = {
        "repo_id": repo_id,
        "repo_type": normalized_repo_type,
        "artifact_path_in_repo": artifact_repo_path,
        "manifest_path_in_repo": manifest_repo_path,
        "artifact_commit": artifact_commit,
    }
    updated_manifest = manifest.model_copy(
        update={"artifact_uri": artifact_url, "metadata": metadata}
    )
    write_manifest_file(manifest_file, updated_manifest)

    manifest_upload = api.upload_file(
        path_or_fileobj=str(manifest_file),
        path_in_repo=manifest_repo_path,
        repo_id=repo_id,
        repo_type=api_repo_type,
        revision=revision,
        token=token,
        commit_message=(
            f"Upload Sluice router manifest "
            f"{manifest.router_name} {manifest.router_version}"
        ),
    )
    manifest_commit = _commit_oid(manifest_upload)
    manifest_url = huggingface_resolve_url(
        repo_id=repo_id,
        repo_type=normalized_repo_type,
        path_in_repo=manifest_repo_path,
        revision=manifest_commit or revision,
        endpoint=endpoint,
    )

    return PublishedHuggingFaceArtifact(
        repo_id=repo_id,
        repo_type=normalized_repo_type,
        artifact_path_in_repo=artifact_repo_path,
        manifest_path_in_repo=manifest_repo_path,
        artifact_url=artifact_url,
        manifest_url=manifest_url,
        artifact_commit=artifact_commit,
        manifest_commit=manifest_commit,
    )
