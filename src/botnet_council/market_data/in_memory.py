from dataclasses import dataclass
from datetime import UTC, datetime

from botnet_council.schemas import MarketSnapshot


@dataclass(frozen=True, slots=True)
class InMemoryMarketDataProvider:
    snapshots: dict[tuple[str, str], MarketSnapshot]

    def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> MarketSnapshot:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        as_of = as_of.astimezone(UTC)
        try:
            source = self.snapshots[(symbol, timeframe)]
        except KeyError as error:
            raise LookupError(f"no snapshot for {symbol} {timeframe}") from error
        bars = tuple(bar for bar in source.bars if bar.closed_at <= as_of)
        if not bars:
            raise LookupError(f"no completed bars for {symbol} {timeframe} at cutoff")
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            as_of=as_of,
            observed_at=as_of,
            bars=bars,
        )
