from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from botnet_council.council import CouncilConfig, DeterministicCouncil
from botnet_council.experience import (
    AgentVersion,
    AppliedWeight,
    DecisionEvidence,
    ExperienceEpisode,
    OutcomeTruth,
    episode_from_experiment,
)
from botnet_council.experiments import (
    ExperimentRequest,
    ExperimentService,
    InMemoryExperimentRepository,
)
from botnet_council.experiments.models import ExperimentAgentConfig
from botnet_council.learning import (
    AdaptiveWeight,
    Librarian,
    LibrarianConfig,
    ScopedAgentWeight,
    Teacher,
    TeacherConfig,
    TeacherDecision,
    WeightProfile,
    WeightProfileStore,
    WeightProposal,
    WeightScope,
)
from botnet_council.market_data import (
    Asset,
    InMemoryHistoricalProvider,
    Instrument,
    ProviderId,
    Timeframe,
)
from botnet_council.schemas import (
    ActionIntent,
    AgentSignal,
    Direction,
    MarketBar,
    MarketSnapshot,
    SignalType,
    SignalValidity,
)

BASE = datetime(2024, 1, 1, tzinfo=UTC)
INSTRUMENT = Instrument(base=Asset.BTC, quote=Asset.USD)


def base_episode(evaluation_hour: int) -> ExperienceEpisode:
    bars = tuple(
        MarketBar(
            opened_at=BASE + index * timedelta(hours=1),
            closed_at=BASE + (index + 1) * timedelta(hours=1),
            available_at=BASE + (index + 1) * timedelta(hours=1),
            open=100.0 + index,
            high=102.0 + index,
            low=99.0 + index,
            close=101.0 + index,
            volume=1.0,
        )
        for index in range(30)
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
        random_seed=1,
    )
    service = ExperimentService(provider, InMemoryExperimentRepository())
    record = service.run(service.create(request).experiment_id)
    return episode_from_experiment(record, asset_class="crypto", regime="bull")


def learning_episode(evaluation_hour: int, *, realized_positive: bool = True) -> ExperienceEpisode:
    source = base_episode(evaluation_hour)
    snapshot = source.evidence.snapshot
    signals = (
        _signal("bad", Direction.SHORT, -0.02, -1.0, snapshot),
        _signal("good", Direction.LONG, 0.02, 1.0, snapshot),
    )
    config = CouncilConfig(
        agent_weights={"good": 1.0, "bad": 1.0},
        minimum_confidence=0.0,
        minimum_conviction=0.0,
    )
    decision = DeterministicCouncil(config).aggregate(snapshot, signals)
    values = source.evidence.model_dump(mode="python", warnings=False)
    values.update(
        {
            "specialist_outputs": signals,
            "agent_versions": (
                AgentVersion(agent_id="bad", version="1"),
                AgentVersion(agent_id="good", version="1"),
            ),
            "council_config": config,
            "applied_weights": (
                AppliedWeight(agent_id="good", weight=1.0),
                AppliedWeight(agent_id="bad", weight=1.0),
            ),
            "council_decision": decision,
        }
    )
    evidence = DecisionEvidence.model_validate(values)
    assert source.truth is not None
    truth = source.truth
    if not realized_positive:
        oracle = truth.oracle_outcome.model_copy(
            update={
                "realized_return": -abs(truth.oracle_outcome.realized_return or 0.01),
                "realized_direction": Direction.SHORT,
            }
        )
        judge = truth.judge_evaluation.model_copy(
            update={
                "realized_return": oracle.realized_return,
                "realized_direction": Direction.SHORT,
                "directional_correctness": False,
            }
        )
        truth = OutcomeTruth(
            oracle_outcome=oracle,
            judge_evaluation=judge,
            available_at=truth.available_at,
        )
    return ExperienceEpisode(evidence=evidence, truth=truth)


def _signal(
    agent_id: str,
    direction: Direction,
    expected_return: float,
    target_exposure: float,
    snapshot: MarketSnapshot,
) -> AgentSignal:
    return AgentSignal(
        schema_version="1.1",
        agent_id=agent_id,
        agent_version="1",
        signal_type=SignalType.ALPHA,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        source_snapshot_id=snapshot.snapshot_id,
        source_as_of=snapshot.as_of,
        forecast_direction=direction,
        expected_return=expected_return,
        target_exposure=target_exposure,
        action=ActionIntent.TARGET_EXPOSURE,
        validity=SignalValidity.VALID,
        confidence=1.0,
        horizon_bars=2,
        generated_at=snapshot.observed_at,
        expires_at=snapshot.observed_at + timedelta(hours=1),
        rationale="controlled learning fixture",
    )


def profile() -> WeightProfile:
    scope = WeightScope()
    return WeightProfile(
        generation=0,
        generation_id="weights-v0000",
        created_at=BASE,
        entries=(
            ScopedAgentWeight(
                agent_id="good",
                scope=scope,
                weight=AdaptiveWeight(long_term=1.0, recent=1.0),
            ),
            ScopedAgentWeight(
                agent_id="bad",
                scope=scope,
                weight=AdaptiveWeight(long_term=1.0, recent=1.0),
            ),
        ),
        scoring_version="teacher-score-v1",
    )


def librarian_proposal() -> tuple[WeightProfile, WeightProposal]:
    current = profile()
    training = tuple(learning_episode(hour) for hour in range(4, 10))
    proposal = Librarian(
        LibrarianConfig(
            maximum_weight_delta=0.2,
            minimum_samples=4,
            full_confidence_samples=4,
            recent_window=4,
        )
    ).propose(
        current,
        training,
        scope=WeightScope(),
        training_cutoff=BASE + timedelta(hours=12),
        created_at=BASE + timedelta(hours=12),
    )
    return current, proposal


def test_librarian_proposes_bounded_slow_and_fast_changes_without_mutation() -> None:
    current, proposal = librarian_proposal()

    changes = {item.agent_id: item for item in proposal.changes}
    assert current == profile()
    assert changes["good"].proposed.long_term == pytest.approx(1.2)
    assert changes["bad"].proposed.long_term == pytest.approx(0.8)
    assert changes["good"].proposed.recent == pytest.approx(1.2)
    assert all(
        abs(item.proposed.long_term - item.current.long_term) <= 0.2
        for item in proposal.changes
    )
    assert len(proposal.training_episode_ids) == 6


def test_teacher_accepts_held_out_improvement_deterministically() -> None:
    current, proposal = librarian_proposal()
    held_out = tuple(learning_episode(hour) for hour in range(12, 18))
    teacher = Teacher(
        TeacherConfig(minimum_held_out_episodes=4, minimum_score_improvement=0.0)
    )

    first = teacher.evaluate(
        current, proposal, held_out, evaluated_at=BASE + timedelta(hours=25)
    )
    repeated = teacher.evaluate(
        current, proposal, reversed(held_out), evaluated_at=BASE + timedelta(hours=25)
    )

    assert first == repeated
    assert first.decision is TeacherDecision.ACCEPT
    assert first.comparison.proposed.score > first.comparison.baseline.score
    assert first.accepted_changes == proposal.changes


def test_teacher_rejects_overfit_proposal_and_profile_store_cannot_promote_it(
    tmp_path: Path,
) -> None:
    current, proposal = librarian_proposal()
    held_out = tuple(
        learning_episode(hour, realized_positive=False) for hour in range(12, 18)
    )
    result = Teacher(
        TeacherConfig(minimum_held_out_episodes=4, minimum_score_improvement=0.0)
    ).evaluate(current, proposal, held_out, evaluated_at=BASE + timedelta(hours=25))
    store = WeightProfileStore(tmp_path / "profiles")
    store.initialize(current)

    assert result.decision is TeacherDecision.REJECT
    with pytest.raises(PermissionError, match="rejected"):
        store.promote(current, proposal, result)
    assert store.active() == current
    assert store.list_reviews()[0].proposal == proposal
    assert store.list_reviews()[0].result == result


def test_only_accepted_teacher_result_creates_generation_and_rollback_preserves_history(
    tmp_path: Path,
) -> None:
    current, proposal = librarian_proposal()
    held_out = tuple(learning_episode(hour) for hour in range(12, 18))
    result = Teacher(
        TeacherConfig(minimum_held_out_episodes=4, minimum_score_improvement=0.0)
    ).evaluate(current, proposal, held_out, evaluated_at=BASE + timedelta(hours=25))
    store = WeightProfileStore(tmp_path / "profiles")
    store.initialize(current)

    promoted = store.promote(current, proposal, result)

    assert promoted.generation_id == "weights-v0001"
    assert promoted.parent_generation_id == "weights-v0000"
    assert store.active() == promoted
    assert tuple(item.generation_id for item in store.list()) == (
        "weights-v0000",
        "weights-v0001",
    )
    assert store.rollback("weights-v0000") == current
    assert store.active() == current
    assert store.get("weights-v0001") == promoted
    assert store.list_reviews()[0].proposal == proposal
    assert store.list_reviews()[0].result == result


def test_teacher_enforces_temporal_holdout_and_ground_truth_availability() -> None:
    current, proposal = librarian_proposal()
    training_episode = learning_episode(10)
    future_truth = learning_episode(12)
    teacher = Teacher(TeacherConfig(minimum_held_out_episodes=2))

    with pytest.raises(ValueError, match="must not precede"):
        teacher.evaluate(
            current,
            proposal,
            (training_episode, learning_episode(13)),
            evaluated_at=BASE + timedelta(hours=25),
        )
    with pytest.raises(ValueError, match="unavailable"):
        teacher.evaluate(
            current,
            proposal,
            (future_truth, learning_episode(13)),
            evaluated_at=BASE + timedelta(hours=13),
        )


def test_scoped_profile_prefers_more_specific_rule_and_blends_recent_weight() -> None:
    scoped = WeightProfile(
        generation=0,
        generation_id="weights-v0000",
        created_at=BASE,
        entries=(
            ScopedAgentWeight(
                agent_id="good",
                weight=AdaptiveWeight(long_term=1.0, recent=1.0),
            ),
            ScopedAgentWeight(
                agent_id="good",
                scope=WeightScope(symbol="BTC/USD", regime="bull"),
                weight=AdaptiveWeight(long_term=1.0, recent=2.0, recent_mix=0.25),
            ),
        ),
        scoring_version="teacher-score-v1",
    )

    resolved = scoped.resolve(
        asset_class="crypto", symbol="BTC/USD", regime="bull", horizon_bars=2
    )

    assert resolved["good"] == pytest.approx(1.25)
