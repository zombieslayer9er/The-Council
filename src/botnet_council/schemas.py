"""Immutable, strictly validated contracts shared across independent subsystems."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from math import isclose, isfinite
from types import MappingProxyType
from typing import Annotated, Any, Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JsonValue = Any
FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
UnitFloat = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
SignedUnitFloat = Annotated[float, Field(strict=True, ge=-1, le=1, allow_inf_nan=False)]

# Quantities within this absolute tolerance are treated as flat at trade boundaries.
# The paper adapter does not support exchange-specific lot-size quantization.
QUANTITY_ABS_TOLERANCE = 1e-12
NOTIONAL_ABS_TOLERANCE = 1e-9
EXPOSURE_ABS_TOLERANCE = 1e-12


class SignalType(StrEnum):
    ALPHA = "alpha"
    VOLATILITY = "volatility"
    REGIME = "regime"


class Direction(StrEnum):
    SHORT = "short"
    FLAT = "flat"
    LONG = "long"


class ActionIntent(StrEnum):
    TARGET_EXPOSURE = "target_exposure"
    ABSTAIN = "abstain"
    NO_ACTION = "no_action"
    REDUCE_ONLY = "reduce_only"


class SignalValidity(StrEnum):
    VALID = "valid"
    INSUFFICIENT_DATA = "insufficient_data"
    INVALID = "invalid"


class ObservationStatus(StrEnum):
    VALID = "valid"
    INSUFFICIENT_DATA = "insufficient_data"


class VolatilityEstimator(StrEnum):
    LOG_RETURN_POPULATION_STDDEV = "log_return_population_stddev"


class VolatilityUnits(StrEnum):
    PER_BAR_DECIMAL = "per_bar_decimal"


class FillPolicy(StrEnum):
    NEXT_BAR_OPEN = "next_bar_open"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class RiskStatus(StrEnum):
    APPROVED = "approved"
    VETOED = "vetoed"


class ExecutionStatus(StrEnum):
    FILLED = "filled"
    REJECTED = "rejected"


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _validate_json_numbers(value: Any, field_name: str) -> Any:
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"{field_name} contains a non-finite number")
    if isinstance(value, float):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _validate_json_numbers(item, field_name) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_validate_json_numbers(item, field_name) for item in value)
    if value is None or isinstance(value, str | int | bool):
        return value
    raise ValueError(f"{field_name} contains a non-JSON value")


class DomainModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, arbitrary_types_allowed=True
    )


class MarketBar(DomainModel):
    """A candle whose values become observable only at ``closed_at``."""

    opened_at: datetime
    closed_at: datetime
    open: PositiveFiniteFloat
    high: PositiveFiniteFloat
    low: PositiveFiniteFloat
    close: PositiveFiniteFloat
    volume: NonNegativeFiniteFloat

    @field_validator("opened_at", "closed_at")
    @classmethod
    def validate_time(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @model_validator(mode="after")
    def validate_bar(self) -> Self:
        if self.closed_at <= self.opened_at:
            raise ValueError("bar closed_at must be after opened_at")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("invalid OHLCV bar")
        if self.low > self.high:
            raise ValueError("invalid OHLCV bar")
        return self


def snapshot_identity(
    symbol: str, timeframe: str, as_of: datetime, bars: tuple[MarketBar, ...]
) -> str:
    material = "|".join(
        (
            symbol,
            timeframe,
            as_of.isoformat(),
            *(
                (
                    f"{bar.opened_at.isoformat()}:{bar.closed_at.isoformat()}:"
                    f"{bar.open.hex()}:{bar.high.hex()}:{bar.low.hex()}:"
                    f"{bar.close.hex()}:{bar.volume.hex()}"
                )
                for bar in bars
            ),
        )
    )
    return sha256(material.encode()).hexdigest()[:24]


class MarketSnapshot(DomainModel):
    """Completed bars available at ``observed_at`` and capped by ``as_of``."""

    symbol: str
    timeframe: str
    as_of: datetime
    observed_at: datetime
    bars: tuple[MarketBar, ...]
    snapshot_id: str = ""

    @field_validator("as_of", "observed_at")
    @classmethod
    def validate_time(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        if re.fullmatch(r"[1-9][0-9]*[mhd]", value) is None:
            raise ValueError("timeframe must use an integer followed by m, h, or d")
        return value

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if not self.symbol or not self.timeframe:
            raise ValueError("symbol and timeframe are required")
        if not self.bars:
            raise ValueError("at least one completed market bar is required")
        intervals = tuple((bar.opened_at, bar.closed_at) for bar in self.bars)
        if intervals != tuple(sorted(intervals)) or len(set(intervals)) != len(intervals):
            raise ValueError("bars must be unique and chronological")
        if any(bar.closed_at > self.as_of for bar in self.bars):
            raise ValueError("snapshot contains a bar completed after its as_of cutoff")
        if any(
            current.opened_at < previous.closed_at
            for previous, current in zip(self.bars, self.bars[1:], strict=False)
        ):
            raise ValueError("snapshot bars cannot overlap")
        if self.observed_at < self.as_of:
            raise ValueError("snapshot cannot be observed before its as_of cutoff")
        if self.observed_at < self.bars[-1].closed_at:
            raise ValueError("snapshot cannot be observed before its newest bar closes")
        expected = snapshot_identity(self.symbol, self.timeframe, self.as_of, self.bars)
        if self.snapshot_id and self.snapshot_id != expected:
            raise ValueError("snapshot_id does not match snapshot contents")
        object.__setattr__(self, "snapshot_id", expected)
        return self

    @property
    def last_price(self) -> float:
        return self.bars[-1].close

    @property
    def latest_closed_at(self) -> datetime:
        return self.bars[-1].closed_at


class PriceObservation(DomainModel):
    symbol: str
    price: PositiveFiniteFloat
    observed_at: datetime
    source_snapshot_id: str

    @field_validator("observed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "observed_at")


class OpeningPriceObservation(DomainModel):
    """A price observable at a bar open; later candle values are deliberately absent."""

    symbol: str
    timeframe: str
    price: PositiveFiniteFloat
    bar_opened_at: datetime
    observed_at: datetime

    @field_validator("bar_opened_at", "observed_at")
    @classmethod
    def validate_time(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.observed_at < self.bar_opened_at:
            raise ValueError("opening price cannot be observed before its bar opens")
        return self


class VolatilityObservation(DomainModel):
    estimator: VolatilityEstimator
    window_bars: Annotated[int, Field(gt=1)]
    units: VolatilityUnits
    observed_at: datetime
    source_snapshot_id: str
    status: ObservationStatus
    value: NonNegativeFiniteFloat | None = None

    @field_validator("observed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "observed_at")

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if (self.status is ObservationStatus.VALID) != (self.value is not None):
            raise ValueError("valid volatility observations must have exactly one finite value")
        return self


class AgentContext(DomainModel):
    """Non-secret contextual data supplied to a specialist."""

    run_id: str
    parameters: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return cast(Mapping[str, JsonValue], _validate_json_numbers(value, "parameters"))


class AgentSignal(DomainModel):
    schema_version: str
    agent_id: str
    agent_version: str
    signal_type: SignalType
    symbol: str
    timeframe: str
    source_snapshot_id: str
    source_as_of: datetime
    forecast_direction: Direction
    expected_return: FiniteFloat | None
    target_exposure: SignedUnitFloat | None
    action: ActionIntent
    validity: SignalValidity
    confidence: UnitFloat
    horizon_bars: Annotated[int, Field(gt=0)]
    generated_at: datetime
    expires_at: datetime
    rationale: str
    volatility: VolatilityObservation | None = None
    metadata: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("source_as_of", "generated_at", "expires_at")
    @classmethod
    def validate_time(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return cast(Mapping[str, JsonValue], _validate_json_numbers(value, "metadata"))

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        if self.schema_version != "1.1":
            raise ValueError("unsupported AgentSignal schema version")
        required = (
            self.agent_id,
            self.agent_version,
            self.symbol,
            self.timeframe,
            self.source_snapshot_id,
        )
        if not all(required):
            raise ValueError("signal identity fields are required")
        if self.expires_at < self.generated_at:
            raise ValueError("signal expires_at cannot precede generated_at")
        actionable = self.action in (ActionIntent.TARGET_EXPOSURE, ActionIntent.REDUCE_ONLY)
        if actionable != (self.target_exposure is not None):
            raise ValueError("actionable signals require target_exposure; other signals forbid it")
        if self.validity is not SignalValidity.VALID and self.action is not ActionIntent.ABSTAIN:
            raise ValueError("non-valid signals must abstain")
        if self.signal_type is SignalType.ALPHA and self.validity is SignalValidity.VALID:
            if self.expected_return is None:
                raise ValueError("valid alpha signals require expected_return")
        elif self.expected_return is not None:
            raise ValueError("only valid alpha signals may contain expected_return")
        if self.forecast_direction is Direction.LONG and (self.expected_return or 0) < 0:
            raise ValueError("long forecasts cannot have a negative expected return")
        if self.forecast_direction is Direction.SHORT and (self.expected_return or 0) > 0:
            raise ValueError("short forecasts cannot have a positive expected return")
        if self.forecast_direction is Direction.FLAT and self.expected_return not in (None, 0):
            raise ValueError("flat forecasts must have zero or no expected return")
        return self


class CouncilDecision(DomainModel):
    decision_id: str
    symbol: str
    timeframe: str
    source_snapshot_id: str
    source_as_of: datetime
    forecast_direction: Direction
    expected_return: FiniteFloat | None
    target_exposure: SignedUnitFloat | None
    action: ActionIntent
    conviction: SignedUnitFloat
    confidence: UnitFloat
    decided_at: datetime
    expires_at: datetime
    signals: tuple[AgentSignal, ...]
    rationale: str

    @field_validator("source_as_of", "decided_at", "expires_at")
    @classmethod
    def validate_time(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        actionable = self.action in (ActionIntent.TARGET_EXPOSURE, ActionIntent.REDUCE_ONLY)
        if actionable != (self.target_exposure is not None):
            raise ValueError(
                "actionable decisions require target_exposure; other decisions forbid it"
            )
        if self.expires_at < self.decided_at:
            raise ValueError("decision expires_at cannot precede decided_at")
        if self.forecast_direction is Direction.LONG and (self.expected_return or 0) < 0:
            raise ValueError("long decisions cannot have a negative expected return")
        if self.forecast_direction is Direction.SHORT and (self.expected_return or 0) > 0:
            raise ValueError("short decisions cannot have a positive expected return")
        if self.forecast_direction is Direction.FLAT and self.expected_return not in (None, 0):
            raise ValueError("flat decisions must have zero or no expected return")
        return self


class Position(DomainModel):
    symbol: str
    quantity: FiniteFloat
    average_entry_price: PositiveFiniteFloat
    mark_price: PositiveFiniteFloat
    mark_observed_at: datetime

    @field_validator("mark_observed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "mark_observed_at")

    @model_validator(mode="after")
    def validate_position(self) -> Self:
        if self.quantity == 0:
            raise ValueError("zero-quantity positions must not be retained")
        return self

    @property
    def notional(self) -> float:
        return self.quantity * self.mark_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.average_entry_price

    @property
    def unrealized_pnl(self) -> float:
        return self.quantity * (self.mark_price - self.average_entry_price)


class PortfolioState(DomainModel):
    cash: FiniteFloat
    equity: FiniteFloat
    valued_at: datetime
    positions: tuple[Position, ...] = ()

    @field_validator("valued_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "valued_at")

    @model_validator(mode="after")
    def validate_equity(self) -> Self:
        if len({position.symbol for position in self.positions}) != len(self.positions):
            raise ValueError("portfolio positions must have unique symbols")
        expected = self.cash + sum(position.notional for position in self.positions)
        if not isclose(self.equity, expected, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError("equity must equal cash plus marked position value")
        return self

    @property
    def gross_exposure(self) -> float:
        return sum(abs(position.notional) for position in self.positions)

    @property
    def unrealized_pnl(self) -> float:
        return sum(position.unrealized_pnl for position in self.positions)


class ExecutionCostBounds(DomainModel):
    fee_bps: NonNegativeFiniteFloat = 0.0
    slippage_bps: NonNegativeFiniteFloat = 0.0

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.fee_bps > 10_000 or self.slippage_bps > 10_000:
            raise ValueError("fee and slippage bounds cannot exceed 10000 bps")
        return self


class ApprovedOrder(DomainModel):
    """Paper execution capability emitted exclusively by the risk workflow."""

    authorization_id: str
    decision_id: str
    source_snapshot_id: str
    symbol: str
    timeframe: str
    side: OrderSide
    quantity: PositiveFiniteFloat
    reference_price: PositiveFiniteFloat
    authorized_at: datetime
    earliest_fill_at: datetime
    expires_at: datetime
    fill_policy: FillPolicy = FillPolicy.NEXT_BAR_OPEN
    max_fee_bps: NonNegativeFiniteFloat = 0.0
    max_slippage_bps: NonNegativeFiniteFloat = 0.0
    reduce_only: bool = False
    paper_only: bool = True

    @field_validator("authorized_at", "earliest_fill_at", "expires_at")
    @classmethod
    def validate_time(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if not self.paper_only:
            raise ValueError("this package only authorizes paper orders")
        if self.earliest_fill_at < self.authorized_at:
            raise ValueError("earliest fill cannot precede authorization")
        if self.expires_at < self.earliest_fill_at:
            raise ValueError("order expires before it can fill")
        if self.max_fee_bps > 10_000 or self.max_slippage_bps > 10_000:
            raise ValueError("order cost bounds cannot exceed 10000 bps")
        return self


class RiskDecision(DomainModel):
    status: RiskStatus
    evaluated_at: datetime
    reasons: tuple[str, ...]
    approved_order: ApprovedOrder | None = None

    @field_validator("evaluated_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "evaluated_at")

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        approved = self.status is RiskStatus.APPROVED
        if approved != (self.approved_order is not None):
            raise ValueError("approved status and approved_order must agree")
        return self


class ExecutionReport(DomainModel):
    authorization_id: str
    status: ExecutionStatus
    symbol: str
    side: OrderSide
    quantity: PositiveFiniteFloat
    submitted_at: datetime
    filled_at: datetime | None
    fill_price: PositiveFiniteFloat | None
    fee: NonNegativeFiniteFloat
    slippage_bps: NonNegativeFiniteFloat
    message: str

    @field_validator("submitted_at", "filled_at")
    @classmethod
    def validate_time(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def validate_execution(self) -> Self:
        filled_values = (self.filled_at, self.fill_price)
        if self.status is ExecutionStatus.FILLED and any(value is None for value in filled_values):
            raise ValueError("filled reports require fill time and price")
        if self.status is ExecutionStatus.REJECTED and any(
            value is not None for value in filled_values
        ):
            raise ValueError("rejected reports cannot contain fill details")
        return self


class RiskReconciliation(DomainModel):
    compliant: bool
    reconciled_at: datetime
    reasons: tuple[str, ...]

    @field_validator("reconciled_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value, "reconciled_at")


def utc_now() -> datetime:
    """Boundary helper; deterministic core methods accept explicit timestamps."""

    return datetime.now(UTC)
