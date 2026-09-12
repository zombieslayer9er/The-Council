# Historical recurrence specialist

`HistoricalRecurrenceAgent` is a long-history evidence specialist. It is distinct from
the calendar-seasonality specialist: seasonality tests one configured calendar hypothesis,
while recurrence retains a structured observation for every supplied prior year, evaluates
a fixed family of forward horizons, and reports how the behavior persists across decades.

The agent implements the existing provider-neutral specialist protocol. It receives only a
causal `MarketSnapshot` and non-secret `AgentContext`, emits one `AgentSignal`, and has no
access to providers, execution, risk, cached outcomes, or Judge results. It analyzes every
reliable bar supplied by the snapshot. Its 200-year warmup declaration is a fetch hint for
the legacy snapshot interface, not an analysis cap.

## Annual observations

Intraday bars are reduced to the last completed close for each UTC trading date. For each
year before the decision year, the agent selects the nearest available trading date within
the configured calendar tolerance. February 29 maps to February 28 in non-leap years. Each
year can produce exactly one observation for each fixed horizon and is never relabeled or
counted twice.

A usable observation records:

- candidate, entry, and endpoint dates;
- the normalized historical path beginning at zero;
- forward return;
- maximum adverse and favorable excursion;
- optional historical regime and similarity to current regime features.

Missing calendar regions, large gaps, incomplete horizons, and horizons not available by
the decision cutoff remain explicit excluded observations. Forward horizons count observed
trading dates, so weekends and differing annual trading-day counts do not masquerade as
missing returns. Corporate-action correctness remains the responsibility of the upstream
provider; equity providers should supply a stable adjusted-price convention and identify it
in provenance.

## Window evidence and safeguards

The initial fixed horizon family is 1, 3, 5, 10, and 20 trading days. Every window exposes
total and usable annual observations, positive/negative/flat counts, raw positive and
directional hit ratios, median and mean return, the full return distribution, median adverse
and favorable excursion, sample count, persistence score, decade summaries, forecast
horizon, and optional regime-matched statistics.

Selection is deterministic. A candidate must meet the minimum independent-year count.
Confidence combines directional agreement, evidence persistence across early/middle/recent
history, sample adequacy, and effect size, then applies `1 / sqrt(number of tested horizons)`
as an explicit multiple-testing penalty. Confidence is capped at 0.75. A tiny perfect sample
therefore cannot receive high authority, and weak evidence produces an
`INSUFFICIENT_DATA` abstention.

The complete `HistoricalRecurrenceEvidence` is serialized under the signal metadata key
`historical_recurrence` for telemetry and later UI visualization. Ratios are always paired
with their raw counts.

## Causal replay

At decision time `T`, `MarketSnapshot` has already rejected any bar whose `available_at`
exceeds `T`. Recurrence additionally uses only years before the decision year and excludes
any historical endpoint on or after the current decision date. Replaying an earlier year
therefore operates on expanding history: observations from later years cannot enter the
signal.

Optional regime inputs use these `AgentContext.parameters` keys:

- `current_regime`: string;
- `historical_regimes`: mapping from year to string;
- `current_regime_features`: finite numeric feature mapping;
- `historical_regime_features`: mapping from year to finite numeric feature mapping.

Absent regime data does not invalidate price-only recurrence evidence. Invalid supplied
regime shapes fail explicitly.
