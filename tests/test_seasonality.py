from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from statistics import pstdev

import pytest

from botnet_council.agents import SeasonalityAgent
from botnet_council.schemas import (
    ActionIntent,
    AgentContext,
    MarketBar,
    MarketSnapshot,
    SignalValidity,
    SnapshotProvenance,
)


def _bar(closed: date, close: float, *, available_at: datetime | None = None) -> MarketBar:
    closed_at = datetime(closed.year, closed.month, closed.day, tzinfo=UTC)
    return MarketBar(
        opened_at=closed_at - timedelta(days=1),
        closed_at=closed_at,
        available_at=available_at or closed_at,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
    )


def _snapshot(
    evaluated: date,
    observations: tuple[tuple[date, float], ...],
    *,
    provenance: bool = False,
) -> MarketSnapshot:
    as_of = datetime(evaluated.year, evaluated.month, evaluated.day, tzinfo=UTC)
    bars = tuple(_bar(closed, close) for closed, close in sorted(observations))
    source = None
    if provenance:
        source = SnapshotProvenance(
            provider="fixture",
            instrument="BTC/USD",
            timeframe="1d",
            requested_start=bars[0].opened_at,
            requested_end=as_of,
            as_of=as_of,
            fetched_at=as_of,
            latest_observation_time=bars[-1].closed_at,
            latest_available_at=bars[-1].available_at,
            source_version="fixture-v1",
            adapter_semantic_version="causal-v1",
            coverage_complete=True,
            cache_key="fixture-key",
        )
    return MarketSnapshot(
        symbol="BTC/USD",
        timeframe="1d",
        as_of=as_of,
        observed_at=as_of,
        bars=bars,
        provenance=source,
    )


def _signal(
    observations: tuple[tuple[date, float], ...],
    *,
    evaluated: date = date(2024, 9, 11),
    **settings: int | float,
):
    parameters: dict[str, int | float] = {
        "tolerance_days": 0,
        "horizon_days": 7,
        "prior_years": 5,
        "minimum_independent_years": 2,
        "minimum_confidence": 0.0,
    }
    parameters.update(settings)
    agent = SeasonalityAgent(**parameters)  # type: ignore[arg-type]
    return agent.analyze(_snapshot(evaluated, observations), AgentContext(run_id="test"))


def test_expected_return_and_diagnostics_are_hand_verifiable() -> None:
    observations = (
        (date(2021, 9, 11), 100.0),
        (date(2021, 9, 18), 110.0),
        (date(2022, 9, 11), 100.0),
        (date(2022, 9, 18), 120.0),
        (date(2023, 9, 11), 100.0),
        (date(2023, 9, 18), 90.0),
    )
    signal = _signal(observations)

    expected = (0.1 + 0.2 - 0.1) / 3
    assert signal.expected_return == pytest.approx(expected)
    assert signal.metadata["median_forward_return"] == pytest.approx(0.1)
    assert signal.metadata["dispersion"] == pytest.approx(pstdev((0.1, 0.2, -0.1)))
    assert signal.metadata["positive_fraction"] == pytest.approx(2 / 3)
    assert signal.metadata["sample_count"] == 3


def test_incomplete_horizon_is_excluded_and_minimum_samples_abstains() -> None:
    signal = _signal(
        (
            (date(2022, 9, 11), 100.0),
            (date(2022, 9, 18), 110.0),
            (date(2023, 9, 11), 100.0),
        )
    )

    assert signal.validity is SignalValidity.INSUFFICIENT_DATA
    assert signal.action is ActionIntent.ABSTAIN
    assert signal.metadata["sample_count"] == 1
    assert signal.expected_return is None


def test_current_and_future_year_entries_are_never_training_samples() -> None:
    signal = _signal(
        (
            (date(2022, 9, 11), 100.0),
            (date(2022, 9, 18), 110.0),
            (date(2023, 9, 11), 100.0),
            (date(2023, 9, 18), 110.0),
            (date(2024, 9, 10), 1.0),
        )
    )

    assert signal.metadata["sample_count"] == 2
    assert all("2024" not in value for value in signal.metadata["matched_dates"])


def test_february_29_has_no_non_leap_substitution() -> None:
    signal = _signal(
        (
            (date(2020, 2, 29), 100.0),
            (date(2020, 3, 7), 110.0),
            (date(2021, 2, 28), 100.0),
            (date(2021, 3, 7), 200.0),
        ),
        evaluated=date(2024, 2, 29),
        prior_years=4,
        minimum_independent_years=1,
    )

    assert signal.metadata["sample_count"] == 1
    assert signal.expected_return == pytest.approx(0.1)
    assert signal.metadata["matched_dates"] == ("2020-02-29T00:00:00+00:00",)


def test_tolerance_window_matches_across_a_year_boundary() -> None:
    signal = _signal(
        (
            (date(2022, 12, 31), 100.0),
            (date(2023, 1, 7), 110.0),
        ),
        evaluated=date(2024, 1, 2),
        tolerance_days=3,
        prior_years=1,
        minimum_independent_years=1,
    )

    assert signal.metadata["sample_count"] == 1
    assert signal.expected_return == pytest.approx(0.1)


def test_noise_and_instability_reduce_confidence() -> None:
    stable = _signal(
        tuple(
            item
            for year in range(2020, 2024)
            for item in ((date(year, 9, 11), 100.0), (date(year, 9, 18), 110.0))
        )
    )
    unstable = _signal(
        tuple(
            item
            for year, endpoint in zip(
                range(2020, 2024), (110.0, 110.0, 90.0, 90.0), strict=True
            )
            for item in ((date(year, 9, 11), 100.0), (date(year, 9, 18), endpoint))
        )
    )

    assert stable.confidence > unstable.confidence
    assert stable.metadata["stability"] == 1.0
    assert unstable.metadata["stability"] == 0.0


def test_weak_complete_evidence_abstains_and_repeated_runs_are_identical() -> None:
    observations = tuple(
        item
        for year, endpoint in zip(
            range(2020, 2024), (110.0, 90.0, 110.0, 90.0), strict=True
        )
        for item in ((date(year, 9, 11), 100.0), (date(year, 9, 18), endpoint))
    )
    agent = SeasonalityAgent(
        tolerance_days=0,
        horizon_days=7,
        prior_years=5,
        minimum_independent_years=2,
        minimum_confidence=0.2,
    )
    snapshot = _snapshot(date(2024, 9, 11), observations)
    context = AgentContext(run_id="same")

    first = agent.analyze(snapshot, context)
    second = agent.analyze(snapshot, context)
    assert first == second
    assert first.validity is SignalValidity.VALID
    assert first.action is ActionIntent.ABSTAIN
    assert first.metadata["state"] == "ABSTAIN"


def test_snapshot_identity_and_provenance_are_preserved() -> None:
    snapshot = _snapshot(
        date(2024, 9, 11),
        (
            (date(2022, 9, 11), 100.0),
            (date(2022, 9, 18), 110.0),
            (date(2023, 9, 11), 100.0),
            (date(2023, 9, 18), 110.0),
        ),
        provenance=True,
    )
    signal = SeasonalityAgent(
        tolerance_days=0,
        horizon_days=7,
        prior_years=2,
        minimum_independent_years=2,
    ).analyze(snapshot, AgentContext(run_id="test"))

    assert signal.source_snapshot_id == snapshot.snapshot_id
    assert signal.source_as_of == snapshot.as_of
    assert signal.metadata["source_provenance"]["cache_key"] == "fixture-key"


def test_non_daily_input_is_an_explicit_invalid_abstention() -> None:
    daily = _snapshot(date(2024, 9, 11), ((date(2023, 9, 11), 100.0),))
    intraday = MarketSnapshot(
        symbol=daily.symbol,
        timeframe="1h",
        as_of=daily.as_of,
        observed_at=daily.observed_at,
        bars=daily.bars,
    )
    signal = SeasonalityAgent().analyze(intraday, AgentContext(run_id="test"))

    assert signal.validity is SignalValidity.INVALID
    assert signal.action is ActionIntent.ABSTAIN


def _overlapping_observations(
    yearly_returns: dict[int, float],
    *,
    offsets: tuple[int, ...] = (0,),
    horizon_days: int = 30,
) -> tuple[tuple[date, float], ...]:
    observations: list[tuple[date, float]] = []
    for year, forward_return in sorted(yearly_returns.items()):
        anchor = date(year, 9, 11)
        for offset in offsets:
            entry = anchor + timedelta(days=offset)
            observations.extend(
                (
                    (entry, 100.0),
                    (entry + timedelta(days=horizon_days), 100.0 * (1.0 + forward_return)),
                )
            )
    return tuple(observations)


def test_fifteen_overlapping_matches_from_one_year_are_one_independent_year() -> None:
    signal = _signal(
        _overlapping_observations({2023: 0.10}, offsets=tuple(range(-7, 8))),
        tolerance_days=7,
        horizon_days=30,
        prior_years=1,
        minimum_independent_years=3,
    )

    assert signal.metadata["raw_match_count"] == 15
    assert signal.metadata["independent_year_count"] == 1
    assert signal.metadata["year_level_observations"][0]["raw_match_count"] == 15
    assert signal.metadata["stability"] == 0.0
    assert signal.confidence == 0.0
    assert signal.validity is SignalValidity.INSUFFICIENT_DATA
    assert signal.action is ActionIntent.ABSTAIN


def test_large_overlapping_annual_windows_cannot_duplicate_one_observation() -> None:
    signal = _signal(
        (
            (date(2022, 9, 11), 100.0),
            (date(2022, 10, 11), 110.0),
        ),
        tolerance_days=400,
        horizon_days=30,
        prior_years=3,
        minimum_independent_years=3,
        minimum_confidence=0.20,
    )

    assert signal.metadata["usable_match_count"] == 1
    assert signal.metadata["independent_year_count"] == 1
    assert signal.metadata["usable_independent_years"] == (2022,)
    assert signal.metadata["year_level_observations"] == (
        {"seasonal_year": 2022, "forward_return": pytest.approx(0.10), "raw_match_count": 1},
    )
    assert signal.confidence == 0.0
    assert signal.validity is SignalValidity.INSUFFICIENT_DATA
    assert signal.action is ActionIntent.ABSTAIN


def test_one_year_is_not_actionable_under_default_evidence_settings() -> None:
    snapshot = _snapshot(
        date(2024, 9, 11),
        _overlapping_observations({2023: 0.10}, offsets=tuple(range(-7, 8))),
    )

    signal = SeasonalityAgent().analyze(snapshot, AgentContext(run_id="default-one-year"))

    assert signal.validity is SignalValidity.INSUFFICIENT_DATA
    assert signal.action is ActionIntent.ABSTAIN
    assert signal.confidence == 0.0
    assert signal.metadata["independent_year_count"] == 1


def test_duplicating_one_years_matches_does_not_increase_confidence() -> None:
    yearly = {2021: 0.10, 2022: 0.10, 2023: 0.10}
    baseline = _signal(
        _overlapping_observations(yearly),
        evaluated=date(2024, 9, 11),
        horizon_days=30,
        minimum_independent_years=3,
    )
    duplicated_observations = (
        *_overlapping_observations({2021: 0.10, 2022: 0.10}),
        *_overlapping_observations({2023: 0.10}, offsets=tuple(range(-7, 8))),
    )
    duplicated = _signal(
        duplicated_observations,
        evaluated=date(2024, 9, 11),
        tolerance_days=7,
        horizon_days=30,
        minimum_independent_years=3,
    )

    assert duplicated.metadata["raw_match_count"] > baseline.metadata["raw_match_count"]
    assert duplicated.metadata["independent_year_count"] == 3
    assert duplicated.confidence == baseline.confidence
    assert duplicated.metadata["stability"] == baseline.metadata["stability"]


def test_consistent_independent_years_increase_confidence_gradually() -> None:
    two_years = _signal(
        _overlapping_observations({2023: 0.10, 2024: 0.10}),
        evaluated=date(2025, 9, 11),
        horizon_days=30,
        minimum_independent_years=2,
    )
    five_years = _signal(
        _overlapping_observations({year: 0.10 for year in range(2020, 2025)}),
        evaluated=date(2025, 9, 11),
        horizon_days=30,
        minimum_independent_years=2,
    )

    assert 0.0 < two_years.confidence < five_years.confidence < 1.0
    assert two_years.confidence < 0.20
    assert five_years.confidence < 0.50


def test_conflicting_years_reduce_stability_and_confidence() -> None:
    consistent = _signal(
        _overlapping_observations({year: 0.10 for year in range(2020, 2024)}),
        horizon_days=30,
        minimum_independent_years=3,
    )
    conflicting = _signal(
        _overlapping_observations(
            {2020: 0.10, 2021: 0.10, 2022: -0.10, 2023: -0.10}
        ),
        horizon_days=30,
        minimum_independent_years=3,
    )

    assert conflicting.metadata["stability"] < consistent.metadata["stability"]
    assert conflicting.confidence < consistent.confidence


def test_correlated_noise_from_one_year_cannot_become_confident() -> None:
    returns = tuple(0.20 if index % 2 else -0.15 for index in range(15))
    observations: list[tuple[date, float]] = []
    anchor = date(2023, 9, 11)
    for offset, forward_return in zip(range(-7, 8), returns, strict=True):
        entry = anchor + timedelta(days=offset)
        observations.extend(
            ((entry, 100.0), (entry + timedelta(days=30), 100.0 * (1 + forward_return)))
        )
    signal = _signal(
        tuple(observations),
        tolerance_days=7,
        horizon_days=30,
        prior_years=1,
        minimum_independent_years=1,
    )

    assert signal.metadata["raw_match_count"] == 15
    assert signal.metadata["independent_year_count"] == 1
    assert signal.confidence == 0.0
    assert signal.action is ActionIntent.ABSTAIN


def test_missing_endpoints_are_explicit_and_reduce_usable_years() -> None:
    observations = (
        *_overlapping_observations({2022: 0.10}),
        (date(2023, 9, 11), 100.0),
    )
    signal = _signal(
        observations,
        horizon_days=30,
        minimum_independent_years=2,
    )

    assert signal.metadata["candidate_match_count"] == 2
    assert signal.metadata["usable_match_count"] == 1
    assert signal.metadata["excluded_match_count"] == 1
    assert signal.metadata["candidate_independent_year_count"] == 2
    assert signal.metadata["independent_year_count"] == 1
    assert signal.metadata["exclusion_reason_counts"] == {"missing_horizon_endpoint": 1}
    assert signal.metadata["excluded_matches"][0]["exclusion_reason"] == (
        "missing_horizon_endpoint"
    )


def test_missing_losing_year_cannot_add_evidence_strength() -> None:
    surviving = _signal(
        _overlapping_observations({2021: 0.10, 2022: 0.10, 2023: 0.10}),
        horizon_days=30,
        minimum_independent_years=3,
    )
    missing_loser = _signal(
        (
            (date(2020, 9, 11), 100.0),
            *_overlapping_observations({2021: 0.10, 2022: 0.10, 2023: 0.10}),
        ),
        horizon_days=30,
        minimum_independent_years=3,
    )

    assert missing_loser.metadata["candidate_independent_year_count"] == 4
    assert missing_loser.metadata["independent_year_count"] == 3
    assert missing_loser.metadata["sample_strength"] == surviving.metadata["sample_strength"]
    assert missing_loser.confidence == surviving.confidence


def test_finite_price_ratio_overflow_is_excluded_without_crashing() -> None:
    signal = _signal(
        (
            (date(2023, 9, 11), 1e-308),
            (date(2023, 10, 11), 1e308),
        ),
        horizon_days=30,
        prior_years=1,
        minimum_independent_years=1,
    )

    assert signal.validity is SignalValidity.INSUFFICIENT_DATA
    assert signal.metadata["raw_match_count"] == 1
    assert signal.metadata["usable_match_count"] == 0
    assert signal.metadata["independent_year_count"] == 0
    assert signal.metadata["sample_forward_returns"] == ()
    assert signal.metadata["year_level_observations"] == ()
    assert signal.metadata["exclusion_reason_counts"] == {"non_finite_forward_return": 1}
