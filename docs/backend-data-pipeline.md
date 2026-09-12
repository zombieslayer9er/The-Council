# Authoritative backend data pipeline

The Council remains engine- and provider-neutral. `FreqtradeBacktestEngine` is the
authoritative production backtest boundary; the original deterministic
`BacktestEngine` remains a unit-test and failure-injection simulator. Results from the
internal simulator must not be presented as authoritative benchmark results.

## Data and control flow

```text
price provider ──> canonical MarketSnapshot ──┐
                                               ├─> ContextService ─> MarketContext
domain providers ─> timestamped ContextDatum ─┘          │
                                                         v
                                              capability-scoped specialists
                                                         │ AgentSignal
                                                         v
                                              provider-neutral CouncilDecision
                                                         │
                                              CouncilDecisionStrategyAdapter
                                                         │ timestamped signals
                                                         v
historical dataset ──────────────────────────> Freqtrade process
                                                         │ exported artifacts
                                                         v
                                             AuthoritativeBacktestResult
                                                         │
                                    validation + trainer-only EpisodeRecord
```

There is one simulated clock. `MarketSnapshot.as_of`, `ContextRequest.as_of`, and
`MarketContext.as_of` must match. A context datum records observation or period time,
publication time, provider availability, ingestion, vintage, revision, provider, source
version, and source identity. Scheduled events may describe a future event, but their
publication, availability, and ingestion timestamps must not exceed the replay cutoff.

## Context capabilities

The initial stable capability vocabulary is price history, benchmark performance, sector
classification, relative strength, correlations, realized volatility, market breadth,
rates and yields, macro indicators, and event calendars.

`ContextService` composes domain providers and caches immutable responses by provider,
source version, and the complete normalized request. It rejects provider identity drift,
undeclared capabilities, and future evidence. Specialists receive `MarketContext`, never
provider clients or credentials. Built-in specialists explicitly declare required and
optional capabilities. A missing required capability produces an
`INSUFFICIENT_DATA` abstention before specialist code runs; missing optional capabilities
are included in specialist context metadata.

## Freqtrade boundary

`AuthoritativeBacktestRequest` includes instruments, timeframe and closed timerange,
capital, fees, order rules, a versioned strategy adapter, context configuration, seed,
dataset identity, data/artifact paths, and engine configuration. Its content identity is
stable and is propagated through results and validations.

`FreqtradeBacktestEngine` verifies and records the engine version, writes the effective
dry-run configuration, executes an argument vector without a shell or cache, and consumes
only the exported JSON/ZIP artifact. It normalizes trades, fills, fees, profit, return,
drawdown, excursions, holding times, and available equity observations. It preserves the
original artifact hash, engine version, effective-config hash, dataset identity, request
identity, and deterministic run identity.

If an export omits an authoritative equity series, the normalized series remains empty
and the result contains an explicit warning; the adapter does not synthesize one from
Council accounting. Missing executables, non-zero exits, ambiguous exports, and malformed
schemas are structured failures. There is no fallback to the internal simulator.

The same engine exposes Freqtrade `lookahead-analysis` and `recursive-analysis` as
versioned `ValidationArtifact` records. A negative validation is evidence, not a mutation:
it never rewrites historical results. An inconclusive parse is reported as inconclusive,
not passed.

## Running Freqtrade

Freqtrade is deliberately not a package dependency of BotnetCouncil. Install it in a
separate environment or container, prepare its historical data and a strategy consuming
the timestamped signals from `CouncilDecisionStrategyAdapter`, then create a strict
`AuthoritativeBacktestRequest` JSON document.

```powershell
botnet-council freqtrade-backtest --request request.json
botnet-council freqtrade-backtest --request request.json --validation lookahead
botnet-council freqtrade-backtest --request request.json --validation recursive
```

The adapter never accepts exchange credentials and forces `dry_run: true`. This work does
not add live trading.

## Episode and training boundary

`EpisodeRecord` joins the exact market context, specialist outputs, Council decision,
engine request/result, validation artifacts, and trainer evaluation. It rejects mixed
snapshot/request identities and trainer evaluation before the backtest horizon. The
trainer therefore consumes only frozen authoritative outcomes and cannot feed future
information back into the episode that generated them.

## Adapter tests

Context provider tests cover causal cutoff rejection, provenance, stable identity,
missing capabilities, cache identity, and deterministic repeat. Engine tests cover
argument propagation, configuration, normalization, provenance, repeated-run identity,
malformed output, a missing binary, process failure, and validation evidence. A real
Freqtrade integration test should skip when the external binary and fixture data are
unavailable; unit tests must never fall back to the internal simulator.
