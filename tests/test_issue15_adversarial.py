"""Regression invariants from the issue 6 adversarial audit and issue 15 patch.

Run explicitly: python -m pytest tests/test_issue15_adversarial.py -v
Production files are not changed by these probes.
"""

import runpy
from datetime import timedelta
from pathlib import Path

import pytest

from botnet_council.experience import DecisionEvidence, ExperienceEpisode
from botnet_council.learning import Teacher, TeacherConfig, WeightProfileStore, WeightProposal

H = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests/test_learning.py"))


def teacher():
    return Teacher(TeacherConfig(minimum_held_out_episodes=4, minimum_score_improvement=0.0))


def repeated_trial(episode, run_id):
    values = {name: getattr(episode.evidence, name) for name in type(episode.evidence).model_fields}
    values["backtest_run_id"] = run_id
    return ExperienceEpisode(evidence=DecisionEvidence(**values), truth=episode.truth)


def test_equivalent_reruns_cannot_satisfy_independent_holdout_minimum():
    base, proposal = H["librarian_proposal"]()
    episode = H["learning_episode"](12)
    trials = tuple(repeated_trial(episode, f"rerun-{i}") for i in range(8))
    assert len({e.episode_id for e in trials}) == 8
    assert len({e.equivalence_id for e in trials}) == 1
    with pytest.raises(ValueError):
        teacher().evaluate(base, proposal, trials, evaluated_at=H["BASE"] + timedelta(hours=25))


def test_proposal_cannot_be_evaluated_before_it_exists():
    base, proposal = H["librarian_proposal"]()
    values = {name: getattr(proposal, name) for name in type(proposal).model_fields}
    values.update(proposal_id="", created_at=H["BASE"] + timedelta(days=100))
    future = WeightProposal(**values)
    with pytest.raises(ValueError):
        teacher().evaluate(
            base,
            future,
            tuple(H["learning_episode"](i) for i in range(12, 24, 2)),
            evaluated_at=H["BASE"] + timedelta(hours=25),
        )


def test_new_promotion_after_rollback_preserves_old_generation(tmp_path):
    base, proposal = H["librarian_proposal"]()
    episodes = tuple(H["learning_episode"](i) for i in range(12, 24, 2))
    first = teacher().evaluate(
        base, proposal, episodes, evaluated_at=H["BASE"] + timedelta(hours=25)
    )
    second = teacher().evaluate(
        base, proposal, episodes, evaluated_at=H["BASE"] + timedelta(hours=26)
    )
    store = WeightProfileStore(tmp_path)
    store.initialize(base)
    old = store.promote(base, proposal, first)
    store.rollback(base.generation_id)
    new = store.promote(base, proposal, second)
    assert new.generation_id != old.generation_id
    assert store.get(old.generation_id) == old


def test_exact_duplicate_holdout_ids_are_rejected():
    base, proposal = H["librarian_proposal"]()
    episode = H["learning_episode"](12)
    with pytest.raises(ValueError):
        teacher().evaluate(
            base, proposal, (episode,) * 8, evaluated_at=H["BASE"] + timedelta(hours=25)
        )


def test_input_order_does_not_change_teacher_result():
    base, proposal = H["librarian_proposal"]()
    episodes = tuple(H["learning_episode"](i) for i in range(12, 24, 2))
    at = H["BASE"] + timedelta(hours=25)
    assert teacher().evaluate(base, proposal, episodes, evaluated_at=at) == teacher().evaluate(
        base, proposal, reversed(episodes), evaluated_at=at
    )


F = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests/test_freqtrade_engine.py"))


def test_success_without_new_export_cannot_reuse_previous_result(tmp_path):
    from botnet_council.backtest import FreqtradeArtifactError, FreqtradeBacktestEngine
    from botnet_council.backtest.freqtrade import ProcessResult

    request = F["request"](tmp_path, H["BASE"])
    FreqtradeBacktestEngine(runner=F["FakeRunner"](F["result_payload"](H["BASE"]))).run(request)

    class NoExport:
        def run(self, command, **kwargs):
            return ProcessResult(0, "Freqtrade 2026.8" if "--version" in command else "", "")

    with pytest.raises(FreqtradeArtifactError):
        FreqtradeBacktestEngine(runner=NoExport()).run(request)


def test_external_result_from_future_period_is_rejected(tmp_path):
    from botnet_council.backtest import FreqtradeArtifactError, FreqtradeBacktestEngine

    request = F["request"](tmp_path, H["BASE"])
    payload = F["result_payload"](H["BASE"] + timedelta(days=365))
    with pytest.raises(FreqtradeArtifactError):
        FreqtradeBacktestEngine(runner=F["FakeRunner"](payload)).run(request)


def test_equivalent_reruns_do_not_create_full_librarian_confidence():
    from botnet_council.learning import Librarian, WeightScope

    episode = H["learning_episode"](4)
    result = Librarian().propose(
        H["profile"](),
        tuple(repeated_trial(episode, f"rerun-{i}") for i in range(40)),
        scope=WeightScope(),
        training_cutoff=H["BASE"] + timedelta(hours=12),
        created_at=H["BASE"] + timedelta(hours=12),
    )
    assert result.changes == ()  # One economic observation is below minimum_samples=8.


def test_overlapping_horizons_are_not_compounded_as_independent_trades():
    from botnet_council.learning.profiles import apply_changes
    from botnet_council.learning.teacher import evaluate_profile

    base, proposal = H["librarian_proposal"]()
    candidate = apply_changes(
        base,
        proposal.changes,
        created_at=H["BASE"] + timedelta(hours=12),
        scoring_version="teacher-score-v1",
    )
    episodes = tuple(H["learning_episode"](i) for i in range(12, 18))
    assert episodes[0].truth.oracle_outcome.horizon_end > episodes[1].evidence.decision_timestamp
    # The fix selects a non-overlapping ledger rather than rejecting the whole input.
    expected = evaluate_profile(candidate, episodes[::2], TeacherConfig())
    assert evaluate_profile(candidate, episodes, TeacherConfig()) == expected


def test_recurrence_rejects_future_snapshot_bars():
    from botnet_council.schemas import MarketSnapshot

    r = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "tests/test_historical_recurrence.py")
    )
    snapshot = r["annual_snapshot"]()
    with pytest.raises(ValueError):
        MarketSnapshot(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            as_of=snapshot.bars[-1].opened_at,
            observed_at=snapshot.as_of,
            bars=snapshot.bars,
        )


def test_recurrence_order_changes_fail_explicitly():
    from botnet_council.schemas import MarketSnapshot

    r = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "tests/test_historical_recurrence.py")
    )
    snapshot = r["annual_snapshot"]()
    with pytest.raises(ValueError):
        MarketSnapshot(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            as_of=snapshot.as_of,
            observed_at=snapshot.observed_at,
            bars=tuple(reversed(snapshot.bars)),
        )


def test_future_decision_cannot_be_mapped_to_an_arbitrarily_old_candle():
    from botnet_council.adapters.freqtrade import CouncilDecisionStrategyAdapter

    decision = H["learning_episode"](12).evidence.council_decision
    with pytest.raises(ValueError):
        CouncilDecisionStrategyAdapter().translate(
            (decision,),
            candle_open_by_decision_id={
                decision.decision_id: decision.source_as_of - timedelta(days=365)
            },
        )
