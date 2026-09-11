from datetime import datetime, timedelta

import pytest

from botnet_council.agents import TrendAgent
from botnet_council.council import CouncilConfig, DeterministicCouncil
from botnet_council.schemas import ActionIntent, AgentContext, Direction, MarketSnapshot


def test_council_is_order_independent(rising_snapshot: MarketSnapshot) -> None:
    council = DeterministicCouncil(
        CouncilConfig(agent_weights={"a": 1.0, "b": 0.5}, minimum_conviction=0.01)
    )
    base = TrendAgent().analyze(rising_snapshot, AgentContext(run_id="test"))
    first = base.model_copy(update={"agent_id": "a"})
    second = base.model_copy(update={"agent_id": "b", "target_exposure": 0.2})

    left = council.aggregate(rising_snapshot, (first, second))
    right = council.aggregate(rising_snapshot, (second, first))

    assert left == right
    assert left.forecast_direction is Direction.LONG


@pytest.mark.parametrize(
    ("offset", "message"),
    [
        (timedelta(seconds=1), "future signals"),
        (timedelta(seconds=-1), "before source data is available"),
    ],
)
def test_council_rejects_future_or_stale_signals(
    rising_snapshot: MarketSnapshot, as_of: datetime, offset: timedelta, message: str
) -> None:
    signal = TrendAgent().analyze(rising_snapshot, AgentContext(run_id="test"))
    generated_at = as_of + offset
    expires_at = generated_at + timedelta(minutes=5)
    altered = signal.model_copy(update={"generated_at": generated_at, "expires_at": expires_at})

    with pytest.raises(ValueError, match=message):
        DeterministicCouncil(CouncilConfig()).aggregate(rising_snapshot, (altered,))


def test_low_confidence_explicit_flatten_is_preserved(
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
            }
        )
    )

    decision = DeterministicCouncil(
        CouncilConfig(minimum_confidence=1.0, minimum_conviction=1.0)
    ).aggregate(rising_snapshot, (signal,))

    assert decision.action is ActionIntent.TARGET_EXPOSURE
    assert decision.target_exposure == 0.0


def test_low_confidence_reduce_only_intent_is_preserved(
    rising_snapshot: MarketSnapshot,
) -> None:
    signal = (
        TrendAgent()
        .analyze(rising_snapshot, AgentContext(run_id="test"))
        .model_copy(
            update={
                "target_exposure": 0.25,
                "confidence": 0.0,
                "action": ActionIntent.REDUCE_ONLY,
            }
        )
    )

    decision = DeterministicCouncil(
        CouncilConfig(minimum_confidence=1.0, minimum_conviction=1.0)
    ).aggregate(rising_snapshot, (signal,))

    assert decision.action is ActionIntent.REDUCE_ONLY
    assert decision.target_exposure == pytest.approx(0.25)
