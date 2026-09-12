# Graph Report - BotnetCouncil  (2026-09-12)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1792 nodes · 6273 edges · 69 communities (64 shown, 4 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 938 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `db70bc8c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- engine.py
- experience/models.py
- market_data/__init__.py
- experiments/models.py
- validate.ts
- context/__init__.py
- types.generated.ts
- serializers.py
- MarketSnapshot
- TelemetryEvent
- App.tsx
- app.py
- researchViews.tsx
- ExperimentService
- create_app
- cli.py
- AgentSignal
- ExperienceEpisode
- test_market_data.py
- schemas.py
- ExperimentRecord
- api.ts
- datetime
- package.json
- _of_type
- backtest/freqtrade.py
- agents/__init__.py
- _date
- datetime
- EventType
- authoritative.py
- DeterministicRiskGovernor
- seasonality.py
- RiskPolicy
- test_freqtrade_engine.py
- PortfolioState
- teacher.py
- episode.py
- test_learning.py
- AgentContext
- PaperExecutionAdapter
- WeightProfile
- compilerOptions
- adapters/freqtrade.py
- CouncilSignalStrategy
- model_validator
- test_issue15_adversarial.py
- FreqtradeBacktestEngine
- test_pipeline.py
- ProcessResult
- test_context.py
- test_pr16_regressions.py
- config.py
- _json_value
- Position
- DockerComposeCommandRunner
- generate_typescript.py
- websocket_events
- _identity
- WeightProposal
- .normalize_time
- logging.py
- sanitize_exception
- .validate_result
- .normalize_public_datetimes
- api/__main__.py
- tools/__init__.py
- botnet-council

## God Nodes (most connected - your core abstractions)
1. `MarketSnapshot` - 132 edges
2. `create_app()` - 90 edges
3. `PublicModel` - 72 edges
4. `AgentContext` - 68 edges
5. `AgentSignal` - 56 edges
6. `TelemetryEvent` - 46 edges
7. `BacktestEngine` - 44 edges
8. `ExperimentService` - 43 edges
9. `MarketBar` - 43 edges
10. `DeterministicRiskGovernor` - 43 edges

## Surprising Connections (you probably didn't know these)
- `test_external_result_from_future_period_is_rejected()` --calls--> `FreqtradeBacktestEngine`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/backtest/freqtrade.py
- `test_future_decision_cannot_be_mapped_to_an_arbitrarily_old_candle()` --uses--> `CouncilDecisionStrategyAdapter`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/adapters/freqtrade.py
- `test_fractional_targets_are_not_silently_binary_trades()` --uses--> `CouncilDecisionStrategyAdapter`  [INFERRED]
  tests/test_pr16_regressions.py → src/botnet_council/adapters/freqtrade.py
- `test_recurrence_order_changes_fail_explicitly()` --uses--> `MarketSnapshot`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/schemas.py
- `test_recurrence_rejects_future_snapshot_bars()` --uses--> `MarketSnapshot`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/schemas.py

## Import Cycles
- None detected.

## Communities (69 total, 4 thin omitted)

### Community 0 - "engine.py"
Cohesion: 0.06
Nodes (67): BacktestEngine, _build_agents(), _instrument(), _lifecycle(), _mark(), _MarketMark, Any, datetime (+59 more)

### Community 1 - "experience/models.py"
Cohesion: 0.07
Nodes (48): Connection, Convert frozen domain containers into canonical JSON-compatible values., to_jsonable(), AgentVersion, AppliedWeight, CouncilReplay, _decision_material(), DecisionEvidence (+40 more)

### Community 2 - "market_data/__init__.py"
Cohesion: 0.08
Nodes (37): HistoricalMarketDataProvider, MarketDataProvider, datetime, Protocol, CacheIntegrityError, ParquetMarketDataCache, Any, Path (+29 more)

### Community 3 - "experiments/models.py"
Cohesion: 0.09
Nodes (49): build_agents(), Any, Build the configured agents through one deterministic registry., aggregate_batch(), _configuration_id(), _configuration_performance(), HistoricalExperimentSelector, Outcome-blind seeded selection and transparent batch aggregation. (+41 more)

### Community 4 - "validate.ts"
Cohesion: 0.17
Nodes (60): ACTIONS, adaptiveWeight(), api(), array(), asSignal(), boolean(), CAPABILITIES, council() (+52 more)

### Community 5 - "context/__init__.py"
Cohesion: 0.09
Nodes (37): analyze_with_context(), _declaration(), optional_capabilities(), Capability-aware specialist dispatch with deterministic abstention., requested_capabilities(), required_capabilities(), context_identity(), ContextCapability (+29 more)

### Community 6 - "types.generated.ts"
Cohesion: 0.05
Nodes (53): AdaptiveWeightPayload, AgentDetailResponse, AgentPage, AgentSignalPayload, API_VERSION, ApiError, AppliedWeightPayload, ApprovedOrderPayload (+45 more)

### Community 7 - "serializers.py"
Cohesion: 0.06
Nodes (53): AdaptiveWeightPayload, AgentSignalPayload, CouncilDecisionPayload, EvaluationMetricsPayload, ExperimentForecastPayload, ExperimentOraclePayload, ExperimentProvenancePayload, LearningReviewPayload (+45 more)

### Community 8 - "MarketSnapshot"
Cohesion: 0.09
Nodes (36): CouncilDecisionStrategyAdapter, Translate decisions without introducing Freqtrade types into Council contracts., MeanReversionAgent, TrendAgent, VolatilityAgent, run_demo(), CouncilConfig, DeterministicCouncil (+28 more)

### Community 9 - "TelemetryEvent"
Cohesion: 0.07
Nodes (29): EventHandler, backtest(), decision(), run(), model_validator, Self, TelemetryEvent, Frontend-safe observability contracts and in-process transport. (+21 more)

### Community 10 - "App.tsx"
Cohesion: 0.07
Nodes (36): AgentSummary, RunSummary, StateResponse, react, App(), BacktestsView(), EventRow(), HistoryView() (+28 more)

### Community 11 - "app.py"
Cohesion: 0.09
Nodes (50): ExperimentBatchResponse, ExperimentRequestPayload, FastAPI, PortfolioPayload, SnapshotPayload, FastAPI application backed exclusively by public telemetry events., AgentDetailResponse, AgentPage (+42 more)

### Community 12 - "researchViews.tsx"
Cohesion: 0.08
Nodes (39): ExperienceDetailPayload, ExperienceSummaryPayload, ExperimentEvaluationPayload, ExperimentForecastPayload, ExperimentOraclePayload, ExperimentSummaryPayload, LearningReviewPayload, WeightGenerationPayload (+31 more)

### Community 13 - "ExperimentService"
Cohesion: 0.12
Nodes (28): create_app(), Any, InMemoryExperimentRepository, ExperimentService, _bars(), _provider(), Path, _request() (+20 more)

### Community 14 - "create_app"
Cohesion: 0.07
Nodes (36): ExperienceDetailPayload, ExperienceSummaryPayload, ExperimentEvaluationPayload, ExperimentSummaryPayload, JSONResponse, Request, _configured_experience_store(), _configured_weight_store() (+28 more)

### Community 15 - "cli.py"
Cohesion: 0.11
Nodes (21): Namespace, download_market_data(), _instrument(), main(), _parse_datetime(), datetime, Deterministic demo, historical download, and backtest commands., run_backtest() (+13 more)

### Community 16 - "AgentSignal"
Cohesion: 0.16
Nodes (21): Protocol, The stable extension point for deterministic, ML, local-LLM, or hosted agents., Provider-neutral specialist interface. Implementations receive market data plus…, Return an agent's declared history requirement without widening its protocol., SpecialistAgent, warmup_bars(), clamp(), direction_for() (+13 more)

### Community 17 - "ExperienceEpisode"
Cohesion: 0.16
Nodes (21): ExperienceEpisode, _bounded_move(), _episode_matches(), Librarian, datetime, Conservative, post-outcome weight proposal generation., _target_weight(), _utc() (+13 more)

### Community 18 - "test_market_data.py"
Cohesion: 0.32
Nodes (29): FakeTransport, provider(), Any, datetime, parametrize, Path, request(), response() (+21 more)

### Community 19 - "schemas.py"
Cohesion: 0.16
Nodes (19): ExecutionReportPayload, ExecutionAdapter, datetime, Protocol, A deliberately narrow, paper-only execution boundary., datetime, Composition layer for the unidirectional research-to-execution workflow., ResearchTradingPipeline (+11 more)

### Community 20 - "ExperimentRecord"
Cohesion: 0.13
Nodes (15): _default_experiment_service(), datetime, Runtime-enforced experiment lifecycle transitions., transition(), ExperimentRecord, LifecycleEvent, ExperimentRepository, FileExperimentRepository (+7 more)

### Community 21 - "api.ts"
Cohesion: 0.12
Nodes (24): BootstrapResponse, ExperiencePage, ExperienceResponse, ExperimentEvaluationResponse, ExperimentForecastResponse, ExperimentOracleResponse, ExperimentPage, HealthResponse (+16 more)

### Community 22 - "datetime"
Cohesion: 0.18
Nodes (8): JsonValue, Any, datetime, field_validator, Boundary helper; deterministic core methods accept explicit timestamps., _utc(), utc_now(), _validate_json_numbers()

### Community 23 - "package.json"
Cohesion: 0.08
Nodes (25): react-dom, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, dependencies, react (+17 more)

### Community 24 - "_of_type"
Cohesion: 0.11
Nodes (25): _active_run_ids(), _agent_values(), agent(), agents(), backtests(), bootstrap(), decisions(), get_portfolio() (+17 more)

### Community 25 - "backtest/freqtrade.py"
Cohesion: 0.22
Nodes (25): _canonical_json(), _effective_config_hash(), _fee_cost(), _file_sha256(), FreqtradeArtifactError, _load_result(), _normalize_equity(), _normalize_result() (+17 more)

### Community 26 - "agents/__init__.py"
Cohesion: 0.17
Nodes (19): _anniversary(), _annual_observation(), AnnualRecurrenceObservation, _daily_closes(), _DailyClose, _epochs(), HistoricalRecurrenceEvidence, _numeric_features() (+11 more)

### Community 27 - "_date"
Cohesion: 0.24
Nodes (24): _date(), _bar(), _overlapping_observations(), datetime, _signal(), _snapshot(), test_conflicting_years_reduce_stability_and_confidence(), test_consistent_independent_years_increase_confidence_gradually() (+16 more)

### Community 28 - "datetime"
Cohesion: 0.16
Nodes (7): duration(), datetime, field_validator, model_validator, Self, timedelta, _utc()

### Community 29 - "EventType"
Cohesion: 0.21
Nodes (19): EventType, StagePayload, event(), datetime, TelemetryEvent, Event construction helpers with explicit causal metadata., build_pipeline(), opening() (+11 more)

### Community 30 - "authoritative.py"
Cohesion: 0.17
Nodes (16): AuthoritativeModel, EngineProvenance, EquityPoint, _json_value(), NormalizedTrade, Any, BaseModel, datetime (+8 more)

### Community 31 - "DeterministicRiskGovernor"
Cohesion: 0.19
Nodes (13): RiskDecisionPayload, Provider-agnostic market research and paper-trading council., PipelineResult, BaseModel, DeterministicRiskGovernor, datetime, Final, deterministic authority over every proposed order., Vetoes or produces the only order type accepted by execution adapters. (+5 more)

### Community 32 - "seasonality.py"
Cohesion: 0.17
Nodes (17): _aggregate_years(), _candidate_metadata(), _CandidateMatch, _causal_exclusion_reason(), _confidence(), _exclusion_reason_counts(), _is_zero(), Deterministic prior-year calendar seasonality research signal. (+9 more)

### Community 33 - "RiskPolicy"
Cohesion: 0.25
Nodes (20): BaseModel, model_validator, Self, RiskPolicy, RiskStatus, authorized_order(), decision_for(), filled_report() (+12 more)

### Community 34 - "test_freqtrade_engine.py"
Cohesion: 0.27
Nodes (19): FakeRunner, datetime, MonkeyPatch, parametrize, Path, request(), result_payload(), test_docker_runner_maps_only_workspace_paths() (+11 more)

### Community 35 - "PortfolioState"
Cohesion: 0.14
Nodes (10): ApprovedOrderPayload, ReconciliationPayload, _PaperPosition, datetime, ApprovedOrder, PortfolioState, Paper execution capability emitted exclusively by the risk workflow., approved_order() (+2 more)

### Community 36 - "teacher.py"
Cohesion: 0.18
Nodes (19): EvaluationMetrics, MetricComparison, StrEnum, TeacherDecision, apply_changes(), datetime, Immutable profile transformations and versioned local profile storage., reduced_changes() (+11 more)

### Community 37 - "episode.py"
Cohesion: 0.15
Nodes (13): AuthoritativeBacktestEngine, AuthoritativeBacktestResult, _plain_json(), Protocol, ValidationArtifact, episode_identity(), EpisodeRecord, datetime (+5 more)

### Community 38 - "test_learning.py"
Cohesion: 0.31
Nodes (17): TeacherConfig, Teacher, base_episode(), learning_episode(), librarian_proposal(), profile(), Path, test_librarian_counts_equivalent_reruns_once() (+9 more)

### Community 39 - "AgentContext"
Cohesion: 0.28
Nodes (14): Canonical construction of built-in specialist agents., HistoricalRecurrenceAgent, Compare a fixed calendar region across independent prior-year observations., AgentContext, Non-secret contextual data supplied to a specialist., annual_snapshot(), evidence(), test_agent_factory_and_evidence_serialization_support_new_kind() (+6 more)

### Community 40 - "PaperExecutionAdapter"
Cohesion: 0.41
Nodes (16): PaperExecutionAdapter, Atomic in-memory simulator with an explicit next-bar-open fill policy., ExecutionStatus, approved_order(), opening(), datetime, test_completed_bar_cannot_be_filled_retroactively_at_its_open(), test_execution_rejects_fill_before_account_state() (+8 more)

### Community 41 - "WeightProfile"
Cohesion: 0.28
Nodes (6): LearningReview, Immutable Librarian proposal joined to its Teacher decision., TeacherResult, WeightProfile, Path, WeightProfileStore

### Community 42 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, esModuleInterop, isolatedModules, jsx, lib, module, moduleResolution (+8 more)

### Community 43 - "adapters/freqtrade.py"
Cohesion: 0.18
Nodes (12): PaperMode, FreqtradeOrderRequest, FreqtradeStrategySignal, datetime, Path, timedelta, Pure translation into Freqtrade-shaped paper/backtest requests. No Freqtrade…, Write immutable input for a Freqtrade strategy's signal merge step. (+4 more)

### Community 44 - "CouncilSignalStrategy"
Cohesion: 0.21
Nodes (10): DataFrame, CouncilSignalStrategy, _parse_datetime(), Any, datetime, timedelta, Standalone Freqtrade strategy consuming a frozen Council signal artifact. This…, _timeframe_duration() (+2 more)

### Community 45 - "model_validator"
Cohesion: 0.24
Nodes (3): model_validator, Self, snapshot_identity()

### Community 46 - "test_issue15_adversarial.py"
Cohesion: 0.22
Nodes (13): Regression invariants from the issue 6 adversarial audit and issue 15 patch.…, repeated_trial(), teacher(), test_equivalent_reruns_cannot_satisfy_independent_holdout_minimum(), test_equivalent_reruns_do_not_create_full_librarian_confidence(), test_exact_duplicate_holdout_ids_are_rejected(), test_external_result_from_future_period_is_rejected(), test_future_decision_cannot_be_mapped_to_an_arbitrarily_old_candle() (+5 more)

### Community 47 - "FreqtradeBacktestEngine"
Cohesion: 0.44
Nodes (6): AuthoritativeBacktestRequest, StrEnum, ValidationKind, ValidationStatus, FreqtradeBacktestEngine, FreqtradeProcessError

### Community 48 - "test_pipeline.py"
Cohesion: 0.42
Nodes (9): InMemoryMarketDataProvider, build_pipeline(), opening(), datetime, SpyPaperExecutionAdapter, test_historical_snapshot_filters_bars_after_as_of(), test_historical_snapshot_filters_by_availability_not_interval_end(), test_pipeline_executes_only_after_approval() (+1 more)

### Community 49 - "ProcessResult"
Cohesion: 0.22
Nodes (7): CommandRunner, ProcessResult, Protocol, SubprocessCommandRunner, run(), test_success_without_new_export_cannot_reuse_previous_result(), run()

### Community 50 - "test_context.py"
Cohesion: 0.42
Nodes (9): datum(), FakeContextProvider, MacroRequiredAgent, datetime, request(), test_context_rejects_evidence_that_was_not_available_at_cutoff(), test_context_service_is_causal_deterministic_and_cached(), test_missing_optional_capability_is_attached_to_signal_telemetry() (+1 more)

### Community 51 - "test_pr16_regressions.py"
Cohesion: 0.25
Nodes (10): Path, Reproductions for Devin's follow-up review of issue #15 / PR #16., blocked(), test_experience_summary_exposes_exact_origin(), test_external_export_requires_period_and_capital_binding(), test_fractional_targets_are_not_silently_binary_trades(), test_native_runner_receives_absolute_paths(), run() (+2 more)

### Community 52 - "config.py"
Cohesion: 0.33
Nodes (9): AppConfig, ExecutionConfig, load_config(), LoggingConfig, Any, BaseModel, Path, Typed, strictly validated TOML configuration. (+1 more)

### Community 53 - "_json_value"
Cohesion: 0.42
Nodes (5): _json_value(), Any, datetime, field_validator, _utc()

### Community 54 - "Position"
Cohesion: 0.29
Nodes (6): Position, datetime, parametrize, test_market_prices_reject_non_finite_values(), test_portfolio_and_cost_inputs_reject_non_finite_values(), test_portfolio_rejects_incorrect_marked_equity()

### Community 55 - "DockerComposeCommandRunner"
Cohesion: 0.25
Nodes (6): DockerComposeCommandRunner, FreqtradeEngineError, FreqtradeUnavailableError, RuntimeError, Base class for structured external-engine failures., Run the external engine in the repository's isolated Compose service.

### Community 56 - "generate_typescript.py"
Cohesion: 0.42
Nodes (7): test_generated_typescript_is_current(), _literal(), main(), Any, Generate the frontend contract directly from the public Pydantic models., render(), typescript_type()

### Community 57 - "websocket_events"
Cohesion: 0.25
Nodes (8): Queue, websocket_events(), enqueue(), put(), _enqueue_or_lag(), _event_json(), _parse_event_types(), EventType

### Community 58 - "_identity"
Cohesion: 0.46
Nodes (3): _identity(), model_validator, Self

### Community 59 - "WeightProposal"
Cohesion: 0.38
Nodes (3): datetime, field_validator, WeightProposal

### Community 60 - ".normalize_time"
Cohesion: 0.57
Nodes (4): datetime, field_validator, _utc(), ValidationInfo

### Community 61 - "logging.py"
Cohesion: 0.40
Nodes (4): LogRecord, configure_logging(), JsonFormatter, Structured logging without an external dependency.

### Community 62 - "sanitize_exception"
Cohesion: 0.40
Nodes (5): Exception, Central policy for safe, low-detail public error messages., Return a stable public description while retaining no raw exception text., sanitize_exception(), SanitizedError

### Community 64 - ".normalize_public_datetimes"
Cohesion: 0.40
Nodes (3): Any, datetime, field_validator

## Knowledge Gaps
- **86 isolated node(s):** `View`, `RecurrenceWindow`, `AdaptiveWeightPayload`, `AgentDetailResponse`, `ApiError` (+81 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 365 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MarketSnapshot` connect `MarketSnapshot` to `engine.py`, `experience/models.py`, `market_data/__init__.py`, `experiments/models.py`, `context/__init__.py`, `serializers.py`, `app.py`, `cli.py`, `AgentSignal`, `schemas.py`, `datetime`, `agents/__init__.py`, `_date`, `EventType`, `DeterministicRiskGovernor`, `seasonality.py`, `RiskPolicy`, `test_freqtrade_engine.py`, `PortfolioState`, `AgentContext`, `model_validator`, `test_issue15_adversarial.py`, `test_pipeline.py`, `test_context.py`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Why does `create_app()` connect `create_app` to `experience/models.py`, `experiments/models.py`, `serializers.py`, `TelemetryEvent`, `WeightProfile`, `app.py`, `ExperimentService`, `ExperimentRecord`, `_of_type`, `websocket_events`, `EventType`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Why does `EventType` connect `EventType` to `engine.py`, `TelemetryEvent`, `app.py`, `create_app`, `schemas.py`, `_of_type`, `websocket_events`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 63 inferred relationships involving `MarketSnapshot` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`MarketSnapshot` has 63 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `create_app()` (e.g. with `require_command_access()` and `AgentDetailResponse`) actually correct?**
  _`create_app()` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `AgentContext` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`AgentContext` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `AgentSignal` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`AgentSignal` has 19 INFERRED edges - model-reasoned connections that need verification._