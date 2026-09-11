"""Typed, provider-neutral identities and historical market-data results."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from botnet_council.schemas import MarketBar


class ProviderId(StrEnum):
    KRAKEN = "kraken"
    IN_MEMORY = "in_memory"


class Asset(StrEnum):
    BTC = "BTC"
    ETH = "ETH"
    USD = "USD"
    USDT = "USDT"


class Timeframe(StrEnum):
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"

    @property
    def duration(self) -> timedelta:
        return {
            Timeframe.MINUTE_1: timedelta(minutes=1),
            Timeframe.MINUTE_5: timedelta(minutes=5),
            Timeframe.MINUTE_15: timedelta(minutes=15),
            Timeframe.HOUR_1: timedelta(hours=1),
            Timeframe.HOUR_4: timedelta(hours=4),
            Timeframe.DAY_1: timedelta(days=1),
        }[self]


class MarketDataModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Instrument(MarketDataModel):
    base: Asset
    quote: Asset

    @model_validator(mode="after")
    def distinct_assets(self) -> Self:
        if self.base is self.quote:
            raise ValueError("instrument base and quote must differ")
        if self.base not in (Asset.BTC, Asset.ETH):
            raise ValueError("V0.1 supports BTC and ETH base assets only")
        if self.quote not in (Asset.USD, Asset.USDT):
            raise ValueError("V0.1 supports USD and USDT quote assets only")
        return self

    @property
    def symbol(self) -> str:
        return f"{self.base.value}/{self.quote.value}"


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


class HistoricalRequest(MarketDataModel):
    instrument: Instrument
    timeframe: Timeframe
    start: datetime
    end: datetime
    as_of: datetime

    @field_validator("start", "end", "as_of")
    @classmethod
    def normalize_time(cls, value: datetime, info: ValidationInfo) -> datetime:
        return _utc(value, info.field_name or "datetime")

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError("historical range end must be after start")
        return self


class ProviderMetadata(MarketDataModel):
    provider: ProviderId
    display_name: str
    supported_instruments: tuple[Instrument, ...]
    supported_timeframes: tuple[Timeframe, ...]
    maximum_rows: Annotated[int, Field(gt=0)]
    requires_credentials: bool
    timestamp_convention: str
    availability_convention: str


class DataGap(MarketDataModel):
    after: datetime
    before: datetime
    missing_intervals: Annotated[int, Field(gt=0)]

    @field_validator("after", "before")
    @classmethod
    def normalize_time(cls, value: datetime, info: ValidationInfo) -> datetime:
        return _utc(value, info.field_name or "datetime")


class DataQualityReport(MarketDataModel):
    input_rows: Annotated[int, Field(ge=0)]
    output_rows: Annotated[int, Field(ge=0)]
    duplicate_rows_removed: Annotated[int, Field(ge=0)] = 0
    input_was_out_of_order: bool = False
    gaps: tuple[DataGap, ...] = ()
    expected_intervals: Annotated[int, Field(ge=0)] = 0
    leading_missing_intervals: Annotated[int, Field(ge=0)] = 0
    trailing_missing_intervals: Annotated[int, Field(ge=0)] = 0
    coverage_complete: bool = False


class HistoricalBars(MarketDataModel):
    provider: ProviderId
    request: HistoricalRequest
    fetched_at: datetime
    bars: tuple[MarketBar, ...]
    quality: DataQualityReport
    source_version: str
    adapter_semantic_version: str
    cache_key: str = ""

    @field_validator("fetched_at")
    @classmethod
    def normalize_fetched_at(cls, value: datetime) -> datetime:
        return _utc(value, "fetched_at")

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if any(bar.available_at > self.request.as_of for bar in self.bars):
            raise ValueError("historical result contains data unavailable at as_of")
        if any(
            bar.opened_at < self.request.start or bar.opened_at >= self.request.end
            for bar in self.bars
        ):
            raise ValueError("historical result contains data outside requested range")
        intervals = tuple((bar.opened_at, bar.closed_at) for bar in self.bars)
        if intervals != tuple(sorted(intervals)) or len(intervals) != len(set(intervals)):
            raise ValueError("historical bars must be unique and chronological")
        key = historical_cache_key(self.provider, self.request)
        if self.cache_key and self.cache_key != key:
            raise ValueError("cache_key does not match historical request")
        object.__setattr__(self, "cache_key", key)
        return self


def historical_cache_key(provider: ProviderId, request: HistoricalRequest) -> str:
    material = (
        f"{provider.value}|{request.instrument.symbol}|{request.timeframe.value}|"
        f"{request.start.isoformat()}|{request.end.isoformat()}|{request.as_of.isoformat()}"
    )
    return sha256(material.encode()).hexdigest()[:24]
