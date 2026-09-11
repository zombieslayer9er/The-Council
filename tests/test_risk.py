from datetime import datetime, timedelta

import pytest

from botnet_council.agents import TrendAgent, VolatilityAgent
from botnet_council.council import CouncilConfig, DeterministicCouncil
from botnet_council.risk import DeterministicRiskGovernor, RiskPolicy
from botnet_council.schemas import (
    ActionIntent,
    AgentContext,
    ApprovedOrder,
    CouncilDecision,
    Direction,
    ExecutionCostBounds,
    ExecutionReport,
    ExecutionStatus,
    MarketSnapshot,
    OrderSide,
    PortfolioState,
    Position,
    RiskStatus,
    VolatilityObservation,
)


def portfolio(as_of: datetime, cash: float = 100_000.0) -> PortfolioState:
    return PortfolioState(cash=cash, equity=cash, valued_at=as_of)


def decision_for(snapshot: MarketSnapshot) -> CouncilDecision:
    signal = TrendAgent().analyze(snapshot, AgentContext(run_id="test"))
    return DeterministicCouncil(CouncilConfig(minimum_conviction=0.01)).aggregate(
        snapshot, (signal,)
    )


def authorized_order(as_of: datetime, quantity: float = 2.0) -> ApprovedOrder:
    return ApprovedOrder(
        authorization_id="auth-reconcile",
        decision_id="decision-reconcile",
        source_snapshot_id="snapshot-reconcile",
        symbol="TEST/USD",
        timeframe="5m",
        side=OrderSide.BUY,
        quantity=quantity,
        reference_price=100.0,
        authorized_at=as_of,
        earliest_fill_at=as_of,
        expires_at=as_of + timedelta(minutes=5),
        max_fee_bps=10.0,
        max_slippage_bps=10.0,
    )


def filled_report(
    order: ApprovedOrder,
    *,
    fill_price: float = 100.0,
    filled_at: datetime | None = None,
    reported_slippage_bps: float = 0.0,
) -> ExecutionReport:
    effective_fill_time = order.earliest_fill_at if filled_at is None else filled_at
    return ExecutionReport(
        authorization_id=order.authorization_id,
        status=ExecutionStatus.FILLED,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        submitted_at=order.authorized_at,
        filled_at=effective_fill_time,
        fill_price=fill_price,
        fee=0.0,
        slippage_bps=reported_slippage_bps,
        message="test fill",
    )


def test_governor_approves_bounded_paper_order(rising_snapshot: MarketSnapshot) -> None:
    result = DeterministicRiskGovernor(RiskPolicy(max_realized_volatility=0.5)).evaluate(
        decision_for(rising_snapshot),
        rising_snapshot,
        portfolio(rising_snapshot.as_of),
        ExecutionCostBounds(),
        rising_snapshot.as_of,
    )

    assert result.status is RiskStatus.APPROVED
    assert result.approved_order is not None
    assert result.approved_order.paper_only is True
    assert result.approved_order.quantity * rising_snapshot.last_price <= 10_000


def test_governor_vetoes_typed_high_volatility(rising_snapshot: MarketSnapshot) -> None:
    trend = TrendAgent().analyze(rising_snapshot, AgentContext(run_id="test"))
    volatility = VolatilityAgent().analyze(rising_snapshot, AgentContext(run_id="test"))
    assert volatility.volatility is not None
    high = VolatilityObservation(
        **{
            **volatility.volatility.model_dump(),
            "value": 0.5,
        }
    )
    volatility = volatility.model_copy(update={"volatility": high})
    decision = DeterministicCouncil(CouncilConfig(minimum_conviction=0.01)).aggregate(
        rising_snapshot, (trend, volatility)
    )

    result = DeterministicRiskGovernor(RiskPolicy(max_realized_volatility=0.08)).evaluate(
        decision,
        rising_snapshot,
        portfolio(rising_snapshot.as_of),
        ExecutionCostBounds(),
        rising_snapshot.as_of,
    )

    assert result.status is RiskStatus.VETOED
    assert any("volatility" in reason for reason in result.reasons)


@pytest.mark.parametrize("offset", [timedelta(seconds=1), timedelta(minutes=-20)])
def test_governor_rejects_future_and_stale_signals(
    rising_snapshot: MarketSnapshot, offset: timedelta
) -> None:
    decision = decision_for(rising_snapshot)
    signal = decision.signals[0].model_copy(
        update={
            "generated_at": rising_snapshot.as_of + offset,
            "expires_at": rising_snapshot.as_of + timedelta(minutes=5),
        }
    )
    decision = decision.model_copy(update={"signals": (signal,)})

    result = DeterministicRiskGovernor(
        RiskPolicy(max_realized_volatility=0.5, max_signal_age_seconds=60)
    ).evaluate(
        decision,
        rising_snapshot,
        portfolio(rising_snapshot.as_of),
        ExecutionCostBounds(),
        rising_snapshot.as_of,
    )

    assert result.status is RiskStatus.VETOED
    assert any(
        "signal" in reason and ("future" in reason or "stale" in reason)
        for reason in result.reasons
    )


def test_governor_rejects_signal_generated_before_source_availability(
    rising_snapshot: MarketSnapshot,
) -> None:
    decision = decision_for(rising_snapshot)
    signal = decision.signals[0].model_copy(
        update={"generated_at": rising_snapshot.observed_at - timedelta(seconds=1)}
    )
    decision = decision.model_copy(update={"signals": (signal,)})

    result = DeterministicRiskGovernor(RiskPolicy(max_realized_volatility=0.5)).evaluate(
        decision,
        rising_snapshot,
        portfolio(rising_snapshot.as_of),
        ExecutionCostBounds(),
        rising_snapshot.as_of,
    )

    assert result.status is RiskStatus.VETOED
    assert any("predates source availability" in reason for reason in result.reasons)


def test_governor_rejects_stale_market_observation(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    later = as_of + timedelta(minutes=30)
    stale = MarketSnapshot(
        symbol=rising_snapshot.symbol,
        timeframe=rising_snapshot.timeframe,
        as_of=later,
        observed_at=later,
        bars=rising_snapshot.bars,
    )
    decision = decision_for(stale)

    result = DeterministicRiskGovernor(
        RiskPolicy(max_realized_volatility=0.5, max_observation_age_seconds=60)
    ).evaluate(decision, stale, portfolio(later), ExecutionCostBounds(), later)

    assert result.status is RiskStatus.VETOED
    assert "market observation is stale" in result.reasons


def test_long_to_flat_is_approved_despite_restrictive_policy(
    rising_snapshot: MarketSnapshot,
) -> None:
    signal = (
        TrendAgent()
        .analyze(rising_snapshot, AgentContext(run_id="test"))
        .model_copy(
            update={
                "forecast_direction": Direction.FLAT,
                "expected_return": 0.0,
                "target_exposure": 0.0,
                "confidence": 0.0,
                "action": ActionIntent.TARGET_EXPOSURE,
            }
        )
    )
    decision = DeterministicCouncil(
        CouncilConfig(minimum_confidence=1.0, minimum_conviction=0.5)
    ).aggregate(rising_snapshot, (signal,))
    position = Position(
        symbol=rising_snapshot.symbol,
        quantity=0.3,
        average_entry_price=100.0,
        mark_price=rising_snapshot.last_price,
        mark_observed_at=rising_snapshot.as_of,
    )
    marked = PortfolioState(
        cash=0.0,
        equity=position.notional,
        valued_at=rising_snapshot.as_of,
        positions=(position,),
    )
    restrictive = RiskPolicy(
        minimum_confidence=1.0,
        minimum_cash_reserve_fraction=0.9,
        max_position_fraction=0.1,
        max_gross_exposure_fraction=0.2,
        max_realized_volatility=1e-12,
        allowed_symbols=("OTHER/USD",),
    )

    result = DeterministicRiskGovernor(restrictive).evaluate(
        decision, rising_snapshot, marked, ExecutionCostBounds(), rising_snapshot.as_of
    )

    assert result.status is RiskStatus.APPROVED
    assert result.approved_order is not None
    assert result.approved_order.side.value == "sell"
    assert result.approved_order.reduce_only is True
    assert result.approved_order.quantity == 0.3


def test_pretrade_risk_includes_bounded_fees_and_slippage(
    rising_snapshot: MarketSnapshot,
) -> None:
    decision = decision_for(rising_snapshot).model_copy(
        update={"target_exposure": 1.0, "conviction": 1.0}
    )
    policy = RiskPolicy(
        max_position_fraction=0.5,
        max_gross_exposure_fraction=1.0,
        minimum_cash_reserve_fraction=0.5,
        max_order_notional=1_000,
        max_realized_volatility=0.5,
        max_fee_bps=100,
        max_slippage_bps=100,
    )

    result = DeterministicRiskGovernor(policy).evaluate(
        decision,
        rising_snapshot,
        portfolio(rising_snapshot.as_of, cash=1_000.0),
        ExecutionCostBounds(fee_bps=100.0, slippage_bps=100.0),
        rising_snapshot.as_of,
    )

    assert result.status is RiskStatus.VETOED
    assert any("including costs" in reason for reason in result.reasons)


def test_reconciliation_enforces_per_position_limit(as_of: datetime) -> None:
    order = authorized_order(as_of, quantity=6.0)
    report = filled_report(order)
    position = Position(
        symbol=order.symbol,
        quantity=6.0,
        average_entry_price=100.0,
        mark_price=100.0,
        mark_observed_at=as_of,
    )
    before = portfolio(as_of, cash=1_000.0)
    after = PortfolioState(cash=400.0, equity=1_000.0, valued_at=as_of, positions=(position,))
    governor = DeterministicRiskGovernor(
        RiskPolicy(
            max_position_fraction=0.5,
            max_gross_exposure_fraction=1.0,
            minimum_cash_reserve_fraction=0.0,
        )
    )

    reconciliation = governor.reconcile(order, report, before, after)

    assert reconciliation.compliant is False
    assert any("position exposure" in reason for reason in reconciliation.reasons)


def test_reconciliation_recomputes_slippage_from_fill_price(as_of: datetime) -> None:
    order = authorized_order(as_of)
    report = filled_report(order, fill_price=101.0, reported_slippage_bps=0.0)
    position = Position(
        symbol=order.symbol,
        quantity=2.0,
        average_entry_price=101.0,
        mark_price=100.0,
        mark_observed_at=as_of,
    )
    before = portfolio(as_of, cash=1_000.0)
    after = PortfolioState(cash=798.0, equity=998.0, valued_at=as_of, positions=(position,))
    governor = DeterministicRiskGovernor(
        RiskPolicy(
            max_position_fraction=1.0,
            max_gross_exposure_fraction=1.0,
            minimum_cash_reserve_fraction=0.0,
        )
    )

    reconciliation = governor.reconcile(order, report, before, after)

    assert reconciliation.compliant is False
    assert any("slippage exceeded" in reason for reason in reconciliation.reasons)


def test_reconciliation_independently_rejects_invalid_fill_timing(as_of: datetime) -> None:
    order = authorized_order(as_of)
    invalid_fill_time = as_of - timedelta(seconds=1)
    report = filled_report(order, filled_at=invalid_fill_time)
    position = Position(
        symbol=order.symbol,
        quantity=2.0,
        average_entry_price=100.0,
        mark_price=100.0,
        mark_observed_at=invalid_fill_time,
    )
    before = portfolio(as_of - timedelta(minutes=1), cash=1_000.0)
    after = PortfolioState(
        cash=800.0,
        equity=1_000.0,
        valued_at=invalid_fill_time,
        positions=(position,),
    )

    reconciliation = DeterministicRiskGovernor(RiskPolicy()).reconcile(order, report, before, after)

    assert reconciliation.compliant is False
    assert any("fill preceded" in reason for reason in reconciliation.reasons)
