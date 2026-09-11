from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

from botnet_council.market_data import (
    Asset,
    CachedHistoricalProvider,
    CacheIntegrityError,
    HistoricalRequest,
    Instrument,
    KrakenHistoricalProvider,
    MarketDataQualityError,
    ParquetMarketDataCache,
    ProviderError,
    ProviderRateLimitError,
    Timeframe,
)


def row(
    opened: datetime,
    *,
    open_: object = "100",
    high: object = "110",
    low: object = "90",
    close: object = "105",
    volume: object = "12.5",
) -> list[object]:
    return [int(opened.timestamp()), open_, high, low, close, "101", volume, 10]


class FakeTransport:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[Mapping[str, str | int]] = []

    def get(self, _url: str, params: Mapping[str, str | int]) -> Mapping[str, Any]:
        self.calls.append(params)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[no-any-return]


def response(rows: list[list[object]], last: datetime) -> dict[str, object]:
    return {"error": [], "result": {"BTC/USD": rows, "last": int(last.timestamp())}}


def request(start: datetime, end: datetime, *, as_of: datetime | None = None) -> HistoricalRequest:
    return HistoricalRequest(
        instrument=Instrument(base=Asset.BTC, quote=Asset.USD),
        timeframe=Timeframe.HOUR_1,
        start=start,
        end=end,
        as_of=as_of or end,
    )


def provider(fake: FakeTransport, fetched_at: datetime) -> KrakenHistoricalProvider:
    return KrakenHistoricalProvider(fake, clock=lambda: fetched_at, max_rate_limit_retries=0)


def test_documented_final_uncommitted_row_is_excluded_and_availability_is_explicit() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=3)
    fake = FakeTransport([response([row(start), row(start + timedelta(hours=1))], end)])

    result = provider(fake, end).fetch_historical(request(start, end))

    assert [bar.opened_at for bar in result.bars] == [start]
    assert result.bars[0].closed_at == start + timedelta(hours=1)
    assert result.bars[0].available_at == start + timedelta(hours=1)


def test_as_of_excludes_committed_row_not_yet_causally_available() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=3)
    fake = FakeTransport(
        [
            response(
                [row(start), row(start + timedelta(hours=1)), row(start + timedelta(hours=2))], end
            )
        ]
    )

    result = provider(fake, end).fetch_historical(
        request(start, end, as_of=start + timedelta(hours=1, minutes=59))
    )

    assert [bar.opened_at for bar in result.bars] == [start]


def test_unix_timestamp_is_normalized_to_utc() -> None:
    eastern = timezone(timedelta(hours=-5))
    start = datetime(2025, 12, 31, 19, tzinfo=eastern)
    end = start + timedelta(hours=2)
    fake = FakeTransport([response([row(start), row(start + timedelta(hours=1))], end)])

    result = provider(fake, end).fetch_historical(request(start, end))

    assert result.bars[0].opened_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert result.bars[0].opened_at.tzinfo is UTC


def test_duplicates_and_out_of_order_are_normalized_and_reported() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    later = start + timedelta(hours=1)
    end = start + timedelta(hours=3)
    fake = FakeTransport([response([row(later), row(start), row(start), row(end)], end)])

    result = provider(fake, end).fetch_historical(request(start, end))

    assert [bar.opened_at for bar in result.bars] == [start, later]
    assert result.quality.duplicate_rows_removed == 1
    assert result.quality.input_was_out_of_order is True


def test_conflicting_duplicate_is_invalid() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    fake = FakeTransport([response([row(start), row(start, close="106"), row(end)], end)])

    with pytest.raises(MarketDataQualityError, match="conflicting duplicate"):
        provider(fake, end).fetch_historical(request(start, end))


def test_gap_is_exposed_without_fabrication() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=4)
    fake = FakeTransport([response([row(start), row(start + timedelta(hours=2)), row(end)], end)])

    result = provider(fake, end).fetch_historical(request(start, end))

    assert len(result.bars) == 2
    assert result.quality.gaps[0].missing_intervals == 1


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"high": "80"}, "invalid Kraken OHLC"),
        ({"open_": "nan"}, "non-finite Kraken OHLC"),
        ({"volume": "inf"}, "non-finite Kraken OHLC"),
        ({"volume": "-1"}, "invalid Kraken OHLC"),
    ],
)
def test_invalid_and_non_finite_values_are_rejected(
    changes: dict[str, object], message: str
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    fake = FakeTransport([response([row(start, **changes), row(end)], end)])

    with pytest.raises(MarketDataQualityError, match=message):
        provider(fake, end).fetch_historical(request(start, end))


def test_pagination_pages_merge_deterministically() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    middle = start + timedelta(hours=2)
    end = start + timedelta(hours=4)
    fake = FakeTransport(
        [
            response([row(start), row(start + timedelta(hours=1))], middle),
            response([row(middle), row(middle + timedelta(hours=1))], end),
        ]
    )

    result = provider(fake, end).fetch_historical(request(start, end))

    assert [bar.opened_at for bar in result.bars] == [start, middle]
    assert [call["since"] for call in fake.calls] == [
        int(start.timestamp()),
        int(middle.timestamp()),
    ]


def test_cache_round_trip_preserves_normalized_data_and_provenance(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    fake = FakeTransport([response([row(start), row(end)], end)])
    result = provider(fake, end).fetch_historical(request(start, end))
    cache = ParquetMarketDataCache(tmp_path)

    path = cache.store(result)
    loaded = cache.load(result.provider, result.request)

    assert (
        path
        == tmp_path
        / "kraken"
        / "BTC-USD"
        / "1h"
        / f"{int(start.timestamp())}-{int(end.timestamp())}-{result.cache_key}.parquet"
    )
    assert loaded == result


def test_neighboring_cache_entries_do_not_change_exact_request_result(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    exact_payload = response([row(start), row(start + timedelta(hours=1)), row(end)], end)
    exact = provider(FakeTransport([exact_payload]), end).fetch_historical(request(start, end))
    neighbor_start = start - timedelta(hours=1)
    neighbor_payload = response([row(neighbor_start), row(start, close="106"), row(end)], end)
    neighbor = provider(FakeTransport([neighbor_payload]), end).fetch_historical(
        request(neighbor_start, end)
    )
    cache = ParquetMarketDataCache(tmp_path)

    cache.store(exact)
    cache.store(neighbor)

    assert cache.load(exact.provider, exact.request) == exact


def test_direct_and_cached_provider_results_are_equivalent(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    payload = response([row(start), row(start + timedelta(hours=1)), row(end)], end)
    direct = provider(FakeTransport([payload]), end).fetch_historical(request(start, end))
    cached_provider = CachedHistoricalProvider(
        provider(FakeTransport([payload]), end), ParquetMarketDataCache(tmp_path)
    )

    first = cached_provider.fetch_historical(request(start, end))
    second = cached_provider.fetch_historical(request(start, end))

    assert first == direct
    assert second == direct


def test_source_and_adapter_version_mismatches_invalidate_cache(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    payload = response([row(start), row(start + timedelta(hours=1)), row(end)], end)
    result = provider(FakeTransport([payload]), end).fetch_historical(request(start, end))
    cache = ParquetMarketDataCache(tmp_path)
    cache.store(result)

    assert (
        cache.load(
            result.provider,
            result.request,
            expected_source_version="different-source",
            expected_adapter_semantic_version=result.adapter_semantic_version,
        )
        is None
    )
    assert (
        cache.load(
            result.provider,
            result.request,
            expected_source_version=result.source_version,
            expected_adapter_semantic_version="different-semantics",
        )
        is None
    )


def test_incomplete_cache_entry_refreshes_until_range_is_complete(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=3)
    fake = FakeTransport(
        [
            response([row(start), row(end)], end),
            response(
                [
                    row(start),
                    row(start + timedelta(hours=1)),
                    row(start + timedelta(hours=2)),
                    row(end),
                ],
                end,
            ),
        ]
    )
    cached_provider = CachedHistoricalProvider(
        provider(fake, end), ParquetMarketDataCache(tmp_path)
    )

    partial = cached_provider.fetch_historical(request(start, end))
    complete = cached_provider.fetch_historical(request(start, end))
    reused = cached_provider.fetch_historical(request(start, end))

    assert partial.quality.coverage_complete is False
    assert partial.quality.trailing_missing_intervals == 2
    assert complete.quality.coverage_complete is True
    assert reused == complete
    assert len(fake.calls) == 2


def test_boundary_coverage_reports_leading_trailing_and_complete_ranges() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    leading_payload = response([row(start + timedelta(hours=1)), row(end)], end)
    trailing_payload = response([row(start), row(end)], end)
    complete_payload = response([row(start), row(start + timedelta(hours=1)), row(end)], end)

    leading = provider(FakeTransport([leading_payload]), end).fetch_historical(request(start, end))
    trailing = provider(FakeTransport([trailing_payload]), end).fetch_historical(
        request(start, end)
    )
    complete = provider(FakeTransport([complete_payload]), end).fetch_historical(
        request(start, end)
    )

    assert leading.quality.leading_missing_intervals == 1
    assert leading.quality.trailing_missing_intervals == 0
    assert leading.quality.coverage_complete is False
    assert trailing.quality.leading_missing_intervals == 0
    assert trailing.quality.trailing_missing_intervals == 1
    assert trailing.quality.coverage_complete is False
    assert complete.quality.leading_missing_intervals == 0
    assert complete.quality.trailing_missing_intervals == 0
    assert complete.quality.coverage_complete is True


def test_tampered_cached_ohlcv_value_fails_integrity_check(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    payload = response([row(start), row(start + timedelta(hours=1)), row(end)], end)
    result = provider(FakeTransport([payload]), end).fetch_historical(request(start, end))
    cache = ParquetMarketDataCache(tmp_path)
    path = cache.store(result)
    table = pq.read_table(path)
    rows = table.to_pylist()
    rows[0]["close"] = 106.0
    tampered = pa.Table.from_pylist(rows).replace_schema_metadata(table.schema.metadata)
    pq.write_table(tampered, path)

    with pytest.raises(CacheIntegrityError, match="digest mismatch"):
        cache.load(result.provider, result.request)


def test_repeated_fetches_produce_identical_normalized_bars_and_snapshot_provenance() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    payload = response([row(start), row(end)], end)
    fake = FakeTransport([payload, payload])
    kraken = provider(fake, end)

    first = kraken.fetch_historical(request(start, end))
    second = kraken.fetch_historical(request(start, end))
    snapshot = KrakenHistoricalProvider(
        FakeTransport([payload]), clock=lambda: end, max_rate_limit_retries=0
    ).snapshot("BTC/USD", "1h", as_of=end)

    assert first.bars == second.bars
    assert first.cache_key == second.cache_key
    assert snapshot.provenance is not None
    assert snapshot.provenance.provider == "kraken"
    assert snapshot.provenance.latest_available_at == snapshot.latest_available_at


def test_rate_limit_and_provider_failures_are_typed() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    limited = FakeTransport([ProviderRateLimitError("limited")])
    failed = FakeTransport([{"error": ["EGeneral:Unavailable"], "result": {}}])

    with pytest.raises(ProviderRateLimitError):
        provider(limited, end).fetch_historical(request(start, end))
    with pytest.raises(ProviderError, match="Unavailable"):
        provider(failed, end).fetch_historical(request(start, end))


def test_rate_limit_payload_is_retried_with_backoff() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    fake = FakeTransport(
        [
            {"error": ["EAPI:Rate limit exceeded"], "result": {}},
            response([row(start), row(end)], end),
        ]
    )
    sleeps: list[float] = []
    kraken = KrakenHistoricalProvider(
        fake,
        clock=lambda: end,
        sleep=sleeps.append,
        max_rate_limit_retries=1,
    )

    result = kraken.fetch_historical(request(start, end))

    assert len(result.bars) == 1
    assert sleeps == [1.0]
