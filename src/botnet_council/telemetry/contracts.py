"""Versioned public models; these intentionally do not expose domain instances."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.1"
API_VERSION = "v1"


class PublicModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def normalize_public_datetimes(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("public timestamps must be timezone-aware")
            return value.astimezone(UTC)
        return value


class EventType(StrEnum):
    PIPELINE_STARTED = "pipeline_started"
    SNAPSHOT_CREATED = "snapshot_created"
    AGENT_STARTED = "agent_started"
    AGENT_SIGNAL_EMITTED = "agent_signal_emitted"
    COUNCIL_ROUND_STARTED = "council_round_started"
    COUNCIL_DECISION_EMITTED = "council_decision_emitted"
    RISK_EVALUATION_STARTED = "risk_evaluation_started"
    RISK_DECISION_EMITTED = "risk_decision_emitted"
    RISK_VETOED = "risk_vetoed"
    ORDER_APPROVED = "order_approved"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_REPORT_EMITTED = "execution_report_emitted"
    PORTFOLIO_UPDATED = "portfolio_updated"
    RECONCILIATION_COMPLETED = "reconciliation_completed"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"
    BACKTEST_STARTED = "backtest_started"
    BACKTEST_PROGRESS = "backtest_progress"
    BACKTEST_COMPLETED = "backtest_completed"


class RunKind(StrEnum):
    PIPELINE = "pipeline"
    BACKTEST = "backtest"


class MarketBarPayload(PublicModel):
    opened_at: datetime
    closed_at: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class SnapshotProvenancePayload(PublicModel):
    provider: str
    instrument: str
    timeframe: str
    requested_start: datetime
    requested_end: datetime
    as_of: datetime
    fetched_at: datetime
    latest_observation_time: datetime
    latest_available_at: datetime
    source_version: str
    adapter_version: str
    coverage_complete: bool
    cache_key: str


class SnapshotPayload(PublicModel):
    snapshot_id: str
    symbol: str
    timeframe: str
    as_of: datetime
    observed_at: datetime
    latest_available_at: datetime
    bars: tuple[MarketBarPayload, ...]
    provenance: SnapshotProvenancePayload | None = None


class VolatilityPayload(PublicModel):
    estimator: str
    window_bars: int
    units: str
    observed_at: datetime
    source_snapshot_id: str
    status: str
    value: float | None = None


class AgentSignalPayload(PublicModel):
    signal_id: str
    domain_schema_version: str
    agent_id: str
    agent_version: str
    signal_type: str
    symbol: str
    timeframe: str
    source_snapshot_id: str
    source_as_of: datetime
    forecast_direction: str
    expected_return: float | None
    target_exposure: float | None
    action: str
    validity: str
    confidence: float
    horizon_bars: int
    generated_at: datetime
    expires_at: datetime
    rationale: str
    volatility: VolatilityPayload | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CouncilDecisionPayload(PublicModel):
    decision_id: str
    symbol: str
    timeframe: str
    source_snapshot_id: str
    source_as_of: datetime
    forecast_direction: str
    expected_return: float | None
    target_exposure: float | None
    action: str
    conviction: float
    confidence: float
    decided_at: datetime
    expires_at: datetime
    rationale: str
    signal_ids: tuple[str, ...]
    participating_agent_ids: tuple[str, ...]


class ApprovedOrderPayload(PublicModel):
    order_id: str
    decision_id: str
    source_snapshot_id: str
    symbol: str
    timeframe: str
    side: str
    quantity: float
    reference_price: float
    authorized_at: datetime
    earliest_fill_at: datetime
    expires_at: datetime
    fill_policy: str
    max_fee_bps: float
    max_slippage_bps: float
    reduce_only: bool
    paper_only: Literal[True]


class RiskDecisionPayload(PublicModel):
    risk_status: str
    approved: bool
    vetoed: bool
    reasons: tuple[str, ...]
    policy_check_ids: tuple[str, ...]
    evaluated_at: datetime
    decision_id: str
    source_snapshot_id: str
    approved_order: ApprovedOrderPayload | None = None
    cash: float
    equity: float
    gross_exposure: float
    position_quantity: float


class ExecutionReportPayload(PublicModel):
    order_id: str
    decision_id: str
    symbol: str
    side: str
    quantity: float
    submitted_at: datetime
    filled_at: datetime | None
    fill_price: float | None
    fees: float
    slippage_bps: float
    slippage_cost: float | None
    total_costs: float | None
    execution_status: str
    message: str
    paper_only: Literal[True]


class PositionPayload(PublicModel):
    symbol: str
    quantity: float
    average_entry_price: float
    mark_price: float
    mark_observed_at: datetime
    market_value: float
    unrealized_pnl: float
    exposure: float


class PortfolioPayload(PublicModel):
    cash: float
    equity: float
    positions: tuple[PositionPayload, ...]
    gross_exposure: float
    unrealized_pnl: float
    valued_at: datetime


class ReconciliationPayload(PublicModel):
    decision_id: str
    order_id: str
    compliant: bool
    reconciled_at: datetime
    reasons: tuple[str, ...]


class StagePayload(PublicModel):
    stage: str
    message: str = ""
    agent_id: str | None = None
    agent_version: str | None = None
    decision_id: str | None = None
    order_id: str | None = None
    total_agents: int | None = None


class PipelineFailedPayload(PublicModel):
    stage: str
    error_code: str
    message: str


class BacktestPayload(PublicModel):
    status: Literal["started", "in_progress", "completed"]
    current: int = 0
    total: int | None = None
    progress: float | None = None
    event_count: int | None = None
    trade_count: int | None = None


TelemetryPayload = Annotated[
    SnapshotPayload
    | AgentSignalPayload
    | CouncilDecisionPayload
    | RiskDecisionPayload
    | ApprovedOrderPayload
    | ExecutionReportPayload
    | PortfolioPayload
    | ReconciliationPayload
    | StagePayload
    | PipelineFailedPayload
    | BacktestPayload,
    Field(union_mode="left_to_right"),
]


_PAYLOAD_TYPES: dict[EventType, type[PublicModel]] = {
    EventType.SNAPSHOT_CREATED: SnapshotPayload,
    EventType.AGENT_SIGNAL_EMITTED: AgentSignalPayload,
    EventType.COUNCIL_DECISION_EMITTED: CouncilDecisionPayload,
    EventType.RISK_DECISION_EMITTED: RiskDecisionPayload,
    EventType.RISK_VETOED: RiskDecisionPayload,
    EventType.ORDER_APPROVED: ApprovedOrderPayload,
    EventType.EXECUTION_REPORT_EMITTED: ExecutionReportPayload,
    EventType.PORTFOLIO_UPDATED: PortfolioPayload,
    EventType.RECONCILIATION_COMPLETED: ReconciliationPayload,
    EventType.PIPELINE_FAILED: PipelineFailedPayload,
    EventType.BACKTEST_STARTED: BacktestPayload,
    EventType.BACKTEST_PROGRESS: BacktestPayload,
    EventType.BACKTEST_COMPLETED: BacktestPayload,
}


class TelemetryEvent(PublicModel):
    event_id: str
    event_type: EventType
    schema_version: Literal["1.1"] = "1.1"
    stream_id: str | None = None
    sequence: int = Field(default=0, ge=0)
    run_id: str
    symbol: str | None = None
    timeframe: str | None = None
    emitted_at: datetime
    source_snapshot_id: str | None = None
    correlation_id: str | None = None
    payload: TelemetryPayload

    @field_validator("emitted_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("emitted_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def matching_payload(self) -> Self:
        expected = _PAYLOAD_TYPES.get(self.event_type, StagePayload)
        if not isinstance(self.payload, expected):
            raise ValueError(f"{self.event_type.value} requires {expected.__name__}")
        if not self.event_id or not self.run_id:
            raise ValueError("event_id and run_id are required")
        return self


class ApiError(PublicModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str


class ErrorResponse(PublicModel):
    api_version: Literal["v1"] = "v1"
    error: ApiError


class Page(PublicModel):
    api_version: Literal["v1"] = "v1"
    items: tuple[dict[str, Any], ...]
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)


class HealthResponse(PublicModel):
    api_version: Literal["v1"] = "v1"
    status: Literal["ok"] = "ok"
    service: Literal["botnet-council-telemetry"] = "botnet-council-telemetry"
    backend_version: str
    read_only: Literal[True] = True


class StateResponse(PublicModel):
    api_version: Literal["v1"] = "v1"
    stream_id: str
    sequence_watermark: int = Field(ge=0)
    event_count: int
    last_sequence: int
    latest_portfolio: PortfolioPayload | None
    latest_decision: CouncilDecisionPayload | None
    latest_risk_decision: RiskDecisionPayload | None
    active_runs: tuple[str, ...]


class PortfolioResponse(PublicModel):
    api_version: Literal["v1"] = "v1"
    portfolio: PortfolioPayload


class EventPage(PublicModel):
    api_version: Literal["v1"] = "v1"
    items: tuple[TelemetryEvent, ...]
    total: int
    limit: int
    offset: int


class DecisionDetailResponse(PublicModel):
    api_version: Literal["v1"] = "v1"
    decision_id: str
    events: tuple[TelemetryEvent, ...]


class RunSummary(PublicModel):
    run_id: str
    run_kind: Literal["pipeline", "backtest"]
    first_sequence: int
    last_sequence: int
    started_at: datetime
    updated_at: datetime
    event_count: int
    status: Literal["running", "completed", "failed"]
    symbol: str | None
    timeframe: str | None


class RunPage(PublicModel):
    api_version: Literal["v1"] = "v1"
    items: tuple[RunSummary, ...]
    total: int
    limit: int
    offset: int


class RunDetailResponse(PublicModel):
    api_version: Literal["v1"] = "v1"
    run_id: str
    events: tuple[TelemetryEvent, ...]


class SnapshotResponse(PublicModel):
    api_version: Literal["v1"] = "v1"
    snapshot: SnapshotPayload


class AgentSummary(PublicModel):
    agent_id: str
    agent_version: str
    latest_signal: TelemetryEvent


class AgentPage(PublicModel):
    api_version: Literal["v1"] = "v1"
    items: tuple[AgentSummary, ...]
    total: int
    limit: int
    offset: int


class AgentDetailResponse(PublicModel):
    api_version: Literal["v1"] = "v1"
    agent_id: str
    signals: tuple[TelemetryEvent, ...]


class BootstrapResponse(PublicModel):
    api_version: Literal["v1"] = "v1"
    stream_id: str
    sequence_watermark: int = Field(ge=0)
    state: StateResponse
    runs: tuple[RunSummary, ...]
    agents: tuple[AgentSummary, ...]
    events: tuple[TelemetryEvent, ...]
