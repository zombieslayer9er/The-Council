"""Kraken Spot REST OHLC adapter with explicit causal timestamp translation."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from math import isfinite
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import ValidationError

from botnet_council.market_data.models import (
    Asset,
    HistoricalBars,
    HistoricalRequest,
    Instrument,
    ProviderId,
    ProviderMetadata,
    Timeframe,
)
from botnet_council.market_data.quality import MarketDataQualityError, normalize_and_assess
from botnet_council.schemas import MarketBar, MarketSnapshot, SnapshotProvenance

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
KRAKEN_SOURCE_VERSION = "spot-rest-ohlc-v1"
KRAKEN_ADAPTER_SEMANTIC_VERSION = "kraken-ohlc-causal-v1"
KRAKEN_INTERVAL_MINUTES: Mapping[Timeframe, int] = {
    Timeframe.MINUTE_1: 1,
    Timeframe.MINUTE_5: 5,
    Timeframe.MINUTE_15: 15,
    Timeframe.HOUR_1: 60,
    Timeframe.HOUR_4: 240,
    Timeframe.DAY_1: 1440,
}


class ProviderError(RuntimeError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class JsonTransport(Protocol):
    def get(self, url: str, params: Mapping[str, str | int]) -> Mapping[str, Any]: ...


class UrllibJsonTransport:
    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self._timeout_seconds = timeout_seconds

    def get(self, url: str, params: Mapping[str, str | int]) -> Mapping[str, Any]:
        request = Request(
            f"{url}?{urlencode(params)}", headers={"User-Agent": "botnet-council/0.1"}
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read())
        except HTTPError as error:
            if error.code == 429:
                raise ProviderRateLimitError("Kraken rate limit exceeded") from error
            raise ProviderError(f"Kraken HTTP error {error.code}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ProviderError("Kraken request failed") from error
        if not isinstance(payload, Mapping):
            raise ProviderError("Kraken returned a non-object response")
        return cast(Mapping[str, Any], payload)


class KrakenHistoricalProvider:
    """Read-only adapter for Kraken's public Spot OHLC endpoint.

    Kraken documents each response's final OHLC row as the current, uncommitted
    timeframe. This adapter removes that row by response position, independently
    of its timestamp. For every remaining committed row, Kraken's first array value
    is translated as interval start; interval end and ``available_at`` are derived
    by adding the requested, documented interval duration.
    """

    def __init__(
        self,
        transport: JsonTransport | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_rate_limit_retries: int = 2,
    ) -> None:
        self._transport = transport or UrllibJsonTransport()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._max_rate_limit_retries = max_rate_limit_retries

    @property
    def metadata(self) -> ProviderMetadata:
        instruments = tuple(
            Instrument(base=base, quote=quote)
            for base in (Asset.BTC, Asset.ETH)
            for quote in (Asset.USD, Asset.USDT)
        )
        return ProviderMetadata(
            provider=ProviderId.KRAKEN,
            display_name="Kraken Spot REST",
            supported_instruments=instruments,
            supported_timeframes=tuple(KRAKEN_INTERVAL_MINUTES),
            maximum_rows=720,
            requires_credentials=False,
            timestamp_convention=(
                "response row[0] is Unix seconds for interval start; interval end is start plus "
                "the requested interval"
            ),
            availability_convention=(
                "the documented final uncommitted row is discarded; committed rows use "
                "available_at=interval_end because Kraken supplies no publication timestamp"
            ),
        )

    @property
    def source_version(self) -> str:
        return KRAKEN_SOURCE_VERSION

    @property
    def adapter_semantic_version(self) -> str:
        return KRAKEN_ADAPTER_SEMANTIC_VERSION

    def fetch_historical(self, request: HistoricalRequest) -> HistoricalBars:
        if request.instrument not in self.metadata.supported_instruments:
            raise ValueError(f"unsupported Kraken instrument {request.instrument.symbol}")
        rows: list[Sequence[Any]] = []
        cursor = int(request.start.timestamp())
        seen_cursors: set[int] = set()
        while cursor not in seen_cursors:
            seen_cursors.add(cursor)
            payload = self._get_with_retry(
                {
                    "pair": request.instrument.symbol,
                    "assetVersion": 1,
                    "interval": KRAKEN_INTERVAL_MINUTES[request.timeframe],
                    "since": cursor,
                }
            )
            page, next_cursor = self._extract_page(payload)
            # Documented API behavior, not a guess from a field name or timestamp:
            # the response's final OHLC row is always current and uncommitted.
            rows.extend(page[:-1] if page else ())
            if next_cursor <= cursor or next_cursor >= int(request.end.timestamp()):
                break
            cursor = next_cursor
        normalized = tuple(self._normalize_row(row, request.timeframe) for row in rows)
        selected = tuple(
            bar
            for bar in normalized
            if request.start <= bar.opened_at < request.end and bar.available_at <= request.as_of
        )
        ordered, quality = normalize_and_assess(
            selected,
            request.timeframe,
            input_rows=len(rows),
            request_start=request.start,
            request_end=request.end,
        )
        return HistoricalBars(
            provider=ProviderId.KRAKEN,
            request=request,
            fetched_at=self._utc_clock(),
            bars=ordered,
            quality=quality,
            source_version=self.source_version,
            adapter_semantic_version=self.adapter_semantic_version,
        )

    def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> MarketSnapshot:
        try:
            base_text, quote_text = symbol.split("/", maxsplit=1)
            instrument = Instrument(base=Asset(base_text), quote=Asset(quote_text))
            selected_timeframe = Timeframe(timeframe)
        except (ValueError, ValidationError) as error:
            raise ValueError(
                f"unsupported canonical market identity {symbol} {timeframe}"
            ) from error
        as_of_utc = self._require_utc(as_of, "as_of")
        start = as_of_utc - selected_timeframe.duration * self.metadata.maximum_rows
        request = HistoricalRequest(
            instrument=instrument,
            timeframe=selected_timeframe,
            start=start,
            end=as_of_utc,
            as_of=as_of_utc,
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
            as_of=as_of_utc,
            observed_at=as_of_utc,
            bars=result.bars,
            provenance=provenance,
        )

    def _get_with_retry(self, params: Mapping[str, str | int]) -> Mapping[str, Any]:
        for attempt in range(self._max_rate_limit_retries + 1):
            try:
                payload = self._transport.get(KRAKEN_OHLC_URL, params)
                errors = payload.get("error")
                if errors and any(
                    "Rate limit" in str(error) or "Throttled" in str(error)
                    for error in cast(Sequence[Any], errors)
                ):
                    raise ProviderRateLimitError("Kraken API rate limit exceeded")
                return payload
            except ProviderRateLimitError:
                if attempt >= self._max_rate_limit_retries:
                    raise
                self._sleep(float(2**attempt))
        raise AssertionError("unreachable")

    @staticmethod
    def _extract_page(payload: Mapping[str, Any]) -> tuple[list[Sequence[Any]], int]:
        errors = payload.get("error")
        if errors:
            message = ", ".join(str(error) for error in cast(Sequence[Any], errors))
            if "Rate limit" in message or "Throttled" in message:
                raise ProviderRateLimitError(message)
            raise ProviderError(f"Kraken API error: {message}")
        result = payload.get("result")
        if not isinstance(result, Mapping) or "last" not in result:
            raise ProviderError("malformed Kraken OHLC result")
        pair_values = [value for key, value in result.items() if key != "last"]
        if len(pair_values) != 1 or not isinstance(pair_values[0], list):
            raise ProviderError("Kraken OHLC result must contain exactly one pair")
        try:
            cursor = int(result["last"])
        except (TypeError, ValueError) as error:
            raise ProviderError("invalid Kraken pagination cursor") from error
        return cast(list[Sequence[Any]], pair_values[0]), cursor

    @staticmethod
    def _normalize_row(row: Sequence[Any], timeframe: Timeframe) -> MarketBar:
        if len(row) < 7:
            raise MarketDataQualityError("malformed Kraken OHLC row")
        try:
            opened_at = datetime.fromtimestamp(int(row[0]), tz=UTC)
            values = tuple(float(row[index]) for index in range(1, 7))
        except (TypeError, ValueError, OSError) as error:
            raise MarketDataQualityError("malformed Kraken OHLC row") from error
        if not all(isfinite(value) for value in values):
            raise MarketDataQualityError("non-finite Kraken OHLC value")
        interval_end = opened_at + timeframe.duration
        try:
            return MarketBar(
                opened_at=opened_at,
                closed_at=interval_end,
                # Kraken does not expose publication time. Per its commitment rule,
                # a non-final row is conservatively usable from the interval boundary.
                available_at=interval_end,
                open=values[0],
                high=values[1],
                low=values[2],
                close=values[3],
                volume=values[5],
            )
        except ValidationError as error:
            raise MarketDataQualityError("invalid Kraken OHLC row") from error

    def _utc_clock(self) -> datetime:
        return self._require_utc(self._clock(), "clock")

    @staticmethod
    def _require_utc(value: datetime, name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
        return value.astimezone(UTC)
