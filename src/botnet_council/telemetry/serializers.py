"""One-way, allow-listed projections from authoritative domain models."""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

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
from botnet_council.telemetry.contracts import (
    AgentSignalPayload,
    ApprovedOrderPayload,
    CouncilDecisionPayload,
    ExecutionReportPayload,
    MarketBarPayload,
    PortfolioPayload,
    PositionPayload,
    ReconciliationPayload,
    RiskDecisionPayload,
    SnapshotPayload,
    SnapshotProvenancePayload,
    VolatilityPayload,
)


def signal_id(signal: AgentSignal) -> str:
    public = agent_signal(signal, include_signal_id=False)
    material = json.dumps(
        public.model_dump(mode="json", warnings=False),
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(material.encode()).hexdigest()[:24]


def agent_signal(
    signal: AgentSignal, *, include_signal_id: bool = True
) -> AgentSignalPayload:
    volatility = signal.volatility
    return AgentSignalPayload(
        signal_id=signal_id(signal) if include_signal_id else "pending",
        domain_schema_version=signal.schema_version,
        agent_id=signal.agent_id,
        agent_version=signal.agent_version,
        signal_type=signal.signal_type.value,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        source_snapshot_id=signal.source_snapshot_id,
        source_as_of=signal.source_as_of,
        forecast_direction=signal.forecast_direction.value,
        expected_return=signal.expected_return,
        target_exposure=signal.target_exposure,
        action=signal.action.value,
        validity=signal.validity.value,
        confidence=signal.confidence,
        horizon_bars=signal.horizon_bars,
        generated_at=signal.generated_at,
        expires_at=signal.expires_at,
        rationale=signal.rationale,
        volatility=(
            None
            if volatility is None
            else VolatilityPayload(
                estimator=volatility.estimator.value,
                window_bars=volatility.window_bars,
                units=volatility.units.value,
                observed_at=volatility.observed_at,
                source_snapshot_id=volatility.source_snapshot_id,
                status=volatility.status.value,
                value=volatility.value,
            )
        ),
        metadata=_public_metadata(signal.metadata),
    )


def council_decision(decision: CouncilDecision) -> CouncilDecisionPayload:
    return CouncilDecisionPayload(
        decision_id=decision.decision_id,
        symbol=decision.symbol,
        timeframe=decision.timeframe,
        source_snapshot_id=decision.source_snapshot_id,
        source_as_of=decision.source_as_of,
        forecast_direction=decision.forecast_direction.value,
        expected_return=decision.expected_return,
        target_exposure=decision.target_exposure,
        action=decision.action.value,
        conviction=decision.conviction,
        confidence=decision.confidence,
        decided_at=decision.decided_at,
        expires_at=decision.expires_at,
        rationale=decision.rationale,
        signal_ids=tuple(signal_id(item) for item in decision.signals),
        participating_agent_ids=tuple(item.agent_id for item in decision.signals),
    )


def approved_order(order: ApprovedOrder) -> ApprovedOrderPayload:
    return ApprovedOrderPayload(
        order_id=order.authorization_id,
        decision_id=order.decision_id,
        source_snapshot_id=order.source_snapshot_id,
        symbol=order.symbol,
        timeframe=order.timeframe,
        side=order.side.value,
        quantity=order.quantity,
        reference_price=order.reference_price,
        authorized_at=order.authorized_at,
        earliest_fill_at=order.earliest_fill_at,
        expires_at=order.expires_at,
        fill_policy=order.fill_policy.value,
        max_fee_bps=order.max_fee_bps,
        max_slippage_bps=order.max_slippage_bps,
        reduce_only=order.reduce_only,
        paper_only=True,
    )


def risk_decision(
    decision: RiskDecision,
    council: CouncilDecision,
    portfolio: PortfolioState,
) -> RiskDecisionPayload:
    position = next(
        (item for item in portfolio.positions if item.symbol == council.symbol), None
    )
    return RiskDecisionPayload(
        risk_status=decision.status.value,
        approved=decision.approved_order is not None,
        vetoed=decision.approved_order is None,
        reasons=decision.reasons,
        # The domain currently provides human-readable reasons, not stable check IDs.
        policy_check_ids=(),
        evaluated_at=decision.evaluated_at,
        decision_id=council.decision_id,
        source_snapshot_id=council.source_snapshot_id,
        approved_order=(
            None if decision.approved_order is None else approved_order(decision.approved_order)
        ),
        cash=portfolio.cash,
        equity=portfolio.equity,
        gross_exposure=portfolio.gross_exposure,
        position_quantity=0.0 if position is None else position.quantity,
    )


def execution_report(
    report: ExecutionReport, order: ApprovedOrder
) -> ExecutionReportPayload:
    slippage_cost = (
        None
        if report.fill_price is None
        else report.quantity * abs(report.fill_price - order.reference_price)
    )
    return ExecutionReportPayload(
        order_id=report.authorization_id,
        decision_id=order.decision_id,
        symbol=report.symbol,
        side=report.side.value,
        quantity=report.quantity,
        submitted_at=report.submitted_at,
        filled_at=report.filled_at,
        fill_price=report.fill_price,
        fees=report.fee,
        slippage_bps=report.slippage_bps,
        slippage_cost=slippage_cost,
        total_costs=None if slippage_cost is None else slippage_cost + report.fee,
        execution_status=report.status.value,
        message=report.message,
        paper_only=True,
    )


def portfolio(state: PortfolioState) -> PortfolioPayload:
    positions = tuple(
        PositionPayload(
            symbol=item.symbol,
            quantity=item.quantity,
            average_entry_price=item.average_entry_price,
            mark_price=item.mark_price,
            mark_observed_at=item.mark_observed_at,
            market_value=item.notional,
            unrealized_pnl=item.unrealized_pnl,
            exposure=abs(item.notional),
        )
        for item in state.positions
    )
    return PortfolioPayload(
        cash=state.cash,
        equity=state.equity,
        positions=positions,
        gross_exposure=state.gross_exposure,
        unrealized_pnl=state.unrealized_pnl,
        valued_at=state.valued_at,
    )


def snapshot(value: MarketSnapshot) -> SnapshotPayload:
    provenance = value.provenance
    return SnapshotPayload(
        snapshot_id=value.snapshot_id,
        symbol=value.symbol,
        timeframe=value.timeframe,
        as_of=value.as_of,
        observed_at=value.observed_at,
        latest_available_at=value.latest_available_at,
        bars=tuple(
            MarketBarPayload(
                opened_at=bar.opened_at,
                closed_at=bar.closed_at,
                available_at=bar.available_at,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in value.bars
        ),
        provenance=(
            None
            if provenance is None
            else SnapshotProvenancePayload(
                provider=provenance.provider,
                instrument=provenance.instrument,
                timeframe=provenance.timeframe,
                requested_start=provenance.requested_start,
                requested_end=provenance.requested_end,
                as_of=provenance.as_of,
                fetched_at=provenance.fetched_at,
                latest_observation_time=provenance.latest_observation_time,
                latest_available_at=provenance.latest_available_at,
                source_version=provenance.source_version,
                adapter_version=provenance.adapter_semantic_version,
                coverage_complete=provenance.coverage_complete,
                cache_key=provenance.cache_key,
            )
        ),
    )


def reconciliation(
    value: RiskReconciliation, order: ApprovedOrder
) -> ReconciliationPayload:
    return ReconciliationPayload(
        decision_id=order.decision_id,
        order_id=order.authorization_id,
        compliant=value.compliant,
        reconciled_at=value.reconciled_at,
        reasons=value.reasons,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _public_metadata(value)
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def _public_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    sensitive = ("secret", "password", "token", "api_key", "credential", "authorization")
    return {
        str(key): (
            "[REDACTED]"
            if any(marker in str(key).lower() for marker in sensitive)
            else _json_value(item)
        )
        for key, item in value.items()
    }
