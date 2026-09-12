# Historical acquisition and scenario API

The V1 historical pipeline keeps exchange download mechanics outside the Council:

```text
Freqtrade data-only process
  -> FreqtradeHistoricalProvider.normalize()
  -> CachedHistoricalProvider
  -> immutable Parquet ranges
  -> BacktestEngine
  -> Council snapshots containing only bars available at simulation time
  -> post-run evaluation and persisted artifacts
```

Freqtrade never supplies domain objects to agents. Its downloaded Feather, Parquet, or
JSON rows are converted to canonical `MarketBar` and `HistoricalBars` contracts first.
The default API composition uses the pinned `freqtrade-data` Compose service from
`integrations/freqtrade/compose.yaml`; it does not enable live trading or credentials.

## Cache behavior

Cache identity includes provider, exchange/market, pair, timeframe, exact requested
range, causal `as_of`, source version, adapter semantic version, quality metadata, and a
digest over all OHLCV and availability timestamps. Cache format 3 separates exchange
directories and rejects older identities rather than silently replaying them.

For a partial overlap, the cache validates all matching immutable artifacts, computes
the absent candle intervals, downloads only those ranges, and composes a new exact
snapshot. Conflicting candles for one opening timestamp are integrity errors. Missing
candles are never filled or interpolated.

## HTTP workflow

Read routes:

- `GET /api/historical/providers`
- `GET /api/historical/providers/{provider}/markets/{market}/pairs`
- `GET /api/historical/cache?provider=...&market=...&instrument=...&timeframe=...`
- `GET /api/historical/scenarios/{scenario_id}`
- `GET /api/historical/operations/{operation_id}`
- `GET /api/historical/operations/{operation_id}/result`
- `GET /api/historical/operations/{operation_id}/candles`
- `GET /api/historical/operations/{operation_id}/council`
- `GET /api/historical/operations/{operation_id}/judge`

Mutation routes use the same bearer token and trusted-browser-origin boundary as other
control operations:

- `POST /api/control/historical/acquisitions` queues missing-data acquisition.
- `POST /api/control/historical/scenarios` stores an immutable scenario definition.
- `POST /api/control/historical/scenarios/{scenario_id}/runs` queues a backtest.
- `POST /api/control/historical/operations/{operation_id}/cancel` requests cancellation.

Set `BOTNET_COUNCIL_CONTROL_TOKEN` to a value of at least 32 characters. POST requests
return immediately with an operation whose status is `queued`, `running`, `completed`,
`cancelled`, or `failed`. Poll the operation route for bounded progress fields.

A scenario embeds `BacktestConfig`, plus provider, exchange/market, deterministic seed,
and an optional `blind_window_bars`. `decision_cadence_bars` controls deterministic
Council evaluation cadence. Blind selection uses only the count and timestamps of
available rows plus the declared seed; it never scores or selects on OHLCV outcomes.

## Causality and persistence

The engine may hold the complete immutable input snapshot, but each specialist receives
only a `MarketSnapshot` whose bars satisfy `available_at <= simulation_time`. Orders fill
only on a strictly later opening. Cancellation is checked at deterministic event
boundaries, and frontend playback speed never enters the engine.

Scenario definitions, operation records, complete run objects, JSON summaries, and
Parquet event/equity/trade artifacts are stored under `historical-results/`. Completed
operations and their result endpoints survive an API restart. The candle endpoint reloads
the exact cache artifact named by run provenance; the Council endpoint returns only frozen
decisions, while the judge endpoint exposes post-run metrics and benchmark evaluation.
