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

Implement `MarketDataProvider.snapshot(symbol, timeframe, *, as_of)`. Normalize times
to UTC, return only bars completed at or before `as_of`, preserve `observed_at`, sort
bars chronologically, and avoid attaching provider clients to domain objects.

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
