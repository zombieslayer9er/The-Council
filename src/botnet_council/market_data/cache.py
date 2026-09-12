"""Exact-request Parquet cache with version and content-integrity validation."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import ValidationError

from botnet_council.market_data.models import (
    AvailabilityRange,
    DataQualityReport,
    HistoricalBars,
    HistoricalRequest,
    ProviderId,
    historical_cache_key,
    historical_content_identity,
)
from botnet_council.market_data.quality import MarketDataQualityError, normalize_and_assess
from botnet_council.schemas import MarketBar

CACHE_FORMAT_VERSION = "3"


class CacheIntegrityError(MarketDataQualityError):
    """A cache artifact failed deterministic content or metadata validation."""


class ParquetMarketDataCache:
    def __init__(self, root: Path) -> None:
        self._root = root

    def path_for(self, provider: ProviderId, request: HistoricalRequest) -> Path:
        start = int(request.start.timestamp())
        end = int(request.end.timestamp())
        request_key = historical_cache_key(provider, request)
        root = self._root / provider.value
        if request.market:
            root /= request.market
        return (
            root
            / request.instrument.symbol.replace("/", "-")
            / request.timeframe.value
            / (f"{start}-{end}-{request_key}.parquet")
        )

    def load(
        self,
        provider: ProviderId,
        request: HistoricalRequest,
        *,
        expected_source_version: str | None = None,
        expected_adapter_semantic_version: str | None = None,
    ) -> HistoricalBars | None:
        path = self.path_for(provider, request)
        if not path.exists():
            return None
        try:
            table = pq.read_table(path)
            metadata = table.schema.metadata or {}
            if self._metadata_text(metadata, "cache_format_version") != CACHE_FORMAT_VERSION:
                return None
            stored_provider = ProviderId(self._metadata_text(metadata, "provider"))
            stored_request = HistoricalRequest.model_validate_json(
                self._metadata_text(metadata, "request")
            )
            source_version = self._metadata_text(metadata, "source_version")
            adapter_version = self._metadata_text(metadata, "adapter_semantic_version")
            if stored_provider is not provider or stored_request != request:
                return None
            if expected_source_version is not None and source_version != expected_source_version:
                return None
            if (
                expected_adapter_semantic_version is not None
                and adapter_version != expected_adapter_semantic_version
            ):
                return None
            bars = tuple(self._row_to_bar(row) for row in table.to_pylist())
            quality = DataQualityReport.model_validate_json(
                self._metadata_text(metadata, "quality")
            )
            result = HistoricalBars(
                provider=stored_provider,
                request=stored_request,
                fetched_at=datetime.fromisoformat(self._metadata_text(metadata, "fetched_at")),
                bars=bars,
                quality=quality,
                source_version=source_version,
                adapter_semantic_version=adapter_version,
                cache_key=self._metadata_text(metadata, "cache_key"),
            )
            expected_digest = self._metadata_text(metadata, "integrity_digest")
            if self._digest(result) != expected_digest:
                raise CacheIntegrityError("cached market-data digest mismatch")
            self._verify_content_quality(result)
            return result
        except CacheIntegrityError:
            raise
        except (
            KeyError,
            OSError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
            ValidationError,
            pa.ArrowException,
        ) as error:
            raise CacheIntegrityError("invalid or corrupted market-data cache") from error

    def store(self, result: HistoricalBars) -> Path:
        # Exact-request artifacts are intentionally not composed with neighboring files.
        self._verify_content_quality(result)
        if not result.quality.coverage_complete:
            raise MarketDataQualityError("refusing to cache incomplete historical coverage")
        path = self.path_for(result.provider, result.request)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = self.load(result.provider, result.request)
            if existing is None:
                raise CacheIntegrityError("refusing to overwrite incompatible cache artifact")
            if historical_content_identity(existing) != historical_content_identity(result):
                raise CacheIntegrityError("refusing to overwrite immutable cache artifact")
            return path
        metadata = {
            b"cache_format_version": CACHE_FORMAT_VERSION.encode(),
            b"provider": result.provider.value.encode(),
            b"request": result.request.model_dump_json().encode(),
            b"fetched_at": result.fetched_at.isoformat().encode(),
            b"quality": result.quality.model_dump_json().encode(),
            b"source_version": result.source_version.encode(),
            b"adapter_semantic_version": result.adapter_semantic_version.encode(),
            b"cache_key": result.cache_key.encode(),
            b"integrity_digest": self._digest(result).encode(),
        }
        table = pa.Table.from_pylist([self._bar_to_row(bar) for bar in result.bars])
        table = table.replace_schema_metadata(metadata)
        temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        pq.write_table(table, temporary, compression="zstd")
        temporary.replace(path)
        return path

    def inspect_availability(
        self,
        provider: ProviderId,
        instrument: object,
        timeframe: object,
        *,
        market: str = "",
        expected_source_version: str | None = None,
        expected_adapter_semantic_version: str | None = None,
    ) -> tuple[AvailabilityRange, ...]:
        """Return contiguous ranges proven by validated immutable artifacts."""
        from botnet_council.market_data.models import Instrument, Timeframe

        if not isinstance(instrument, Instrument) or not isinstance(timeframe, Timeframe):
            raise TypeError("instrument and timeframe must use canonical market-data types")
        bars = self._validated_bars(
            provider,
            instrument,
            timeframe,
            market=market,
            expected_source_version=expected_source_version,
            expected_adapter_semantic_version=expected_adapter_semantic_version,
        )
        if not bars:
            return ()
        bounds: list[tuple[datetime, datetime]] = []
        start, end = bars[0].opened_at, bars[0].closed_at
        for bar in bars[1:]:
            if bar.opened_at == end:
                end = bar.closed_at
            else:
                bounds.append((start, end))
                start, end = bar.opened_at, bar.closed_at
        bounds.append((start, end))
        return tuple(
            AvailabilityRange(
                provider=provider,
                market=market,
                instrument=instrument,
                timeframe=timeframe,
                start=start,
                end=end,
                source_version=expected_source_version or "mixed",
                adapter_semantic_version=expected_adapter_semantic_version or "mixed",
            )
            for start, end in bounds
        )

    def load_range(
        self,
        provider: ProviderId,
        request: HistoricalRequest,
        *,
        expected_source_version: str,
        expected_adapter_semantic_version: str,
    ) -> HistoricalBars | None:
        results = self._validated_results(
            provider,
            request.instrument,
            request.timeframe,
            market=request.market,
            expected_source_version=expected_source_version,
            expected_adapter_semantic_version=expected_adapter_semantic_version,
        )
        bars = tuple(
            bar
            for result in results
            for bar in result.bars
            if request.start <= bar.opened_at < request.end and bar.available_at <= request.as_of
        )
        ordered, quality = normalize_and_assess(
            bars,
            request.timeframe,
            request_start=request.start,
            request_end=request.end,
        )
        if not quality.coverage_complete:
            return None
        return HistoricalBars(
            provider=provider,
            request=request,
            fetched_at=max(result.fetched_at for result in results),
            bars=ordered,
            quality=quality,
            source_version=expected_source_version,
            adapter_semantic_version=expected_adapter_semantic_version,
        )

    def missing_ranges(
        self,
        provider: ProviderId,
        request: HistoricalRequest,
        *,
        expected_source_version: str,
        expected_adapter_semantic_version: str,
    ) -> tuple[HistoricalRequest, ...]:
        cached_opens = {
            bar.opened_at
            for bar in self._validated_bars(
                provider,
                request.instrument,
                request.timeframe,
                market=request.market,
                expected_source_version=expected_source_version,
                expected_adapter_semantic_version=expected_adapter_semantic_version,
            )
            if request.start <= bar.opened_at < request.end and bar.available_at <= request.as_of
        }
        missing: list[HistoricalRequest] = []
        cursor = request.start
        range_start: datetime | None = None
        while cursor < request.end:
            if cursor not in cached_opens and range_start is None:
                range_start = cursor
            elif cursor in cached_opens and range_start is not None:
                missing.append(request.model_copy(update={"start": range_start, "end": cursor}))
                range_start = None
            cursor += request.timeframe.duration
        if range_start is not None:
            missing.append(request.model_copy(update={"start": range_start, "end": request.end}))
        return tuple(missing)

    def _validated_bars(
        self,
        provider: ProviderId,
        instrument: object,
        timeframe: object,
        market: str = "",
        **versions: str | None,
    ) -> tuple[MarketBar, ...]:
        by_open: dict[datetime, MarketBar] = {}
        for result in self._validated_results(
            provider, instrument, timeframe, market=market, **versions
        ):
            for bar in result.bars:
                previous = by_open.get(bar.opened_at)
                if previous is not None and previous != bar:
                    raise CacheIntegrityError(
                        f"conflicting cached candle at {bar.opened_at.isoformat()}"
                    )
                by_open[bar.opened_at] = bar
        return tuple(by_open[key] for key in sorted(by_open))

    def _validated_results(
        self,
        provider: ProviderId,
        instrument: object,
        timeframe: object,
        *,
        market: str = "",
        expected_source_version: str | None = None,
        expected_adapter_semantic_version: str | None = None,
    ) -> tuple[HistoricalBars, ...]:
        from botnet_council.market_data.models import Instrument, Timeframe

        if not isinstance(instrument, Instrument) or not isinstance(timeframe, Timeframe):
            raise TypeError("instrument and timeframe must use canonical market-data types")
        root = self._root / provider.value
        if market:
            root /= market
        directory = root / instrument.symbol.replace("/", "-") / timeframe.value
        results: list[HistoricalBars] = []
        for path in sorted(directory.glob("*.parquet")):
            try:
                metadata = pq.read_metadata(path).metadata or {}
                stored = HistoricalRequest.model_validate_json(
                    self._metadata_text(metadata, "request")
                )
                if stored.market != market:
                    continue
            except (OSError, ValueError, ValidationError, pa.ArrowException) as error:
                raise CacheIntegrityError("invalid or corrupted market-data cache") from error
            loaded = self.load(
                provider,
                stored,
                expected_source_version=expected_source_version,
                expected_adapter_semantic_version=expected_adapter_semantic_version,
            )
            if loaded is not None:
                results.append(loaded)
        return tuple(results)

    @staticmethod
    def _verify_content_quality(result: HistoricalBars) -> None:
        _, recomputed = normalize_and_assess(
            result.bars,
            result.request.timeframe,
            request_start=result.request.start,
            request_end=result.request.end,
        )
        stored = result.quality
        stored_content = (
            stored.output_rows,
            stored.gaps,
            stored.expected_intervals,
            stored.leading_missing_intervals,
            stored.trailing_missing_intervals,
            stored.coverage_complete,
        )
        recomputed_content = (
            recomputed.output_rows,
            recomputed.gaps,
            recomputed.expected_intervals,
            recomputed.leading_missing_intervals,
            recomputed.trailing_missing_intervals,
            recomputed.coverage_complete,
        )
        if stored_content != recomputed_content:
            raise CacheIntegrityError("cached data-quality metadata does not match candle contents")

    @staticmethod
    def _digest(result: HistoricalBars) -> str:
        material = {
            "cache_format_version": CACHE_FORMAT_VERSION,
            "provider": result.provider.value,
            "request": result.request.model_dump(mode="json"),
            "fetched_at": result.fetched_at.isoformat(),
            "quality": result.quality.model_dump(mode="json"),
            "source_version": result.source_version,
            "adapter_semantic_version": result.adapter_semantic_version,
            "cache_key": result.cache_key,
            "bars": [
                {
                    "opened_at": bar.opened_at.isoformat(),
                    "closed_at": bar.closed_at.isoformat(),
                    "available_at": bar.available_at.isoformat(),
                    "open": bar.open.hex(),
                    "high": bar.high.hex(),
                    "low": bar.low.hex(),
                    "close": bar.close.hex(),
                    "volume": bar.volume.hex(),
                }
                for bar in result.bars
            ],
        }
        canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _metadata_text(metadata: dict[bytes, bytes], key: str) -> str:
        try:
            return metadata[key.encode()].decode()
        except KeyError as error:
            raise CacheIntegrityError(f"cache metadata is missing {key}") from error

    @staticmethod
    def _bar_to_row(bar: MarketBar) -> dict[str, Any]:
        return {
            "opened_at": bar.opened_at.isoformat(),
            "closed_at": bar.closed_at.isoformat(),
            "available_at": bar.available_at.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }

    @staticmethod
    def _row_to_bar(row: dict[str, Any]) -> MarketBar:
        try:
            return MarketBar(
                opened_at=datetime.fromisoformat(cast(str, row["opened_at"])),
                closed_at=datetime.fromisoformat(cast(str, row["closed_at"])),
                available_at=datetime.fromisoformat(cast(str, row["available_at"])),
                open=cast(float, row["open"]),
                high=cast(float, row["high"]),
                low=cast(float, row["low"]),
                close=cast(float, row["close"]),
                volume=cast(float, row["volume"]),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise CacheIntegrityError("invalid cached market-data row") from error
