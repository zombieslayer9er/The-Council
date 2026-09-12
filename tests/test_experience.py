import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from botnet_council.council import CouncilConfig, DeterministicCouncil
from botnet_council.experience import (
    CacheWriteStatus,
    CouncilReplay,
    EpisodeQuery,
    ExperienceCorruptionError,
    ExperienceEpisode,
    ExperienceStore,
    IncompatibleExperienceStoreError,
    OutcomeTruth,
    episode_from_experiment,
)
from botnet_council.experiments import (
    ExperimentRequest,
    ExperimentService,
    InMemoryExperimentRepository,
)
from botnet_council.experiments.models import ExperimentAgentConfig, ExperimentRecord
from botnet_council.market_data import (
    Asset,
    InMemoryHistoricalProvider,
    Instrument,
    ProviderId,
    Timeframe,
)
from botnet_council.schemas import MarketBar

BASE = datetime(2024, 1, 1, tzinfo=UTC)
INSTRUMENT = Instrument(base=Asset.BTC, quote=Asset.USD)


def completed_experiment(evaluation_hour: int = 4) -> ExperimentRecord:
    prices = tuple(90.0 + index * 5 for index in range(20))
    bars = tuple(
        MarketBar(
            opened_at=BASE + index * timedelta(hours=1),
            closed_at=BASE + (index + 1) * timedelta(hours=1),
            available_at=BASE + (index + 1) * timedelta(hours=1),
            open=price,
            high=price + 1.0,
            low=price - 1.0,
            close=price,
            volume=1.0,
        )
        for index, price in enumerate(prices)
    )
    provider = InMemoryHistoricalProvider(
        instrument=INSTRUMENT,
        timeframe=Timeframe.HOUR_1,
        bars=bars,
        fetched_at=BASE + timedelta(days=2),
    )
    request = ExperimentRequest(
        instrument="BTC/USD",
        provider=ProviderId.IN_MEMORY,
        evaluation_time=BASE + timedelta(hours=evaluation_hour),
        forecast_horizon="2h",
        timeframe="1h",
        agents=(
            ExperimentAgentConfig(
                kind="trend", parameters={"fast_window": 2, "slow_window": 3}
            ),
        ),
        council=CouncilConfig(minimum_confidence=0.0, minimum_conviction=0.0),
        random_seed=7,
    )
    service = ExperimentService(provider, InMemoryExperimentRepository())
    return service.run(service.create(request).experiment_id)


def episode(evaluation_hour: int = 4) -> ExperienceEpisode:
    return episode_from_experiment(
        completed_experiment(evaluation_hour),
        weight_generation_id="weights-v0001",
        regime="bull",
    )


def test_episode_has_run_equivalence_and_decision_cache_identities() -> None:
    original = episode()
    other_evidence = original.evidence.model_copy(update={"backtest_run_id": "repeat-run"})
    repeated = ExperienceEpisode(evidence=other_evidence, truth=original.truth)

    assert original.episode_id != repeated.episode_id
    assert original.equivalence_id == repeated.equivalence_id
    assert original.decision_cache_key == repeated.decision_cache_key
    assert original.training_eligible is True


def test_store_is_immutable_idempotent_and_queryable(tmp_path: Path) -> None:
    store = ExperienceStore(tmp_path / "experience")
    value = episode()

    assert store.save(value) is CacheWriteStatus.STORED
    assert store.save(value) is CacheWriteStatus.HIT
    assert store.get(value.episode_id) == value
    assert store.query(EpisodeQuery(symbol="BTC/USD", regime="bull")) == (value,)
    assert store.query(EpisodeQuery(agent_id="trend", agent_version="1.0")) == (value,)
    assert store.query(EpisodeQuery(symbol="ETH/USD")) == ()
    assert store.cached_decisions("0" * 64) == ()
    assert store.cached_decisions(value.decision_cache_key)[0].episode_id == value.episode_id


def test_replay_excludes_truth_and_reuses_frozen_specialist_outputs(tmp_path: Path) -> None:
    store = ExperienceStore(tmp_path / "experience")
    value = episode()
    store.save(value)

    replay = store.replay(value.episode_id)
    reweighted = CouncilConfig(
        agent_weights={"trend": 0.5}, minimum_confidence=0.0, minimum_conviction=0.0
    )
    decision = store.reaggregate(value.episode_id, reweighted)

    assert "truth" not in CouncilReplay.model_fields
    assert replay.specialist_outputs == value.evidence.specialist_outputs
    assert decision == DeterministicCouncil(reweighted).aggregate(
        replay.snapshot, replay.specialist_outputs
    )


def test_temporal_split_never_trains_on_truth_unavailable_at_cutoff(tmp_path: Path) -> None:
    store = ExperienceStore(tmp_path / "experience")
    training = episode(4)
    held_out = episode(8)
    store.save(training)
    store.save(held_out)

    split = store.temporal_split(BASE + timedelta(hours=7))

    assert tuple(item.episode_id for item in split.training) == (training.episode_id,)
    assert tuple(item.episode_id for item in split.held_out) == (held_out.episode_id,)
    assert split.excluded_unavailable_truth == ()


def test_temporal_split_excludes_decision_with_late_truth(tmp_path: Path) -> None:
    store = ExperienceStore(tmp_path / "experience")
    original = episode(4)
    assert original.truth is not None
    delayed_truth = original.truth.model_copy(
        update={"available_at": BASE + timedelta(hours=8)}
    )
    delayed = ExperienceEpisode(evidence=original.evidence, truth=delayed_truth)
    store.save(delayed)

    split = store.temporal_split(BASE + timedelta(hours=7))

    assert split.training == ()
    assert split.held_out == ()
    assert split.excluded_unavailable_truth == (delayed.episode_id,)


def test_truth_cannot_be_available_before_horizon() -> None:
    value = episode()
    assert value.truth is not None

    with pytest.raises(ValidationError, match="before the outcome horizon"):
        OutcomeTruth(
            oracle_outcome=value.truth.oracle_outcome,
            judge_evaluation=value.truth.judge_evaluation,
            available_at=value.truth.oracle_outcome.horizon_end - timedelta(seconds=1),
        )


def test_corrupted_payload_is_detected(tmp_path: Path) -> None:
    root = tmp_path / "experience"
    store = ExperienceStore(root)
    value = episode()
    store.save(value)
    payload_path = root / "episodes" / f"{value.episode_id}.parquet"
    payload_path.write_bytes(b"not parquet")

    with pytest.raises(ExperienceCorruptionError, match="cannot read"):
        store.get(value.episode_id)


def test_incompatible_store_version_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "experience"
    ExperienceStore(root)
    with sqlite3.connect(root / "experience.sqlite3") as connection:
        connection.execute(
            "UPDATE metadata SET value = '99.0' WHERE key = 'schema_version'"
        )
        connection.commit()

    with pytest.raises(IncompatibleExperienceStoreError, match="unsupported"):
        ExperienceStore(root)
