"""Deterministic aggregation with no provider or execution dependencies."""

from collections.abc import Mapping
from hashlib import sha256
from math import isfinite
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, field_validator

from botnet_council.schemas import (
    EXPOSURE_ABS_TOLERANCE,
    ActionIntent,
    AgentSignal,
    CouncilDecision,
    Direction,
    MarketSnapshot,
    SignalType,
    SignalValidity,
)


class CouncilConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    agent_weights: Mapping[str, float] = Field(default_factory=dict)
    minimum_confidence: float = Field(default=0.20, strict=True, ge=0, le=1, allow_inf_nan=False)
    minimum_conviction: float = Field(default=0.10, strict=True, ge=0, le=1, allow_inf_nan=False)

    @field_validator("agent_weights")
    @classmethod
    def validate_weights(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        if any(not isfinite(weight) or weight < 0 for weight in value.values()):
            raise ValueError("agent weights must be finite and non-negative")
        return MappingProxyType(dict(value))


class DeterministicCouncil:
    def __init__(self, config: CouncilConfig) -> None:
        self._config = config

    def aggregate(
        self, snapshot: MarketSnapshot, signals: tuple[AgentSignal, ...]
    ) -> CouncilDecision:
        ordered = tuple(sorted(signals, key=lambda signal: signal.agent_id))
        if not ordered:
            raise ValueError("a council round requires at least one signal")
        if len({signal.agent_id for signal in ordered}) != len(ordered):
            raise ValueError("each agent may submit only one signal per council round")
        for signal in ordered:
            self._validate_signal_source(snapshot, signal)

        alpha = tuple(
            signal
            for signal in ordered
            if signal.signal_type is SignalType.ALPHA
            and signal.validity is SignalValidity.VALID
            and signal.action in (ActionIntent.TARGET_EXPOSURE, ActionIntent.REDUCE_ONLY)
        )
        weighted_capacity = sum(self._weight(signal) for signal in alpha)
        effective_weight = sum(self._weight(signal) * signal.confidence for signal in alpha)
        if effective_weight == 0 or weighted_capacity == 0:
            conviction = (
                0.0
                if weighted_capacity == 0
                else sum(self._weight(signal) * (signal.target_exposure or 0.0) for signal in alpha)
                / weighted_capacity
            )
            expected_return, confidence = None, 0.0
        else:
            conviction = (
                sum(
                    self._weight(signal) * signal.confidence * (signal.target_exposure or 0.0)
                    for signal in alpha
                )
                / effective_weight
            )
            expected_return = (
                sum(
                    self._weight(signal) * signal.confidence * (signal.expected_return or 0.0)
                    for signal in alpha
                )
                / effective_weight
            )
            confidence = effective_weight / weighted_capacity

        all_explicitly_flat = bool(alpha) and all(
            abs(signal.target_exposure or 0.0) <= EXPOSURE_ABS_TOLERANCE for signal in alpha
        )
        all_reduce_only = bool(alpha) and all(
            signal.action is ActionIntent.REDUCE_ONLY for signal in alpha
        )
        preserves_or_reduces_exposure = all_explicitly_flat or all_reduce_only
        if not alpha:
            action, target_exposure = ActionIntent.ABSTAIN, None
        elif not preserves_or_reduces_exposure and (
            confidence < self._config.minimum_confidence
            or abs(conviction) < self._config.minimum_conviction
        ):
            action, target_exposure = ActionIntent.NO_ACTION, None
        else:
            target_exposure = 0.0 if all_explicitly_flat else conviction
            action = ActionIntent.REDUCE_ONLY if all_reduce_only else ActionIntent.TARGET_EXPOSURE

        if expected_return is not None and expected_return > 0:
            direction = Direction.LONG
        elif expected_return is not None and expected_return < 0:
            direction = Direction.SHORT
        else:
            direction = Direction.FLAT

        rationale = (
            f"Aggregated {len(alpha)} valid alpha signal(s); retained "
            f"{len(ordered) - len(alpha)} advisory or abstaining signal(s)."
        )
        expires_at = min(signal.expires_at for signal in ordered)
        decision_id = self._decision_id(snapshot, ordered, action, target_exposure)
        return CouncilDecision(
            decision_id=decision_id,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            source_snapshot_id=snapshot.snapshot_id,
            source_as_of=snapshot.as_of,
            forecast_direction=direction,
            expected_return=expected_return,
            target_exposure=target_exposure,
            action=action,
            conviction=conviction,
            confidence=confidence,
            decided_at=snapshot.observed_at,
            expires_at=expires_at,
            signals=ordered,
            rationale=rationale,
        )

    @staticmethod
    def _validate_signal_source(snapshot: MarketSnapshot, signal: AgentSignal) -> None:
        if (signal.symbol, signal.timeframe) != (snapshot.symbol, snapshot.timeframe):
            raise ValueError("all signals must match the market snapshot")
        if (
            signal.source_snapshot_id != snapshot.snapshot_id
            or signal.source_as_of != snapshot.as_of
        ):
            raise ValueError("all signals must identify the exact source snapshot")
        if signal.generated_at < snapshot.observed_at:
            raise ValueError("signals cannot be generated before source data is available")
        if signal.generated_at > snapshot.observed_at:
            raise ValueError("future signals are not available to this council round")
        if signal.expires_at < snapshot.observed_at:
            raise ValueError("stale signals are not available to this council round")
        if signal.volatility is not None:
            if signal.volatility.source_snapshot_id != snapshot.snapshot_id:
                raise ValueError("volatility observation source does not match the snapshot")
            if signal.volatility.observed_at > snapshot.as_of:
                raise ValueError("volatility observation is after the evaluation cutoff")

    def _weight(self, signal: AgentSignal) -> float:
        return self._config.agent_weights.get(signal.agent_id, 1.0)

    @staticmethod
    def _decision_id(
        snapshot: MarketSnapshot,
        signals: tuple[AgentSignal, ...],
        action: ActionIntent,
        target_exposure: float | None,
    ) -> str:
        material = "|".join(
            (
                snapshot.snapshot_id,
                *(
                    (
                        f"{signal.agent_id}:{signal.agent_version}:"
                        f"{signal.generated_at.isoformat()}:{signal.action.value}:"
                        f"{signal.validity.value}:{signal.forecast_direction.value}:"
                        f"{signal.expected_return!r}:{signal.target_exposure!r}:"
                        f"{signal.confidence.hex()}:{signal.horizon_bars}"
                    )
                    for signal in signals
                ),
                action.value,
                "none" if target_exposure is None else target_exposure.hex(),
            )
        )
        return sha256(material.encode()).hexdigest()[:24]
