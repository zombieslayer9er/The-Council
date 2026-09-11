from dataclasses import dataclass
from math import isfinite

from botnet_council.agents._math import clamp, mean, realized_volatility, timeframe_delta
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
class RegimeClassificationAgent:
    agent_id: str = "regime"
    agent_version: str = "1.0"
    signal_type: SignalType = SignalType.REGIME
    window: int = 20
    trend_threshold: float = 0.01
    high_volatility_threshold: float = 0.03

    @property
    def warmup_bars(self) -> int:
        return self.window

    def __post_init__(self) -> None:
        values = (self.trend_threshold, self.high_volatility_threshold)
        if (
            isinstance(self.window, bool)
            or any(isinstance(value, bool) for value in values)
            or self.window < 3
            or any(not isfinite(value) or value <= 0 for value in values)
        ):
            raise ValueError("regime settings are invalid")

    def analyze(self, snapshot: MarketSnapshot, context: AgentContext) -> AgentSignal:
        del context
        closes = tuple(bar.close for bar in snapshot.bars[-self.window :])
        observation = realized_volatility(snapshot, self.window)
        if observation.status is ObservationStatus.INSUFFICIENT_DATA:
            slope, regime, confidence = 0.0, "unknown", 0.0
            validity, action = SignalValidity.INSUFFICIENT_DATA, ActionIntent.ABSTAIN
        else:
            midpoint = max(1, len(closes) // 2)
            early = mean(closes[:midpoint])
            late = mean(closes[midpoint:])
            slope = (late - early) / early
            if (
                observation.value is not None
                and observation.value >= self.high_volatility_threshold
            ):
                regime = "high_volatility"
            elif abs(slope) >= self.trend_threshold:
                regime = "trending_up" if slope > 0 else "trending_down"
            else:
                regime = "range_bound"
            confidence = clamp(len(closes) / self.window, 0.0, 1.0)
            validity, action = SignalValidity.VALID, ActionIntent.NO_ACTION
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
            action=action,
            validity=validity,
            confidence=confidence,
            horizon_bars=self.window,
            generated_at=snapshot.observed_at,
            expires_at=snapshot.observed_at + timeframe_delta(snapshot.timeframe),
            rationale="Deterministic slope and typed volatility classify the regime.",
            volatility=observation,
            metadata={"regime": regime, "relative_slope": slope},
        )
