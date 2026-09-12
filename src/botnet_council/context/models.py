"""Causal, provider-neutral contracts for enriched market context."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from types import MappingProxyType
from typing import Any, Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from botnet_council.schemas import MarketSnapshot


class ContextCapability(StrEnum):
    PRICE_HISTORY = "price_history"
    BENCHMARK_PERFORMANCE = "benchmark_performance"
    SECTOR_CLASSIFICATION = "sector_classification"
    RELATIVE_STRENGTH = "relative_strength"
    CORRELATIONS = "correlations"
    REALIZED_VOLATILITY = "realized_volatility"
    MARKET_BREADTH = "market_breadth"
    RATES_AND_YIELDS = "rates_and_yields"
    MACRO_INDICATORS = "macro_indicators"
    EVENT_CALENDAR = "event_calendar"


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


class ContextModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, arbitrary_types_allowed=True
    )


class TemporalProvenance(ContextModel):
    """When a datum describes reality and when it became usable in replay."""

    provider: str
    source_id: str
    observed_at: datetime
    period_start: datetime | None = None
    period_end: datetime | None = None
    published_at: datetime | None = None
    provider_available_at: datetime
    ingested_at: datetime
    vintage: str
    revision: str | None = None
    source_version: str

    @field_validator(
        "observed_at",
        "period_start",
        "period_end",
        "published_at",
        "provider_available_at",
        "ingested_at",
    )
    @classmethod
    def normalize_time(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def validate_timeline(self) -> Self:
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("period_start and period_end must be supplied together")
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError("period_end cannot precede period_start")
        if self.published_at is not None and self.provider_available_at < self.published_at:
            raise ValueError("provider availability cannot precede publication")
        if self.ingested_at < self.provider_available_at:
            raise ValueError("ingestion cannot precede provider availability")
        if not all((self.provider, self.source_id, self.vintage, self.source_version)):
            raise ValueError("provenance identity fields are required")
        return self


class ContextDatum(ContextModel):
    capability: ContextCapability
    instrument: str
    name: str
    value: Any
    unit: str
    provenance: TemporalProvenance

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: Any) -> Any:
        return _json_value(value, "value")

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.capability is ContextCapability.PRICE_HISTORY:
            raise ValueError("price_history is represented by MarketSnapshot")
        if not all((self.instrument, self.name, self.unit)):
            raise ValueError("context datum identity fields are required")
        return self


class ContextRequest(ContextModel):
    instrument: str
    timeframe: str
    as_of: datetime
    required: frozenset[ContextCapability] = frozenset({ContextCapability.PRICE_HISTORY})
    optional: frozenset[ContextCapability] = frozenset()
    configuration: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return _utc(value, "as_of")

    @field_validator("configuration")
    @classmethod
    def validate_configuration(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return cast(Mapping[str, Any], _json_value(value, "configuration"))

    @model_validator(mode="after")
    def validate_capabilities(self) -> Self:
        if self.required & self.optional:
            raise ValueError("required and optional capabilities must be disjoint")
        if ContextCapability.PRICE_HISTORY not in self.required:
            raise ValueError("price_history must be required")
        return self

    @property
    def identity(self) -> str:
        material = _plain_json(self.model_dump(mode="python", warnings=False))
        canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return sha256(canonical.encode()).hexdigest()


class MarketContext(ContextModel):
    snapshot: MarketSnapshot
    as_of: datetime
    data: tuple[ContextDatum, ...] = ()
    requested_required: frozenset[ContextCapability] = frozenset(
        {ContextCapability.PRICE_HISTORY}
    )
    requested_optional: frozenset[ContextCapability] = frozenset()
    missing_required: frozenset[ContextCapability] = frozenset()
    missing_optional: frozenset[ContextCapability] = frozenset()
    context_id: str = ""

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return _utc(value, "as_of")

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if self.snapshot.as_of != self.as_of:
            raise ValueError("context and price snapshot must share one as_of clock")
        if self.missing_required - self.requested_required:
            raise ValueError("missing_required contains an unrequested capability")
        if self.missing_optional - self.requested_optional:
            raise ValueError("missing_optional contains an unrequested capability")
        available = {ContextCapability.PRICE_HISTORY, *(item.capability for item in self.data)}
        requested = self.requested_required | self.requested_optional
        if any(item.capability not in requested for item in self.data):
            raise ValueError("context contains an unrequested capability")
        if self.missing_required != self.requested_required - available:
            raise ValueError("missing_required does not match available context")
        if self.missing_optional != self.requested_optional - available:
            raise ValueError("missing_optional does not match available context")
        if any(item.provenance.provider_available_at > self.as_of for item in self.data):
            raise ValueError("context contains evidence unavailable at as_of")
        if any(item.provenance.ingested_at > self.as_of for item in self.data):
            raise ValueError("context contains evidence ingested after as_of")
        identities = tuple(
            (item.capability, item.instrument, item.name, item.provenance.source_id)
            for item in self.data
        )
        if len(identities) != len(set(identities)):
            raise ValueError("context data identities must be unique")
        expected = context_identity(self)
        if self.context_id and self.context_id != expected:
            raise ValueError("context_id does not match context contents")
        object.__setattr__(self, "context_id", expected)
        return self

    @property
    def available_capabilities(self) -> frozenset[ContextCapability]:
        return frozenset(
            {ContextCapability.PRICE_HISTORY, *(item.capability for item in self.data)}
        )


def context_identity(context: MarketContext) -> str:
    material = {
        "snapshot_id": context.snapshot.snapshot_id,
        "as_of": context.as_of.isoformat(),
        "data": [
            _plain_json(item.model_dump(mode="python", warnings=False))
            for item in context.data
        ],
        "required": sorted(item.value for item in context.requested_required),
        "optional": sorted(item.value for item in context.requested_optional),
        "missing_required": sorted(item.value for item in context.missing_required),
        "missing_optional": sorted(item.value for item in context.missing_optional),
    }
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
    if isinstance(value, StrEnum):
        return value.value
    return value
