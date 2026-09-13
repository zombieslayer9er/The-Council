"""Persistent historical scenarios and non-blocking deterministic run orchestration."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from botnet_council.backtest import (
    BacktestCancelledError,
    BacktestConfig,
    BacktestEngine,
    BacktestRun,
    persist_backtest,
)
from botnet_council.backtest.models import to_jsonable
from botnet_council.experience import (
    CacheWriteStatus,
    ExperienceOrigin,
    ExperienceStore,
    episodes_from_backtest,
)
from botnet_council.market_data import (
    Asset,
    CachedHistoricalProvider,
    HistoricalMarketDataProvider,
    HistoricalRequest,
    Instrument,
    ParquetMarketDataCache,
    ProviderId,
    Timeframe,
)
from botnet_council.schemas import CouncilDecision, MarketBar
from botnet_council.telemetry.publisher import EventPublisher


class ScenarioModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ScenarioApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HistoricalAcquisitionRequest(ScenarioModel):
    provider: ProviderId
    market: str
    instrument: Instrument
    timeframe: Timeframe
    start: datetime
    end: datetime
    as_of: datetime

    @field_validator("start", "end", "as_of")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("historical timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid(self) -> HistoricalAcquisitionRequest:
        if self.end <= self.start:
            raise ValueError("historical acquisition end must be after start")
        if self.as_of < self.end:
            raise ValueError("acquisition as_of cannot precede requested end")
        return self

    def historical_request(self) -> HistoricalRequest:
        return HistoricalRequest(
            instrument=self.instrument,
            timeframe=self.timeframe,
            start=self.start,
            end=self.end,
            as_of=self.as_of,
            market=self.market,
        )


class HistoricalAcquisitionCreate(ScenarioApiModel):
    provider: ProviderId
    market: str
    instrument: Instrument
    timeframe: Timeframe
    start: datetime
    end: datetime
    as_of: datetime

    def domain(self) -> HistoricalAcquisitionRequest:
        return HistoricalAcquisitionRequest(
            provider=self.provider,
            market=self.market,
            instrument=self.instrument,
            timeframe=self.timeframe,
            start=self.start,
            end=self.end,
            as_of=self.as_of,
        )


class HistoricalScenarioRequest(ScenarioModel):
    provider: ProviderId
    market: str
    config: BacktestConfig
    blind_window_bars: int | None = Field(default=None, ge=2)
    deterministic_seed: int = 0


class HistoricalScenarioCreate(ScenarioApiModel):
    provider: ProviderId
    market: str
    config: BacktestConfig
    blind_window_bars: int | None = Field(default=None, ge=2)
    deterministic_seed: int = 0

    @field_validator("config", mode="before")
    @classmethod
    def parse_config(cls, value: Any) -> BacktestConfig:
        return BacktestConfig.model_validate(value, strict=False)

    def domain(self) -> HistoricalScenarioRequest:
        return HistoricalScenarioRequest(
            provider=self.provider,
            market=self.market,
            config=self.config,
            blind_window_bars=self.blind_window_bars,
            deterministic_seed=self.deterministic_seed,
        )


class HistoricalScenario(ScenarioModel):
    scenario_id: str
    definition: HistoricalScenarioRequest
    created_at: datetime


class OperationKind(StrEnum):
    ACQUISITION = "acquisition"
    BACKTEST = "backtest"


class OperationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class LearningStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class HistoricalOperation(ScenarioModel):
    operation_id: str
    kind: OperationKind
    status: OperationStatus
    created_at: datetime
    updated_at: datetime
    progress: float = Field(ge=0, le=1)
    current: int = Field(ge=0)
    total: int = Field(ge=0)
    scenario_id: str | None = None
    result_run_id: str | None = None
    error: str | None = None
    learning_status: LearningStatus = LearningStatus.NOT_APPLICABLE
    learning_eligible: bool = False
    learning_episode_ids: tuple[str, ...] = ()
    learning_episodes_rejected: int = Field(default=0, ge=0)
    learning_message: str | None = None


class HistoricalScenarioService:
    def __init__(
        self,
        providers: Mapping[ProviderId, HistoricalMarketDataProvider],
        cache: ParquetMarketDataCache,
        result_root: str | Path,
        *,
        telemetry: EventPublisher | None = None,
        experience_store: ExperienceStore | None = None,
        clock: Any | None = None,
    ) -> None:
        self._providers = dict(providers)
        self._cache = cache
        self._result_root = Path(result_root)
        self._scenario_root = self._result_root / "scenarios"
        self._operation_root = self._result_root / "operations"
        self._telemetry = telemetry
        self._experience_store = experience_store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        self._scenarios: dict[str, HistoricalScenario] = {}
        self._operations: dict[str, HistoricalOperation] = {}
        self._cancellations: dict[str, Event] = {}
        self._results: dict[str, BacktestRun] = {}
        self._load_scenarios()
        self._load_operations()

    def providers(self) -> tuple[dict[str, Any], ...]:
        values = []
        for provider_id, provider in sorted(
            self._providers.items(), key=lambda item: item[0].value
        ):
            metadata = provider.metadata
            markets_method = getattr(provider, "list_markets", None)
            markets = tuple(markets_method()) if callable(markets_method) else (provider_id.value,)
            values.append(
                {
                    "provider": provider_id.value,
                    "display_name": metadata.display_name,
                    "markets": markets,
                    "timeframes": tuple(item.value for item in metadata.supported_timeframes),
                    "requires_credentials": metadata.requires_credentials,
                }
            )
        return tuple(values)

    def pairs(self, provider_id: ProviderId, market: str) -> tuple[Instrument, ...]:
        provider = self._provider(provider_id)
        method = getattr(provider, "list_pairs", None)
        if callable(method):
            return tuple(method(market))
        if market != provider_id.value:
            raise ValueError("provider does not expose the requested market")
        return provider.metadata.supported_instruments

    def availability(
        self, provider_id: ProviderId, market: str, instrument: Instrument, timeframe: Timeframe
    ) -> tuple[Any, ...]:
        self._provider(provider_id)
        return self._cache.inspect_availability(
            provider_id,
            instrument,
            timeframe,
            market=market,
        )

    def define(self, definition: HistoricalScenarioRequest) -> HistoricalScenario:
        provider = self._provider(definition.provider)
        instrument = _instrument(definition.config.instrument)
        timeframe = Timeframe(definition.config.timeframe)
        if instrument not in self.pairs(definition.provider, definition.market):
            raise ValueError("scenario instrument is unsupported by provider market")
        if timeframe not in provider.metadata.supported_timeframes:
            raise ValueError("scenario timeframe is unsupported by provider")
        material = json.dumps(to_jsonable(definition), sort_keys=True, separators=(",", ":"))
        scenario_id = sha256(material.encode()).hexdigest()[:24]
        scenario = HistoricalScenario(
            scenario_id=scenario_id,
            definition=definition,
            created_at=self._now(),
        )
        with self._lock:
            existing = self._scenarios.get(scenario_id)
            if existing is not None:
                return existing
            self._scenarios[scenario_id] = scenario
            self._write(self._scenario_root / f"{scenario_id}.json", to_jsonable(scenario))
        return scenario

    def scenario(self, scenario_id: str) -> HistoricalScenario:
        with self._lock:
            try:
                return self._scenarios[scenario_id]
            except KeyError as error:
                raise LookupError("historical scenario was not found") from error

    def scenarios(self) -> tuple[HistoricalScenario, ...]:
        """Return persisted scenario definitions in stable creation order."""
        with self._lock:
            return tuple(
                sorted(
                    self._scenarios.values(),
                    key=lambda item: (item.created_at, item.scenario_id),
                )
            )

    def start_acquisition(self, request: HistoricalAcquisitionRequest) -> HistoricalOperation:
        self._provider(request.provider)
        operation = self._new_operation(OperationKind.ACQUISITION)
        Thread(
            target=self._acquire,
            args=(operation.operation_id, request),
            daemon=True,
            name=f"historical-acquisition-{operation.operation_id}",
        ).start()
        return operation

    def start_backtest(self, scenario_id: str) -> HistoricalOperation:
        self.scenario(scenario_id)
        operation = self._new_operation(OperationKind.BACKTEST, scenario_id=scenario_id)
        Thread(
            target=self._run,
            args=(operation.operation_id, scenario_id),
            daemon=True,
            name=f"historical-backtest-{operation.operation_id}",
        ).start()
        return operation

    @property
    def learning_configured(self) -> bool:
        return self._experience_store is not None

    def operation(self, operation_id: str) -> HistoricalOperation:
        with self._lock:
            try:
                return self._operations[operation_id]
            except KeyError as error:
                raise LookupError("historical operation was not found") from error

    def operations(self) -> tuple[HistoricalOperation, ...]:
        """Return reconstructable operation state in stable creation order."""
        with self._lock:
            return tuple(
                sorted(
                    self._operations.values(),
                    key=lambda item: (item.created_at, item.operation_id),
                )
            )

    def statistics(self) -> dict[str, int]:
        operations = tuple(
            item for item in self.operations() if item.kind is OperationKind.BACKTEST
        )
        store = (
            self._experience_store.learning_statistics()
            if self._experience_store is not None
            else {
                "current_experience_set": 0,
                "learning_episodes_accepted": 0,
                "user_initiated_learning_episodes": 0,
                "automated_learning_episodes": 0,
            }
        )
        return {
            "total_tests_executed": len(operations),
            "successful_completed_tests": sum(
                item.status is OperationStatus.COMPLETED for item in operations
            ),
            "failed_cancelled_tests": sum(
                item.status in {OperationStatus.FAILED, OperationStatus.CANCELLED}
                for item in operations
            ),
            "learning_eligible_tests": sum(item.learning_eligible for item in operations),
            "learning_episodes_rejected": sum(
                item.learning_episodes_rejected for item in operations
            ),
            **store,
        }

    def cancel(self, operation_id: str) -> HistoricalOperation:
        operation = self.operation(operation_id)
        if operation.status in {
            OperationStatus.COMPLETED,
            OperationStatus.CANCELLED,
            OperationStatus.FAILED,
        }:
            return operation
        self._cancellations[operation_id].set()
        return self.operation(operation_id)

    def result(self, operation_id: str) -> BacktestRun:
        operation = self.operation(operation_id)
        if (
            operation.status is not OperationStatus.COMPLETED
            or operation.kind is not OperationKind.BACKTEST
        ):
            raise ValueError("backtest result is not available")
        with self._lock:
            return self._results[operation_id]

    def candles(self, operation_id: str) -> tuple[MarketBar, ...]:
        return self._candles_for_run(self.result(operation_id))

    def council_outputs(self, operation_id: str) -> tuple[CouncilDecision, ...]:
        return tuple(
            event.council_decision
            for event in self.result(operation_id).ledger.events
            if event.council_decision is not None
        )

    def _new_operation(
        self, kind: OperationKind, *, scenario_id: str | None = None
    ) -> HistoricalOperation:
        now = self._now()
        operation = HistoricalOperation(
            operation_id=uuid4().hex,
            kind=kind,
            status=OperationStatus.QUEUED,
            created_at=now,
            updated_at=now,
            progress=0,
            current=0,
            total=0,
            scenario_id=scenario_id,
            learning_status=(
                LearningStatus.PENDING
                if kind is OperationKind.BACKTEST
                else LearningStatus.NOT_APPLICABLE
            ),
        )
        with self._lock:
            self._operations[operation.operation_id] = operation
            self._cancellations[operation.operation_id] = Event()
            self._persist_operation(operation)
        return operation

    def _acquire(self, operation_id: str, request: HistoricalAcquisitionRequest) -> None:
        try:
            self._update(operation_id, status=OperationStatus.RUNNING, total=1)
            if self._cancellations[operation_id].is_set():
                raise BacktestCancelledError("acquisition cancellation requested")
            provider = CachedHistoricalProvider(self._provider(request.provider), self._cache)
            result = provider.fetch_historical(request.historical_request())
            self._update(
                operation_id,
                status=OperationStatus.COMPLETED,
                progress=1,
                current=len(result.bars),
                total=len(result.bars),
            )
        except BacktestCancelledError:
            self._update(operation_id, status=OperationStatus.CANCELLED)
        except Exception as error:
            self._update(
                operation_id,
                status=OperationStatus.FAILED,
                error=f"{type(error).__name__}: historical acquisition failed",
            )

    def _run(self, operation_id: str, scenario_id: str) -> None:
        try:
            self._update(operation_id, status=OperationStatus.RUNNING)
            scenario = self.scenario(scenario_id)
            provider = CachedHistoricalProvider(
                self._provider(scenario.definition.provider), self._cache
            )
            config = self._resolved_config(provider, scenario.definition)
            engine = BacktestEngine(provider, self._telemetry)

            def progress(current: int, total: int) -> None:
                self._update(
                    operation_id,
                    progress=current / total,
                    current=current,
                    total=total,
                    persist=current == total or current % max(1, total // 100) == 0,
                )

            run = engine.run(
                config,
                should_cancel=self._cancellations[operation_id].is_set,
                on_progress=progress,
            )
            persist_backtest(run, config, self._result_root / "backtests")
            with self._lock:
                self._results[operation_id] = run
                self._write(
                    self._operation_root / f"{operation_id}.result.json",
                    to_jsonable(run),
                )
            try:
                learning = self._record_learning(run, config)
            except Exception as error:
                learning = {
                    "learning_status": LearningStatus.REJECTED,
                    "learning_message": f"{type(error).__name__}: learning acceptance failed",
                }
            self._update(
                operation_id,
                status=OperationStatus.COMPLETED,
                progress=1,
                result_run_id=run.result.run_id,
                **learning,
            )
        except BacktestCancelledError:
            self._update(
                operation_id,
                status=OperationStatus.CANCELLED,
                learning_status=LearningStatus.REJECTED,
                learning_message="cancelled runs are not learning eligible",
            )
        except Exception as error:
            self._update(
                operation_id,
                status=OperationStatus.FAILED,
                error=f"{type(error).__name__}: historical backtest failed",
                learning_status=LearningStatus.REJECTED,
                learning_message="failed runs are not learning eligible",
            )

    def _record_learning(self, run: BacktestRun, config: BacktestConfig) -> dict[str, Any]:
        candidates = sum(
            event.measured and event.council_decision is not None
            for event in run.ledger.events
        )
        episodes = episodes_from_backtest(run, config, self._candles_for_run(run))
        rejected = candidates - len(episodes)
        if self._experience_store is None:
            return {
                "learning_status": LearningStatus.REJECTED,
                "learning_eligible": bool(episodes),
                "learning_episodes_rejected": rejected + len(episodes),
                "learning_message": "experience store is not configured",
            }
        accepted: list[str] = []
        for episode in episodes:
            status = self._experience_store.save_learning_episode(
                episode,
                origin=ExperienceOrigin.USER_INITIATED,
                source_run_id=run.result.run_id,
            )
            if status is CacheWriteStatus.STORED:
                accepted.append(episode.episode_id)
            else:
                rejected += 1
        return {
            "learning_status": (
                LearningStatus.ACCEPTED if accepted else LearningStatus.REJECTED
            ),
            "learning_eligible": bool(episodes),
            "learning_episode_ids": tuple(accepted),
            "learning_episodes_rejected": rejected,
            "learning_message": (
                "episode persisted in the canonical experience dataset"
                if accepted
                else "no new episode was accepted; outcome was incomplete or already learned"
            ),
        }

    def _candles_for_run(self, run: BacktestRun) -> tuple[MarketBar, ...]:
        provenance = run.result.market_data_provenance
        loaded = self._cache.load(
            provenance.provider,
            provenance.request,
            expected_source_version=provenance.source_version,
            expected_adapter_semantic_version=provenance.adapter_semantic_version,
        )
        if loaded is None:
            raise LookupError("immutable run market-data snapshot is unavailable")
        return loaded.bars

    def _resolved_config(
        self,
        provider: CachedHistoricalProvider,
        definition: HistoricalScenarioRequest,
    ) -> BacktestConfig:
        config = definition.config
        config = config.model_copy(update={"market": definition.market})
        if definition.blind_window_bars is None:
            return config
        instrument = _instrument(config.instrument)
        timeframe = Timeframe(config.timeframe)
        request = HistoricalRequest(
            instrument=instrument,
            timeframe=timeframe,
            start=config.start,
            end=config.end + timeframe.duration,
            as_of=config.end + timeframe.duration,
            market=definition.market,
        )
        history = provider.fetch_historical(request)
        count = definition.blind_window_bars
        candidate_count = len(history.bars) - count + 1
        if candidate_count <= 0:
            raise ValueError("available dataset is too short for blind scenario window")
        # Selection depends only on row positions and the declared seed, never OHLCV outcomes.
        offset = random.Random(definition.deterministic_seed).randrange(candidate_count)
        start = history.bars[offset].opened_at
        return config.model_copy(
            update={
                "start": start,
                "end": start + timeframe.duration * count,
                "random_seed": definition.deterministic_seed,
            }
        )

    def _update(
        self, operation_id: str, *, persist: bool = True, **changes: Any
    ) -> HistoricalOperation:
        with self._lock:
            operation = self._operations[operation_id].model_copy(
                update={**changes, "updated_at": self._now()}
            )
            self._operations[operation_id] = operation
            if persist:
                self._persist_operation(operation)
            return operation

    def _provider(self, provider_id: ProviderId) -> HistoricalMarketDataProvider:
        try:
            return self._providers[provider_id]
        except KeyError as error:
            raise ValueError(f"historical provider {provider_id.value!r} is unavailable") from error

    def _load_scenarios(self) -> None:
        if not self._scenario_root.exists():
            return
        for path in sorted(self._scenario_root.glob("*.json")):
            scenario = HistoricalScenario.model_validate_json(path.read_text(encoding="utf-8"))
            self._scenarios[scenario.scenario_id] = scenario

    def _persist_operation(self, operation: HistoricalOperation) -> None:
        self._write(self._operation_root / f"{operation.operation_id}.json", to_jsonable(operation))

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _load_operations(self) -> None:
        if not self._operation_root.exists():
            return
        for path in sorted(self._operation_root.glob("*.json")):
            if path.name.endswith(".result.json"):
                continue
            operation = HistoricalOperation.model_validate_json(path.read_text(encoding="utf-8"))
            if operation.status in {OperationStatus.QUEUED, OperationStatus.RUNNING}:
                operation = operation.model_copy(
                    update={
                        "status": OperationStatus.FAILED,
                        "updated_at": self._now(),
                        "error": "service restarted before operation completed",
                        "learning_status": (
                            LearningStatus.REJECTED
                            if operation.kind is OperationKind.BACKTEST
                            else LearningStatus.NOT_APPLICABLE
                        ),
                        "learning_message": (
                            "interrupted runs are not learning eligible"
                            if operation.kind is OperationKind.BACKTEST
                            else None
                        ),
                    }
                )
            self._operations[operation.operation_id] = operation
            self._cancellations[operation.operation_id] = Event()
            result_path = self._operation_root / f"{operation.operation_id}.result.json"
            if result_path.exists():
                self._results[operation.operation_id] = BacktestRun.model_validate_json(
                    result_path.read_text(encoding="utf-8")
                )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scenario clock must be timezone-aware")
        return value.astimezone(UTC)


def _instrument(symbol: str) -> Instrument:
    base, quote = symbol.split("/", maxsplit=1)
    return Instrument(base=Asset(base), quote=Asset(quote))
