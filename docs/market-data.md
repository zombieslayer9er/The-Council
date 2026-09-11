# Historical market data

V0.1 uses Kraken Spot's public REST `OHLC` endpoint. It needs no API key and supports
BTC and ETH with USD or USDT quotes. Canonical timeframes are `1m`, `5m`, `15m`, `1h`,
`4h`, and `1d`; the adapter translates these to Kraken's documented minute intervals
1, 5, 15, 60, 240, and 1440.

## Causal timestamp translation

The translation is explicit in `KrakenHistoricalProvider._normalize_row`:

- Kraken row element 0 is interpreted as Unix seconds at interval start.
- `closed_at` is `opened_at + requested interval`.
- Kraken documents that the final OHLC array entry is always the current,
  not-yet-committed timeframe, regardless of `since`. The adapter discards that row
  by its position in each response, not by inspecting its timestamp or a field name.
- Kraken supplies no candle publication timestamp. For the remaining committed rows,
  V0.1 conservatively declares `available_at = closed_at`. This is an adapter policy
  derived from Kraken's commitment rule, not a claim of sub-second publication timing.
- A query includes a row only when `available_at <= as_of`, `opened_at >= start`, and
  `opened_at < end`. Thus a current/incomplete or future candle cannot enter a snapshot.

Provider documentation: [Kraken Get OHLC Data](https://docs.kraken.com/api-reference/market-data/get-ohlc-data).

## Quality and gaps

All times normalize to UTC. Malformed, non-finite, negative-price/volume, impossible
OHLC, conflicting-duplicate, duration-mismatched, and overlapping rows are invalid and
raise `MarketDataQualityError`. Identical duplicates are removed and reported. Input
ordering is reported and normalized. Missing intervals appear as `DataGap` values;
there is no filling or interpolation.

## Cache and provenance

Normalized bars are stored as Zstandard-compressed Parquet at:

`<root>/<provider>/<base>-<quote>/<timeframe>/<start>-<end>-<request-key>.parquet`

Each file is an exact-request artifact. Neighboring range files are never merged into
it, so cache history cannot alter its candles or assign a new fetch's provenance to old
rows. Parquet metadata records format version, typed request (including `as_of`), fetch
time, quality report, provider source version, adapter semantic version, and cache key.
Snapshot provenance also exposes source and adapter versions and whether requested
coverage is complete.

The cache stores a SHA-256 digest over canonical candle timestamps and hexadecimal
floating-point values plus the cache schema, request, provider, fetch provenance,
quality report, source version, adapter semantic version, and cache key. Loads verify
that digest and independently recompute content-derived quality and coverage from the
Parquet rows. A malformed file or mismatch raises `CacheIntegrityError`; cache schema,
source-version, or adapter-semantic-version mismatches are cache misses.

## Coverage and refresh policy

Quality reports distinguish `leading_missing_intervals`, internal `gaps`, and
`trailing_missing_intervals` across the requested `[start, end)` range.
`coverage_complete` is true only when the range is interval-aligned and every expected
interval is present. Internally contiguous data can therefore still be incomplete.

An entry is reusable without a provider call only when coverage is complete and its
recorded fetch occurred at or after the requested range end. Such a fully closed,
validated range is immutable. Empty, partial, not-yet-closed, version-stale, or
semantically stale entries are refreshed on every subsequent request. A refreshed
response replaces only the artifact for that exact request.

## Manual integration command

This read-only command downloads a small historical range and constructs a validated
snapshot. Pick a recent range: Kraken returns at most the most recent 720 entries.

```powershell
python -m botnet_council download-market-data `
  --symbol BTC/USD --timeframe 1h `
  --start 2026-09-08T00:00:00Z --end 2026-09-09T00:00:00Z
```

## Known limitations

- Kraken's endpoint returns at most 720 recent entries and cannot retrieve older data,
  regardless of `since`; this adapter cannot provide deep history from this endpoint.
- There is no provider publication timestamp. `available_at=closed_at` is the stated
  V0.1 convention for committed historical rows.
- No live feed, websocket, order book, credentials, automatic gap repair, or backtest
  engine is included.
