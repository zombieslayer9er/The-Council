# Issue 15 / PR 16 verification

Reviewed the integrated feature stack at fdcc4e4 and Devin's seven published
comments plus the expanded review. The original issue 6 report remains a
historical assessment of the pre-patch branches.

## Corrected follow-up defects

- P1: Council signal adapter 1.3 rejects nonzero target exposures and nonzero
  reduce-only targets: the standalone strategy has no position sizing contract.
  Flatten commands are supported; NO_ACTION and ABSTAIN emit no trades. The
  standalone consumer rejects forged entry commands and inconsistent exits.
- P1: external results require matching timeframe and period metadata, requested
  starting capital, and internally consistent profit/return balances. Native
  subprocess paths are absolute. Fresh invocation directories still prevent
  accepting stale exports.
- P1: Teacher skips overlapping trials before every metric, including sample
  count and turnover. Minimum held-out evidence counts only selected independent
  intervals. Scoring identity is now teacher-score-v3. Existing success fixtures
  use six non-overlapping trials rather than six correlated observations.
- P1: Librarian credits a signal only when its horizon matches the realized
  outcome and any requested horizon scope.
- P2: validation uses at most three balanced chronological slices.
- P2: context cache rejects source revision drift; concurrent cache misses share
  a locked fetch rather than returning independently fetched versions.
- P2: experiment commands run in a serialized worker lane so API health and
  streaming remain responsive. Failure timestamps preserve lifecycle ordering,
  and records reject decreasing lifecycle timestamps.
- P2: experience summaries expose backtest_run_id. Outcomes joins evidence by
  exact experiment origin, rejects ambiguous matches, and refreshes when the
  same experiment completes. Generated TypeScript and browser validation agree.

## Validation and boundaries

The twelve original adversarial probes pass. The overlap probe now compares all
metrics with the manually selected non-overlapping sequence, an allowed safe
alternative to rejecting the input. Follow-up regressions include forged signal
artifacts, directional no-ops, fractional targets, API responsiveness, version
drift, concurrent cache misses, horizon mixing, balanced slices and provenance.
Python tests, Ruff, strict mypy, frontend tests, TypeScript and production build
pass. Browser inspection confirmed pending-to-complete evidence refresh.

This is not certification of a live Docker/Freqtrade run or evidence of trading
profitability. Nonzero Council targets deliberately fail until actual sizing is
implemented; the adapter must not substitute a full-sized trade. The daily-close
boundary is covered synthetically, not independently verified against engine
fills. Experiment command serialization is per application instance: deployments
must use one worker and direct service calls must be serialized. Distributed
claims/multi-process execution remain unsupported. The architectural scope flag
is addressed by the requested consolidation of the complete feature stack.

The original all-branches issue 6 empirical request still lacks sufficient real
cross-market history for a profitability or generalization conclusion.
