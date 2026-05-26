import json
import sys
from types import SimpleNamespace
from pathlib import Path

from sluice.models import RouterArtifactFormat
from sluice.router import (
    ArtifactCache,
    build_router_artifact,
    huggingface_resolve_url,
    load_manifest_file,
    publish_router_artifact_to_huggingface,
)
from sluice.sandbox import SandboxRunner


def _write_sample_router(source_dir: Path) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "agent.py").write_text(
        "\n".join(
            [
                "def agent_main(task: dict) -> dict:",
                "    provider = task['candidate_providers'][0]",
                "    return {",
                "        'task_id': task['task_id'],",
                "        'selected_provider_id': provider['provider_id'],",
                "        'fallback_provider_ids': [],",
                "        'expected_cost_usd': float(provider['estimated_cost_usd']),",
                "        'expected_latency_ms': int(provider['estimated_latency_ms']),",
                "        'expected_quality_score': float(provider['quality_score']),",
                "        'expected_reliability_score': float(provider['reliability_score']),",
                "        'confidence': 0.8,",
                "        'rationale': 'selected first provider',",
                "    }",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_build_router_artifact_and_materialize(tmp_path):
    source_dir = tmp_path / "router-src"
    output_dir = tmp_path / "release"
    cache_dir = tmp_path / "cache"
    _write_sample_router(source_dir)

    artifact_path, manifest_path, built_manifest = build_router_artifact(
        source_dir=source_dir,
        output_dir=output_dir,
        router_name="test-router",
        router_version="1.2.3",
        artifact_format=RouterArtifactFormat.tar_gz,
        supported_capabilities=["json-mode"],
        supported_privacy_tiers=["public"],
        description="Unit test router artifact.",
    )

    assert artifact_path.exists()
    manifest = load_manifest_file(manifest_path)
    assert manifest.sha256 == built_manifest.sha256
    assert manifest.router_name == "test-router"
    assert manifest.router_version == "1.2.3"

    cache = ArtifactCache(cache_dir=cache_dir)
    cached = cache.materialize(manifest)

    assert cached.entrypoint_path.exists()
    assert cached.entrypoint_path.read_text(encoding="utf-8").startswith(
        "def agent_main"
    )
    metadata = json.loads((cache_dir / manifest.sha256 / "manifest.json").read_text())
    assert metadata["sha256"] == manifest.sha256


def test_build_router_artifact_can_write_public_artifact_uri(tmp_path):
    source_dir = tmp_path / "router-src"
    output_dir = tmp_path / "release"
    _write_sample_router(source_dir)

    artifact_path, manifest_path, built_manifest = build_router_artifact(
        source_dir=source_dir,
        output_dir=output_dir,
        router_name="test-router",
        router_version="1.2.3",
        artifact_format=RouterArtifactFormat.tar_gz,
        artifact_uri="https://example.com/releases/test-router-1.2.3.tar.gz",
    )

    manifest = load_manifest_file(manifest_path)
    assert artifact_path.exists()
    assert manifest.artifact_uri == "https://example.com/releases/test-router-1.2.3.tar.gz"
    assert manifest.sha256 == built_manifest.sha256


def test_huggingface_resolve_url_for_model_and_dataset():
    assert (
        huggingface_resolve_url(
            repo_id="alice/router",
            path_in_repo="routers/router.tar.gz",
            revision="abc123",
        )
        == "https://huggingface.co/alice/router/resolve/abc123/routers/router.tar.gz"
    )
    assert (
        huggingface_resolve_url(
            repo_id="alice/router-data",
            repo_type="dataset",
            path_in_repo="router manifests/router.json",
            revision="refs/pr/1",
        )
        == "https://huggingface.co/datasets/alice/router-data/resolve/"
        "refs%2Fpr%2F1/router%20manifests/router.json"
    )


def test_publish_router_artifact_to_huggingface_updates_manifest(
    monkeypatch, tmp_path
):
    source_dir = tmp_path / "router-src"
    output_dir = tmp_path / "release"
    _write_sample_router(source_dir)
    artifact_path, manifest_path, _built_manifest = build_router_artifact(
        source_dir=source_dir,
        output_dir=output_dir,
        router_name="test-router",
        router_version="1.2.3",
        artifact_format=RouterArtifactFormat.tar_gz,
    )

    calls: list[tuple[str, dict]] = []

    class FakeHfApi:
        def __init__(self, endpoint=None):
            self.endpoint = endpoint

        def create_repo(self, **kwargs):
            calls.append(("create_repo", kwargs))

        def upload_file(self, **kwargs):
            calls.append(("upload_file", kwargs))
            oid = "a" * 40 if len(calls) == 2 else "b" * 40
            return SimpleNamespace(oid=oid)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=FakeHfApi),
    )

    published = publish_router_artifact_to_huggingface(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        repo_id="alice/router",
        path_prefix="routers",
        token="hf_fake",
    )

    manifest = load_manifest_file(manifest_path)
    expected_artifact_url = (
        "https://huggingface.co/alice/router/resolve/"
        f"{'a' * 40}/routers/test-router-1.2.3.tar.gz"
    )
    assert published.artifact_url == expected_artifact_url
    assert manifest.artifact_uri == expected_artifact_url
    assert manifest.metadata["huggingface"]["repo_id"] == "alice/router"
    assert calls[0][0] == "create_repo"
    assert calls[1][1]["path_in_repo"] == "routers/test-router-1.2.3.tar.gz"
    assert calls[2][1]["path_in_repo"] == "routers/test-router-1.2.3.manifest.json"


def test_artifact_cache_adds_huggingface_auth_header(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    assert ArtifactCache._auth_headers_for_uri(
        "https://huggingface.co/alice/router/resolve/main/router.tar.gz"
    ) == {"Authorization": "Bearer hf_fake"}
    assert (
        ArtifactCache._auth_headers_for_uri("https://example.com/router.tar.gz") == {}
    )


def test_sandbox_runner_reads_validator_runtime_env(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("SLUICE_SANDBOX_IMAGE", "custom-sluice-agent:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "12")
    monkeypatch.setenv("MAX_CONCURRENT_SANDBOXES", "2")
    monkeypatch.setenv("SLUICE_HOST_RUNTIME_ROOT", str(runtime_root))

    runner = SandboxRunner()

    assert runner.IMAGE_NAME == "custom-sluice-agent:latest"
    assert runner.SANDBOX_TIMEOUT_S == 12
    assert runner.MAX_CONCURRENT == 2
    assert runner.HOST_RUNTIME_ROOT == runtime_root
