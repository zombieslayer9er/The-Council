"""Composition layer for the unidirectional research-to-execution workflow."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from functools import partial

from pydantic import BaseModel, ConfigDict

from botnet_council.agents import SpecialistAgent
from botnet_council.context import (
    ContextCapability,
    ContextRequest,
    ContextService,
    MarketContext,
    analyze_with_context,
    requested_capabilities,
)
from botnet_council.council import DeterministicCouncil
from botnet_council.execution import ExecutionAdapter
from botnet_council.market_data import MarketDataProvider
from botnet_council.risk import DeterministicRiskGovernor
from botnet_council.schemas import (
    AgentContext,
    AgentSignal,
    CouncilDecision,
    ExecutionReport,
    ExecutionStatus,
    MarketSnapshot,
    OpeningPriceObservation,
    PriceObservation,
    RiskDecision,
    RiskReconciliation,
    RiskStatus,
)
from botnet_council.telemetry.contracts import (
    EventType,
    PipelineFailedPayload,
    PublicModel,
    StagePayload,
    TelemetryPayload,
)
from botnet_council.telemetry.events import event
from botnet_council.telemetry.publisher import EventPublisher, safe_publish
from botnet_council.telemetry.sanitize import sanitize_exception
from botnet_council.telemetry.serializers import (
    agent_signal as serialize_agent_signal,
)
from botnet_council.telemetry.serializers import (
    approved_order as serialize_approved_order,
)
from botnet_council.telemetry.serializers import (
    council_decision as serialize_council_decision,
)
from botnet_council.telemetry.serializers import (
    execution_report as serialize_execution_report,
)
from botnet_council.telemetry.serializers import market_context as serialize_market_context
from botnet_council.telemetry.serializers import (
    portfolio as serialize_portfolio,
)
from botnet_council.telemetry.serializers import (
    reconciliation as serialize_reconciliation,
)
from botnet_council.telemetry.serializers import (
    risk_decision as serialize_risk_decision,
)
from botnet_council.telemetry.serializers import (
    snapshot as serialize_snapshot,
)

logger = logging.getLogger(__name__)


class PipelineResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    snapshot: MarketSnapshot
    signals: tuple[AgentSignal, ...]
    council_decision: CouncilDecision
    risk_decision: RiskDecision
    execution_report: ExecutionReport | None
    post_fill_reconciliation: RiskReconciliation | None


class ResearchTradingPipeline:
    def __init__(
        self,
        market_data: MarketDataProvider,
        agents: Iterable[SpecialistAgent],
        council: DeterministicCouncil,
        risk_governor: DeterministicRiskGovernor,
        execution: ExecutionAdapter,
        telemetry: EventPublisher | None = None,
        context_service: ContextService | None = None,
    ) -> None:
        self._market_data = market_data
        self._agents = tuple(agents)
        self._council = council
        self._risk_governor = risk_governor
        self._execution = execution
        self._telemetry = telemetry
        self._context_service = context_service

    def run(
        self,
        symbol: str,
        timeframe: str,
        run_id: str,
        evaluated_at: datetime,
        *,
        opening_price: OpeningPriceObservation | None = None,
    ) -> PipelineResult:
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        evaluated_at = evaluated_at.astimezone(UTC)
        stage = "pipeline"
        self._emit(
            EventType.PIPELINE_STARTED,
            run_id,
            evaluated_at,
            StagePayload(stage="pipeline", total_agents=len(self._agents)),
            symbol=symbol,
            timeframe=timeframe,
        )
        try:
            stage = "market_data"
            snapshot = self._market_data.snapshot(symbol, timeframe, as_of=evaluated_at)
            if snapshot.as_of > evaluated_at or snapshot.observed_at > evaluated_at:
                raise ValueError("market provider returned data after the evaluation cutoff")
            self._emit(
                EventType.SNAPSHOT_CREATED,
                run_id,
                evaluated_at,
                lambda: serialize_snapshot(snapshot),
                symbol=symbol,
                timeframe=timeframe,
                source_snapshot_id=snapshot.snapshot_id,
            )
            context = AgentContext(run_id=run_id)
            required_context, optional_context = requested_capabilities(self._agents)
            context_request = ContextRequest(
                instrument=symbol,
                timeframe=timeframe,
                as_of=evaluated_at,
                required=required_context,
                optional=optional_context,
            )
            if self._context_service is None:
                market_context = MarketContext(
                    snapshot=snapshot,
                    as_of=evaluated_at,
                    requested_required=required_context,
                    requested_optional=optional_context,
                    missing_required=frozenset(
                        required_context - {ContextCapability.PRICE_HISTORY}
                    ),
                    missing_optional=frozenset(
                        optional_context - {ContextCapability.PRICE_HISTORY}
                    ),
                )
            else:
                market_context = self._context_service.enrich(snapshot, context_request)
            self._emit(
                EventType.MARKET_CONTEXT_READY,
                run_id,
                evaluated_at,
                lambda: serialize_market_context(market_context),
                symbol=symbol,
                timeframe=timeframe,
                source_snapshot_id=snapshot.snapshot_id,
                correlation_id=market_context.context_id,
            )
            collected: list[AgentSignal] = []
            stage = "agents"
            for agent in self._agents:
                self._emit(
                    EventType.AGENT_STARTED,
                    run_id,
                    evaluated_at,
                    StagePayload(
                        stage="agent",
                        agent_id=agent.agent_id,
                        agent_version=getattr(agent, "agent_version", None),
                    ),
                    symbol=symbol,
                    timeframe=timeframe,
                    source_snapshot_id=snapshot.snapshot_id,
                    correlation_id=agent.agent_id,
                )
                signal = analyze_with_context(agent, market_context, context)
                collected.append(signal)
                logger.info(
                    "specialist signal emitted",
                    extra={"run_id": run_id, "symbol": symbol, "agent_id": signal.agent_id},
                )
                self._emit(
                    EventType.AGENT_SIGNAL_EMITTED,
                    run_id,
                    evaluated_at,
                    partial(serialize_agent_signal, signal),
                    symbol=symbol,
                    timeframe=timeframe,
                    source_snapshot_id=snapshot.snapshot_id,
                    correlation_id=signal.agent_id,
                )
            signals = tuple(collected)
            stage = "council"
            self._emit(
                EventType.COUNCIL_ROUND_STARTED,
                run_id,
                evaluated_at,
                StagePayload(stage="council", total_agents=len(signals)),
                symbol=symbol,
                timeframe=timeframe,
                source_snapshot_id=snapshot.snapshot_id,
            )
            council_decision = self._council.aggregate(snapshot, signals)
            self._emit(
                EventType.COUNCIL_DECISION_EMITTED,
                run_id,
                evaluated_at,
                lambda: serialize_council_decision(council_decision),
                symbol=symbol,
                timeframe=timeframe,
                source_snapshot_id=snapshot.snapshot_id,
                correlation_id=council_decision.decision_id,
            )

            stage = "portfolio_mark"
            before_marks = self._execution.portfolio_state()
            observations: list[PriceObservation] = []
            for held_symbol in (position.symbol for position in before_marks.positions):
                held_snapshot = (
                    snapshot
                    if held_symbol == symbol
                    else self._market_data.snapshot(held_symbol, timeframe, as_of=evaluated_at)
                )
                if held_snapshot.as_of > evaluated_at or held_snapshot.observed_at > evaluated_at:
                    raise ValueError("market provider returned a future portfolio mark")
                observations.append(
                    PriceObservation(
                        symbol=held_symbol,
                        price=held_snapshot.last_price,
                        observed_at=held_snapshot.latest_available_at,
                        source_snapshot_id=held_snapshot.snapshot_id,
                    )
                )
            marked_portfolio = self._execution.mark_to_market(
                tuple(observations), valued_at=evaluated_at
            )
            self._emit(
                EventType.PORTFOLIO_UPDATED,
                run_id,
                evaluated_at,
                lambda: serialize_portfolio(marked_portfolio),
                symbol=symbol,
                timeframe=timeframe,
                source_snapshot_id=snapshot.snapshot_id,
                correlation_id=council_decision.decision_id,
            )
            stage = "risk"
            self._emit(
                EventType.RISK_EVALUATION_STARTED,
                run_id,
                evaluated_at,
                StagePayload(
                    stage="risk", decision_id=council_decision.decision_id
                ),
                symbol=symbol,
                timeframe=timeframe,
                source_snapshot_id=snapshot.snapshot_id,
                correlation_id=council_decision.decision_id,
            )
            risk_decision = self._risk_governor.evaluate(
                council_decision,
                snapshot,
                marked_portfolio,
                self._execution.cost_bounds,
                evaluated_at,
            )
            logger.info(
                "risk decision emitted",
                extra={
                    "run_id": run_id,
                    "symbol": symbol,
                    "risk_status": risk_decision.status.value,
                },
            )
            self._emit(
                EventType.RISK_DECISION_EMITTED,
                run_id,
                evaluated_at,
                lambda: serialize_risk_decision(
                    risk_decision, council_decision, marked_portfolio
                ),
                symbol=symbol,
                timeframe=timeframe,
                source_snapshot_id=snapshot.snapshot_id,
                correlation_id=council_decision.decision_id,
            )
            if risk_decision.status is RiskStatus.VETOED:
                self._emit(
                    EventType.RISK_VETOED,
                    run_id,
                    evaluated_at,
                    lambda: serialize_risk_decision(
                        risk_decision, council_decision, marked_portfolio
                    ),
                    symbol=symbol,
                    timeframe=timeframe,
                    source_snapshot_id=snapshot.snapshot_id,
                    correlation_id=council_decision.decision_id,
                )
            order = risk_decision.approved_order
            if order is not None:
                self._emit(
                    EventType.ORDER_APPROVED,
                    run_id,
                    evaluated_at,
                    lambda: serialize_approved_order(order),
                    symbol=symbol,
                    timeframe=timeframe,
                    source_snapshot_id=snapshot.snapshot_id,
                    correlation_id=council_decision.decision_id,
                )

            report = None
            reconciliation = None
            if risk_decision.status is RiskStatus.APPROVED and opening_price is not None:
                if order is None:
                    raise RuntimeError("approved risk decision did not contain an order")
                stage = "execution"
                self._emit(
                    EventType.EXECUTION_STARTED,
                    run_id,
                    evaluated_at,
                    StagePayload(
                        stage="execution",
                        decision_id=council_decision.decision_id,
                        order_id=order.authorization_id,
                    ),
                    symbol=symbol,
                    timeframe=timeframe,
                    source_snapshot_id=snapshot.snapshot_id,
                    correlation_id=council_decision.decision_id,
                )
                report = self._execution.execute(
                    order, opening_price, submitted_at=evaluated_at
                )
                self._emit(
                    EventType.EXECUTION_REPORT_EMITTED,
                    run_id,
                    evaluated_at,
                    lambda: serialize_execution_report(report, order),
                    symbol=symbol,
                    timeframe=timeframe,
                    source_snapshot_id=snapshot.snapshot_id,
                    correlation_id=council_decision.decision_id,
                )
                if report.status is ExecutionStatus.FILLED:
                    reconciliation = self._risk_governor.reconcile(
                        order,
                        report,
                        marked_portfolio,
                        self._execution.portfolio_state(),
                    )
                    self._emit(
                        EventType.RECONCILIATION_COMPLETED,
                        run_id,
                        evaluated_at,
                        lambda: serialize_reconciliation(reconciliation, order),
                        symbol=symbol,
                        timeframe=timeframe,
                        source_snapshot_id=snapshot.snapshot_id,
                        correlation_id=council_decision.decision_id,
                    )
                    self._emit(
                        EventType.PORTFOLIO_UPDATED,
                        run_id,
                        evaluated_at,
                        lambda: serialize_portfolio(self._execution.portfolio_state()),
                        symbol=symbol,
                        timeframe=timeframe,
                        source_snapshot_id=snapshot.snapshot_id,
                        correlation_id=council_decision.decision_id,
                    )
            result = PipelineResult(
                snapshot=snapshot,
                signals=signals,
                council_decision=council_decision,
                risk_decision=risk_decision,
                execution_report=report,
                post_fill_reconciliation=reconciliation,
            )
            self._emit(
                EventType.PIPELINE_COMPLETED,
                run_id,
                evaluated_at,
                StagePayload(
                    stage="pipeline", decision_id=council_decision.decision_id
                ),
                symbol=symbol,
                timeframe=timeframe,
                source_snapshot_id=snapshot.snapshot_id,
                correlation_id=council_decision.decision_id,
            )
            return result
        except Exception as error:
            safe_error = sanitize_exception(error, stage=stage)
            self._emit(
                EventType.PIPELINE_FAILED,
                run_id,
                evaluated_at,
                PipelineFailedPayload(
                    stage=stage,
                    error_code=safe_error.code,
                    message=safe_error.message,
                ),
                symbol=symbol,
                timeframe=timeframe,
            )
            raise

    def _emit(
        self,
        event_type: EventType,
        run_id: str,
        emitted_at: datetime,
        payload: TelemetryPayload | Callable[[], TelemetryPayload],
        **identity: str | None,
    ) -> None:
        if self._telemetry is None:
            return
        try:
            resolved = payload() if callable(payload) else payload
            if not isinstance(resolved, PublicModel):
                raise TypeError("telemetry payload must be a public contract")
            safe_publish(
                self._telemetry,
                event(
                    event_type,
                    run_id=run_id,
                    emitted_at=emitted_at,
                    payload=resolved,
                    **identity,
                ),
            )
        except Exception:
            logger.exception("telemetry event construction failed")
