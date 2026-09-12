from dataclasses import dataclass
from datetime import UTC, datetime

from botnet_council.market_data.models import (
    HistoricalBars,
    HistoricalRequest,
    Instrument,
    ProviderId,
    ProviderMetadata,
    Timeframe,
)
from botnet_council.market_data.quality import normalize_and_assess
from botnet_council.schemas import MarketBar, MarketSnapshot


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
        bars = tuple(bar for bar in source.bars if bar.available_at <= as_of)
        if not bars:
            raise LookupError(f"no completed bars for {symbol} {timeframe} at cutoff")
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            as_of=as_of,
            observed_at=as_of,
            bars=bars,
        )


@dataclass(frozen=True, slots=True)
class InMemoryHistoricalProvider:
    """Deterministic historical provider for synthetic research fixtures."""

    instrument: Instrument
    timeframe: Timeframe
    bars: tuple[MarketBar, ...]
    fetched_at: datetime

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider=ProviderId.IN_MEMORY,
            display_name="In-memory historical data",
            supported_instruments=(self.instrument,),
            supported_timeframes=(self.timeframe,),
            maximum_rows=max(1, len(self.bars)),
            requires_credentials=False,
            timestamp_convention="bar interval open and close in UTC",
            availability_convention="explicit per-bar available_at",
        )

    @property
    def source_version(self) -> str:
        return "in-memory-v1"

    @property
    def adapter_semantic_version(self) -> str:
        return "1"

    def fetch_historical(self, request: HistoricalRequest) -> HistoricalBars:
        if request.instrument != self.instrument or request.timeframe is not self.timeframe:
            raise ValueError("in-memory provider does not support the requested market")
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
            fetched_at=self.fetched_at,
            bars=normalized,
            quality=quality,
            source_version=self.source_version,
            adapter_semantic_version=self.adapter_semantic_version,
        )

    def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> MarketSnapshot:
        if symbol != self.instrument.symbol or timeframe != self.timeframe.value:
            raise LookupError(f"no snapshot for {symbol} {timeframe}")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(UTC)
        bars = tuple(bar for bar in self.bars if bar.available_at <= cutoff)
        if not bars:
            raise LookupError(f"no completed bars for {symbol} {timeframe} at cutoff")
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            as_of=cutoff,
            observed_at=cutoff,
            bars=bars,
        )
