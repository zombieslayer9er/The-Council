"""End-to-end replay episode joining evidence, decisions, engine, and validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from botnet_council.backtest.authoritative import (
    AuthoritativeBacktestRequest,
    AuthoritativeBacktestResult,
    AuthoritativeModel,
    ValidationArtifact,
    _plain_json,
)
from botnet_council.context import MarketContext
from botnet_council.schemas import AgentSignal, CouncilDecision


class EpisodeRecord(AuthoritativeModel):
    """Normalized audit record; trainer evidence cannot predate engine outcomes."""

    context: MarketContext
    specialist_outputs: tuple[AgentSignal, ...]
    council_decision: CouncilDecision
    engine_request: AuthoritativeBacktestRequest
    engine_result: AuthoritativeBacktestResult
    validations: tuple[ValidationArtifact, ...] = ()
    trainer_evaluation: Mapping[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime
    episode_id: str = ""

    @field_validator("evaluated_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_episode(self) -> Self:
        if self.council_decision.signals != self.specialist_outputs:
            raise ValueError("episode specialist outputs must be the frozen council inputs")
        if self.council_decision.source_snapshot_id != self.context.snapshot.snapshot_id:
            raise ValueError("episode context and Council decision snapshots differ")
        if self.engine_result.provenance.request_id != self.engine_request.request_id:
            raise ValueError("episode engine request and result identities differ")
        if any(item.request_id != self.engine_request.request_id for item in self.validations):
            raise ValueError("episode validation belongs to another engine request")
        if self.evaluated_at < self.engine_request.end:
            raise ValueError("trainer evaluation cannot precede the backtest horizon")
        expected = episode_identity(self)
        if self.episode_id and self.episode_id != expected:
            raise ValueError("episode_id does not match episode contents")
        object.__setattr__(self, "episode_id", expected)
        return self


def episode_identity(episode: EpisodeRecord) -> str:
    material = _plain_json(
        episode.model_dump(mode="python", exclude={"episode_id"}, warnings=False)
    )
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode()).hexdigest()
