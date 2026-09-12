"""Versioned weight, Librarian proposal, and Teacher decision contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from types import MappingProxyType
from typing import Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from botnet_council.backtest.models import to_jsonable

LEARNING_SCHEMA_VERSION = "1.0"


class LearningModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, arbitrary_types_allowed=True
    )


class WeightScope(LearningModel):
    asset_class: str | None = None
    symbol: str | None = None
    regime: str | None = None
    horizon_bars: int | None = Field(default=None, gt=0)

    @property
    def specificity(self) -> int:
        return sum(
            value is not None
            for value in (self.asset_class, self.symbol, self.regime, self.horizon_bars)
        )


class AdaptiveWeight(LearningModel):
    long_term: float = Field(ge=0, le=4, allow_inf_nan=False)
    recent: float = Field(ge=0, le=4, allow_inf_nan=False)
    recent_mix: float = Field(default=0.25, ge=0, le=0.5, allow_inf_nan=False)

    @property
    def effective(self) -> float:
        return self.long_term * (1.0 - self.recent_mix) + self.recent * self.recent_mix


class ScopedAgentWeight(LearningModel):
    agent_id: str
    scope: WeightScope = Field(default_factory=WeightScope)
    weight: AdaptiveWeight


class WeightProfile(LearningModel):
    schema_version: str = LEARNING_SCHEMA_VERSION
    generation: int = Field(ge=0)
    generation_id: str
    parent_generation_id: str | None = None
    created_at: datetime
    entries: tuple[ScopedAgentWeight, ...]
    scoring_version: str
    profile_id: str = ""

    @field_validator("created_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        if self.schema_version != LEARNING_SCHEMA_VERSION:
            raise ValueError("unsupported learning schema version")
        if self.generation_id != f"weights-v{self.generation:04d}":
            raise ValueError("generation_id must match generation")
        identities = tuple((item.agent_id, item.scope) for item in self.entries)
        if len(identities) != len(set(identities)):
            raise ValueError("profile entries must have unique agent and scope identities")
        if not self.entries or not self.scoring_version:
            raise ValueError("profile entries and scoring version are required")
        expected = _identity(self.model_dump(mode="python", exclude={"profile_id"}, warnings=False))
        if self.profile_id and self.profile_id != expected:
            raise ValueError("profile_id does not match profile contents")
        object.__setattr__(self, "profile_id", expected)
        return self

    def resolve(
        self,
        *,
        asset_class: str | None,
        symbol: str,
        regime: str | None,
        horizon_bars: int,
    ) -> Mapping[str, float]:
        matched: dict[str, ScopedAgentWeight] = {}
        for entry in self.entries:
            if not _scope_matches(entry.scope, asset_class, symbol, regime, horizon_bars):
                continue
            current = matched.get(entry.agent_id)
            if current is None or _scope_key(entry.scope) > _scope_key(current.scope):
                matched[entry.agent_id] = entry
        return MappingProxyType(
            {key: matched[key].weight.effective for key in sorted(matched)}
        )


class WeightChange(LearningModel):
    agent_id: str
    scope: WeightScope
    current: AdaptiveWeight
    proposed: AdaptiveWeight
    sample_count: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    long_term_accuracy: float | None = Field(default=None, ge=0, le=1)
    recent_accuracy: float | None = Field(default=None, ge=0, le=1)
    reason: str


class WeightProposal(LearningModel):
    schema_version: str = LEARNING_SCHEMA_VERSION
    proposal_id: str = ""
    base_generation_id: str
    created_at: datetime
    training_cutoff: datetime
    training_episode_ids: tuple[str, ...]
    changes: tuple[WeightChange, ...]
    librarian_version: str

    @field_validator("created_at", "training_cutoff")
    @classmethod
    def normalize_time(cls, value: datetime, info: object) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            name = getattr(info, "field_name", "datetime")
            raise ValueError(f"{name} must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_proposal(self) -> Self:
        if self.created_at < self.training_cutoff:
            raise ValueError("proposal cannot be created before its training cutoff")
        if len(self.training_episode_ids) != len(set(self.training_episode_ids)):
            raise ValueError("training episode IDs must be unique")
        identities = tuple((item.agent_id, item.scope) for item in self.changes)
        if len(identities) != len(set(identities)):
            raise ValueError("proposal changes must have unique agent and scope identities")
        expected = _identity(
            self.model_dump(mode="python", exclude={"proposal_id"}, warnings=False)
        )
        if self.proposal_id and self.proposal_id != expected:
            raise ValueError("proposal_id does not match proposal contents")
        object.__setattr__(self, "proposal_id", expected)
        return self


class EvaluationMetrics(LearningModel):
    episode_count: int = Field(ge=0)
    total_return: float = Field(allow_inf_nan=False)
    benchmark_relative_return: float = Field(allow_inf_nan=False)
    maximum_drawdown: float = Field(ge=0, allow_inf_nan=False)
    hit_rate: float = Field(ge=0, le=1, allow_inf_nan=False)
    mean_calibration_error: float = Field(ge=0, le=1, allow_inf_nan=False)
    risk_adjusted_return: float = Field(allow_inf_nan=False)
    turnover: float = Field(ge=0, allow_inf_nan=False)
    cost_adjusted_return: float = Field(allow_inf_nan=False)
    worst_slice_return: float = Field(allow_inf_nan=False)
    score: float = Field(allow_inf_nan=False)


class MetricComparison(LearningModel):
    baseline: EvaluationMetrics
    proposed: EvaluationMetrics


class TeacherDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    ACCEPT_REDUCED_UPDATE = "accept_reduced_update"


class TeacherResult(LearningModel):
    schema_version: str = LEARNING_SCHEMA_VERSION
    result_id: str = ""
    decision: TeacherDecision
    base_generation_id: str
    proposal_id: str
    held_out_episode_ids: tuple[str, ...]
    comparison: MetricComparison
    accepted_changes: tuple[WeightChange, ...]
    reasons: tuple[str, ...]
    evaluated_at: datetime
    teacher_version: str
    scoring_version: str

    @field_validator("evaluated_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        accepted = self.decision is not TeacherDecision.REJECT
        if accepted != bool(self.accepted_changes):
            raise ValueError("accepted changes must agree with Teacher decision")
        if len(self.held_out_episode_ids) != len(set(self.held_out_episode_ids)):
            raise ValueError("held-out episode IDs must be unique")
        expected = _identity(self.model_dump(mode="python", exclude={"result_id"}, warnings=False))
        if self.result_id and self.result_id != expected:
            raise ValueError("result_id does not match Teacher result contents")
        object.__setattr__(self, "result_id", expected)
        return self


class LearningReview(LearningModel):
    """Immutable Librarian proposal joined to its Teacher decision."""

    proposal: WeightProposal
    result: TeacherResult

    @model_validator(mode="after")
    def validate_join(self) -> Self:
        if self.result.proposal_id != self.proposal.proposal_id:
            raise ValueError("Teacher result belongs to another proposal")
        if self.result.base_generation_id != self.proposal.base_generation_id:
            raise ValueError("proposal and Teacher result use different base generations")
        return self


class LibrarianConfig(LearningModel):
    maximum_weight_delta: float = Field(default=0.10, gt=0, le=0.50)
    minimum_samples: int = Field(default=8, ge=2)
    full_confidence_samples: int = Field(default=40, ge=2)
    recent_window: int = Field(default=12, ge=2)
    target_weight_at_random: float = Field(default=1.0, ge=0, le=4)
    accuracy_weight_slope: float = Field(default=1.0, gt=0, le=2)

    @model_validator(mode="after")
    def validate_samples(self) -> Self:
        if self.full_confidence_samples < self.minimum_samples:
            raise ValueError("full confidence samples cannot be below minimum samples")
        return self


class TeacherConfig(LearningModel):
    scoring_version: str = "teacher-score-v1"
    minimum_held_out_episodes: int = Field(default=8, ge=2)
    minimum_score_improvement: float = Field(default=0.001, ge=0)
    maximum_worst_slice_degradation: float = Field(default=0.02, ge=0)
    turnover_cost_bps: float = Field(default=5.0, ge=0, le=10_000)
    metric_weights: Mapping[str, float] = Field(
        default_factory=lambda: {
            "total_return": 1.0,
            "benchmark_relative_return": 0.5,
            "maximum_drawdown": -0.75,
            "hit_rate": 0.25,
            "mean_calibration_error": -0.25,
            "risk_adjusted_return": 0.20,
            "cost_adjusted_return": 0.50,
            "worst_slice_return": 0.50,
        }
    )

    @field_validator("metric_weights")
    @classmethod
    def validate_weights(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        required = {
            "total_return",
            "benchmark_relative_return",
            "maximum_drawdown",
            "hit_rate",
            "mean_calibration_error",
            "risk_adjusted_return",
            "cost_adjusted_return",
            "worst_slice_return",
        }
        if set(value) != required or any(not isfinite(item) for item in value.values()):
            raise ValueError("metric_weights must define every finite Teacher metric weight")
        return MappingProxyType(dict(value))


def _scope_matches(
    scope: WeightScope,
    asset_class: str | None,
    symbol: str,
    regime: str | None,
    horizon_bars: int,
) -> bool:
    return all(
        (
            scope.asset_class is None or scope.asset_class == asset_class,
            scope.symbol is None or scope.symbol == symbol,
            scope.regime is None or scope.regime == regime,
            scope.horizon_bars is None or scope.horizon_bars == horizon_bars,
        )
    )


def _scope_key(scope: WeightScope) -> tuple[int, str, str, str, int]:
    return (
        scope.specificity,
        scope.asset_class or "",
        scope.symbol or "",
        scope.regime or "",
        scope.horizon_bars or 0,
    )


def _identity(value: object) -> str:
    material = json.dumps(
        to_jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return sha256(material.encode()).hexdigest()


def model_mapping(value: Mapping[str, float]) -> Mapping[str, float]:
    return cast(Mapping[str, float], MappingProxyType(dict(value)))
