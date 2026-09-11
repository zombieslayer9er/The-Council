from __future__ import annotations

import re
from datetime import timedelta
from math import log
from statistics import fmean, pstdev

from botnet_council.schemas import (
    Direction,
    MarketSnapshot,
    ObservationStatus,
    VolatilityEstimator,
    VolatilityObservation,
    VolatilityUnits,
)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def direction_for(value: float, deadband: float = 0.05) -> tuple[Direction, float]:
    if abs(value) < deadband:
        return Direction.FLAT, 0.0
    return (Direction.LONG if value > 0 else Direction.SHORT), clamp(value, -1.0, 1.0)


def timeframe_delta(timeframe: str) -> timedelta:
    match = re.fullmatch(r"([1-9][0-9]*)([mhd])", timeframe)
    if match is None:
        raise ValueError("timeframe must use an integer followed by m, h, or d")
    amount, unit = int(match.group(1)), match.group(2)
    seconds = amount * {"m": 60, "h": 3_600, "d": 86_400}[unit]
    return timedelta(seconds=seconds)


def realized_volatility(snapshot: MarketSnapshot, window_bars: int) -> VolatilityObservation:
    closes = tuple(bar.close for bar in snapshot.bars[-window_bars:])
    if len(closes) < 3:
        return VolatilityObservation(
            estimator=VolatilityEstimator.LOG_RETURN_POPULATION_STDDEV,
            window_bars=window_bars,
            units=VolatilityUnits.PER_BAR_DECIMAL,
            observed_at=snapshot.latest_available_at,
            source_snapshot_id=snapshot.snapshot_id,
            status=ObservationStatus.INSUFFICIENT_DATA,
            value=None,
        )
    returns = tuple(
        log(current / previous) for previous, current in zip(closes, closes[1:], strict=False)
    )
    return VolatilityObservation(
        estimator=VolatilityEstimator.LOG_RETURN_POPULATION_STDDEV,
        window_bars=window_bars,
        units=VolatilityUnits.PER_BAR_DECIMAL,
        observed_at=snapshot.latest_available_at,
        source_snapshot_id=snapshot.snapshot_id,
        status=ObservationStatus.VALID,
        value=pstdev(returns),
    )


def mean(values: tuple[float, ...]) -> float:
    return fmean(values)
