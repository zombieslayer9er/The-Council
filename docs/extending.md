# Extending the system

## Add a specialist

Create a class satisfying `SpecialistAgent`. Keep provider objects private to that
class, use only read-only inputs, and normalize the result to `AgentSignal(schema_version="1.1", ...)`.
Do not pass provider-native messages into the council.

For an LLM-backed specialist:

1. Define a constrained provider response schema.
2. Parse and validate it inside the specialist adapter.
3. Supply source snapshot identity, agent version, bar horizon, expiry, validity,
   expected decimal return, normalized target exposure, and explicit intent.
4. Bound target exposure and confidence through `AgentSignal` validation.
5. Treat rationale/metadata as untrusted observational text/data.
6. Never expose execution tools or credentials to the model.

This applies equally to an OpenAI Agents SDK agent or a local model; neither requires
changes to `DeterministicCouncil`.

## Add market data

Implement `HistoricalMarketDataProvider.fetch_historical(HistoricalRequest)` and the
compatibility `snapshot(symbol, timeframe, *, as_of)` boundary. Document the external
provider's timestamp and candle-commitment behavior, translate it explicitly into
UTC `opened_at`, `closed_at`, and `available_at`, and filter on `available_at <= as_of`.
Never infer availability from a provider field name or fabricate missing intervals.

## Add a backtest adapter

Implement `ExecutionAdapter` and accept only `ApprovedOrder`. Expose bounded costs and
timestamped mark-to-market, and require a separate next-bar opening observation plus
submission time for execution. Validate a complete candidate account state before
mutation. Keep simulated fills, fees, slippage, and portfolio state inside the adapter.
There is intentionally no live adapter protocol in this repository.

## Integrate Freqtrade

Call `to_freqtrade_order(approved_order, mode="dry_run" | "backtest")` at a Freqtrade
strategy/plugin boundary. Do not import Freqtrade into `agents/`, `council/`, or
`risk/`. The translator rejects any other mode. An integration should preserve the
authorization ID for audit and idempotency and must not give strategy credentials to
specialists or models.
