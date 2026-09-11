from botnet_council.agents import (
    MeanReversionAgent,
    RegimeClassificationAgent,
    TrendAgent,
    VolatilityAgent,
)
from botnet_council.schemas import (
    ActionIntent,
    AgentContext,
    Direction,
    MarketSnapshot,
    ObservationStatus,
    SignalType,
)


def test_builtin_agents_emit_versioned_snapshot_bound_signals(
    rising_snapshot: MarketSnapshot,
) -> None:
    agents = (TrendAgent(), MeanReversionAgent(), VolatilityAgent(), RegimeClassificationAgent())
    signals = tuple(agent.analyze(rising_snapshot, AgentContext(run_id="test")) for agent in agents)

    assert {signal.agent_id for signal in signals} == {
        "trend",
        "mean_reversion",
        "volatility",
        "regime",
    }
    assert all(signal.schema_version == "1.1" for signal in signals)
    assert all(signal.agent_version == "1.0" for signal in signals)
    assert all(signal.source_snapshot_id == rising_snapshot.snapshot_id for signal in signals)
    assert all(signal.horizon_bars > 0 for signal in signals)
    assert signals[0].forecast_direction is Direction.LONG
    assert signals[0].target_exposure is not None
    assert signals[2].signal_type is SignalType.VOLATILITY
    assert signals[2].action is ActionIntent.NO_ACTION
    assert signals[2].volatility is not None
    assert signals[2].volatility.status is ObservationStatus.VALID
