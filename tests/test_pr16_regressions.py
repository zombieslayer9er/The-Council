"""Reproductions for Devin's follow-up review of issue #15 / PR #16."""

import asyncio
import runpy
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event

import httpx
import pytest

from botnet_council.adapters.freqtrade import CouncilDecisionStrategyAdapter
from botnet_council.api import create_app
from botnet_council.backtest import FreqtradeBacktestEngine
from botnet_council.context import ContextService
from botnet_council.context.service import ContextProviderError
from botnet_council.experiments import ExperimentService, InMemoryExperimentRepository
from botnet_council.learning import TeacherConfig
from botnet_council.learning.teacher import evaluate_profile
from botnet_council.schemas import ActionIntent, Direction, MarketSnapshot
from botnet_council.telemetry.serializers import experience_summary

ROOT = Path(__file__).resolve().parents[1]
L = runpy.run_path(str(ROOT / "tests/test_learning.py"))
F = runpy.run_path(str(ROOT / "tests/test_freqtrade_engine.py"))
C = runpy.run_path(str(ROOT / "tests/test_context.py"))
E = runpy.run_path(str(ROOT / "tests/test_experiments.py"))


def test_standalone_strategy_rejects_forged_entry_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    import sys
    from types import ModuleType

    pandas = ModuleType("pandas")
    pandas.Timestamp = lambda value: None
    pandas.DataFrame = object
    strategy = ModuleType("freqtrade.strategy")
    strategy.IStrategy = object
    monkeypatch.setitem(sys.modules, "pandas", pandas)
    monkeypatch.setitem(sys.modules, "freqtrade.strategy", strategy)
    namespace = runpy.run_path(
        str(ROOT / "integrations/freqtrade/strategies/CouncilSignalStrategy.py")
    )
    artifact = tmp_path / "forged.json"
    artifact.write_text(
        json.dumps(
            {
                "adapter_id": "council-decision-signals",
                "adapter_version": "1.3",
                "signals": [
                    {
                        "pair": "TEST/USD",
                        "candle_at": "2026-01-01T00:00:00Z",
                        "decided_at": "2026-01-01T01:00:00Z",
                        "source_as_of": "2026-01-01T01:00:00Z",
                        "timeframe": "1h",
                        "signal_tag": "target_exposure",
                        "enter_long": True,
                        "enter_short": False,
                        "exit_long": False,
                        "exit_short": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    instance = namespace["CouncilSignalStrategy"]()
    instance.config = {"botnet_council_signal_artifact": str(artifact)}
    with pytest.raises(ValueError, match="sizing"):
        _ = instance._signals


@pytest.mark.parametrize("action", [ActionIntent.NO_ACTION, ActionIntent.ABSTAIN])
def test_non_actionable_decisions_emit_no_commands(action: ActionIntent) -> None:
    original = L["learning_episode"](12).evidence.council_decision
    values = original.model_dump(mode="python", warnings=False)
    values.update(
        action=action,
        target_exposure=None,
        forecast_direction=Direction.SHORT,
        expected_return=-0.02,
        decision_id="",
    )
    decision = type(original).model_validate(values)
    row = CouncilDecisionStrategyAdapter().translate(
        (decision,),
        candle_open_by_decision_id={
            decision.decision_id: decision.source_as_of - timedelta(hours=1)
        },
    )[0]
    assert not any((row.enter_long, row.enter_short, row.exit_long, row.exit_short))


def test_nonzero_reduce_only_requires_position_context() -> None:
    original = L["learning_episode"](12).evidence.council_decision
    values = original.model_dump(mode="python", warnings=False)
    values.update(
        action=ActionIntent.REDUCE_ONLY,
        target_exposure=0.25,
        forecast_direction=Direction.LONG,
        expected_return=0.02,
        decision_id="",
    )
    decision = type(original).model_validate(values)
    with pytest.raises(ValueError, match="position"):
        CouncilDecisionStrategyAdapter().translate(
            (decision,),
            candle_open_by_decision_id={
                decision.decision_id: decision.source_as_of - timedelta(hours=1)
            },
        )


def test_native_runner_receives_absolute_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    request = F["request"](Path("."), L["BASE"])

    class PathsRunner(F["FakeRunner"]):
        def run(self, command, *, cwd, timeout):
            if "backtesting" in command:
                for flag in ("--config", "--datadir", "--strategy-path", "--backtest-directory"):
                    assert Path(command[command.index(flag) + 1]).is_absolute(), flag
            return super().run(command, cwd=cwd, timeout=timeout)

    FreqtradeBacktestEngine(runner=PathsRunner(F["result_payload"](L["BASE"]))).run(request)


def test_skipped_overlap_cannot_change_any_scoring_metric() -> None:
    episodes = tuple(L["learning_episode"](hour) for hour in (12, 13, 14))
    current, proposal = L["librarian_proposal"]()
    from botnet_council.learning.profiles import apply_changes

    candidate = apply_changes(
        current,
        proposal.changes,
        created_at=proposal.created_at,
        scoring_version="teacher-score-v2",
    )
    expected = evaluate_profile(candidate, (episodes[0], episodes[2]), TeacherConfig())
    actual = evaluate_profile(candidate, episodes, TeacherConfig())
    assert actual == expected


def test_context_source_revision_mismatch_is_never_cached(
    rising_snapshot: MarketSnapshot,
    as_of: datetime,
) -> None:
    provider = C["FakeContextProvider"](C["datum"](as_of), source_version="different-version")
    service = ContextService((provider,))
    for _ in range(2):
        with pytest.raises(ContextProviderError, match="version"):
            service.enrich(rising_snapshot, C["request"](as_of))
    assert provider.calls == 2


def test_concurrent_context_misses_share_one_fetch(
    rising_snapshot: MarketSnapshot,
    as_of: datetime,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep

    provider = C["FakeContextProvider"](C["datum"](as_of))
    original = provider.fetch

    def slow_fetch(request):
        sleep(0.05)
        return original(request)

    provider.fetch = slow_fetch
    service = ContextService((provider,))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: service.enrich(rising_snapshot, C["request"](as_of)), range(4))
        )
    assert provider.calls == 1
    assert all(result == results[0] for result in results)


def test_oracle_failure_keeps_lifecycle_monotonic(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ExperimentService(
        E["_provider"](tuple(100.0 + i for i in range(10))), InMemoryExperimentRepository()
    )
    record = service.create(E["_request"]())

    def fail(request):
        raise RuntimeError("synthetic provider failure")

    monkeypatch.setattr(service._oracle, "outcome", fail)
    failed = service.run(record.experiment_id)
    times = [event.occurred_at for event in failed.lifecycle]
    assert times == sorted(times)
    assert times[-1] == record.request.horizon_end


def test_blocked_experiment_does_not_block_health(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ExperimentService(
        E["_provider"](tuple(100.0 + i for i in range(10))), InMemoryExperimentRepository()
    )
    record = service.create(E["_request"]())
    entered, release, finished = Event(), Event(), Event()
    run = service.run

    def blocked(identifier):
        entered.set()
        release.wait(2)
        finished.set()
        return run(identifier)

    monkeypatch.setattr(service, "run", blocked)
    app = create_app(experiment_service=service, command_token=E["CONTROL_TOKEN"])

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            task = asyncio.create_task(
                client.post(
                    f"/api/control/experiments/{record.experiment_id}/run",
                    headers=E["CONTROL_HEADERS"],
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                response = await client.get("/api/health")
                assert response.status_code == 200
                assert not finished.is_set(), "health waited for blocking experiment work"
            finally:
                release.set()
                await task

    asyncio.run(check())


def test_experience_summary_exposes_exact_origin() -> None:
    episode = L["base_episode"](12)
    assert (
        experience_summary(episode).model_dump()["backtest_run_id"]
        == episode.evidence.backtest_run_id
    )


def test_teacher_minimum_counts_only_non_overlapping_trials() -> None:
    from botnet_council.learning import Teacher

    current, proposal = L["librarian_proposal"]()
    episodes = tuple(L["learning_episode"](hour) for hour in range(12, 18))
    with pytest.raises(ValueError, match="insufficient non-overlapping"):
        Teacher(TeacherConfig(minimum_held_out_episodes=4)).evaluate(
            current, proposal, episodes, evaluated_at=L["BASE"] + timedelta(hours=25)
        )


def test_fractional_targets_are_not_silently_binary_trades() -> None:
    decision = L["base_episode"](12).evidence.council_decision
    assert 0 < decision.target_exposure < 1
    with pytest.raises(ValueError, match="sizing"):
        CouncilDecisionStrategyAdapter().translate(
            (decision,),
            candle_open_by_decision_id={
                decision.decision_id: decision.source_as_of - timedelta(hours=1)
            },
        )


def test_teacher_has_at_most_three_balanced_validation_slices() -> None:
    from botnet_council.learning.teacher import _slice_returns

    values = _slice_returns([0.01] * 8)
    assert values == pytest.approx((1.01**3 - 1, 1.01**3 - 1, 1.01**2 - 1))


def test_external_export_requires_period_and_capital_binding(tmp_path: Path) -> None:
    from botnet_council.backtest import FreqtradeArtifactError

    payload = F["result_payload"](L["BASE"])
    strategy = payload["strategy"]["CouncilStrategy"]
    for key in ("backtest_start_ts", "backtest_end_ts", "timeframe"):
        strategy.pop(key, None)
    with pytest.raises(FreqtradeArtifactError, match="period"):
        FreqtradeBacktestEngine(runner=F["FakeRunner"](payload)).run(
            F["request"](tmp_path, L["BASE"])
        )


def test_librarian_never_scores_a_different_signal_horizon() -> None:
    from botnet_council.council import DeterministicCouncil
    from botnet_council.experience import DecisionEvidence, ExperienceEpisode
    from botnet_council.learning import Librarian, LibrarianConfig, WeightScope

    episodes = []
    for hour in (4, 6, 8, 10):
        original = L["learning_episode"](hour)
        evidence = original.evidence
        signals = tuple(
            signal.model_copy(update={"horizon_bars": 4}) if signal.agent_id == "bad" else signal
            for signal in evidence.specialist_outputs
        )
        values = {name: getattr(evidence, name) for name in type(evidence).model_fields}
        values.update(
            specialist_outputs=signals,
            council_decision=DeterministicCouncil(evidence.council_config).aggregate(
                evidence.snapshot, signals
            ),
        )
        episodes.append(
            ExperienceEpisode(evidence=DecisionEvidence(**values), truth=original.truth)
        )
    proposal = Librarian(LibrarianConfig(minimum_samples=2)).propose(
        L["profile"](),
        episodes,
        scope=WeightScope(),
        training_cutoff=L["BASE"] + timedelta(hours=14),
        created_at=L["BASE"] + timedelta(hours=14),
    )
    assert all(change.agent_id != "bad" for change in proposal.changes)
