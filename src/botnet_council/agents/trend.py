from dataclasses import dataclass

from botnet_council.agents._math import clamp, direction_for, mean, timeframe_delta
from botnet_council.schemas import (
    ActionIntent,
    AgentContext,
    AgentSignal,
    MarketSnapshot,
    SignalType,
    SignalValidity,
)


@dataclass(frozen=True, slots=True)
class TrendAgent:
    agent_id: str = "trend"
    agent_version: str = "1.0"
    signal_type: SignalType = SignalType.ALPHA
    fast_window: int = 5
    slow_window: int = 20

    def __post_init__(self) -> None:
        if (
            isinstance(self.fast_window, bool)
            or isinstance(self.slow_window, bool)
            or self.fast_window <= 0
            or self.slow_window <= self.fast_window
        ):
            raise ValueError("trend windows must be positive and ordered")

    def analyze(self, snapshot: MarketSnapshot, context: AgentContext) -> AgentSignal:
        del context
        closes = tuple(bar.close for bar in snapshot.bars)
        if len(closes) < self.slow_window:
            expected_return = None
            target_exposure = None
            confidence = 0.0
            validity = SignalValidity.INSUFFICIENT_DATA
            action = ActionIntent.ABSTAIN
            direction = direction_for(0)[0]
            rationale = f"Need {self.slow_window} bars; received {len(closes)}."
        else:
            fast = mean(closes[-self.fast_window :])
            slow = mean(closes[-self.slow_window :])
            expected_return = (fast - slow) / slow
            direction, target_exposure = direction_for(expected_return * 20.0)
            if direction.value == "flat":
                expected_return = 0.0
            confidence = clamp(abs(expected_return) * 50.0, 0.05, 1.0)
            validity = SignalValidity.VALID
            action = ActionIntent.TARGET_EXPOSURE
            rationale = "Fast/slow spread forecasts a decimal return over the stated horizon."
        return AgentSignal(
            schema_version="1.1",
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            signal_type=self.signal_type,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            source_snapshot_id=snapshot.snapshot_id,
            source_as_of=snapshot.as_of,
            forecast_direction=direction,
            expected_return=expected_return,
            target_exposure=target_exposure,
            action=action,
            validity=validity,
            confidence=confidence,
            horizon_bars=self.slow_window,
            generated_at=snapshot.observed_at,
            expires_at=snapshot.observed_at + timeframe_delta(snapshot.timeframe),
            rationale=rationale,
            metadata={"fast_window": self.fast_window, "slow_window": self.slow_window},
        )
