import json
import subprocess
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from botnet_council.agents import TrendAgent
from botnet_council.backtest import (
    AuthoritativeBacktestRequest,
    DockerComposeCommandRunner,
    EpisodeRecord,
    FreqtradeArtifactError,
    FreqtradeBacktestEngine,
    FreqtradeProcessError,
    FreqtradeUnavailableError,
    StrategyAdapterConfig,
    ValidationKind,
    ValidationStatus,
)
from botnet_council.backtest.freqtrade import ProcessResult
from botnet_council.context import MarketContext
from botnet_council.council import CouncilConfig, DeterministicCouncil
from botnet_council.schemas import AgentContext, MarketSnapshot


class FakeRunner:
    def __init__(self, payload: object | None = None, *, returncode: int = 0) -> None:
        self.payload = payload
        self.returncode = returncode
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: Sequence[str], *, cwd: Path, timeout: int) -> ProcessResult:
        del timeout
        self.commands.append(tuple(command))
        if "--version" in command:
            return ProcessResult(0, "Freqtrade 2026.8", "")
        if self.returncode:
            return ProcessResult(self.returncode, "", "safe failure")
        if "backtesting" in command:
            output = Path(command[command.index("--backtest-directory") + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / "result.json").write_text(json.dumps(self.payload), encoding="utf-8")
        elif "lookahead-analysis" in command:
            output = Path(command[command.index("--lookahead-analysis-exportfilename") + 1])
            output.write_text("filename,has_bias\nCouncilStrategy,Yes\n", encoding="utf-8")
        return ProcessResult(0, "analysis completed", "")


def request(tmp_path: Path, as_of: datetime) -> AuthoritativeBacktestRequest:
    strategy_path = tmp_path / "strategies"
    strategy_path.mkdir(exist_ok=True)
    data_path = tmp_path / "data"
    data_path.mkdir(exist_ok=True)
    return AuthoritativeBacktestRequest(
        instruments=("BTC/USD",),
        timeframe="5m",
        start=as_of - timedelta(days=1),
        end=as_of,
        starting_capital=10_000.0,
        fee_ratio=0.001,
        order_types={"entry": "market", "exit": "market"},
        strategy=StrategyAdapterConfig(
            adapter_id="council-signals",
            adapter_version="1",
            strategy_name="CouncilStrategy",
            strategy_path=strategy_path,
        ),
        dataset_id="fixture-v1",
        data_directory=data_path,
        artifact_directory=tmp_path / "artifacts",
        engine_configuration={"exchange_name": "kraken", "max_open_trades": 2},
    )


def result_payload(as_of: datetime) -> dict[str, object]:
    opened = as_of - timedelta(hours=2)
    closed = as_of - timedelta(hours=1)
    return {
        "strategy": {
            "CouncilStrategy": {
                "backtest_start_ts": (as_of - timedelta(days=1)).timestamp(),
                "backtest_end_ts": as_of.timestamp(),
                "timeframe": "5m",
                "starting_balance": 10_000.0,
                "final_balance": 10_098.0,
                "profit_total_abs": 98.0,
                "profit_total": 0.0098,
                "max_drawdown_account": 0.02,
                "daily_profit": [[closed.isoformat(), 98.0]],
                "trades": [
                    {
                        "trade_id": 7,
                        "pair": "BTC/USD",
                        "open_date": opened.isoformat(),
                        "close_date": closed.isoformat(),
                        "open_rate": 100.0,
                        "close_rate": 101.0,
                        "amount": 100.0,
                        "fee_open": 0.001,
                        "fee_close": 0.001,
                        "profit_abs": 98.0,
                        "profit_ratio": 0.0098,
                        "trade_duration": 60,
                        "max_rate": 102.0,
                        "min_rate": 99.0,
                        "is_short": False,
                        "enter_tag": "target_exposure",
                        "exit_reason": "exit_signal",
                    }
                ],
            }
        }
    }


def test_freqtrade_is_authoritative_and_preserves_replay_identity(
    tmp_path: Path, as_of: datetime
) -> None:
    runner = FakeRunner(result_payload(as_of))
    engine = FreqtradeBacktestEngine(runner=runner)
    configured = request(tmp_path, as_of)

    result = engine.run(configured)
    repeated = engine.run(configured)

    assert result == repeated
    assert result.total_pnl == 98.0
    assert result.trades[0].entry_fee == pytest.approx(10.0)
    assert result.trades[0].exit_fee == pytest.approx(10.1)
    assert result.trades[0].maximum_favorable_excursion == pytest.approx(0.02)
    assert result.provenance.engine_version == "Freqtrade 2026.8"
    assert result.provenance.dataset_id == "fixture-v1"
    command = runner.commands[1]
    assert command[:2] == ("freqtrade", "backtesting")
    assert command[command.index("--cache") + 1] == "none"
    assert command[command.index("--timerange") + 1] == (
        f"{configured.start:%Y%m%dT%H%M}-{configured.end:%Y%m%dT%H%M}"
    )
    assert configured.instruments[0] in command
    transcript = configured.artifact_directory / configured.request_id / "process.txt"
    assert transcript.read_text(encoding="utf-8") == (
        "stdout:\nanalysis completed\nstderr:\n"
    )
    config_path = Path(command[command.index("--config") + 1])
    effective_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert effective_config["dry_run"] is True
    assert effective_config["order_types"]["stoploss_on_exchange"] is False
    assert effective_config["order_types"]["stoploss"] == "market"
    assert effective_config["entry_pricing"] == {
        "price_side": "other",
        "use_order_book": False,
    }
    assert effective_config["exit_pricing"] == {
        "price_side": "other",
        "use_order_book": False,
    }
    assert effective_config["botnet_council_seed"] == 0
    assert effective_config["botnet_council_dataset_id"] == "fixture-v1"


def test_freqtrade_process_failure_never_falls_back(tmp_path: Path, as_of: datetime) -> None:
    runner = FakeRunner(returncode=2)

    with pytest.raises(FreqtradeProcessError, match="status 2"):
        FreqtradeBacktestEngine(runner=runner).run(request(tmp_path, as_of))


def test_freqtrade_rejects_reused_result_from_prior_invocation(
    tmp_path: Path, as_of: datetime
) -> None:
    configured = request(tmp_path, as_of)
    engine = FreqtradeBacktestEngine(runner=FakeRunner(result_payload(as_of)))
    engine.run(configured)

    class SilentRunner(FakeRunner):
        def run(
            self, command: Sequence[str], *, cwd: Path, timeout: int
        ) -> ProcessResult:
            self.commands.append(tuple(command))
            if "--version" in command:
                return ProcessResult(0, "Freqtrade 2026.8", "")
            return ProcessResult(0, "analysis completed", "")

    with pytest.raises(FreqtradeArtifactError, match="produced no result artifact"):
        FreqtradeBacktestEngine(runner=SilentRunner()).run(configured)


@pytest.mark.parametrize(
    ("mutator", "message"),
        (
            (lambda payload, as_of: payload["strategy"]["CouncilStrategy"]["trades"][0].update(
                {
                    "open_date": (as_of + timedelta(days=1)).isoformat(),
                    "close_date": (as_of + timedelta(days=1, hours=1)).isoformat(),
                }
            ), "outside requested period"),
        (lambda payload, as_of: payload["strategy"]["CouncilStrategy"]["trades"][0].update(
            {"pair": "OTHER/USD"}
        ), "not in request"),
    ),
)
def test_freqtrade_rejects_result_from_foreign_period(
    tmp_path: Path, as_of: datetime, mutator: object, message: str
) -> None:
    payload = result_payload(as_of)
    assert callable(mutator)
    mutator(payload, as_of)  # type: ignore[operator]
    with pytest.raises(FreqtradeArtifactError, match=message):
        FreqtradeBacktestEngine(runner=FakeRunner(payload)).run(request(tmp_path, as_of))


def test_freqtrade_malformed_export_is_structured_failure(
    tmp_path: Path, as_of: datetime
) -> None:
    with pytest.raises(FreqtradeArtifactError, match="no strategy object"):
        FreqtradeBacktestEngine(runner=FakeRunner({})).run(request(tmp_path, as_of))


def test_lookahead_validation_preserves_bias_artifact(tmp_path: Path, as_of: datetime) -> None:
    result = FreqtradeBacktestEngine(runner=FakeRunner()).validate(
        request(tmp_path, as_of), ValidationKind.LOOKAHEAD
    )

    assert result.status is ValidationStatus.FAILED
    assert result.artifact_path.exists()
    assert result.findings[0].startswith("BIAS:")


def test_recursive_validation_omits_execution_only_arguments(
    tmp_path: Path, as_of: datetime
) -> None:
    runner = FakeRunner()

    result = FreqtradeBacktestEngine(runner=runner).validate(
        request(tmp_path, as_of), ValidationKind.RECURSIVE
    )

    assert result.status is ValidationStatus.PASSED
    command = runner.commands[1]
    assert command[:2] == ("freqtrade", "recursive-analysis")
    assert "--fee" not in command
    assert "--dry-run-wallet" not in command


def test_missing_freqtrade_binary_is_explicit(tmp_path: Path, as_of: datetime) -> None:
    engine = FreqtradeBacktestEngine(executable="definitely-missing-freqtrade-binary")

    with pytest.raises(FreqtradeUnavailableError, match="not installed"):
        engine.run(request(tmp_path, as_of))


def test_docker_runner_maps_only_workspace_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    compose = tmp_path / "compose.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    runner = DockerComposeCommandRunner(compose, workspace)

    assert runner.map_path(workspace / "artifacts" / "result.json") == (
        "/workspace/artifacts/result.json"
    )
    with pytest.raises(ValueError, match="must remain inside"):
        runner.map_path(tmp_path / "outside.json")


def test_docker_runner_uses_disposable_noninteractive_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    compose = tmp_path / "compose.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(command: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = tuple(command)
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "Freqtrade 2026.8", "")

    monkeypatch.setattr("botnet_council.backtest.freqtrade.shutil.which", lambda _: "docker")
    monkeypatch.setattr("botnet_council.backtest.freqtrade.subprocess.run", fake_run)
    runner = DockerComposeCommandRunner(compose, workspace)

    result = runner.run(("freqtrade", "--version"), cwd=workspace, timeout=30)

    command = captured["command"]
    assert isinstance(command, tuple)
    assert command[-6:] == (
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "freqtrade",
        "--version",
    )
    assert captured["shell"] is False
    assert captured["timeout"] == 30
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["BOTNET_COUNCIL_WORKSPACE"] == str(workspace.resolve())
    assert result.stdout == "Freqtrade 2026.8"


def test_docker_runner_reports_missing_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    compose = tmp_path / "compose.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr("botnet_council.backtest.freqtrade.shutil.which", lambda _: None)

    with pytest.raises(FreqtradeUnavailableError, match="Docker executable"):
        DockerComposeCommandRunner(
            compose, workspace, docker_executable="definitely-missing-docker"
        ).run(
            ("freqtrade", "--version"), cwd=workspace, timeout=30
        )


def test_episode_joins_frozen_context_decision_and_authoritative_outcome(
    tmp_path: Path, as_of: datetime, rising_snapshot: MarketSnapshot
) -> None:
    configured = request(tmp_path, as_of)
    result = FreqtradeBacktestEngine(runner=FakeRunner(result_payload(as_of))).run(configured)
    context = MarketContext(snapshot=rising_snapshot, as_of=as_of)
    signal = TrendAgent().analyze(rising_snapshot, AgentContext(run_id="episode"))
    decision = DeterministicCouncil(CouncilConfig(minimum_conviction=0.0)).aggregate(
        rising_snapshot, (signal,)
    )

    episode = EpisodeRecord(
        context=context,
        specialist_outputs=(signal,),
        council_decision=decision,
        engine_request=configured,
        engine_result=result,
        evaluated_at=as_of,
        trainer_evaluation={"directional_correctness": True},
    )

    assert len(episode.episode_id) == 64
    invalid = episode.model_dump(mode="python", exclude={"episode_id"}, warnings=False)
    invalid["evaluated_at"] = as_of - timedelta(seconds=1)
    with pytest.raises(ValueError, match="cannot precede"):
        EpisodeRecord.model_validate(invalid)
