from dataclasses import dataclass
from math import isfinite
from statistics import pstdev

from botnet_council.agents._math import clamp, direction_for, mean, timeframe_delta
from botnet_council.schemas import (
    ActionIntent,
    AgentContext,
    AgentSignal,
    Direction,
    MarketSnapshot,
    SignalType,
    SignalValidity,
)


@dataclass(frozen=True, slots=True)
class MeanReversionAgent:
    agent_id: str = "mean_reversion"
    agent_version: str = "1.0"
    signal_type: SignalType = SignalType.ALPHA
    window: int = 20
    entry_z_score: float = 1.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.window, bool)
            or isinstance(self.entry_z_score, bool)
            or self.window < 2
            or not isfinite(self.entry_z_score)
            or self.entry_z_score <= 0
        ):
            raise ValueError("mean-reversion settings are invalid")

    def analyze(self, snapshot: MarketSnapshot, context: AgentContext) -> AgentSignal:
        del context
        closes = tuple(bar.close for bar in snapshot.bars)
        if len(closes) < self.window:
            z_score = 0.0
            expected_return = None
            target_exposure = None
            confidence = 0.0
            validity = SignalValidity.INSUFFICIENT_DATA
            action = ActionIntent.ABSTAIN
            direction = Direction.FLAT
            rationale = f"Need {self.window} bars; received {len(closes)}."
        else:
            sample = closes[-self.window :]
            average = mean(sample)
            deviation = pstdev(sample)
            z_score = 0.0 if deviation == 0 else (sample[-1] - average) / deviation
            expected_return = (average - sample[-1]) / sample[-1]
            raw_target = -z_score / max(self.entry_z_score * 3.0, 1.0)
            raw_target = clamp(raw_target, -1.0, 1.0) if abs(z_score) >= self.entry_z_score else 0.0
            direction, target_exposure = direction_for(raw_target)
            confidence = clamp(abs(z_score) / 3.0, 0.05, 1.0) if raw_target else 0.05
            validity = SignalValidity.VALID
            action = ActionIntent.TARGET_EXPOSURE
            if direction is Direction.FLAT:
                expected_return = 0.0
            rationale = "Distance from the rolling mean forecasts a decimal reversion return."
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
            horizon_bars=self.window,
            generated_at=snapshot.observed_at,
            expires_at=snapshot.observed_at + timeframe_delta(snapshot.timeframe),
            rationale=rationale,
            metadata={"window": self.window, "z_score": z_score},
        )
