"""Strict immutable contracts for causally blind historical experiments."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from botnet_council.backtest.models import to_jsonable
from botnet_council.council import CouncilConfig
from botnet_council.market_data import HistoricalRequest, ProviderId
from botnet_council.schemas import (
    AgentContext,
    AgentSignal,
    CouncilDecision,
    Direction,
    MarketSnapshot,
    PortfolioState,
)

AgentKind = Literal["trend", "mean_reversion", "volatility", "regime", "seasonality"]


class ExperimentModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def duration(value: str) -> timedelta:
    match = re.fullmatch(r"([1-9][0-9]*)([mhd])", value)
    if match is None:
        raise ValueError("duration must use a positive integer followed by m, h, or d")
    amount = int(match.group(1))
    return {
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
    }[match.group(2)]


class ExperimentState(StrEnum):
    CREATED = "created"
    CONTEXT_READY = "context_ready"
    FORECASTING = "forecasting"
    FORECAST_LOCKED = "forecast_locked"
    EVALUATING = "evaluating"
    COMPLETE = "complete"
    FAILED = "failed"


class ExperimentAgentConfig(ExperimentModel):
    kind: AgentKind
    parameters: Mapping[str, int | float] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: Mapping[str, int | float]) -> Mapping[str, int | float]:
        for key, item in value.items():
            if not key or isinstance(item, bool) or not isfinite(item):
                raise ValueError("agent parameters require named finite numeric values")
        return dict(sorted(value.items()))


class ExperimentRequest(ExperimentModel):
    instrument: str
    provider: ProviderId
    evaluation_time: datetime
    forecast_horizon: str
    timeframe: str
    agents: tuple[ExperimentAgentConfig, ...]
    council: CouncilConfig = Field(default_factory=CouncilConfig)
    starting_portfolio: PortfolioState | None = None
    random_seed: int | None = None
    context_bars: Annotated[int | None, Field(ge=1)] = None

    @field_validator("evaluation_time")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "evaluation_time")

    @field_validator("forecast_horizon", "timeframe")
    @classmethod
    def validate_duration(cls, value: str) -> str:
        duration(value)
        return value

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if not self.instrument or not self.agents:
            raise ValueError("instrument and at least one agent are required")
        if len({agent.kind for agent in self.agents}) != len(self.agents):
            raise ValueError("experiment agent kinds must be unique")
        if duration(self.forecast_horizon) % duration(self.timeframe) != timedelta(0):
            raise ValueError("forecast horizon must be an exact multiple of timeframe")
        return self

    @property
    def horizon_end(self) -> datetime:
        return self.evaluation_time + duration(self.forecast_horizon)

    @property
    def identity(self) -> str:
        material = json.dumps(
            to_jsonable(self.model_dump(mode="python", warnings=False)),
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(material.encode()).hexdigest()

    @property
    def experiment_id(self) -> str:
        return self.identity[:24]


class BlindInputProvenance(ExperimentModel):
    request: HistoricalRequest
    provider: ProviderId
    fetched_at: datetime
    source_version: str
    adapter_semantic_version: str
    cache_key: str
    content_identity: str
    snapshot_id: str

    @field_validator("fetched_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "fetched_at")


class ExperimentContext(ExperimentModel):
    """The complete object supplied to forecasting; it cannot represent oracle data."""

    experiment_id: str
    evaluation_time: datetime
    snapshot: MarketSnapshot
    agent_context: AgentContext
    provenance: BlindInputProvenance

    @field_validator("evaluation_time")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "evaluation_time")

    @model_validator(mode="after")
    def enforce_cutoff(self) -> Self:
        if self.snapshot.as_of != self.evaluation_time:
            raise ValueError("blind snapshot cutoff must equal evaluation_time")
        if any(bar.available_at > self.evaluation_time for bar in self.snapshot.bars):
            raise ValueError("future market data cannot enter an experiment context")
        if self.snapshot.snapshot_id != self.provenance.snapshot_id:
            raise ValueError("blind provenance must identify the exact snapshot")
        if self.agent_context.run_id != self.experiment_id:
            raise ValueError("agent context must identify the experiment")
        return self


class CouncilWeight(ExperimentModel):
    agent_id: str
    weight: float = Field(ge=0, allow_inf_nan=False)


class AgentVersion(ExperimentModel):
    agent_id: str
    version: str


class Forecast(ExperimentModel):
    forecast_id: str
    experiment_id: str
    evaluation_time: datetime
    instrument: str
    forecast_horizon: str
    expected_return: float | None = Field(allow_inf_nan=False)
    direction: Direction
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    agent_forecasts: tuple[AgentSignal, ...]
    council_decision: CouncilDecision
    council_weights: tuple[CouncilWeight, ...]
    source_provenance: BlindInputProvenance
    agent_versions: tuple[AgentVersion, ...]
    finalized_at: datetime

    @field_validator("evaluation_time", "finalized_at")
    @classmethod
    def validate_time(cls, value: datetime, info: object) -> datetime:
        name = getattr(info, "field_name", "datetime")
        return _utc(value, name)

    @model_validator(mode="after")
    def validate_lock(self) -> Self:
        if self.council_decision.signals != self.agent_forecasts:
            raise ValueError("forecast signals must be the frozen council inputs")
        if self.council_decision.source_snapshot_id != self.source_provenance.snapshot_id:
            raise ValueError("forecast and blind provenance snapshot IDs differ")
        return self


class OracleProvenance(ExperimentModel):
    request: HistoricalRequest
    provider: ProviderId
    fetched_at: datetime
    source_version: str
    adapter_semantic_version: str
    cache_key: str
    content_identity: str

    @field_validator("fetched_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "fetched_at")


class OracleOutcome(ExperimentModel):
    experiment_id: str
    evaluation_time: datetime
    horizon_end: datetime
    price_convention: Literal["completed_bar_close"] = "completed_bar_close"
    start_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    endpoint_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    realized_return: float | None = Field(default=None, allow_inf_nan=False)
    realized_direction: Direction | None = None
    maximum_favorable_excursion: float | None = Field(default=None, allow_inf_nan=False)
    maximum_adverse_excursion: float | None = Field(default=None, allow_inf_nan=False)
    provenance: OracleProvenance
    horizon_complete: bool

    @field_validator("evaluation_time", "horizon_end")
    @classmethod
    def validate_time(cls, value: datetime, info: object) -> datetime:
        name = getattr(info, "field_name", "datetime")
        return _utc(value, name)

    @model_validator(mode="after")
    def validate_completeness(self) -> Self:
        measurements = (
            self.start_price,
            self.endpoint_price,
            self.realized_return,
            self.realized_direction,
            self.maximum_favorable_excursion,
            self.maximum_adverse_excursion,
        )
        if self.horizon_complete != all(item is not None for item in measurements):
            raise ValueError("complete oracle outcomes require every measurement")
        return self


class ForecastEvaluation(ExperimentModel):
    experiment_id: str
    forecast_id: str
    directional_correctness: bool
    forecast_direction: Direction
    realized_direction: Direction
    expected_return: float | None = Field(allow_inf_nan=False)
    realized_return: float = Field(allow_inf_nan=False)
    absolute_return_error: float | None = Field(ge=0, allow_inf_nan=False)
    signed_return_error: float | None = Field(allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    calibration_bucket: str
    evaluated_at: datetime

    @field_validator("evaluated_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "evaluated_at")


class LifecycleEvent(ExperimentModel):
    state: ExperimentState
    occurred_at: datetime
    message: str = ""

    @field_validator("occurred_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "occurred_at")


class ExperimentRecord(ExperimentModel):
    experiment_id: str
    request: ExperimentRequest
    state: ExperimentState
    lifecycle: tuple[LifecycleEvent, ...]
    context: ExperimentContext | None = None
    forecast: Forecast | None = None
    oracle_outcome: OracleOutcome | None = None
    evaluation: ForecastEvaluation | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.experiment_id != self.request.experiment_id:
            raise ValueError("experiment ID does not match request identity")
        if not self.lifecycle or self.lifecycle[-1].state is not self.state:
            raise ValueError("lifecycle tail must match current state")
        if self.forecast is not None and self.state in {
            ExperimentState.CREATED,
            ExperimentState.CONTEXT_READY,
            ExperimentState.FORECASTING,
        }:
            raise ValueError("forecast cannot exist before FORECAST_LOCKED")
        if self.oracle_outcome is not None and self.forecast is None:
            raise ValueError("oracle outcome cannot exist before a forecast")
        if self.evaluation is not None and self.oracle_outcome is None:
            raise ValueError("evaluation requires an oracle outcome")
        if self.state is ExperimentState.COMPLETE and self.evaluation is None:
            raise ValueError("complete experiments require an evaluation")
        return self


class RandomExperimentRequest(ExperimentModel):
    template: ExperimentRequest
    range_start: datetime
    range_end: datetime
    samples: Annotated[int, Field(gt=0)]
    seed: int

    @field_validator("range_start", "range_end")
    @classmethod
    def validate_time(cls, value: datetime, info: object) -> datetime:
        name = getattr(info, "field_name", "datetime")
        return _utc(value, name)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.range_end <= self.range_start:
            raise ValueError("random experiment range_end must follow range_start")
        return self


class CalibrationBucket(ExperimentModel):
    bucket: str
    count: int = Field(ge=0)
    mean_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    directional_accuracy: float = Field(ge=0, le=1, allow_inf_nan=False)


class ConfigurationPerformance(ExperimentModel):
    configuration_id: str
    experiment_count: int = Field(ge=0)
    directional_accuracy: float = Field(ge=0, le=1, allow_inf_nan=False)
    mean_absolute_return_error: float | None = Field(ge=0, allow_inf_nan=False)
    forecast_bias: float | None = Field(allow_inf_nan=False)


class BatchResult(ExperimentModel):
    batch_id: str
    selection_seed: int
    experiment_ids: tuple[str, ...]
    experiment_count: int = Field(ge=0)
    directional_accuracy: float = Field(ge=0, le=1, allow_inf_nan=False)
    mean_absolute_return_error: float | None = Field(ge=0, allow_inf_nan=False)
    forecast_bias: float | None = Field(allow_inf_nan=False)
    confidence_calibration: tuple[CalibrationBucket, ...]
    performance_by_configuration: tuple[ConfigurationPerformance, ...]
