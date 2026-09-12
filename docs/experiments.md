# Blind historical experiments

The experiment subsystem measures forecasts against later historical outcomes while keeping
future observations outside the forecasting object graph. It is research-only and does not place
orders, allocate capital, optimize parameters, or modify agents.

## Information boundary

The forecasting path is `ExperimentContextBuilder -> ExperimentContext -> BlindForecaster`.
`ExperimentContext` contains a cutoff-bound `MarketSnapshot`, an `AgentContext`, and blind-input
provenance. It cannot contain a provider, oracle outcome, future bars, target label, or score.
Every completed bar in the snapshot has `available_at <= evaluation_time`.

The post-lock path is `HistoricalOracle -> OracleOutcome -> evaluate`. `BlindForecaster` has no
oracle dependency or argument. The service persists and reads back the immutable forecast in
`FORECAST_LOCKED` before transitioning to `EVALUATING` and invoking the oracle. The repository
rejects any later change to the forecast or request.

Historical provider objects are deliberately kept out of both `ExperimentContext` and
`AgentContext`. This matters because `fetch_historical(request)` and `snapshot(..., as_of=...)`
allow their caller to choose a range or cutoff and therefore must never be capabilities held by
an agent.

## Lifecycle

The only successful path is:

`CREATED -> CONTEXT_READY -> FORECASTING -> FORECAST_LOCKED -> EVALUATING -> COMPLETE`

Any non-terminal state can transition to `FAILED`. Other transitions are rejected at runtime.
An incomplete oracle horizon produces a persisted incomplete `OracleOutcome`, preserves the
locked forecast, and ends in `FAILED` without an evaluation.

## Price and error conventions

V0.1 uses completed candle closes. The reference price is the close whose `closed_at` equals the
evaluation timestamp. The endpoint is the close whose `closed_at` equals `evaluation_time +
forecast_horizon`. The horizon must be an exact multiple of the timeframe and every interval must
be present and available by the endpoint.

Realized return is `endpoint_close / reference_close - 1`. Maximum favorable excursion is the
largest future-bar high return relative to the reference close; maximum adverse excursion is the
smallest future-bar low return. Signed return error is `forecast_expected_return -
realized_return`; absolute error is its magnitude. Exact zero is `flat`. Confidence calibration
uses transparent 10-percentage-point buckets.

The council's current `expected_return` remains the existing standardized agent/council output.
Some built-in agents derive their own `horizon_bars`; V0.1 records those values alongside the
configured evaluation horizon rather than rescaling or silently treating them as identical.

## Deterministic sampling and batches

Random selection enumerates evaluation timestamps with complete warmup and oracle intervals,
then ranks them by SHA-256 of the seed and timestamp for stable seeded sampling. Eligibility reads timestamps and
`available_at` only; OHLC values and profitability do not affect selection. The seed is copied
into every selected request and the batch result.

Batch output preserves each individual experiment and reports directional accuracy, mean
absolute return error, signed forecast bias, confidence-bucket measurements, and performance by
configuration identity. It performs no fitting or parameter search.

## API separation

Command routes are separate from observational routes:

- `POST /api/control/experiments`
- `POST /api/control/experiments/{experiment_id}/run`
- `POST /api/control/experiment-batches/run`
- `GET /api/experiments`
- `GET /api/experiments/{experiment_id}`
- `GET /api/experiments/{experiment_id}/forecast`
- `GET /api/experiments/{experiment_id}/oracle`
- `GET /api/experiments/{experiment_id}/evaluation`

There is intentionally no endpoint for `ExperimentContext`. Oracle access before the forecast
lock returns a conflict response. The local API defaults to the canonical cached Kraken provider
and persists records under `experiment-results/`; tests can inject the in-memory historical
provider and repository.

Experiment control is disabled unless `BOTNET_COUNCIL_CONTROL_TOKEN` contains at least 32
characters (or an equivalent token is injected into `create_app`). Every command requires that
token as an `Authorization: Bearer ...` credential. Browser requests must additionally supply one
of the localhost Origins in the API allowlist; a supplied untrusted or `null` Origin is rejected.
Non-browser clients may omit Origin but still require the bearer token. Health reports whether
control is enabled, its authentication mode, and the service's active capabilities.
