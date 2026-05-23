import json
from pathlib import Path

from sluice.models import RouterArtifactFormat
from sluice.router import ArtifactCache, build_router_artifact, load_manifest_file


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
