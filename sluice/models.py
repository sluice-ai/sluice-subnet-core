from __future__ import annotations

from enum import Enum
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class PrivacyTier(str, Enum):
    public = "public"
    internal = "internal"
    confidential = "confidential"


PRIVACY_ORDER: dict[PrivacyTier, int] = {
    PrivacyTier.public: 0,
    PrivacyTier.internal: 1,
    PrivacyTier.confidential: 2,
}


def privacy_rank(tier: PrivacyTier | str) -> int:
    normalized = tier if isinstance(tier, PrivacyTier) else PrivacyTier(tier)
    return PRIVACY_ORDER[normalized]


def privacy_satisfies(required: PrivacyTier | str, actual: PrivacyTier | str) -> bool:
    return privacy_rank(actual) >= privacy_rank(required)


class RouterArtifactFormat(str, Enum):
    directory = "directory"
    tar = "tar"
    tar_gz = "tar.gz"
    zip = "zip"


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return [str(value).strip().lower()]


class RouterArtifactManifest(BaseModel):
    artifact_uri: str
    sha256: str = Field(
        description="Lowercase SHA-256 digest for the artifact bytes or directory tree.",
    )
    artifact_format: RouterArtifactFormat = RouterArtifactFormat.tar_gz
    entrypoint_path: str = "agent.py"
    entrypoint_callable: str = "agent_main"
    router_name: str = "sluice-router"
    router_version: str = "0.1.0"
    supported_capabilities: list[str] = Field(default_factory=list)
    supported_privacy_tiers: list[str] = Field(
        default_factory=lambda: [PrivacyTier.public.value]
    )
    description: str = ""
    artifact_size_bytes: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized):
            raise ValueError("sha256 must be a 64-character lowercase hexadecimal digest.")
        return normalized

    @field_validator("entrypoint_path")
    @classmethod
    def validate_entrypoint_path(cls, value: str) -> str:
        normalized = value.strip().replace("\\", "/")
        if not normalized:
            raise ValueError("entrypoint_path must not be empty.")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValueError("entrypoint_path must be a safe relative path.")
        return normalized

    @field_validator("entrypoint_callable")
    @classmethod
    def validate_entrypoint_callable(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("entrypoint_callable must not be empty.")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", normalized):
            raise ValueError("entrypoint_callable must be a valid Python identifier.")
        return normalized

    @field_validator("supported_capabilities", "supported_privacy_tiers", mode="before")
    @classmethod
    def normalize_supported_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("supported_privacy_tiers")
    @classmethod
    def validate_supported_privacy_tiers(cls, value: list[str]) -> list[str]:
        for tier in value:
            PrivacyTier(tier)
        return value


class ProviderOption(BaseModel):
    provider_id: str
    provider_kind: str = Field(
        description="For example: external_api, bittensor_subnet, tee."
    )
    model_id: str
    estimated_cost_usd: float = Field(ge=0)
    estimated_latency_ms: int = Field(gt=0)
    quality_score: float = Field(ge=0, le=1)
    reliability_score: float = Field(ge=0, le=1)
    privacy_tier: PrivacyTier = PrivacyTier.public
    capabilities: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("capabilities", mode="before")
    @classmethod
    def normalize_capabilities(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class RoutingTask(BaseModel):
    task_id: str
    workload_type: str
    objective: str
    prompt_tokens: int = Field(gt=0)
    completion_tokens: int = Field(ge=0)
    max_latency_ms: int = Field(gt=0)
    min_quality_score: float = Field(ge=0, le=1)
    privacy_requirement: PrivacyTier = PrivacyTier.public
    max_cost_usd: float | None = Field(default=None, ge=0)
    required_capabilities: list[str] = Field(default_factory=list)
    candidate_providers: list[ProviderOption] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("required_capabilities", mode="before")
    @classmethod
    def normalize_required_capabilities(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def validate_candidates(self) -> "RoutingTask":
        if not self.candidate_providers:
            raise ValueError("RoutingTask requires at least one candidate provider.")
        return self


class RoutingExecutionReport(BaseModel):
    task_id: str
    selected_provider_id: str
    fallback_provider_ids: list[str] = Field(default_factory=list)
    expected_cost_usd: float = Field(ge=0)
    expected_latency_ms: int = Field(ge=0)
    expected_quality_score: float = Field(ge=0, le=1)
    expected_reliability_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    rationale: str
    policy_tags: list[str] = Field(default_factory=list)
    agent_name: str = "sluice-router"
    agent_version: str = "0.1.0"

    @field_validator("fallback_provider_ids", "policy_tags", mode="before")
    @classmethod
    def normalize_optional_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)
