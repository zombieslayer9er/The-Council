"""Deterministic prior-year calendar seasonality research signal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import exp, isfinite
from statistics import median, pstdev
from typing import ClassVar

from botnet_council.agents._math import clamp, mean, timeframe_delta
from botnet_council.context.models import ContextCapability
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


@dataclass(frozen=True, slots=True)
class _CandidateMatch:
    seasonal_year: int
    entry: MarketBar
    endpoint_at: datetime
    endpoint: MarketBar | None
    forward_return: float | None
    exclusion_reason: str | None


@dataclass(frozen=True, slots=True)
class _YearObservation:
    seasonal_year: int
    forward_return: float
    raw_match_count: int


@dataclass(frozen=True, slots=True)
class _Stability:
    score: float
    sign_consistency: float
    dispersion_factor: float
    extreme_balance: float


@dataclass(frozen=True, slots=True)
class SeasonalityAgent:
    """Measure close-to-close returns near the same UTC date in prior years.

    V0.1 intentionally accepts fixed hypothesis parameters only. It performs no
    parameter selection, feature search, calibration, or mutable fitting.
    """

    required_context_capabilities: ClassVar[frozenset[ContextCapability]] = frozenset(
        {ContextCapability.PRICE_HISTORY}
    )
    optional_context_capabilities: ClassVar[frozenset[ContextCapability]] = frozenset(
        {ContextCapability.EVENT_CALENDAR}
    )

    agent_id: str = "seasonality"
    agent_version: str = "0.1"
    signal_type: SignalType = SignalType.ALPHA
    tolerance_days: int = 7
    horizon_days: int = 30
    prior_years: int = 10
    minimum_independent_years: int = 3
    minimum_confidence: float = 0.20

    def __post_init__(self) -> None:
        integers = (
            self.tolerance_days,
            self.horizon_days,
            self.prior_years,
            self.minimum_independent_years,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in integers):
            raise ValueError("seasonality day, year, and evidence settings must be integers")
        if (
            self.tolerance_days < 0
            or self.horizon_days <= 0
            or self.prior_years <= 0
            or self.minimum_independent_years <= 0
            or isinstance(self.minimum_confidence, bool)
            or not isfinite(self.minimum_confidence)
            or not 0 <= self.minimum_confidence <= 1
        ):
            raise ValueError("seasonality settings are invalid")

    @property
    def warmup_days(self) -> int:
        """Conservative calendar history needed by deterministic replay."""
        return self.prior_years * 366 + self.tolerance_days + 1

    def analyze(self, snapshot: MarketSnapshot, context: AgentContext) -> AgentSignal:
        del context
        if snapshot.timeframe != "1d":
            return self._signal(
                snapshot,
                candidates=(),
                year_observations=(),
                validity=SignalValidity.INVALID,
                action=ActionIntent.ABSTAIN,
                rationale="Seasonality V0.1 requires UTC 1d bars.",
            )

        candidates = self._candidates(snapshot)
        year_observations = _aggregate_years(candidates)
        independent_year_count = len(year_observations)
        if independent_year_count < self.minimum_independent_years:
            return self._signal(
                snapshot,
                candidates=candidates,
                year_observations=year_observations,
                validity=SignalValidity.INSUFFICIENT_DATA,
                action=ActionIntent.ABSTAIN,
                rationale=(
                    f"Need {self.minimum_independent_years} usable independent years; "
                    f"found {independent_year_count}."
                ),
            )

        year_returns = tuple(item.forward_return for item in year_observations)
        confidence = _confidence(year_returns)
        expected_return = mean(year_returns)
        action = (
            ActionIntent.TARGET_EXPOSURE
            if confidence > 0
            and confidence >= self.minimum_confidence
            and not _is_zero(expected_return)
            else ActionIntent.ABSTAIN
        )
        rationale = (
            "Independent prior-year observations produced a sufficiently reliable forecast."
            if action is ActionIntent.TARGET_EXPOSURE
            else "Independent-year evidence is complete but weak or contradictory; abstaining."
        )
        return self._signal(
            snapshot,
            candidates=candidates,
            year_observations=year_observations,
            validity=SignalValidity.VALID,
            action=action,
            rationale=rationale,
        )

    def _candidates(self, snapshot: MarketSnapshot) -> tuple[_CandidateMatch, ...]:
        by_close = {bar.closed_at: bar for bar in snapshot.bars}
        by_close_date = {bar.closed_at.date(): bar for bar in snapshot.bars}
        evaluation_date = snapshot.as_of.date()
        candidates: list[_CandidateMatch] = []
        potential: list[tuple[int, int, MarketBar]] = []
        for seasonal_year in range(
            evaluation_date.year - self.prior_years, evaluation_date.year
        ):
            try:
                anchor = date(seasonal_year, evaluation_date.month, evaluation_date.day)
            except ValueError:
                # February 29 has no non-leap surrogate in V0.1.
                continue
            for offset in range(-self.tolerance_days, self.tolerance_days + 1):
                matched_date = anchor + timedelta(days=offset)
                entry = by_close_date.get(matched_date)
                if entry is not None:
                    potential.append((abs(offset), seasonal_year, entry))

        # Annual windows may overlap for large tolerances. Assign each source
        # observation once, to its nearest anchor; ties go to the earlier year.
        assigned_entries: set[datetime] = set()
        for _, seasonal_year, entry in sorted(
            potential, key=lambda item: (item[0], item[1], item[2].closed_at)
        ):
            if entry.closed_at in assigned_entries:
                continue
            assigned_entries.add(entry.closed_at)
            endpoint_at = entry.closed_at + timedelta(days=self.horizon_days)
            endpoint = by_close.get(endpoint_at)
            reason = _causal_exclusion_reason(
                entry,
                endpoint,
                snapshot=snapshot,
                evaluation_year=evaluation_date.year,
            )
            forward_return = None
            if reason is None and endpoint is not None:
                forward_return, reason = _validated_return(entry.close, endpoint.close)
            candidates.append(
                _CandidateMatch(
                    seasonal_year=seasonal_year,
                    entry=entry,
                    endpoint_at=endpoint_at,
                    endpoint=endpoint,
                    forward_return=forward_return,
                    exclusion_reason=reason,
                )
            )
        return tuple(
            sorted(candidates, key=lambda item: (item.seasonal_year, item.entry.closed_at))
        )

    def _signal(
        self,
        snapshot: MarketSnapshot,
        *,
        candidates: tuple[_CandidateMatch, ...],
        year_observations: tuple[_YearObservation, ...],
        validity: SignalValidity,
        action: ActionIntent,
        rationale: str,
    ) -> AgentSignal:
        usable = tuple(item for item in candidates if item.forward_return is not None)
        excluded = tuple(item for item in candidates if item.exclusion_reason is not None)
        raw_returns = tuple(
            item.forward_return for item in usable if item.forward_return is not None
        )
        year_returns = tuple(item.forward_return for item in year_observations)
        enough = validity is SignalValidity.VALID
        expected_return = mean(year_returns) if enough else None
        dispersion = pstdev(year_returns) if year_returns else 0.0
        stability = _stability(year_returns)
        confidence = _confidence(year_returns) if enough else 0.0
        if expected_return is None or _is_zero(expected_return):
            direction = Direction.FLAT
            if expected_return is not None:
                expected_return = 0.0
        else:
            direction = Direction.LONG if expected_return > 0 else Direction.SHORT
        if action is ActionIntent.TARGET_EXPOSURE and expected_return is not None:
            denominator = abs(expected_return) + dispersion
            target_exposure = clamp(
                (expected_return / denominator if denominator else 0.0) * confidence,
                -1.0,
                1.0,
            )
        else:
            target_exposure = None
        state = (
            "INSUFFICIENT_DATA"
            if validity is SignalValidity.INSUFFICIENT_DATA
            else "INVALID"
            if validity is SignalValidity.INVALID
            else "ABSTAIN"
            if action is ActionIntent.ABSTAIN
            else "VALID"
        )
        provenance = (
            {}
            if snapshot.provenance is None
            else {
                "provider": snapshot.provenance.provider,
                "source_version": snapshot.provenance.source_version,
                "adapter_semantic_version": snapshot.provenance.adapter_semantic_version,
                "cache_key": snapshot.provenance.cache_key,
            }
        )
        candidate_years = tuple(sorted({item.seasonal_year for item in candidates}))
        usable_years = tuple(item.seasonal_year for item in year_observations)
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
            horizon_bars=self.horizon_days,
            generated_at=snapshot.observed_at,
            expires_at=snapshot.observed_at + timeframe_delta(snapshot.timeframe),
            rationale=rationale,
            metadata={
                "state": state,
                "calendar_policy": "same_month_day_utc_no_feb29_substitution",
                "anchor_assignment": "nearest_eligible_anchor_then_earlier_year",
                "year_aggregation": "median_of_usable_raw_matches",
                "tolerance_days": self.tolerance_days,
                "horizon_days": self.horizon_days,
                "prior_years": self.prior_years,
                "minimum_independent_years": self.minimum_independent_years,
                "minimum_confidence": self.minimum_confidence,
                "candidate_match_count": len(candidates),
                "raw_match_count": len(candidates),
                "usable_match_count": len(usable),
                "excluded_match_count": len(excluded),
                "exclusion_reason_counts": _exclusion_reason_counts(excluded),
                "candidate_independent_year_count": len(candidate_years),
                "independent_year_count": len(usable_years),
                "candidate_independent_years": candidate_years,
                "usable_independent_years": usable_years,
                "sample_count": len(usable_years),
                "candidate_matches": tuple(_candidate_metadata(item) for item in candidates),
                "excluded_matches": tuple(_candidate_metadata(item) for item in excluded),
                "matched_dates": tuple(item.entry.closed_at.isoformat() for item in usable),
                "endpoint_dates": tuple(
                    item.endpoint.closed_at.isoformat()
                    for item in usable
                    if item.endpoint is not None
                ),
                "sample_forward_returns": raw_returns,
                "year_level_observations": tuple(
                    {
                        "seasonal_year": item.seasonal_year,
                        "forward_return": item.forward_return,
                        "raw_match_count": item.raw_match_count,
                    }
                    for item in year_observations
                ),
                "mean_forward_return": mean(year_returns) if year_returns else None,
                "median_forward_return": median(year_returns) if year_returns else None,
                "dispersion": dispersion if year_returns else None,
                "positive_fraction": (
                    sum(value > 0 for value in year_returns) / len(year_returns)
                    if year_returns
                    else None
                ),
                "stability": stability.score,
                "stability_components": {
                    "sign_consistency": stability.sign_consistency,
                    "dispersion_factor": stability.dispersion_factor,
                    "extreme_balance": stability.extreme_balance,
                },
                "sample_strength": _sample_strength(len(year_returns)),
                "source_provenance": provenance,
            },
        )


def _causal_exclusion_reason(
    entry: MarketBar,
    endpoint: MarketBar | None,
    *,
    snapshot: MarketSnapshot,
    evaluation_year: int,
) -> str | None:
    if entry.closed_at.year >= evaluation_year:
        return "entry_not_in_prior_calendar_year"
    if entry.closed_at >= snapshot.as_of:
        return "entry_not_complete_before_evaluation"
    if entry.available_at > snapshot.as_of:
        return "entry_unavailable_at_evaluation"
    if endpoint is None:
        return "missing_horizon_endpoint"
    if endpoint.available_at > snapshot.as_of:
        return "endpoint_unavailable_at_evaluation"
    return None


def _validated_return(entry_close: float, endpoint_close: float) -> tuple[float | None, str | None]:
    try:
        value = endpoint_close / entry_close - 1.0
    except OverflowError:
        return None, "forward_return_overflow"
    if not isfinite(value):
        return None, "non_finite_forward_return"
    return value, None


def _aggregate_years(
    candidates: tuple[_CandidateMatch, ...],
) -> tuple[_YearObservation, ...]:
    grouped: dict[int, list[float]] = {}
    for item in candidates:
        if item.forward_return is not None:
            grouped.setdefault(item.seasonal_year, []).append(item.forward_return)
    return tuple(
        _YearObservation(
            seasonal_year=year,
            forward_return=median(values),
            raw_match_count=len(values),
        )
        for year, values in sorted(grouped.items())
    )


def _stability(year_returns: tuple[float, ...]) -> _Stability:
    """Bounded agreement across independent yearly observations."""
    count = len(year_returns)
    if count < 2:
        return _Stability(0.0, 0.0, 0.0, 0.0)
    signs = tuple(1 if value > 0 else -1 if value < 0 else 0 for value in year_returns)
    sign_consistency = abs(sum(signs)) / count
    center = abs(median(year_returns))
    dispersion = pstdev(year_returns)
    dispersion_factor = center / (center + dispersion) if center + dispersion > 0 else 0.0
    absolute = tuple(abs(value) for value in year_returns)
    maximum = max(absolute)
    if maximum == 0:
        extreme_balance = 0.0
    else:
        maximum_share = 1.0 / sum(value / maximum for value in absolute)
        ideal_share = 1.0 / count
        extreme_balance = clamp(
            (1.0 - maximum_share) / (1.0 - ideal_share), 0.0, 1.0
        )
    score = clamp(sign_consistency * dispersion_factor * extreme_balance, 0.0, 1.0)
    return _Stability(score, sign_consistency, dispersion_factor, extreme_balance)


def _sample_strength(independent_year_count: int) -> float:
    if independent_year_count <= 1:
        return 0.0
    return 1.0 - exp(-(independent_year_count - 1) / 6.0)


def _confidence(year_returns: tuple[float, ...]) -> float:
    return clamp(_sample_strength(len(year_returns)) * _stability(year_returns).score, 0.0, 1.0)


def _candidate_metadata(candidate: _CandidateMatch) -> dict[str, object]:
    return {
        "seasonal_year": candidate.seasonal_year,
        "matched_at": candidate.entry.closed_at.isoformat(),
        "endpoint_at": candidate.endpoint_at.isoformat(),
        "status": "excluded" if candidate.exclusion_reason else "usable",
        "exclusion_reason": candidate.exclusion_reason,
        "forward_return": candidate.forward_return,
    }


def _exclusion_reason_counts(
    excluded: tuple[_CandidateMatch, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in excluded:
        if item.exclusion_reason is not None:
            counts[item.exclusion_reason] = counts.get(item.exclusion_reason, 0) + 1
    return dict(sorted(counts.items()))


def _is_zero(value: float) -> bool:
    return abs(value) <= 1e-15
