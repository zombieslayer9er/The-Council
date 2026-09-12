from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from botnet_council.market_data.models import (
    AvailabilityRange,
    HistoricalBars,
    HistoricalRequest,
    Instrument,
    ProviderMetadata,
    Timeframe,
)
from botnet_council.schemas import MarketSnapshot


@runtime_checkable
class MarketDataProvider(Protocol):
    def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> MarketSnapshot: ...


@runtime_checkable
class HistoricalMarketDataProvider(MarketDataProvider, Protocol):
    @property
    def metadata(self) -> ProviderMetadata: ...

    @property
    def source_version(self) -> str: ...

    @property
    def adapter_semantic_version(self) -> str: ...

    def fetch_historical(self, request: HistoricalRequest) -> HistoricalBars: ...


@runtime_checkable
class HistoricalDataProvider(HistoricalMarketDataProvider, Protocol):
    """Discovery and acquisition boundary for substantial historical datasets."""

    def list_markets(self) -> tuple[str, ...]: ...

    def list_pairs(self, market: str) -> tuple[Instrument, ...]: ...

    def inspect_availability(
        self, market: str, instrument: Instrument, timeframe: Timeframe
    ) -> tuple[AvailabilityRange, ...]: ...

    def fetch_range(self, request: HistoricalRequest) -> HistoricalBars: ...

    def normalize(
        self, rows: Iterable[Mapping[str, Any]], request: HistoricalRequest
    ) -> HistoricalBars: ...
