"""Caching decorator for a historical market-data provider."""

from __future__ import annotations

from datetime import UTC, datetime

from botnet_council.market_data.base import HistoricalMarketDataProvider
from botnet_council.market_data.cache import ParquetMarketDataCache
from botnet_council.market_data.models import (
    Asset,
    HistoricalBars,
    HistoricalRequest,
    Instrument,
    ProviderMetadata,
    Timeframe,
)
from botnet_council.schemas import MarketSnapshot, SnapshotProvenance


class CachedHistoricalProvider:
    def __init__(
        self, provider: HistoricalMarketDataProvider, cache: ParquetMarketDataCache
    ) -> None:
        self._provider = provider
        self._cache = cache

    @property
    def metadata(self) -> ProviderMetadata:
        return self._provider.metadata

    @property
    def source_version(self) -> str:
        return self._provider.source_version

    @property
    def adapter_semantic_version(self) -> str:
        return self._provider.adapter_semantic_version

    def fetch_historical(self, request: HistoricalRequest) -> HistoricalBars:
        cached = self._cache.load(
            self.metadata.provider,
            request,
            expected_source_version=self.source_version,
            expected_adapter_semantic_version=self.adapter_semantic_version,
        )
        if (
            cached is not None
            and cached.quality.coverage_complete
            and request.end <= cached.fetched_at
        ):
            return cached
        composed = self._cache.load_range(
            self.metadata.provider,
            request,
            expected_source_version=self.source_version,
            expected_adapter_semantic_version=self.adapter_semantic_version,
        )
        if composed is not None:
            self._cache.store(composed)
            return composed
        missing = self._cache.missing_ranges(
            self.metadata.provider,
            request,
            expected_source_version=self.source_version,
            expected_adapter_semantic_version=self.adapter_semantic_version,
        ) or (request,)
        for part in missing:
            result = self._provider.fetch_historical(part)
            if result.source_version != self.source_version:
                raise ValueError(
                    "provider result source version does not match provider capability"
                )
            if result.adapter_semantic_version != self.adapter_semantic_version:
                raise ValueError(
                    "provider result adapter version does not match provider capability"
                )
            self._cache.store(result)
        loaded = self._cache.load_range(
            self.metadata.provider,
            request,
            expected_source_version=self.source_version,
            expected_adapter_semantic_version=self.adapter_semantic_version,
        )
        if loaded is None:
            raise ValueError("provider returned incomplete historical coverage")
        self._cache.store(loaded)
        return loaded

    def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> MarketSnapshot:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        as_of = as_of.astimezone(UTC)
        try:
            base, quote = symbol.split("/", maxsplit=1)
            instrument = Instrument(base=Asset(base), quote=Asset(quote))
            selected_timeframe = Timeframe(timeframe)
        except ValueError as error:
            raise ValueError(
                f"unsupported canonical market identity {symbol} {timeframe}"
            ) from error
        request = HistoricalRequest(
            instrument=instrument,
            timeframe=selected_timeframe,
            start=as_of - selected_timeframe.duration * self.metadata.maximum_rows,
            end=as_of,
            as_of=as_of,
        )
        result = self.fetch_historical(request)
        if not result.bars:
            raise LookupError(f"no causally available bars for {symbol} {timeframe} at cutoff")
        latest = result.bars[-1]
        provenance = SnapshotProvenance(
            provider=result.provider.value,
            instrument=instrument.symbol,
            timeframe=selected_timeframe.value,
            requested_start=request.start,
            requested_end=request.end,
            as_of=request.as_of,
            fetched_at=result.fetched_at,
            latest_observation_time=latest.closed_at,
            latest_available_at=latest.available_at,
            source_version=result.source_version,
            adapter_semantic_version=result.adapter_semantic_version,
            coverage_complete=result.quality.coverage_complete,
            cache_key=result.cache_key,
        )
        return MarketSnapshot(
            symbol=instrument.symbol,
            timeframe=selected_timeframe.value,
            as_of=as_of,
            observed_at=as_of,
            bars=result.bars,
            provenance=provenance,
        )
