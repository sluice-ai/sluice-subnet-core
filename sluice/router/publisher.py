from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from sluice.router.huggingface import publish_router_artifact_to_huggingface

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_default_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env.miner", override=False)
    cwd_env = Path.cwd() / ".env.miner"
    if cwd_env.resolve() != (PROJECT_ROOT / ".env.miner").resolve():
        load_dotenv(cwd_env, override=False)


def _env_token() -> str | None:
    return (
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGING_FACE_HUB_TOKEN")
        or os.getenv("HUGGINGFACE_HUB_TOKEN")
    )


def parse_args() -> argparse.Namespace:
    _load_default_env()
    parser = argparse.ArgumentParser(
        description="Publish a pinned Sluice router artifact to Hugging Face."
    )
    parser.add_argument("--artifact-path", required=True, help="Built router archive.")
    parser.add_argument("--manifest-path", required=True, help="Router manifest JSON.")
    parser.add_argument(
        "--repo-id",
        default=os.getenv("HF_ROUTER_REPO_ID", ""),
        help="Hugging Face repo id, for example username/sluice-router.",
    )
    parser.add_argument(
        "--repo-type",
        choices=["model", "dataset", "space"],
        default=os.getenv("HF_ROUTER_REPO_TYPE", "model"),
    )
    parser.add_argument(
        "--path-prefix",
        default=os.getenv("HF_ROUTER_PATH_PREFIX", "routers"),
        help="Folder inside the Hugging Face repo.",
    )
    parser.add_argument("--artifact-path-in-repo", default=None)
    parser.add_argument("--manifest-path-in-repo", default=None)
    parser.add_argument(
        "--revision",
        default=os.getenv("HF_ROUTER_REVISION", "main"),
        help="Branch or revision to upload to.",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        default=os.getenv("HF_ROUTER_PRIVATE", "0") == "1",
    )
    parser.add_argument("--no-create-repo", action="store_true")
    parser.add_argument("--token", default=_env_token())
    parser.add_argument("--endpoint", default=os.getenv("HF_ENDPOINT") or None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.repo_id:
        raise SystemExit("Set --repo-id or HF_ROUTER_REPO_ID.")

    published = publish_router_artifact_to_huggingface(
        artifact_path=args.artifact_path,
        manifest_path=args.manifest_path,
        repo_id=args.repo_id,
        repo_type=args.repo_type,
        path_prefix=args.path_prefix,
        artifact_path_in_repo=args.artifact_path_in_repo,
        manifest_path_in_repo=args.manifest_path_in_repo,
        revision=args.revision,
        private=args.private,
        create_repo=not args.no_create_repo,
        token=args.token,
        endpoint=args.endpoint,
    )

    print(f"artifact_uri={published.artifact_url}")
    print(f"manifest_uri={published.manifest_url}")
    print(f"artifact_path_in_repo={published.artifact_path_in_repo}")
    print(f"manifest_path_in_repo={published.manifest_path_in_repo}")


if __name__ == "__main__":
    main()
