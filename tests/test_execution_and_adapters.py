from datetime import datetime, timedelta

import pytest

from botnet_council.adapters import to_freqtrade_order
from botnet_council.execution import PaperExecutionAdapter
from botnet_council.schemas import (
    ApprovedOrder,
    ExecutionStatus,
    OpeningPriceObservation,
    OrderSide,
    PriceObservation,
)


def approved_order(
    as_of: datetime,
    *,
    quantity: float = 2.0,
    fee_bps: float = 10.0,
    slippage_bps: float = 10.0,
    side: OrderSide = OrderSide.BUY,
    authorization_id: str = "auth-1",
    reduce_only: bool = False,
) -> ApprovedOrder:
    return ApprovedOrder(
        authorization_id=authorization_id,
        decision_id="decision-1",
        source_snapshot_id="snapshot-1",
        symbol="TEST/USD",
        timeframe="5m",
        side=side,
        quantity=quantity,
        reference_price=100.0,
        authorized_at=as_of,
        earliest_fill_at=as_of,
        expires_at=as_of + timedelta(minutes=5),
        max_fee_bps=fee_bps,
        max_slippage_bps=slippage_bps,
        reduce_only=reduce_only,
    )


def opening(as_of: datetime, price: float = 100.0) -> OpeningPriceObservation:
    return OpeningPriceObservation(
        symbol="TEST/USD",
        timeframe="5m",
        price=price,
        bar_opened_at=as_of,
        observed_at=as_of,
    )


def test_paper_adapter_fills_once_at_next_bar_open(as_of: datetime) -> None:
    adapter = PaperExecutionAdapter(
        1_000.0, opened_at=as_of - timedelta(minutes=1), slippage_bps=10, fee_bps=10
    )

    first = adapter.execute(approved_order(as_of), opening(as_of), submitted_at=as_of)
    duplicate = adapter.execute(approved_order(as_of), opening(as_of), submitted_at=as_of)

    assert first.status is ExecutionStatus.FILLED
    assert first.fill_price == pytest.approx(100.1)
    assert first.filled_at == as_of
    assert duplicate.status is ExecutionStatus.REJECTED


def test_completed_bar_cannot_be_filled_retroactively_at_its_open(as_of: datetime) -> None:
    adapter = PaperExecutionAdapter(1_000.0, opened_at=as_of - timedelta(hours=1))
    old_open = opening(as_of - timedelta(minutes=5))

    report = adapter.execute(approved_order(as_of), old_open, submitted_at=as_of)

    assert report.status is ExecutionStatus.REJECTED
    assert "retroactively" in report.message


def test_mark_to_market_preserves_cost_basis_and_updates_equity(as_of: datetime) -> None:
    adapter = PaperExecutionAdapter(1_000.0, opened_at=as_of - timedelta(minutes=1))
    report = adapter.execute(approved_order(as_of), opening(as_of), submitted_at=as_of)
    assert report.status is ExecutionStatus.FILLED
    later = as_of + timedelta(minutes=5)

    state = adapter.mark_to_market(
        (
            PriceObservation(
                symbol="TEST/USD",
                price=120.0,
                observed_at=later,
                source_snapshot_id="snapshot-2",
            ),
        ),
        valued_at=later,
    )

    position = state.positions[0]
    assert position.average_entry_price == 100.0
    assert position.mark_price == 120.0
    assert position.unrealized_pnl == 40.0
    assert state.equity == 1_040.0


def test_slipped_fill_does_not_become_the_market_mark(as_of: datetime) -> None:
    adapter = PaperExecutionAdapter(
        1_000.0, opened_at=as_of - timedelta(minutes=1), slippage_bps=100.0
    )

    report = adapter.execute(
        approved_order(as_of, slippage_bps=100.0), opening(as_of), submitted_at=as_of
    )

    assert report.fill_price == pytest.approx(101.0)
    position = adapter.portfolio_state().positions[0]
    assert position.average_entry_price == pytest.approx(101.0)
    assert position.mark_price == 100.0
    assert position.mark_observed_at == as_of
    assert adapter.portfolio_state().equity == pytest.approx(998.0)


def test_long_position_can_fill_to_exactly_flat(as_of: datetime) -> None:
    adapter = PaperExecutionAdapter(2_000.0, opened_at=as_of - timedelta(minutes=1))
    entry = approved_order(as_of, quantity=10.0)
    assert (
        adapter.execute(entry, opening(as_of), submitted_at=as_of).status is ExecutionStatus.FILLED
    )
    exit_time = as_of + timedelta(minutes=5)
    exit_order = approved_order(
        exit_time,
        quantity=10.0 + 5e-13,
        side=OrderSide.SELL,
        authorization_id="auth-2",
        reduce_only=True,
    )

    report = adapter.execute(exit_order, opening(exit_time), submitted_at=exit_time)

    assert report.status is ExecutionStatus.FILLED
    assert adapter.portfolio_state().positions == ()


def test_mark_to_market_rejects_time_before_account_state(as_of: datetime) -> None:
    adapter = PaperExecutionAdapter(1_000.0, opened_at=as_of - timedelta(minutes=1))
    adapter.execute(approved_order(as_of), opening(as_of), submitted_at=as_of)
    before = adapter.portfolio_state()

    with pytest.raises(ValueError, match="cannot precede account state time"):
        adapter.mark_to_market(
            (
                PriceObservation(
                    symbol="TEST/USD",
                    price=99.0,
                    observed_at=as_of - timedelta(seconds=1),
                    source_snapshot_id="older",
                ),
            ),
            valued_at=as_of - timedelta(seconds=1),
        )

    assert adapter.portfolio_state() == before


def test_execution_rejects_fill_before_account_state(as_of: datetime) -> None:
    adapter = PaperExecutionAdapter(1_000.0, opened_at=as_of - timedelta(minutes=1))
    later = as_of + timedelta(minutes=1)
    adapter.mark_to_market((), valued_at=later)
    before = adapter.portfolio_state()

    report = adapter.execute(approved_order(as_of), opening(as_of), submitted_at=as_of)

    assert report.status is ExecutionStatus.REJECTED
    assert "account state time" in report.message
    assert adapter.portfolio_state() == before


def test_rejected_execution_is_atomic(as_of: datetime) -> None:
    adapter = PaperExecutionAdapter(1_000.0, opened_at=as_of - timedelta(minutes=1))
    before = adapter.portfolio_state()

    report = adapter.execute(
        approved_order(as_of, quantity=20.0), opening(as_of), submitted_at=as_of
    )

    assert report.status is ExecutionStatus.REJECTED
    assert adapter.portfolio_state() == before


def test_fee_and_slippage_authorization_boundaries(as_of: datetime) -> None:
    at_bound = PaperExecutionAdapter(
        1_000.0, opened_at=as_of - timedelta(minutes=1), fee_bps=10, slippage_bps=10
    )
    above_bound = PaperExecutionAdapter(
        1_000.0, opened_at=as_of - timedelta(minutes=1), fee_bps=11, slippage_bps=10
    )

    filled = at_bound.execute(approved_order(as_of), opening(as_of), submitted_at=as_of)
    rejected = above_bound.execute(approved_order(as_of), opening(as_of), submitted_at=as_of)

    assert filled.status is ExecutionStatus.FILLED
    assert rejected.status is ExecutionStatus.REJECTED
    assert above_bound.portfolio_state().cash == 1_000.0


def test_freqtrade_translation_rejects_live_mode(as_of: datetime) -> None:
    with pytest.raises(ValueError, match="dry_run and backtest only"):
        to_freqtrade_order(approved_order(as_of), mode="live")  # type: ignore[arg-type]
