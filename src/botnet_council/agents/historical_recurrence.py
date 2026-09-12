"""Full-history annual recurrence specialist with independent yearly evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil, exp, isfinite, sqrt
from statistics import mean, median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from botnet_council.agents._math import clamp, timeframe_delta
from botnet_council.schemas import (
    ActionIntent,
    AgentContext,
    AgentSignal,
    Direction,
    MarketBar,
    MarketSnapshot,
    SignalType,
    SignalValidity,
)


class RecurrenceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class AnnualRecurrenceObservation(RecurrenceModel):
    annual_year: int
    candidate_date: date
    entry_date: date | None = None
    end_date: date | None = None
    status: str
    exclusion_reason: str | None = None
    normalized_path: tuple[float, ...] = ()
    forward_return: float | None = Field(default=None, allow_inf_nan=False)
    maximum_adverse_excursion: float | None = Field(default=None, allow_inf_nan=False)
    maximum_favorable_excursion: float | None = Field(default=None, allow_inf_nan=False)
    regime: str | None = None
    regime_similarity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

class RecurrenceEpoch(RecurrenceModel):
    first_year: int
    last_year: int
    usable_observations: int = Field(ge=0)
    positive_outcomes: int = Field(ge=0)
    negative_outcomes: int = Field(ge=0)
    directional_hit_ratio: float | None = Field(default=None, ge=0, le=1)
    median_forward_return: float | None = Field(default=None, allow_inf_nan=False)


class RecurrenceWindowEvidence(RecurrenceModel):
    candidate_start: date
    candidate_end: date
    horizon_days: int = Field(gt=0)
    total_annual_observations: int = Field(ge=0)
    usable_observations: int = Field(ge=0)
    positive_outcomes: int = Field(ge=0)
    negative_outcomes: int = Field(ge=0)
    flat_outcomes: int = Field(ge=0)
    raw_positive_hit_ratio: float | None = Field(default=None, ge=0, le=1)
    directional_hit_ratio: float | None = Field(default=None, ge=0, le=1)
    median_forward_return: float | None = Field(default=None, allow_inf_nan=False)
    mean_forward_return: float | None = Field(default=None, allow_inf_nan=False)
    median_maximum_adverse_excursion: float | None = Field(
        default=None, allow_inf_nan=False
    )
    median_maximum_favorable_excursion: float | None = Field(
        default=None, allow_inf_nan=False
    )
    forward_return_distribution: tuple[float, ...]
    persistence_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    sample_count: int = Field(ge=0)
    regime_matched_sample_count: int = Field(ge=0)
    regime_matched_wins: int = Field(ge=0)
    regime_matched_losses: int = Field(ge=0)
    regime_matched_hit_ratio: float | None = Field(default=None, ge=0, le=1)
    mean_regime_similarity: float | None = Field(default=None, ge=0, le=1)
    observations: tuple[AnnualRecurrenceObservation, ...]
    epochs: tuple[RecurrenceEpoch, ...]


class HistoricalRecurrenceEvidence(RecurrenceModel):
    schema_version: str = "1.0"
    as_of: str
    input_first_date: date
    input_last_date: date
    daily_observation_count: int = Field(ge=0)
    selected_horizon_days: int | None = None
    tested_horizons_days: tuple[int, ...]
    multiple_testing_adjustment: float = Field(gt=0, le=1, allow_inf_nan=False)
    current_regime: str | None = None
    windows: tuple[RecurrenceWindowEvidence, ...]


@dataclass(frozen=True, slots=True)
class _DailyClose:
    day: date
    close: float


@dataclass(frozen=True, slots=True)
class HistoricalRecurrenceAgent:
    """Compare a fixed calendar region across independent prior-year observations."""

    agent_id: str = "historical_recurrence"
    agent_version: str = "1.0"
    signal_type: SignalType = SignalType.ALPHA
    horizons_days: tuple[int, ...] = (1, 3, 5, 10, 20)
    history_request_years: int = 200
    calendar_tolerance_days: int = 3
    minimum_usable_years: int = 5
    confidence_sample_target: int = 12
    minimum_confidence: float = 0.20

    def __post_init__(self) -> None:
        integers = (
            self.history_request_years,
            self.calendar_tolerance_days,
            self.minimum_usable_years,
            self.confidence_sample_target,
            *self.horizons_days,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in integers):
            raise ValueError(
                "recurrence year, tolerance, sample, and horizon settings are integers"
            )
        if (
            self.history_request_years < 1
            or not self.horizons_days
            or len(set(self.horizons_days)) != len(self.horizons_days)
            or tuple(sorted(self.horizons_days)) != self.horizons_days
            or min(self.horizons_days) < 1
            or max(self.horizons_days) > 60
            or not 0 <= self.calendar_tolerance_days <= 30
            or self.minimum_usable_years < 2
            or self.confidence_sample_target < self.minimum_usable_years
            or not isfinite(self.minimum_confidence)
            or not 0 <= self.minimum_confidence <= 1
        ):
            raise ValueError("historical recurrence settings are invalid")

    @property
    def warmup_days(self) -> int:
        return (
            self.history_request_years * 366
            + max(self.horizons_days)
            + self.calendar_tolerance_days
        )

    def analyze(self, snapshot: MarketSnapshot, context: AgentContext) -> AgentSignal:
        daily = _daily_closes(snapshot.bars)
        current_regime, historical_regimes, current_features, historical_features = (
            _regime_context(context)
        )
        windows = tuple(
            self._window(
                daily,
                snapshot.as_of.date(),
                horizon,
                current_regime,
                historical_regimes,
                current_features,
                historical_features,
            )
            for horizon in self.horizons_days
        )
        eligible = tuple(
            item
            for item in windows
            if item.usable_observations >= self.minimum_usable_years
            and item.median_forward_return is not None
        )
        selected = max(eligible, key=_selection_score, default=None)
        adjustment = 1.0 / sqrt(len(self.horizons_days))
        confidence = 0.0 if selected is None else self._confidence(selected, adjustment)
        expected_return = None if selected is None else selected.median_forward_return
        if (
            selected is None
            or expected_return is None
            or expected_return == 0
            or confidence < self.minimum_confidence
        ):
            validity = SignalValidity.INSUFFICIENT_DATA
            action = ActionIntent.ABSTAIN
            direction = Direction.FLAT
            target_exposure = None
            expected_return = None
            rationale = "Annual recurrence evidence is insufficient after sample safeguards."
            selected_horizon = None
        else:
            validity = SignalValidity.VALID
            action = ActionIntent.TARGET_EXPOSURE
            direction = Direction.LONG if expected_return > 0 else Direction.SHORT
            target_exposure = clamp(expected_return * 5.0, -1.0, 1.0)
            selected_horizon = selected.horizon_days
            rationale = (
                f"Selected fixed {selected.horizon_days}-day recurrence window from "
                f"{selected.usable_observations}/{selected.total_annual_observations} "
                "independent annual observations after multiple-testing adjustment."
            )
        evidence = HistoricalRecurrenceEvidence(
            as_of=snapshot.as_of.isoformat(),
            input_first_date=daily[0].day,
            input_last_date=daily[-1].day,
            daily_observation_count=len(daily),
            selected_horizon_days=selected_horizon,
            tested_horizons_days=self.horizons_days,
            multiple_testing_adjustment=adjustment,
            current_regime=current_regime,
            windows=windows,
        )
        horizon_days = selected_horizon or max(self.horizons_days)
        horizon_bars = max(
            1,
            ceil(
                timedelta(days=horizon_days).total_seconds()
                / timeframe_delta(snapshot.timeframe).total_seconds()
            ),
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
            forecast_direction=direction,
            expected_return=expected_return,
            target_exposure=target_exposure,
            action=action,
            validity=validity,
            confidence=confidence,
            horizon_bars=horizon_bars,
            generated_at=snapshot.observed_at,
            expires_at=snapshot.observed_at + timeframe_delta(snapshot.timeframe),
            rationale=rationale,
            metadata={
                "historical_recurrence": evidence.model_dump(mode="json"),
                "minimum_usable_years": self.minimum_usable_years,
                "confidence_sample_target": self.confidence_sample_target,
            },
        )

    def _window(
        self,
        daily: tuple[_DailyClose, ...],
        current_day: date,
        horizon_days: int,
        current_regime: str | None,
        historical_regimes: dict[int, str],
        current_features: dict[str, float],
        historical_features: dict[int, dict[str, float]],
    ) -> RecurrenceWindowEvidence:
        by_year: dict[int, tuple[int, ...]] = {}
        for index, item in enumerate(daily):
            by_year.setdefault(item.day.year, ())
            by_year[item.day.year] += (index,)
        # Analyze every supplied reliable observation. ``history_request_years`` is only
        # a provider warmup hint for the legacy snapshot protocol, never an analysis cap.
        first_year = daily[0].day.year
        years = range(first_year, current_day.year)
        observations = tuple(
            _annual_observation(
                year,
                current_day,
                daily,
                by_year.get(year, ()),
                horizon_days,
                self.calendar_tolerance_days,
                historical_regimes,
                current_features,
                historical_features,
            )
            for year in years
        )
        usable = tuple(item for item in observations if item.forward_return is not None)
        returns = tuple(item.forward_return for item in usable if item.forward_return is not None)
        positives = sum(value > 0 for value in returns)
        negatives = sum(value < 0 for value in returns)
        flats = len(returns) - positives - negatives
        selected_direction = 0 if not returns else (1 if median(returns) > 0 else -1)
        directional_wins = (
            positives if selected_direction > 0 else negatives if selected_direction < 0 else flats
        )
        adverse = tuple(
            item.maximum_adverse_excursion
            for item in usable
            if item.maximum_adverse_excursion is not None
        )
        favorable = tuple(
            item.maximum_favorable_excursion
            for item in usable
            if item.maximum_favorable_excursion is not None
        )
        regime_matched = tuple(
            item for item in usable if current_regime is not None and item.regime == current_regime
        )
        matched_returns = tuple(
            item.forward_return
            for item in regime_matched
            if item.forward_return is not None
        )
        similarities = tuple(
            item.regime_similarity
            for item in usable
            if item.regime_similarity is not None
        )
        return RecurrenceWindowEvidence(
            candidate_start=current_day,
            candidate_end=current_day + timedelta(days=horizon_days),
            horizon_days=horizon_days,
            total_annual_observations=len(observations),
            usable_observations=len(usable),
            positive_outcomes=positives,
            negative_outcomes=negatives,
            flat_outcomes=flats,
            raw_positive_hit_ratio=None if not returns else positives / len(returns),
            directional_hit_ratio=(
                None if not returns else directional_wins / len(returns)
            ),
            median_forward_return=None if not returns else median(returns),
            mean_forward_return=None if not returns else mean(returns),
            median_maximum_adverse_excursion=None if not adverse else median(adverse),
            median_maximum_favorable_excursion=None if not favorable else median(favorable),
            forward_return_distribution=returns,
            persistence_score=_persistence(returns),
            sample_count=len(returns),
            regime_matched_sample_count=len(matched_returns),
            regime_matched_wins=sum(value > 0 for value in matched_returns),
            regime_matched_losses=sum(value < 0 for value in matched_returns),
            regime_matched_hit_ratio=(
                None
                if not matched_returns
                else sum(value > 0 for value in matched_returns) / len(matched_returns)
            ),
            mean_regime_similarity=None if not similarities else mean(similarities),
            observations=observations,
            epochs=_epochs(usable),
        )

    def _confidence(self, window: RecurrenceWindowEvidence, adjustment: float) -> float:
        if window.directional_hit_ratio is None:
            return 0.0
        sample_factor = min(1.0, window.sample_count / self.confidence_sample_target)
        effect_factor = 0.0
        if window.median_forward_return is not None:
            effect_factor = 1.0 - exp(-abs(window.median_forward_return) * 50.0)
        raw = (
            window.directional_hit_ratio
            * window.persistence_score
            * sqrt(sample_factor)
            * (0.5 + 0.5 * effect_factor)
            * adjustment
        )
        return clamp(raw, 0.0, 0.75)


def _daily_closes(bars: tuple[MarketBar, ...]) -> tuple[_DailyClose, ...]:
    closes: dict[date, _DailyClose] = {}
    for bar in bars:
        day = bar.opened_at.date()
        closes[day] = _DailyClose(day=day, close=bar.close)
    return tuple(closes[day] for day in sorted(closes))


def _annual_observation(
    year: int,
    current_day: date,
    daily: tuple[_DailyClose, ...],
    indices: tuple[int, ...],
    horizon_days: int,
    tolerance_days: int,
    regimes: dict[int, str],
    current_features: dict[str, float],
    historical_features: dict[int, dict[str, float]],
) -> AnnualRecurrenceObservation:
    candidate = _anniversary(current_day, year)
    possible = tuple(
        index
        for index in indices
        if abs((daily[index].day - candidate).days) <= tolerance_days
    )
    regime = regimes.get(year)
    similarity = _similarity(current_features, historical_features.get(year, {}))
    if not possible:
        return AnnualRecurrenceObservation(
            annual_year=year,
            candidate_date=candidate,
            status="excluded",
            exclusion_reason="missing_calendar_region",
            regime=regime,
            regime_similarity=similarity,
        )
    entry_index = min(
        possible,
        key=lambda index: (abs((daily[index].day - candidate).days), daily[index].day),
    )
    endpoint_index = entry_index + horizon_days
    if endpoint_index >= len(daily) or any(
        (current.day - previous.day).days > 7
        for previous, current in zip(
            daily[entry_index:endpoint_index],
            daily[entry_index + 1 : endpoint_index + 1],
            strict=True,
        )
    ):
        reason = "incomplete_horizon"
    elif daily[endpoint_index].day >= current_day:
        reason = "horizon_unavailable_at_decision_time"
    else:
        reason = ""
    if reason:
        return AnnualRecurrenceObservation(
            annual_year=year,
            candidate_date=candidate,
            entry_date=daily[entry_index].day,
            status="excluded",
            exclusion_reason=reason,
            regime=regime,
            regime_similarity=similarity,
        )
    path = tuple(
        item.close / daily[entry_index].close - 1.0
        for item in daily[entry_index : endpoint_index + 1]
    )
    return AnnualRecurrenceObservation(
        annual_year=year,
        candidate_date=candidate,
        entry_date=daily[entry_index].day,
        end_date=daily[endpoint_index].day,
        status="usable",
        normalized_path=path,
        forward_return=path[-1],
        maximum_adverse_excursion=min(path),
        maximum_favorable_excursion=max(path),
        regime=regime,
        regime_similarity=similarity,
    )


def _anniversary(current_day: date, year: int) -> date:
    try:
        return current_day.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def _persistence(returns: tuple[float, ...]) -> float:
    if not returns:
        return 0.0
    overall = 1 if median(returns) > 0 else -1 if median(returns) < 0 else 0
    group_size = ceil(len(returns) / min(3, len(returns)))
    groups = tuple(
        returns[index : index + group_size]
        for index in range(0, len(returns), group_size)
    )
    matches = 0.0
    for group in groups:
        group_direction = 1 if median(group) > 0 else -1 if median(group) < 0 else 0
        matches += 1.0 if group_direction == overall else 0.0
    return matches / len(groups)


def _epochs(
    observations: tuple[AnnualRecurrenceObservation, ...],
) -> tuple[RecurrenceEpoch, ...]:
    years = sorted({item.annual_year // 10 * 10 for item in observations})
    result: list[RecurrenceEpoch] = []
    for first_year in years:
        values = tuple(
            item.forward_return
            for item in observations
            if first_year <= item.annual_year <= first_year + 9
            and item.forward_return is not None
        )
        if not values:
            continue
        central = median(values)
        wins = (
            sum(value > 0 for value in values)
            if central > 0
            else sum(value < 0 for value in values)
        )
        result.append(
            RecurrenceEpoch(
                first_year=first_year,
                last_year=first_year + 9,
                usable_observations=len(values),
                positive_outcomes=sum(value > 0 for value in values),
                negative_outcomes=sum(value < 0 for value in values),
                directional_hit_ratio=wins / len(values),
                median_forward_return=central,
            )
        )
    return tuple(result)


def _selection_score(window: RecurrenceWindowEvidence) -> tuple[float, int]:
    effect = abs(window.median_forward_return or 0.0)
    direction = window.directional_hit_ratio or 0.0
    return (
        effect * direction * window.persistence_score * sqrt(window.sample_count),
        -window.horizon_days,
    )


def _regime_context(
    context: AgentContext,
) -> tuple[str | None, dict[int, str], dict[str, float], dict[int, dict[str, float]]]:
    current_regime = context.parameters.get("current_regime")
    if current_regime is not None and not isinstance(current_regime, str):
        raise ValueError("current_regime must be a string")
    raw_regimes = context.parameters.get("historical_regimes", {})
    raw_current = context.parameters.get("current_regime_features", {})
    raw_historical = context.parameters.get("historical_regime_features", {})
    if not isinstance(raw_regimes, Mapping):
        raise ValueError("historical_regimes must be a mapping")
    if not isinstance(raw_current, Mapping) or not isinstance(raw_historical, Mapping):
        raise ValueError("regime features must be mappings")
    regimes = {int(year): str(value) for year, value in raw_regimes.items()}
    current_features = _numeric_features(raw_current)
    historical_features = {
        int(year): _numeric_features(values) for year, values in raw_historical.items()
    }
    return current_regime, regimes, current_features, historical_features


def _numeric_features(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("regime feature row must be a mapping")
    result: dict[str, float] = {}
    for name, item in value.items():
        if isinstance(item, bool) or not isinstance(item, int | float) or not isfinite(item):
            raise ValueError("regime features must be finite numbers")
        result[str(name)] = float(item)
    return result


def _similarity(current: dict[str, float], historical: dict[str, float]) -> float | None:
    keys = sorted(current.keys() & historical.keys())
    if not keys:
        return None
    distance = sqrt(sum((current[key] - historical[key]) ** 2 for key in keys))
    return 1.0 / (1.0 + distance)
