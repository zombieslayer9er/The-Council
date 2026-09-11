from dataclasses import dataclass
from math import isfinite

from botnet_council.agents._math import clamp, realized_volatility, timeframe_delta
from botnet_council.schemas import (
    ActionIntent,
    AgentContext,
    AgentSignal,
    Direction,
    MarketSnapshot,
    ObservationStatus,
    SignalType,
    SignalValidity,
)


@dataclass(frozen=True, slots=True)
class VolatilityAgent:
    agent_id: str = "volatility"
    agent_version: str = "1.0"
    signal_type: SignalType = SignalType.VOLATILITY
    window: int = 20
    elevated_threshold: float = 0.03

    def __post_init__(self) -> None:
        if (
            isinstance(self.window, bool)
            or isinstance(self.elevated_threshold, bool)
            or self.window < 3
            or not isfinite(self.elevated_threshold)
            or self.elevated_threshold <= 0
        ):
            raise ValueError("volatility settings are invalid")

    def analyze(self, snapshot: MarketSnapshot, context: AgentContext) -> AgentSignal:
        del context
        observation = realized_volatility(snapshot, self.window)
        valid = observation.status is ObservationStatus.VALID
        state = (
            "insufficient_data"
            if observation.value is None
            else "elevated"
            if observation.value >= self.elevated_threshold
            else "normal"
        )
        return AgentSignal(
            schema_version="1.1",
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            signal_type=self.signal_type,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            source_snapshot_id=snapshot.snapshot_id,
            source_as_of=snapshot.as_of,
            forecast_direction=Direction.FLAT,
            expected_return=None,
            target_exposure=None,
            action=ActionIntent.NO_ACTION if valid else ActionIntent.ABSTAIN,
            validity=SignalValidity.VALID if valid else SignalValidity.INSUFFICIENT_DATA,
            confidence=clamp(len(snapshot.bars[-self.window :]) / self.window, 0.0, 1.0),
            horizon_bars=self.window,
            generated_at=snapshot.observed_at,
            expires_at=snapshot.observed_at + timeframe_delta(snapshot.timeframe),
            rationale="Typed per-bar log-return dispersion classifies current volatility.",
            volatility=observation,
            metadata={"volatility_state": state},
        )
