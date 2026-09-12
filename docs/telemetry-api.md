# Telemetry and read-only API

Blind experiment commands share the local FastAPI host but are outside the telemetry stream.
Commands live under `/api/control/`; read-only projections live under `/api/experiments`. See
[experiments.md](experiments.md). The API never projects `ExperimentContext` and gates oracle
observations until the forecast has been locked.

Experiment control is disabled by default. Set a strong `BOTNET_COUNCIL_CONTROL_TOKEN` and send
it as a bearer credential to enable command routes. Supplied browser Origins are restricted to
the localhost allowlist. `/api/health` reports `read_only`, `capabilities`, and
`command_authentication` from the effective policy rather than describing the service as always
read-only.

The telemetry package is a one-way projection of the authoritative domain models. The domain
does not import FastAPI, WebSocket, JSON, or frontend code. `ResearchTradingPipeline` and
`BacktestEngine` accept an optional transport-neutral publisher; omitting it retains the original
execution path. Event construction, serialization, storage, and subscriber failures are isolated
from financial decisions.

## Contract

Every event is immutable and uses telemetry schema version `1.1`. Each in-process bus owns an
immutable `stream_id`; `sequence` is assigned monotonically within that generation and is never
derived from retained-history length. A new process creates a new `stream_id`, so its sequence 1
must not be compared with a previous generation. `run_id`, `source_snapshot_id`,
and `correlation_id` join the causal chain; a Council decision ID is the correlation ID from the
Council event through risk, order, execution, and reconciliation. Agent signals have stable
content-derived `signal_id` values and Council payloads reference those IDs.

All timestamps are UTC and timezone-aware. Payloads are explicit allow-listed Pydantic models;
arbitrary Python attributes are never dumped. Snapshot bars and provenance are separate from
signals, Council decisions, risk decisions, execution reports, reconciliations, and portfolio
state. Agent metadata is recursively converted to JSON-safe values and values under common
credential-like keys are replaced with `[REDACTED]` as a defense in depth measure. Pipeline
failure telemetry also passes through one centralized sanitizer: public failures retain a stable
stage code and safe message, while secret assignments and private-looking filesystem paths are
removed. The original exception is re-raised for existing local logging and debugging; its raw
text is never copied into an event payload.

The event types are:

- `pipeline_started`
- `snapshot_created`
- `agent_started`
- `agent_signal_emitted`
- `council_round_started`
- `council_decision_emitted`
- `risk_evaluation_started`
- `risk_decision_emitted`
- `risk_vetoed`
- `order_approved`
- `execution_started`
- `execution_report_emitted`
- `portfolio_updated`
- `reconciliation_completed`
- `pipeline_completed`
- `pipeline_failed`
- `backtest_started`
- `backtest_progress`
- `backtest_completed`

Events are emitted only at observed call boundaries. An approved order without a supplied opening
observation therefore produces `order_approved` but no execution events.

## REST and WebSocket

Install and run the optional local service:

```console
python -m pip install -e ".[api]"
botnet-council-api
```

It binds to `127.0.0.1:8000` by default and contains no mutation or trading endpoint.

- `GET /api/health`
- `GET /api/bootstrap`
- `GET /api/state`
- `GET /api/portfolio`
- `GET /api/decisions?limit=50&offset=0`
- `GET /api/decisions/{decision_id}`
- `GET /api/runs?limit=50&offset=0`
- `GET /api/runs/{run_id}`
- `GET /api/snapshots/{snapshot_id}`
- `GET /api/backtests?limit=50&offset=0`
- `GET /api/backtests/{run_id}`
- `GET /api/agents?limit=50&offset=0`
- `GET /api/agents/{agent_id}`
- `WS /ws/events`

The socket accepts optional `symbol`, `run_id`, `timeframe`, and comma-separated `event_type`
query filters. It only streams events published after subscription and cannot trigger work.
Invalid filters produce a `stream_error` and close code 1008. REST errors contain `code`,
`message`, safe `details`, and `request_id`; stack traces are not returned.

Use the socket for incremental live updates. On every connection or reconnect, obtain
`/api/bootstrap`, which atomically returns the stream generation, sequence watermark, derived
state, run and agent registries, and retained events from one bus snapshot. Buffer socket events
while that request is pending, discard same-generation events at or below the watermark, and then
apply only contiguous newer sequences. A generation change or sequence gap requires another full
bootstrap. A socket opening does not by itself establish authoritative live state.
Use `/api/runs/{run_id}` or `/api/decisions/{decision_id}` for deterministic historical replay.
Backtest runs emit their market, signal, Council, risk, order, execution, reconciliation, and
portfolio events alongside progress events, while the existing backtest ledger remains the
authoritative artifact.

The default `InMemoryEventBus` is process-local and loses data on restart. By default it retains
the newest 10,000 events and 20,000 event IDs for duplicate suppression; both limits are
constructor-configurable and oldest entries are evicted deterministically. Sequence numbers keep
increasing after eviction. Each WebSocket has a 256-event outbound queue by default, configurable
when the app is created. A consumer that exceeds the bound receives `consumer_lagged` when
possible, is closed with code 1013, and must bootstrap again.

Browser WebSocket origins are limited to `localhost`/`127.0.0.1` on the Vite development port or
the API port. Non-browser clients without an Origin header remain supported. REST is intended to
be same-origin through the Vite proxy and the service continues to bind to `127.0.0.1`. Exposing
the API on another interface requires authentication, authorization, TLS, and an explicit origin
policy; V0.1 does not provide those controls.

Production use needs an
append-only durable event store with a unique `(stream_id, sequence)` constraint, indexed
`run_id`/snapshot/decision IDs, retention policy, and cursor-based reads. An external broker can
later implement the same `EventPublisher` interface; Redis Streams, NATS JetStream, or Kafka are
reasonable only when process-local fan-out is no longer sufficient.

## TypeScript generation

`contracts/typescript/types.generated.ts` is generated from the Pydantic public models:

```console
python tools/generate_typescript.py
python tools/generate_typescript.py --check
```

Use `TypedTelemetryEvent` in reducers to narrow `payload` from `event_type`. CI tests fail if the
checked-in file is stale. Breaking fields require a new telemetry `schema_version` and, for REST
shape changes, a new `api_version`.

## Representative envelopes

Agent signal:

```json
{"event_id":"e-signal","event_type":"agent_signal_emitted","schema_version":"1.1","stream_id":"stream-7","sequence":4,"run_id":"run-42","symbol":"BTC/USD","timeframe":"5m","emitted_at":"2026-09-11T14:00:00Z","source_snapshot_id":"snap-42","correlation_id":"trend","payload":{"signal_id":"sig-42","domain_schema_version":"1.1","agent_id":"trend","agent_version":"1.0","signal_type":"alpha","symbol":"BTC/USD","timeframe":"5m","source_snapshot_id":"snap-42","source_as_of":"2026-09-11T14:00:00Z","forecast_direction":"long","expected_return":0.012,"target_exposure":0.2,"action":"target_exposure","validity":"valid","confidence":0.76,"horizon_bars":3,"generated_at":"2026-09-11T14:00:00Z","expires_at":"2026-09-11T14:15:00Z","rationale":"Fast trend exceeds slow trend.","volatility":null,"metadata":{"fast_window":5,"slow_window":20}}}
```

Council decision:

```json
{"event_id":"e-council","event_type":"council_decision_emitted","schema_version":"1.1","stream_id":"stream-7","sequence":7,"run_id":"run-42","symbol":"BTC/USD","timeframe":"5m","emitted_at":"2026-09-11T14:00:00Z","source_snapshot_id":"snap-42","correlation_id":"decision-42","payload":{"decision_id":"decision-42","symbol":"BTC/USD","timeframe":"5m","source_snapshot_id":"snap-42","source_as_of":"2026-09-11T14:00:00Z","forecast_direction":"long","expected_return":0.01,"target_exposure":0.15,"action":"target_exposure","conviction":0.6,"confidence":0.72,"decided_at":"2026-09-11T14:00:00Z","expires_at":"2026-09-11T14:15:00Z","rationale":"Weighted alpha consensus.","signal_ids":["sig-42"],"participating_agent_ids":["trend"]}}
```

Risk decision:

```json
{"event_id":"e-risk","event_type":"risk_decision_emitted","schema_version":"1.1","stream_id":"stream-7","sequence":10,"run_id":"run-42","symbol":"BTC/USD","timeframe":"5m","emitted_at":"2026-09-11T14:00:00Z","source_snapshot_id":"snap-42","correlation_id":"decision-42","payload":{"risk_status":"approved","approved":true,"vetoed":false,"reasons":["approved by deterministic risk policy"],"policy_check_ids":[],"evaluated_at":"2026-09-11T14:00:00Z","decision_id":"decision-42","source_snapshot_id":"snap-42","approved_order":{"order_id":"order-42","decision_id":"decision-42","source_snapshot_id":"snap-42","symbol":"BTC/USD","timeframe":"5m","side":"buy","quantity":0.05,"reference_price":60000.0,"authorized_at":"2026-09-11T14:00:00Z","earliest_fill_at":"2026-09-11T14:05:00Z","expires_at":"2026-09-11T14:15:00Z","fill_policy":"next_bar_open","max_fee_bps":10.0,"max_slippage_bps":20.0,"reduce_only":false,"paper_only":true},"cash":100000.0,"equity":100000.0,"gross_exposure":0.0,"position_quantity":0.0}}
```

Execution report:

```json
{"event_id":"e-fill","event_type":"execution_report_emitted","schema_version":"1.1","stream_id":"stream-7","sequence":13,"run_id":"run-42","symbol":"BTC/USD","timeframe":"5m","emitted_at":"2026-09-11T14:05:00Z","source_snapshot_id":"snap-42","correlation_id":"decision-42","payload":{"order_id":"order-42","decision_id":"decision-42","symbol":"BTC/USD","side":"buy","quantity":0.05,"submitted_at":"2026-09-11T14:00:00Z","filled_at":"2026-09-11T14:05:00Z","fill_price":60006.0,"fees":3.0,"slippage_bps":1.0,"slippage_cost":0.3,"total_costs":3.3,"execution_status":"filled","message":"paper fill at causally valid next-bar open","paper_only":true}}
```

## Current data limitations

- Risk decisions have human-readable reasons but no stable domain-level policy/check IDs, so
  `policy_check_ids` is empty rather than fabricated.
- Execution reports expose an authorization ID, not a separately modeled broker order ID; the
  public `order_id` is that paper authorization ID.
- There is no realized-P&L field on live `PortfolioState`; only equity, gross exposure, and
  unrealized P&L can be projected reliably. Backtest ledgers contain richer cumulative metrics.
- No durable live-run registry exists. The REST history is limited to the lifetime of the process.
- Agent configuration/health metadata beyond IDs, versions, and emitted signals is not currently
  modeled.

