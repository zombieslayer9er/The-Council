# Seasonality specialist V0.1

`SeasonalityAgent` tests a narrow hypothesis: close-to-close returns following a fixed
UTC calendar position may recur across prior years. Historical seasonality does not
imply that the effect will persist. This is an inspectable research signal, not an
autonomous strategy or an order generator.

## Fixed inputs and matching

V0.1 accepts `tolerance_days`, `horizon_days`, `prior_years`,
`minimum_independent_years`, and `minimum_confidence`. They are inputs to the
hypothesis. The agent and backtester do not search, tune, rank, or select these values
using evaluation results.

Only UTC `1d` bars are supported. For evaluation timestamp `T`, the agent constructs
the same month/day in each of the configured prior calendar years and accepts completed
bar close dates within the fixed inclusive ± tolerance. It never accepts an entry from
`T`'s calendar year or a later year. A February 29 evaluation has matches only in prior
leap years; it is not silently shifted to February 28 or March 1. Adding/subtracting the
tolerance uses ordinary calendar arithmetic, so a window may cross a year boundary.
When very large tolerances make annual windows overlap, each source entry observation
is assigned exactly once: to its nearest eligible calendar anchor, with ties resolved
to the earlier anchor year. One historical return therefore cannot populate multiple
independent-year groups.

A raw match return is exactly `endpoint_close / entry_close - 1`, where the endpoint
bar closes exactly `horizon_days` after the entry bar. Missing endpoints are excluded;
returns are never shortened, interpolated, or partially calculated. Derived returns
must also be finite. Overflowed or otherwise non-finite results are excluded explicitly.

## Causality

Both the entry and endpoint must be present in the source `MarketSnapshot`, and each
must have `available_at <= T`. The entry must close before `T`. Snapshot validation and
the agent's own checks therefore exclude future candles, delayed unpublished candles,
the current evaluation target period, and incomplete forward returns. Diagnostics are
derived afresh on every call and introduce no mutable fitting state. Metadata separately
reports candidate, usable, and excluded raw matches; exclusion reasons; candidate and
usable years; and the resulting year-level observations. Missing outcomes are never
imputed as gains or losses.

## Statistics, stability, and reliability

Raw tolerance-window matches are not independent evidence. All usable matches assigned
to one seasonal anchor year are deterministically reduced to their median return. Each
year therefore contributes exactly one observation to the forecast, statistics,
stability, and confidence regardless of how many overlapping raw matches it contains.

Metadata reports raw and independent-year counts, timestamps, raw returns, year-level
returns, arithmetic mean, median, population standard deviation, positive fraction,
and stability. Year-level stability is:

`sign_consistency * dispersion_factor * extreme_balance`

where:

- `sign_consistency = abs(sum(sign(year_return))) / independent_year_count`
- `dispersion_factor = abs(median) / (abs(median) + population_stddev)`
- `extreme_balance` rescales the largest absolute-return share so equal-magnitude years
  score 1 and dependence on a single extreme year approaches 0

With fewer than two usable years, stability is zero. Every factor and the product are
bounded to `[0, 1]`.

Confidence is a research reliability score, not statistical certainty or win rate:

`confidence = sample_strength * stability`

and the saturating independent-year strength is:

`sample_strength = 1 - exp(-(independent_year_count - 1) / 6)`

One year therefore has zero stability and confidence. Two perfectly agreeing years
remain low-confidence; confidence rises gradually and can become high only with many
consistent independent years. Fewer than `minimum_independent_years` usable years
produces `INSUFFICIENT_DATA`. Adequate but weak, zero, or contradictory evidence
produces a valid `ABSTAIN`. Other sufficiently reliable evidence produces a standard
alpha forecast for the council. Its normalized target exposure is the signed
effect-to-dispersion ratio multiplied by confidence; risk, council weighting, and
execution remain separate and unchanged.

Known limitations include small prior-year samples, sensitivity to market structure
changes, dependence within each year even after median aggregation, no
statistical-significance claim, and daily close conventions that may differ among
providers. V0.1 deliberately excludes hyperparameter optimization, walk-forward tuning,
feature mining, ML, sentiment, portfolio construction, and execution behavior.
