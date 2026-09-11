from datetime import datetime
from typing import Protocol, runtime_checkable

from botnet_council.market_data.models import HistoricalBars, HistoricalRequest, ProviderMetadata
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
