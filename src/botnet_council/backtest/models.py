"""Immutable configuration, ledger, and summary contracts for historical replay."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum, StrEnum
from hashlib import sha256
from math import isfinite
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from botnet_council.council import CouncilConfig
from botnet_council.market_data import (
    DataQualityReport,
    HistoricalRequest,
    ProviderId,
)
from botnet_council.risk import RiskPolicy
from botnet_council.schemas import (
    AgentSignal,
    ApprovedOrder,
    CouncilDecision,
    ExecutionReport,
    MarketSnapshot,
    PortfolioState,
    RiskDecision,
    RiskReconciliation,
)


class BacktestModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class AgentConfig(BacktestModel):
    kind: Literal[
        "trend",
        "mean_reversion",
        "volatility",
        "regime",
        "seasonality",
        "historical_recurrence",
    ]
    parameters: Mapping[str, int | float] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: Mapping[str, int | float]) -> Mapping[str, int | float]:
        for key, item in value.items():
            if not key or isinstance(item, bool) or not isfinite(item):
                raise ValueError("agent parameters require named finite numeric values")
        return dict(sorted(value.items()))


class BacktestConfig(BacktestModel):
    instrument: str
    timeframe: str
    start: datetime
    end: datetime
    starting_cash: float = Field(gt=0, allow_inf_nan=False)
    fee_bps: float = Field(default=0.0, ge=0, le=10_000, allow_inf_nan=False)
    slippage_bps: float = Field(default=0.0, ge=0, le=10_000, allow_inf_nan=False)
    agents: tuple[AgentConfig, ...]
    council: CouncilConfig = Field(default_factory=CouncilConfig)
    risk: RiskPolicy = Field(default_factory=RiskPolicy)
    random_seed: int = 0
    warmup_bars: int | None = Field(default=None, ge=0)

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: datetime, info: Any) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{info.field_name} must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        if re.fullmatch(r"[1-9][0-9]*[mhd]", value) is None:
            raise ValueError("timeframe must use an integer followed by m, h, or d")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        if self.end <= self.start:
            raise ValueError("backtest end must be after start")
        if not self.instrument or not self.agents:
            raise ValueError("instrument and at least one agent are required")
        if len({agent.kind for agent in self.agents}) != len(self.agents):
            raise ValueError("backtest agent kinds must be unique")
        return self

    @property
    def identity(self) -> str:
        material = json.dumps(
            to_jsonable(self.model_dump(mode="python", warnings=False)),
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(material.encode()).hexdigest()


class BacktestDataProvenance(BacktestModel):
    provider: ProviderId
    request: HistoricalRequest
    fetched_at: datetime
    source_version: str
    adapter_semantic_version: str
    cache_key: str
    content_identity: str
    quality: DataQualityReport

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("fetched_at must be timezone-aware")
        return value.astimezone(UTC)


class OrderLifecycleStatus(StrEnum):
    PROPOSED = "proposed"
    AUTHORIZED = "authorized"
    QUEUED = "queued"
    FILLED = "filled"
    REJECTED = "rejected"


class OrderLifecycleRecord(BacktestModel):
    status: OrderLifecycleStatus
    occurred_at: datetime
    decision_id: str
    source_snapshot_id: str
    authorization_id: str | None = None
    reason: str = ""

    @field_validator("occurred_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value.astimezone(UTC)


class BacktestEvent(BacktestModel):
    sequence: int = Field(ge=0)
    simulation_time: datetime
    snapshot: MarketSnapshot | None
    signals: tuple[AgentSignal, ...] = ()
    council_decision: CouncilDecision | None = None
    risk_decision: RiskDecision | None = None
    queued_order: ApprovedOrder | None = None
    execution_report: ExecutionReport | None = None
    reconciliation: RiskReconciliation | None = None
    lifecycle: tuple[OrderLifecycleRecord, ...] = ()
    portfolio: PortfolioState
    market_value: float = Field(allow_inf_nan=False)
    gross_realized_pnl: float = Field(allow_inf_nan=False)
    net_realized_pnl: float = Field(allow_inf_nan=False)
    unrealized_pnl: float = Field(allow_inf_nan=False)
    cumulative_fees: float = Field(ge=0, allow_inf_nan=False)
    cumulative_slippage_cost: float = Field(ge=0, allow_inf_nan=False)
    measured: bool

    @field_validator("simulation_time")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("simulation_time must be timezone-aware")
        return value.astimezone(UTC)


class BacktestLedger(BacktestModel):
    run_id: str
    events: tuple[BacktestEvent, ...]


class PerformanceMetrics(BacktestModel):
    starting_equity: float = Field(allow_inf_nan=False)
    ending_equity: float = Field(allow_inf_nan=False)
    total_return: float = Field(allow_inf_nan=False)
    gross_realized_pnl: float = Field(allow_inf_nan=False)
    net_realized_pnl: float = Field(allow_inf_nan=False)
    unrealized_pnl: float = Field(allow_inf_nan=False)
    maximum_drawdown: float = Field(ge=0, le=1, allow_inf_nan=False)
    number_of_trades: int = Field(ge=0)
    win_count: int = Field(ge=0)
    loss_count: int = Field(ge=0)
    total_fees: float = Field(ge=0, allow_inf_nan=False)
    slippage_cost: float = Field(ge=0, allow_inf_nan=False)
    turnover: float = Field(ge=0, allow_inf_nan=False)
    average_gross_exposure: float = Field(ge=0, allow_inf_nan=False)


class BenchmarkMetrics(BacktestModel):
    start_price: float = Field(gt=0, allow_inf_nan=False)
    end_price: float = Field(gt=0, allow_inf_nan=False)
    total_return: float = Field(allow_inf_nan=False)
    ending_equity: float = Field(allow_inf_nan=False)


class BacktestResult(BacktestModel):
    run_id: str
    config_identity: str
    market_data_provenance: BacktestDataProvenance
    evaluation_start: datetime
    evaluation_end: datetime
    final_portfolio: PortfolioState
    metrics: PerformanceMetrics
    benchmark: BenchmarkMetrics
    event_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    warnings: tuple[str, ...] = ()
    data_quality_status: str


class BacktestRun(BacktestModel):
    result: BacktestResult
    ledger: BacktestLedger


def to_jsonable(value: Any) -> Any:
    """Convert frozen domain containers into canonical JSON-compatible values."""
    if isinstance(value, BaseModel):
        return to_jsonable(value.model_dump(mode="python", warnings=False))
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"value of type {type(value).__name__} is not JSON serializable")
