from datetime import datetime, timedelta
from math import inf, nan

import pytest

from botnet_council.agents import TrendAgent
from botnet_council.risk import RiskPolicy
from botnet_council.schemas import (
    AgentContext,
    ExecutionCostBounds,
    MarketBar,
    MarketSnapshot,
    PortfolioState,
    Position,
)


@pytest.mark.parametrize("bad", [nan, inf, -inf])
def test_market_prices_reject_non_finite_values(as_of: datetime, bad: float) -> None:
    with pytest.raises(ValueError):
        MarketBar(
            opened_at=as_of - timedelta(minutes=5),
            closed_at=as_of,
            open=100.0,
            high=101.0,
            low=99.0,
            close=bad,
            volume=1_000.0,
        )


@pytest.mark.parametrize("bad", [nan, inf, -inf])
def test_portfolio_and_cost_inputs_reject_non_finite_values(as_of: datetime, bad: float) -> None:
    with pytest.raises(ValueError):
        PortfolioState(cash=bad, equity=bad, valued_at=as_of)
    with pytest.raises(ValueError):
        ExecutionCostBounds(fee_bps=bad)
    with pytest.raises(ValueError):
        RiskPolicy(max_slippage_bps=bad)


def test_signal_returns_and_nested_metadata_reject_non_finite_values(
    rising_snapshot: MarketSnapshot,
) -> None:
    signal = TrendAgent().analyze(rising_snapshot, AgentContext(run_id="test"))
    with pytest.raises(ValueError):
        signal.__class__(
            **{
                **signal.model_dump(exclude={"metadata"}),
                "metadata": dict(signal.metadata),
                "expected_return": nan,
            }
        )
    with pytest.raises(ValueError):
        AgentContext(run_id="test", parameters={"nested": [1.0, inf]})


def test_portfolio_rejects_incorrect_marked_equity(as_of: datetime) -> None:
    position = Position(
        symbol="TEST/USD",
        quantity=2.0,
        average_entry_price=100.0,
        mark_price=120.0,
        mark_observed_at=as_of,
    )
    with pytest.raises(ValueError, match="cash plus marked"):
        PortfolioState(cash=800.0, equity=1_000.0, valued_at=as_of, positions=(position,))
