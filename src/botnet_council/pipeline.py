"""Composition layer for the unidirectional research-to-execution workflow."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from botnet_council.agents import SpecialistAgent
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
    ) -> None:
        self._market_data = market_data
        self._agents = tuple(agents)
        self._council = council
        self._risk_governor = risk_governor
        self._execution = execution

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
        snapshot = self._market_data.snapshot(symbol, timeframe, as_of=evaluated_at)
        if snapshot.as_of > evaluated_at or snapshot.observed_at > evaluated_at:
            raise ValueError("market provider returned data after the evaluation cutoff")
        context = AgentContext(run_id=run_id)
        signals = tuple(agent.analyze(snapshot, context) for agent in self._agents)
        for signal in signals:
            logger.info(
                "specialist signal emitted",
                extra={"run_id": run_id, "symbol": symbol, "agent_id": signal.agent_id},
            )
        council_decision = self._council.aggregate(snapshot, signals)

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
        report = None
        reconciliation = None
        if risk_decision.status is RiskStatus.APPROVED and opening_price is not None:
            order = risk_decision.approved_order
            if order is None:
                raise RuntimeError("approved risk decision did not contain an order")
            report = self._execution.execute(order, opening_price, submitted_at=evaluated_at)
            if report.status is ExecutionStatus.FILLED:
                reconciliation = self._risk_governor.reconcile(
                    order,
                    report,
                    marked_portfolio,
                    self._execution.portfolio_state(),
                )
        return PipelineResult(
            snapshot=snapshot,
            signals=signals,
            council_decision=council_decision,
            risk_decision=risk_decision,
            execution_report=report,
            post_fill_reconciliation=reconciliation,
        )
