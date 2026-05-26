from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from sluice.models import PrivacyTier, RouterArtifactFormat, RouterArtifactManifest
from sluice.router.artifacts import (
    compute_artifact_sha256,
    create_router_archive,
    write_manifest_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_default_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env.miner", override=False)
    cwd_env = Path.cwd() / ".env.miner"
    if cwd_env.resolve() != (PROJECT_ROOT / ".env.miner").resolve():
        load_dotenv(cwd_env, override=False)


def build_router_artifact(
    *,
    source_dir: str | Path,
    output_dir: str | Path,
    router_name: str = "sluice-router",
    router_version: str = "0.1.0",
    entrypoint_path: str = "agent.py",
    entrypoint_callable: str = "agent_main",
    artifact_format: RouterArtifactFormat = RouterArtifactFormat.tar_gz,
    supported_capabilities: list[str] | None = None,
    supported_privacy_tiers: list[str] | None = None,
    description: str = "",
    artifact_uri: str | None = None,
) -> tuple[Path, Path, RouterArtifactManifest]:
    source_root = Path(source_dir).resolve()
    release_root = Path(output_dir).resolve()
    release_root.mkdir(parents=True, exist_ok=True)

    entrypoint = source_root / entrypoint_path
    if not entrypoint.exists():
        raise FileNotFoundError(
            f"Entrypoint {entrypoint_path} was not found under {source_root}"
        )

    file_stem = f"{router_name}-{router_version}".replace("/", "-")
    if artifact_format == RouterArtifactFormat.directory:
        artifact_path = source_root
        resolved_artifact_uri = artifact_uri or artifact_path.as_uri()
        artifact_size_bytes = None
        manifest_path = release_root / f"{file_stem}.manifest.json"
    else:
        suffix = {
            RouterArtifactFormat.tar: ".tar",
            RouterArtifactFormat.tar_gz: ".tar.gz",
            RouterArtifactFormat.zip: ".zip",
        }[artifact_format]
        artifact_path = create_router_archive(
            source_root,
            release_root / f"{file_stem}{suffix}",
            artifact_format=artifact_format,
        )
        resolved_artifact_uri = artifact_uri or artifact_path.as_uri()
        artifact_size_bytes = artifact_path.stat().st_size
        manifest_path = release_root / f"{file_stem}.manifest.json"

    manifest = RouterArtifactManifest(
        artifact_uri=resolved_artifact_uri,
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
    )
    write_manifest_file(manifest_path, manifest)
    return artifact_path, manifest_path, manifest


def parse_args() -> argparse.Namespace:
    _load_default_env()
    parser = argparse.ArgumentParser(
        description="Build a pinned Sluice router artifact and manifest."
    )
    parser.add_argument("--source-dir", required=True, help="Router source directory.")
    parser.add_argument("--output-dir", required=True, help="Where to write build outputs.")
    parser.add_argument("--router-name", default="sluice-router")
    parser.add_argument("--router-version", default="0.1.0")
    parser.add_argument("--entrypoint-path", default="agent.py")
    parser.add_argument("--entrypoint-callable", default="agent_main")
    parser.add_argument(
        "--artifact-format",
        choices=[item.value for item in RouterArtifactFormat],
        default=RouterArtifactFormat.tar_gz.value,
    )
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Add a supported capability. Repeat this flag to add more.",
    )
    parser.add_argument(
        "--privacy-tier",
        action="append",
        default=[],
        help="Add a supported privacy tier. Repeat this flag to add more.",
    )
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--artifact-uri",
        default=None,
        help=(
            "Public URI validators should fetch. If omitted, the manifest uses "
            "a local file:// URI for development only."
        ),
    )
    parser.add_argument(
        "--hf-repo-id",
        default=os.getenv("HF_ROUTER_REPO_ID", ""),
        help="Upload the built artifact to this Hugging Face repo and rewrite the manifest.",
    )
    parser.add_argument(
        "--hf-repo-type",
        choices=["model", "dataset", "space"],
        default=os.getenv("HF_ROUTER_REPO_TYPE", "model"),
    )
    parser.add_argument(
        "--hf-path-prefix",
        default=os.getenv("HF_ROUTER_PATH_PREFIX", "routers"),
        help="Folder inside the Hugging Face repo for artifact and manifest files.",
    )
    parser.add_argument("--hf-artifact-path-in-repo", default=None)
    parser.add_argument("--hf-manifest-path-in-repo", default=None)
    parser.add_argument(
        "--hf-revision",
        default=os.getenv("HF_ROUTER_REVISION", "main"),
        help="Hugging Face branch or revision to upload to.",
    )
    parser.add_argument(
        "--hf-private",
        action="store_true",
        default=os.getenv("HF_ROUTER_PRIVATE", "0") == "1",
        help="Create or use a private Hugging Face repo.",
    )
    parser.add_argument("--hf-no-create-repo", action="store_true")
    parser.add_argument(
        "--hf-token",
        default=(
            os.getenv("HF_TOKEN")
            or os.getenv("HUGGING_FACE_HUB_TOKEN")
            or os.getenv("HUGGINGFACE_HUB_TOKEN")
        ),
    )
    parser.add_argument("--hf-endpoint", default=os.getenv("HF_ENDPOINT") or None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact_path, manifest_path, manifest = build_router_artifact(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        router_name=args.router_name,
        router_version=args.router_version,
        entrypoint_path=args.entrypoint_path,
        entrypoint_callable=args.entrypoint_callable,
        artifact_format=RouterArtifactFormat(args.artifact_format),
        supported_capabilities=args.capability,
        supported_privacy_tiers=args.privacy_tier or [PrivacyTier.public.value],
        description=args.description,
        artifact_uri=args.artifact_uri,
    )
    if args.hf_repo_id:
        from sluice.router.huggingface import publish_router_artifact_to_huggingface

        published = publish_router_artifact_to_huggingface(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            repo_id=args.hf_repo_id,
            repo_type=args.hf_repo_type,
            path_prefix=args.hf_path_prefix,
            artifact_path_in_repo=args.hf_artifact_path_in_repo,
            manifest_path_in_repo=args.hf_manifest_path_in_repo,
            revision=args.hf_revision,
            private=args.hf_private,
            create_repo=not args.hf_no_create_repo,
            token=args.hf_token,
            endpoint=args.hf_endpoint,
        )
        manifest = RouterArtifactManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        print(f"hf_artifact_uri={published.artifact_url}")
        print(f"hf_manifest_uri={published.manifest_url}")

    print(f"artifact={artifact_path}")
    print(f"manifest={manifest_path}")
    print(f"sha256={manifest.sha256}")


if __name__ == "__main__":
    main()
