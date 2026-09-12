"""Provider-neutral contracts for authoritative external backtest engines."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, Self, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _json_value(value: Any, field_name: str) -> Any:
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError(f"{field_name} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _json_value(item, field_name) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_json_value(item, field_name) for item in value)
    if value is None or isinstance(value, str | int | bool):
        return value
    raise ValueError(f"{field_name} contains a non-JSON value")


class AuthoritativeModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, arbitrary_types_allowed=True
    )


class StrategyAdapterConfig(AuthoritativeModel):
    adapter_id: str
    adapter_version: str
    strategy_name: str
    strategy_path: Path
    signal_artifact: Path | None = None


class AuthoritativeBacktestRequest(AuthoritativeModel):
    instruments: tuple[str, ...]
    timeframe: str
    start: datetime
    end: datetime
    starting_capital: float = Field(gt=0, allow_inf_nan=False)
    fee_ratio: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)
    order_types: Mapping[str, str] = Field(default_factory=dict)
    strategy: StrategyAdapterConfig
    context_configuration: Mapping[str, Any] = Field(default_factory=dict)
    seed: int = 0
    dataset_id: str
    data_directory: Path
    artifact_directory: Path
    engine_configuration: Mapping[str, Any] = Field(default_factory=dict)
    request_id: str = ""

    @field_validator("start", "end")
    @classmethod
    def normalize_time(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @field_validator(
        "order_types", "context_configuration", "engine_configuration"
    )
    @classmethod
    def validate_mapping(cls, value: Mapping[str, Any], info: Any) -> Mapping[str, Any]:
        return cast(Mapping[str, Any], _json_value(value, info.field_name))

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.end <= self.start:
            raise ValueError("backtest end must be after start")
        if not self.instruments or any(not item for item in self.instruments):
            raise ValueError("at least one named instrument is required")
        if len(self.instruments) != len(set(self.instruments)):
            raise ValueError("instruments must be unique")
        if not all((self.timeframe, self.dataset_id, self.strategy.adapter_id)):
            raise ValueError("request identity fields are required")
        expected = request_identity(self)
        if self.request_id and self.request_id != expected:
            raise ValueError("request_id does not match request contents")
        object.__setattr__(self, "request_id", expected)
        return self


class NormalizedTrade(AuthoritativeModel):
    trade_id: str
    instrument: str
    side: str
    opened_at: datetime
    closed_at: datetime
    entry_price: float = Field(gt=0, allow_inf_nan=False)
    exit_price: float = Field(gt=0, allow_inf_nan=False)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    entry_fee: float = Field(ge=0, allow_inf_nan=False)
    exit_fee: float = Field(ge=0, allow_inf_nan=False)
    pnl: float = Field(allow_inf_nan=False)
    return_ratio: float = Field(allow_inf_nan=False)
    maximum_favorable_excursion: float | None = Field(default=None, allow_inf_nan=False)
    maximum_adverse_excursion: float | None = Field(default=None, allow_inf_nan=False)
    holding_seconds: int = Field(ge=0)
    entry_tag: str | None = None
    exit_reason: str | None = None

    @field_validator("opened_at", "closed_at")
    @classmethod
    def normalize_time(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @model_validator(mode="after")
    def validate_trade(self) -> Self:
        if self.closed_at < self.opened_at:
            raise ValueError("trade close cannot precede open")
        return self


class EquityPoint(AuthoritativeModel):
    timestamp: datetime
    equity: float = Field(allow_inf_nan=False)
    drawdown_ratio: float = Field(ge=0, allow_inf_nan=False)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _utc(value, "timestamp")


class RejectedOrder(AuthoritativeModel):
    timestamp: datetime
    instrument: str
    reason: str
    signal_tag: str | None = None

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _utc(value, "timestamp")


class EngineProvenance(AuthoritativeModel):
    engine: str
    engine_version: str
    effective_config_hash: str
    dataset_id: str
    request_id: str
    run_id: str
    artifact_path: Path
    artifact_sha256: str


class AuthoritativeBacktestResult(AuthoritativeModel):
    provenance: EngineProvenance
    trades: tuple[NormalizedTrade, ...]
    equity_curve: tuple[EquityPoint, ...]
    rejected_orders: tuple[RejectedOrder, ...] = ()
    rejected_order_count: int = Field(default=0, ge=0)
    starting_capital: float = Field(gt=0, allow_inf_nan=False)
    ending_capital: float = Field(allow_inf_nan=False)
    total_pnl: float = Field(allow_inf_nan=False)
    total_return: float = Field(allow_inf_nan=False)
    maximum_drawdown: float = Field(ge=0, allow_inf_nan=False)
    warnings: tuple[str, ...] = ()


class ValidationKind(StrEnum):
    LOOKAHEAD = "lookahead"
    RECURSIVE = "recursive"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class ValidationArtifact(AuthoritativeModel):
    kind: ValidationKind
    status: ValidationStatus
    engine_version: str
    request_id: str
    artifact_path: Path
    artifact_sha256: str
    findings: tuple[str, ...] = ()


@runtime_checkable
class AuthoritativeBacktestEngine(Protocol):
    @property
    def engine_id(self) -> str: ...

    def run(self, request: AuthoritativeBacktestRequest) -> AuthoritativeBacktestResult: ...

    def validate(
        self, request: AuthoritativeBacktestRequest, kind: ValidationKind
    ) -> ValidationArtifact: ...


def request_identity(request: AuthoritativeBacktestRequest) -> str:
    material = _plain_json(
        request.model_dump(mode="python", exclude={"request_id"}, warnings=False)
    )
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode()).hexdigest()


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, frozenset):
        return sorted((_plain_json(item) for item in value), key=str)
    if isinstance(value, tuple | list):
        return [_plain_json(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    return value
