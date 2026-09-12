"""Idempotent experiment persistence with immutable forecast enforcement."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from threading import RLock
from typing import Protocol
from uuid import uuid4

from botnet_council.backtest.models import to_jsonable
from botnet_council.experiments.models import ExperimentRecord


class ExperimentRepository(Protocol):
    def get(self, experiment_id: str) -> ExperimentRecord: ...

    def save(self, record: ExperimentRecord) -> None: ...

    def list(self) -> tuple[ExperimentRecord, ...]: ...


def _protect_forecast(previous: ExperimentRecord | None, current: ExperimentRecord) -> None:
    if (
        previous is not None
        and previous.forecast is not None
        and current.forecast != previous.forecast
    ):
        raise ValueError("a locked forecast is immutable")
    if previous is not None and previous.request != current.request:
        raise ValueError("an experiment request is immutable")


class InMemoryExperimentRepository:
    def __init__(self) -> None:
        self._records: dict[str, ExperimentRecord] = {}
        self._lock = RLock()

    def get(self, experiment_id: str) -> ExperimentRecord:
        with self._lock:
            try:
                return self._records[experiment_id]
            except KeyError as error:
                raise LookupError(f"unknown experiment {experiment_id}") from error

    def save(self, record: ExperimentRecord) -> None:
        with self._lock:
            previous = self._records.get(record.experiment_id)
            _protect_forecast(previous, record)
            self._records[record.experiment_id] = record

    def list(self) -> tuple[ExperimentRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._records.values(),
                    key=lambda item: (item.request.evaluation_time, item.experiment_id),
                    reverse=True,
                )
            )


class FileExperimentRepository:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._lock = RLock()

    def get(self, experiment_id: str) -> ExperimentRecord:
        path = self._path(experiment_id)
        try:
            return ExperimentRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise LookupError(f"unknown experiment {experiment_id}") from error

    def save(self, record: ExperimentRecord) -> None:
        with self._lock:
            try:
                previous = self.get(record.experiment_id)
            except LookupError:
                previous = None
            _protect_forecast(previous, record)
            self._root.mkdir(parents=True, exist_ok=True)
            path = self._path(record.experiment_id)
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            temporary.write_text(
                json.dumps(
                    to_jsonable(record), sort_keys=True, separators=(",", ":"), ensure_ascii=True
                )
                + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)

    def list(self) -> tuple[ExperimentRecord, ...]:
        if not self._root.exists():
            return ()
        return tuple(
            sorted(
                (self.get(path.stem) for path in self._root.glob("*.json")),
                key=lambda item: (item.request.evaluation_time, item.experiment_id),
                reverse=True,
            )
        )

    def _path(self, experiment_id: str) -> Path:
        if not experiment_id or any(
            character not in "0123456789abcdef" for character in experiment_id
        ):
            raise ValueError("experiment_id must be a lowercase hexadecimal identity")
        return self._root / f"{experiment_id}.json"


def replace_records(repository: ExperimentRepository, records: Iterable[ExperimentRecord]) -> None:
    for record in records:
        repository.save(record)
