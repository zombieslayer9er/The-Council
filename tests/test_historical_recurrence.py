import json
from datetime import UTC, date, datetime, time, timedelta

from botnet_council.agents import (
    HistoricalRecurrenceAgent,
    HistoricalRecurrenceEvidence,
    SeasonalityAgent,
)
from botnet_council.agents.factory import build_agents
from botnet_council.backtest import AgentConfig
from botnet_council.backtest.models import to_jsonable
from botnet_council.schemas import AgentContext, MarketBar, MarketSnapshot, SignalValidity


def annual_snapshot(
    *,
    first_year: int = 2015,
    current_year: int = 2026,
    missing_year: int | None = None,
    month: int = 1,
    day: int = 15,
) -> MarketSnapshot:
    bars: list[MarketBar] = []
    for year in range(first_year, current_year):
        anchor = date(year, month, min(day, 28) if month == 2 else day)
        start = anchor - timedelta(days=5)
        count = 8 if year == missing_year else 31
        for offset in range(count):
            opened = datetime.combine(start + timedelta(days=offset), time(), tzinfo=UTC)
            base = 100.0 + (year - first_year)
            close = base * (1.0 + 0.01 * offset)
            bars.append(
                MarketBar(
                    opened_at=opened,
                    closed_at=opened + timedelta(days=1),
                    available_at=opened + timedelta(days=1),
                    open=close,
                    high=close + 1.0,
                    low=close - 1.0,
                    close=close,
                    volume=1_000.0,
                )
            )
    try:
        as_of = datetime(current_year, month, day, tzinfo=UTC)
    except ValueError:
        as_of = datetime(current_year, month, 28, tzinfo=UTC)
    return MarketSnapshot(
        symbol="TEST/USD",
        timeframe="1d",
        as_of=as_of,
        observed_at=as_of,
        bars=tuple(bars),
    )


def evidence(signal_metadata: object) -> HistoricalRecurrenceEvidence:
    assert isinstance(signal_metadata, dict) or hasattr(signal_metadata, "items")
    return HistoricalRecurrenceEvidence.model_validate_json(
        json.dumps(to_jsonable(signal_metadata))
    )


def test_full_history_recurrence_preserves_independent_years_and_paths() -> None:
    snapshot = annual_snapshot()
    agent = HistoricalRecurrenceAgent(minimum_confidence=0.0)

    signal = agent.analyze(snapshot, AgentContext(run_id="recurrence"))
    result = evidence(signal.metadata["historical_recurrence"])
    selected = next(
        item for item in result.windows if item.horizon_days == result.selected_horizon_days
    )

    assert signal.validity is SignalValidity.VALID
    assert selected.total_annual_observations == 11
    assert selected.usable_observations == 11
    assert selected.positive_outcomes == 11
    assert selected.raw_positive_hit_ratio == 1.0
    assert len({item.annual_year for item in selected.observations}) == 11
    assert all(item.normalized_path[0] == 0.0 for item in selected.observations)
    assert selected.sample_count == len(selected.forward_return_distribution)
    assert selected.epochs


def test_incomplete_year_is_one_excluded_observation_not_a_reused_year() -> None:
    signal = HistoricalRecurrenceAgent(
        horizons_days=(10,), minimum_usable_years=3, confidence_sample_target=3,
        minimum_confidence=0.0,
    ).analyze(
        annual_snapshot(first_year=2018, missing_year=2022),
        AgentContext(run_id="incomplete"),
    )
    window = evidence(signal.metadata["historical_recurrence"]).windows[0]

    assert window.total_annual_observations == 8
    assert window.usable_observations == 7
    excluded = tuple(item for item in window.observations if item.status == "excluded")
    assert len(excluded) == 1
    assert excluded[0].annual_year == 2022
    assert excluded[0].exclusion_reason == "incomplete_horizon"


def test_small_sample_abstains_even_with_perfect_hit_rate() -> None:
    signal = HistoricalRecurrenceAgent(
        horizons_days=(1,), minimum_usable_years=5, confidence_sample_target=5
    ).analyze(
        annual_snapshot(first_year=2023),
        AgentContext(run_id="small-sample"),
    )

    assert signal.validity is SignalValidity.INSUFFICIENT_DATA
    assert signal.confidence == 0.0
    assert signal.expected_return is None


def test_recurrence_is_deterministic_and_causally_truncated() -> None:
    agent = HistoricalRecurrenceAgent(minimum_confidence=0.0)
    snapshot = annual_snapshot(first_year=2010)

    first = agent.analyze(snapshot, AgentContext(run_id="first"))
    repeated = agent.analyze(snapshot, AgentContext(run_id="second"))
    result = evidence(first.metadata["historical_recurrence"])

    assert first == repeated
    assert all(
        observation.annual_year < snapshot.as_of.year
        for window in result.windows
        for observation in window.observations
    )
    assert all(
        observation.end_date is None or observation.end_date < snapshot.as_of.date()
        for window in result.windows
        for observation in window.observations
    )


def test_regime_matching_and_similarity_are_optional_structured_evidence() -> None:
    snapshot = annual_snapshot(first_year=2018)
    years = range(2018, 2026)
    context = AgentContext(
        run_id="regime",
        parameters={
            "current_regime": "bull",
            "historical_regimes": {str(year): "bull" for year in years},
            "current_regime_features": {"volatility": 0.2},
            "historical_regime_features": {
                str(year): {"volatility": 0.2} for year in years
            },
        },
    )

    signal = HistoricalRecurrenceAgent(
        horizons_days=(1,), minimum_usable_years=3, confidence_sample_target=3,
        minimum_confidence=0.0,
    ).analyze(snapshot, context)
    window = evidence(signal.metadata["historical_recurrence"]).windows[0]

    assert window.regime_matched_sample_count == window.usable_observations
    assert window.regime_matched_hit_ratio == 1.0
    assert window.mean_regime_similarity == 1.0


def test_leap_day_maps_to_february_28_in_non_leap_years() -> None:
    snapshot = annual_snapshot(
        first_year=2018, current_year=2024, month=2, day=29
    )
    signal = HistoricalRecurrenceAgent(
        horizons_days=(1,), minimum_usable_years=3, confidence_sample_target=3,
        minimum_confidence=0.0,
    ).analyze(snapshot, AgentContext(run_id="leap"))
    observations = evidence(signal.metadata["historical_recurrence"]).windows[0].observations

    assert all(item.candidate_date.month == 2 for item in observations)
    assert all(
        item.candidate_date.day == 28
        for item in observations
        if item.annual_year not in {2020}
    )
    assert next(item for item in observations if item.annual_year == 2020).candidate_date.day == 29


def test_agent_factory_and_evidence_serialization_support_new_kind() -> None:
    configured = build_agents(
        (AgentConfig(kind="historical_recurrence", parameters={}),)
    )[0]
    signal = configured.analyze(
        annual_snapshot(first_year=2018), AgentContext(run_id="factory")
    )
    payload = evidence(signal.metadata["historical_recurrence"])

    assert isinstance(configured, HistoricalRecurrenceAgent)
    assert payload.schema_version == "1.0"
    assert HistoricalRecurrenceAgent is not SeasonalityAgent
