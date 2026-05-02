from __future__ import annotations

from enum import Enum
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


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return [str(value).strip().lower()]


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
