# Deterministic historical backtesting

This document describes the deterministic internal simulator used for unit tests and
failure injection. Authoritative research backtests use the external Freqtrade boundary
described in [backend-data-pipeline.md](backend-data-pipeline.md).

The V0.1 backtester replays one instrument and timeframe through the existing agents,
council, risk governor, paper execution adapter, and reconciliation gate. It is a
research-correctness tool, not a strategy optimizer.

## Clock and causal ordering

Simulation timestamps are timezone-aware UTC bar boundaries and increase strictly.
At a boundary, two facts share a timestamp but not a causal order: the new bar opens
before a decision can consume the preceding bar's completed OHLCV. The engine therefore
uses this explicit micro-order:

1. advance to the boundary;
2. expose that boundary's opening-price-only observation to an order queued earlier;
3. fill and reconcile that order atomically, aborting on reconciliation failure;
4. expose completed bars whose explicit `available_at` is no later than simulation time;
5. mark open positions from the newest independent causal observation, preferring the
   current opening over the previous close when both share a timestamp;
6. build the `as_of=simulation_time` snapshot and evaluate agents;
7. aggregate council output and run risk authorization;
8. queue an approval for a strictly later opening; and
9. append the complete event/account record.

Fill price, opening observation, and previous close remain separate values. This also
resolves the apparent same-timestamp conflict in `NEXT_BAR_OPEN`: at 11:00, the
10:00-11:00 candle becomes complete only after the 11:00 opening event. A decision based
on that candle can first fill at 12:00, never retroactively at 11:00.
Mark precedence is ordered by the observation's market timestamp, not publication time;
a delayed publication of an older close cannot replace a newer opening mark.

## Warm-up and evaluation

Built-in agents declare their required warm-up bar count. The engine requests the
maximum declared requirement (or a larger configured override) before `start`.
Warm-up bars may appear in snapshots, but the engine does not authorize trades or add
equity observations to measured metrics before `start`. The evaluation interval is
`[start, end]`; decisions occur on `[start, end)`, and the final opening at `end` may
complete a previously queued order before the final independent mark.

Coverage must be contiguous from the effective warm-up start through the extra opening
needed at evaluation end. Missing leading/trailing data, gaps, overlaps, invalid bars,
future snapshots, or time regressions fail the run.

## Metrics and benchmark

Total return is `ending_equity / starting_equity - 1`. Maximum drawdown is the largest
peak-to-subsequent-equity decline sampled at simulation boundaries. Gross realized PnL
uses independent opening observations for closed quantities. Net realized PnL subtracts
proportionally allocated entry/exit fees and measurable slippage; win/loss counts use
that net round-trip result. Costs are also reported separately. Turnover is filled
notional divided by starting equity. Average
gross exposure is the arithmetic mean of boundary gross-exposure/equity ratios.

The simple buy-and-hold benchmark buys notionally at the evaluation-start opening and
marks at the last completed close available at evaluation end. It excludes fees and
slippage so its formula remains `end_close / start_open - 1` and is directly auditable.
No Sharpe or Sortino ratio is reported in V0.1.

## Reproducibility and output

The run ID is SHA-256 over canonical JSON configuration identity plus the SHA-256 hash
of normalized input bars. Wall-clock fetch time and cache-hit status are provenance,
not run identity. Agent order is configured, council aggregation is deterministic, and
the random seed is recorded even though current agents are deterministic.

Each output directory is named by run ID and contains `config.json`, `summary.json`,
`provenance.json`, `events.parquet`, `equity.parquet`, and (when fills occur)
`trades.parquet`. Event records retain snapshots, signals, decisions, authorization,
order lifecycle, fills, reconciliation, account state, costs, and PnL.

## Current limitations

V0.1 is single-instrument, spot, long-only by default, full-fill, market-next-open, and
paper-only. It has no margin, partial fills, order book, live feed, optimizer, ML/LLM
training, database, or distributed execution. Floating-point accounting is retained to
match the current paper adapter and is not suitable for production brokerage books.
