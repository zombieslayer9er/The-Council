from datetime import datetime
from typing import Protocol, runtime_checkable

from botnet_council.schemas import MarketSnapshot


@runtime_checkable
class MarketDataProvider(Protocol):
    def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> MarketSnapshot: ...
