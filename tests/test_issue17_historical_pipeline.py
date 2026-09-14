from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.feather as feather
import pytest
from fastapi.testclient import TestClient

from botnet_council.api import create_app
from botnet_council.backtest import (
    AgentConfig,
    BacktestCancelledError,
    BacktestConfig,
    BacktestEngine,
    BacktestRun,
)
from botnet_council.backtest.models import to_jsonable
from botnet_council.council import CouncilConfig
from botnet_council.experience import ExperienceStore
from botnet_council.market_data import (
    Asset,
    CachedHistoricalProvider,
    FreqtradeHistoricalProvider,
    HistoricalBars,
    HistoricalRequest,
    Instrument,
    ParquetMarketDataCache,
    ProviderId,
    ProviderMetadata,
    Timeframe,
)
from botnet_council.market_data.quality import normalize_and_assess
from botnet_council.risk import RiskPolicy
from botnet_council.scenarios import (
    HistoricalScenarioRequest,
    HistoricalScenarioService,
    LearningStatus,
    OperationStatus,
)
from botnet_council.schemas import MarketBar, MarketSnapshot
from botnet_council.telemetry.publisher import InMemoryEventBus

ORIGIN = datetime(2026, 1, 1, tzinfo=UTC)
INSTRUMENT = Instrument(base=Asset.BTC, quote=Asset.USD)


class FixtureProvider:
    source_version = "fixture-v1"
    adapter_semantic_version = "fixture-causal-v1"

    def __init__(self, bars: tuple[MarketBar, ...]) -> None:
        self.bars = bars
        self.calls: list[HistoricalRequest] = []

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider=ProviderId.IN_MEMORY,
            display_name="fixture",
            supported_instruments=(INSTRUMENT,),
            supported_timeframes=(Timeframe.HOUR_1,),
            maximum_rows=10_000,
            requires_credentials=False,
            timestamp_convention="UTC interval open",
            availability_convention="available at close",
        )

    def fetch_historical(self, request: HistoricalRequest) -> HistoricalBars:
        self.calls.append(request)
        selected = tuple(
            bar
            for bar in self.bars
            if request.start <= bar.opened_at < request.end and bar.available_at <= request.as_of
        )
        normalized, quality = normalize_and_assess(
            selected,
            request.timeframe,
            request_start=request.start,
            request_end=request.end,
        )
        return HistoricalBars(
            provider=ProviderId.IN_MEMORY,
            request=request,
            fetched_at=self.bars[-1].closed_at,
            bars=normalized,
            quality=quality,
            source_version=self.source_version,
            adapter_semantic_version=self.adapter_semantic_version,
        )

    def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            as_of=as_of,
            observed_at=as_of,
            bars=tuple(bar for bar in self.bars if bar.available_at <= as_of),
        )


def bars(count: int = 10) -> tuple[MarketBar, ...]:
    return tuple(
        MarketBar(
            opened_at=ORIGIN + timedelta(hours=index),
            closed_at=ORIGIN + timedelta(hours=index + 1),
            available_at=ORIGIN + timedelta(hours=index + 1),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=10.0,
        )
        for index in range(count)
    )


def request(start_hour: int, end_hour: int) -> HistoricalRequest:
    return HistoricalRequest(
        instrument=INSTRUMENT,
        timeframe=Timeframe.HOUR_1,
        start=ORIGIN + timedelta(hours=start_hour),
        end=ORIGIN + timedelta(hours=end_hour),
        as_of=ORIGIN + timedelta(hours=end_hour),
        market="in_memory",
    )


def test_partially_overlapping_request_fetches_only_missing_range(tmp_path: Path) -> None:
    source = FixtureProvider(bars())
    provider = CachedHistoricalProvider(source, ParquetMarketDataCache(tmp_path))

    first = provider.fetch_historical(request(0, 3))
    extended = provider.fetch_historical(request(0, 6))
    repeated = provider.fetch_historical(request(0, 6))

    assert len(first.bars) == 3
    assert extended == repeated
    assert [(item.start, item.end) for item in source.calls] == [
        (ORIGIN, ORIGIN + timedelta(hours=3)),
        (ORIGIN + timedelta(hours=3), ORIGIN + timedelta(hours=6)),
    ]


def test_cache_artifacts_are_immutable_for_one_request_identity(tmp_path: Path) -> None:
    source = FixtureProvider(bars())
    result = source.fetch_historical(request(0, 3))
    cache = ParquetMarketDataCache(tmp_path)
    cache.store(result)
    changed = result.model_copy(
        update={
            "bars": (
                result.bars[0].model_copy(update={"close": result.bars[0].close + 0.25}),
                *result.bars[1:],
            )
        }
    )

    with pytest.raises(ValueError, match="immutable cache artifact"):
        cache.store(changed)


@dataclass
class RunnerResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class FakeFreqtradeRunner:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: Sequence[str], *, cwd: Path, timeout: int) -> RunnerResult:
        assert cwd == self.root.resolve()
        assert timeout > 0
        self.commands.append(tuple(command))
        if "--version" in command:
            return RunnerResult(0, "Freqtrade 2026.8\n")
        destination = Path(command[command.index("--datadir") + 1])
        destination.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "date": (ORIGIN + timedelta(hours=index)).replace(tzinfo=None),
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
                "volume": 10.0,
            }
            for index in range(3)
        ]
        feather.write_feather(pa.Table.from_pylist(rows), destination / "BTC_USD-1h.feather")
        return RunnerResult(0)


def test_freqtrade_download_is_normalized_before_entering_cache(tmp_path: Path) -> None:
    runner = FakeFreqtradeRunner(tmp_path)
    provider = FreqtradeHistoricalProvider(tmp_path, runner=runner)
    requested = HistoricalRequest(
        instrument=INSTRUMENT,
        timeframe=Timeframe.HOUR_1,
        start=ORIGIN,
        end=ORIGIN + timedelta(hours=3),
        as_of=ORIGIN + timedelta(hours=3),
        market="kraken",
    )

    result = provider.fetch_historical(requested)

    assert result.provider is ProviderId.FREQTRADE
    assert result.quality.coverage_complete is True
    assert all(bar.available_at == bar.closed_at for bar in result.bars)
    download = next(command for command in runner.commands if "download-data" in command)
    assert download[download.index("--exchange") + 1] == "kraken"
    assert download[download.index("--pairs") + 1] == "BTC/USD"


def test_freqtrade_availability_preserves_gaps(tmp_path: Path) -> None:
    market_root = tmp_path / "kraken"
    market_root.mkdir()
    rows = [
        {
            "date": (ORIGIN + timedelta(hours=index)).replace(tzinfo=None),
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.5 + index,
            "volume": 10.0,
        }
        for index in (0, 1, 3)
    ]
    feather.write_feather(pa.Table.from_pylist(rows), market_root / "BTC_USD-1h.feather")
    provider = FreqtradeHistoricalProvider(tmp_path, runner=FakeFreqtradeRunner(tmp_path))

    ranges = provider.inspect_availability("kraken", INSTRUMENT, Timeframe.HOUR_1)

    assert [(item.start, item.end) for item in ranges] == [
        (ORIGIN, ORIGIN + timedelta(hours=2)),
        (ORIGIN + timedelta(hours=3), ORIGIN + timedelta(hours=4)),
    ]


def scenario_request() -> HistoricalScenarioRequest:
    return HistoricalScenarioRequest(
        provider=ProviderId.IN_MEMORY,
        market="in_memory",
        config=BacktestConfig(
            instrument="BTC/USD",
            timeframe="1h",
            start=ORIGIN + timedelta(hours=3),
            end=ORIGIN + timedelta(hours=8),
            starting_cash=1_000.0,
            agents=(AgentConfig(kind="trend", parameters={"fast_window": 1, "slow_window": 2}),),
            council=CouncilConfig(minimum_confidence=0.01, minimum_conviction=0.001),
            risk=RiskPolicy(
                minimum_confidence=0.01,
                max_position_fraction=0.5,
                max_gross_exposure_fraction=0.5,
                max_order_notional=1_000.0,
                minimum_cash_reserve_fraction=0.0,
                max_realized_volatility=1.0,
                max_signal_age_seconds=3_600,
                max_observation_age_seconds=3_600,
                order_validity_seconds=3_600,
                allowed_symbols=("BTC/USD",),
            ),
            warmup_bars=3,
            decision_cadence_bars=2,
        ),
        deterministic_seed=17,
    )


def wait_for_completion(service: HistoricalScenarioService, operation_id: str) -> OperationStatus:
    for _ in range(200):
        status = service.operation(operation_id).status
        if status in {
            OperationStatus.COMPLETED,
            OperationStatus.CANCELLED,
            OperationStatus.FAILED,
        }:
            return status
        time.sleep(0.01)
    raise AssertionError("historical operation did not finish")


def test_scenario_run_is_non_blocking_persisted_and_causally_blind(tmp_path: Path) -> None:
    source = FixtureProvider(bars())
    cache = ParquetMarketDataCache(tmp_path / "cache")
    service = HistoricalScenarioService({ProviderId.IN_MEMORY: source}, cache, tmp_path / "results")
    scenario = service.define(scenario_request())

    operation = service.start_backtest(scenario.scenario_id)
    assert operation.status in {OperationStatus.QUEUED, OperationStatus.RUNNING}
    assert wait_for_completion(service, operation.operation_id) is OperationStatus.COMPLETED

    run = service.result(operation.operation_id)
    assert all(
        bar.available_at <= event.simulation_time
        for event in run.ledger.events
        if event.snapshot is not None
        for bar in event.snapshot.bars
    )
    assert len(service.council_outputs(operation.operation_id)) == 3
    assert service.candles(operation.operation_id)

    reloaded = HistoricalScenarioService(
        {ProviderId.IN_MEMORY: source}, cache, tmp_path / "results"
    )
    assert reloaded.result(operation.operation_id) == run


def test_user_backtest_feeds_canonical_learning_store_exactly_once(tmp_path: Path) -> None:
    source = FixtureProvider(bars())
    cache = ParquetMarketDataCache(tmp_path / "cache")
    experiences = ExperienceStore(tmp_path / "experiences")
    service = HistoricalScenarioService(
        {ProviderId.IN_MEMORY: source},
        cache,
        tmp_path / "results",
        experience_store=experiences,
    )
    scenario = service.define(scenario_request())

    first = service.start_backtest(scenario.scenario_id)
    assert wait_for_completion(service, first.operation_id) is OperationStatus.COMPLETED
    accepted = service.operation(first.operation_id)
    assert accepted.learning_status is LearningStatus.ACCEPTED
    assert accepted.learning_eligible is True
    assert len(accepted.learning_episode_ids) == 3
    assert len(experiences.query()) == 3

    repeated = service.start_backtest(scenario.scenario_id)
    assert wait_for_completion(service, repeated.operation_id) is OperationStatus.COMPLETED
    duplicate = service.operation(repeated.operation_id)
    assert duplicate.learning_status is LearningStatus.REJECTED
    assert duplicate.learning_episodes_rejected == 3
    assert len(experiences.query()) == 3
    assert service.statistics() == {
        "total_tests_executed": 2,
        "successful_completed_tests": 2,
        "failed_cancelled_tests": 0,
        "learning_eligible_tests": 2,
        "learning_episodes_rejected": 3,
        "current_experience_set": 3,
        "learning_episodes_accepted": 3,
        "user_initiated_learning_episodes": 3,
        "automated_learning_episodes": 0,
    }

    reloaded = HistoricalScenarioService(
        {ProviderId.IN_MEMORY: source},
        cache,
        tmp_path / "results",
        experience_store=experiences,
    )
    assert reloaded.statistics() == service.statistics()


def test_identical_scenario_definition_is_idempotent(tmp_path: Path) -> None:
    instants = iter((ORIGIN + timedelta(days=1), ORIGIN + timedelta(days=2)))
    service = HistoricalScenarioService(
        {ProviderId.IN_MEMORY: FixtureProvider(bars())},
        ParquetMarketDataCache(tmp_path / "cache"),
        tmp_path / "results",
        clock=lambda: next(instants),
    )

    first = service.define(scenario_request())
    repeated = service.define(scenario_request())

    assert repeated == first
    assert repeated.created_at == ORIGIN + timedelta(days=1)


def test_blind_selection_can_choose_final_valid_window(tmp_path: Path) -> None:
    definition = scenario_request().model_copy(
        update={
            "blind_window_bars": 2,
            "deterministic_seed": 17,
            "config": scenario_request().config.model_copy(
                update={"start": ORIGIN, "end": ORIGIN + timedelta(hours=9)}
            ),
        }
    )
    service = HistoricalScenarioService(
        {ProviderId.IN_MEMORY: FixtureProvider(bars(12))},
        ParquetMarketDataCache(tmp_path / "cache"),
        tmp_path / "results",
    )
    scenario = service.define(definition)
    operation = service.start_backtest(scenario.scenario_id)

    assert wait_for_completion(service, operation.operation_id) is OperationStatus.COMPLETED
    run = service.result(operation.operation_id)
    assert run.result.evaluation_start == ORIGIN + timedelta(hours=8)
    assert run.result.evaluation_end == ORIGIN + timedelta(hours=10)


def test_future_candle_change_does_not_change_past_council_inputs_or_decisions() -> None:
    original = bars()
    changed = (
        *original[:7],
        original[7].model_copy(
            update={"open": 500.0, "high": 510.0, "low": 490.0, "close": 505.0}
        ),
        *original[8:],
    )

    original_run = BacktestEngine(FixtureProvider(original)).run(scenario_request().config)
    changed_run = BacktestEngine(FixtureProvider(changed)).run(scenario_request().config)
    cutoff = original[7].available_at

    def past_council(run: BacktestRun) -> tuple[tuple[object, object, object], ...]:
        return tuple(
            (event.simulation_time, event.snapshot, event.council_decision)
            for event in run.ledger.events
            if event.simulation_time < cutoff
        )

    assert past_council(changed_run) == past_council(original_run)


def test_backtest_cancellation_is_checked_at_event_boundaries() -> None:
    source = FixtureProvider(bars())
    with pytest.raises(BacktestCancelledError):
        BacktestEngine(source).run(
            scenario_request().config,
            should_cancel=lambda: True,
        )


def test_historical_api_exposes_discovery_and_async_run_status(tmp_path: Path) -> None:
    experiences = ExperienceStore(tmp_path / "experiences")
    service = HistoricalScenarioService(
        {ProviderId.IN_MEMORY: FixtureProvider(bars())},
        ParquetMarketDataCache(tmp_path / "cache"),
        tmp_path / "results",
        experience_store=experiences,
    )
    token = "historical-control-token-that-is-long-enough"
    client = TestClient(
        create_app(
            InMemoryEventBus(),
            command_token=token,
            historical_service=service,
            experience_store=experiences,
        )
    )
    headers = {"Authorization": f"Bearer {token}"}

    providers = client.get("/api/historical/providers")
    created = client.post(
        "/api/control/historical/scenarios",
        json=to_jsonable(scenario_request()),
        headers=headers,
    )
    scenario_id = created.json()["scenario"]["scenario_id"]
    started = client.post(f"/api/control/historical/scenarios/{scenario_id}/runs", headers=headers)

    assert providers.json()["items"][0]["provider"] == "in_memory"
    assert created.status_code == 201
    assert started.status_code == 202
    operation_id = started.json()["operation"]["operation_id"]
    assert client.get(f"/api/historical/operations/{operation_id}").status_code == 200
    assert wait_for_completion(service, operation_id) is OperationStatus.COMPLETED
    assert client.get(f"/api/historical/operations/{operation_id}/result").status_code == 200
    assert client.get(f"/api/historical/operations/{operation_id}/candles").json()["items"]
    assert client.get(f"/api/historical/operations/{operation_id}/council").json()["items"]
    assert (
        client.get(f"/api/historical/operations/{operation_id}/judge")
        .json()["evaluation"]["metrics"]["starting_equity"]
        == 1_000.0
    )
    assert client.get("/api/historical/scenarios").json()["items"][0]["scenario_id"] == scenario_id
    listed_operation = client.get("/api/historical/operations").json()["items"][0]
    assert listed_operation["operation_id"] == operation_id
    assert listed_operation["learning_status"] == "accepted"
    assert client.get("/api/historical/statistics").json()["statistics"] == {
        "total_tests_executed": 1,
        "successful_completed_tests": 1,
        "failed_cancelled_tests": 0,
        "learning_eligible_tests": 1,
        "learning_episodes_rejected": 0,
        "current_experience_set": 3,
        "learning_episodes_accepted": 3,
        "user_initiated_learning_episodes": 3,
        "automated_learning_episodes": 0,
    }
    artifacts = client.get(
        f"/api/historical/operations/{operation_id}/artifacts"
    ).json()
    assert artifacts["operation"]["result_run_id"] == artifacts["run"]["result"]["run_id"]
    assert artifacts["scenario"]["scenario_id"] == scenario_id
    assert artifacts["candles"]
    assert artifacts["run"]["ledger"]["events"]
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert "HistoricalScenarioCreate" in schemas

    acquisition = client.post(
        "/api/control/historical/acquisitions",
        json={
            "provider": "in_memory",
            "market": "in_memory",
            "instrument": {"base": "BTC", "quote": "USD"},
            "timeframe": "1h",
            "start": ORIGIN.isoformat(),
            "end": (ORIGIN + timedelta(hours=3)).isoformat(),
            "as_of": (ORIGIN + timedelta(hours=3)).isoformat(),
        },
        headers=headers,
    )
    assert acquisition.status_code == 202
