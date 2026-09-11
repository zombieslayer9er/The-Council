# Architecture and safety invariants

## Dependency rule

Dependencies point inward toward `schemas.py`. Agent implementations, the council,
and the risk governor do not import Freqtrade or an execution implementation. The
pipeline wires protocols to concrete implementations at the application boundary.

| Layer | Input | Output | May perform I/O? |
|---|---|---|---|
| Market data | symbol, timeframe, `as_of` | `MarketSnapshot` | Read-only |
| Specialist | snapshot, non-secret context | `AgentSignal` | Prefer no; never trade |
| Council | snapshot, signals | `CouncilDecision` | No |
| Risk | decision, snapshot, marked portfolio, cost bounds | `RiskDecision` / `ApprovedOrder` | No |
| Execution | `ApprovedOrder`, next-bar opening observation | `ExecutionReport` | Simulation only |

## Invariants

1. Cross-layer models use strict Pydantic validation and reject NaN, infinities,
   coercive numeric strings, and inconsistent causal or accounting state.
2. Council results are deterministic for equivalent inputs and insensitive to
   signal input order.
3. Advisory regime/volatility signals do not silently become directional votes.
4. The risk governor always runs after the council and before execution.
5. A veto produces no `ApprovedOrder`; the pipeline therefore has nothing executable.
6. Every approved order is capped, marked `paper_only`, deterministically identified,
   cost-bounded, and restricted to a causal `NEXT_BAR_OPEN` window.
7. No agent API includes an execution adapter, broker, secret, or credential argument.
8. Freqtrade vocabulary and lifecycle hooks stay in `adapters/`.
9. Every risk evaluation receives a portfolio marked at exactly `evaluated_at`.
   Average entry price remains unchanged when a current mark changes; equity is cash
   plus marked position value and unrealized PnL is quantity times mark-minus-entry.
   A slipped fill changes cash and entry basis, but only an independent market-price
   observation changes the mark.
10. A zero target is an actionable flatten request. `ABSTAIN` and `NO_ACTION` do
    not create orders; `REDUCE_ONLY` cannot cross through flat or increase exposure.
11. Causal identity flows from snapshot to signal, council decision, authorization,
    submission, and fill. Stale or future evidence is rejected at council/risk gates.
12. Paper execution validates the complete candidate account state before committing
    cash, positions, marks, or idempotency state. Rejections leave the account unchanged.
13. Account state time is monotonic across fills and mark-to-market operations.
14. Signal generation cannot precede source-snapshot availability, and reconciliation
    recomputes authorization timing, slippage, cash, quantity, and exposure constraints.

Python types are architectural guardrails, not a hardened security sandbox. A future
deployment should also isolate model processes from secrets at the process/network
level and keep credentials exclusively inside a separately audited execution service.

## Determinism

`MarketBar.opened_at`, `closed_at`, and `available_at` distinguish interval start,
interval end, and the earliest provider-derived usability time. These values must not
be inferred from similarly named provider fields. `MarketSnapshot.as_of` is the hard
data cutoff; `observed_at` is when that snapshot is assembled. Providers must exclude
every bar whose `available_at` exceeds `as_of`.

Signals identify the exact snapshot, their generation and expiry times, agent version,
forecast horizon in bars, expected decimal return, normalized target exposure, intent,
and validity. Volatility is a typed per-bar observation with estimator, window, units,
source, timestamp, and explicit insufficient-data state.

Authorization occurs only after mark-to-market and risk evaluation. A paper order may
fill only from a separate opening-price observation where submission was no later than
the opening event and the event lies within the authorization window. A completed
candle's close is never reused as a retroactive fill for that candle.

Given identical ordered data, timestamps, signals, policy, cost bounds, and portfolio
state, council and risk outputs—including identifiers—are identical. Floating-point
calculations should still be replaced with fixed-point/decimal rules before any
production-scale financial accounting.

Historical replay preserves these contracts with the boundary micro-order documented in
[`backtesting.md`](backtesting.md). In particular, an opening event at the same nominal
timestamp as a candle close occurs first, so a close-informed order cannot consume it.
