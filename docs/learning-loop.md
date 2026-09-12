# Librarian, weight profiles, and Teacher validation

The learning layer is downstream of completed, judged experience episodes. It can propose
and validate Council weight changes, but it cannot mutate specialists, market data, Judge
truth, execution semantics, risk limits, or the risk governor's veto authority.

```text
Historical run → Judge → ExperienceStore → Librarian → WeightProposal
       → temporal held-out Teacher replay → accept/reject → WeightProfileStore
```

## Versioned profiles

`WeightProfile` generations use immutable IDs such as `weights-v0000` and
`weights-v0001`, parent links, creation timestamps, scoring versions, and deterministic
content identities. Every experience episode records the generation used for its original
decision.

Each scoped agent entry has separate `long_term` and `recent` weights. The effective weight
is a bounded blend whose recent share cannot exceed 50%, so a short run cannot overwrite
long-term competence. Scopes may target asset class, symbol, regime, or forecast horizon.
The most specific matching rule wins, with a global rule as fallback.

`WeightProfileStore` writes each generation once and keeps a separate active-generation
pointer. Only a non-rejected `TeacherResult` can call `promote`. Rollback moves the active
pointer to an ancestor without deleting or rewriting any generation.

## Librarian

The Librarian receives an immutable profile and completed `ExperienceEpisode` values. It
has no reference to the profile store or trading pipeline. It filters episodes by scope and
uses an episode only when its outcome/Judge truth was available strictly before the
training cutoff.

For each agent it measures long-term directional accuracy and a fixed recent window.
Proposals include raw sample count, accuracy, confidence, old/new slow and fast weights,
scope, and a reason. The maximum movement is:

```text
configured maximum delta × min(1, sample count / full-confidence sample count)
```

Batches below the minimum sample count produce no change. A `WeightProposal` is immutable
and cannot activate itself.

## Teacher

The Teacher requires a disjoint held-out episode set whose decisions occur at or after the
proposal's cutoff. It also rejects truth that was not available by `evaluated_at`. It
replays only frozen snapshots and specialist outputs; providers and specialists are never
called again.

Both old and proposed profiles are scored with versioned, explicit metrics:

- total and benchmark-relative return;
- maximum drawdown;
- directional hit rate and confidence calibration error;
- risk-adjusted return;
- turnover and configurable cost sensitivity;
- worst return across up to three chronological validation slices.

An update must improve the weighted score and remain inside the worst-slice degradation
limit. The result is `ACCEPT`, `REJECT`, or `ACCEPT_REDUCED_UPDATE` when a half-sized update
passes after the full proposal fails. Results include old/new metrics, accepted changes,
held-out episode IDs, scoring version, and reasons. Rejected results cannot create a
generation.

This is intentionally conservative infrastructure. It does not automatically schedule
training, choose hyperparameters, bypass Council aggregation, or authorize trading.
