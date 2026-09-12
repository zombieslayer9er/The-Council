# Immutable experience cache and replay

The experience layer records completed historical observations without changing the
deterministic trading pipeline. It adapts already-complete blind experiments; it does not
participate in forecasting, Council aggregation, risk, execution, or judging.

## Episode schema

`ExperienceEpisode` has a deliberate one-way boundary:

- `DecisionEvidence` contains only the snapshot and provenance available at decision
  time, frozen specialist outputs, agent versions, applied weights, Council configuration
  and decision, weight generation, risk-policy version, optional risk/execution/portfolio
  evidence, regime, and run identity.
- `OutcomeTruth` contains the completed oracle outcome and Judge evaluation. Its
  `available_at` cannot precede either the outcome horizon or Judge evaluation.

The evidence model has no outcome or Judge field. `CouncilReplay` contains only the
snapshot, specialist outputs, original Council configuration, and identity fields; this
makes it structurally impossible for a replayed Council aggregation to receive cached
ground truth.

Each episode has three SHA-256 identities:

1. `episode_id` identifies the exact run, evidence, and truth.
2. `equivalence_id` omits only the run ID so repeated semantically identical observations
   can be found together.
3. `decision_cache_key` identifies the market-data content, snapshot, specialist outputs,
   versions, weights, Council configuration, and weight generation needed to replay
   aggregation without rerunning providers or specialists.

Changing any identity-bearing input invalidates the corresponding cache identity. Schema
version `1.0` is exact: incompatible stores or payloads fail explicitly rather than being
silently coerced.

## Storage

`ExperienceStore` uses `experience.sqlite3` for indexed metadata and one immutable Parquet
payload per episode under `episodes/`. The SQLite indexes support symbol/time-range,
weight generation, regime, agent/version, training eligibility, semantic equivalence, and
decision-cache queries. Parquet holds canonical JSON so nested strict contracts retain
their exact round-trip representation without inventing a second domain schema.

Saving the same episode twice returns `stored` and then `hit`. Existing content is never
overwritten. Payload hashes, path identities, embedded model identities, and schema
versions are verified on every read. Missing, malformed, changed, or incompatible records
raise explicit store errors.

```python
store = ExperienceStore(".experience")
episode, status = store.save_experiment(completed_record)
replay = store.replay(episode.episode_id)
alternative = store.reaggregate(
    episode.episode_id,
    CouncilConfig(agent_weights={"trend": 0.8}),
)
```

Existing market-data and backtest datasets remain referenced through their content,
version, cache, and run identities. The store does not recollect or mutate those sources.

## Temporal training and held-out replay

`temporal_split(cutoff)` assigns decisions at or after the cutoff to held-out replay.
Earlier decisions enter training only when their truth was available strictly before the
cutoff. Earlier decisions whose outcomes or Judge results arrived later are listed under
`excluded_unavailable_truth`. This prevents an outcome that was still in the future at the
training boundary from leaking into a Librarian proposal.

The store implements infrastructure only. It does not optimize weights or activate a new
profile; those responsibilities belong to the later Librarian and Teacher layer.
