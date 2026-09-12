# Graph Report - BotnetCouncil  (2026-09-12)

## Corpus Check
- 152 files · ~87,669 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 10 file(s) not represented in the graph (top: (none) 5, .css 3, .toml 1)

## Summary
- 2120 nodes · 6986 edges · 104 communities (93 shown, 9 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 982 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5de54b2b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- engine.py
- experience/models.py
- ParquetMarketDataCache
- ExperimentContextBuilder
- validate.ts
- context/__init__.py
- types.generated.ts
- weight_generation
- MarketSnapshot
- TelemetryEvent
- App.tsx
- serializers.py
- researchViews.tsx
- ExperimentService
- create_app
- KrakenHistoricalProvider
- schemas.py
- learning/models.py
- test_market_data.py
- experiments/__init__.py
- ExperimentRecord
- experiments/models.py
- datetime
- package.json
- app.py
- backtest/freqtrade.py
- historical_recurrence.py
- _date
- datetime
- EventType
- datetime
- DeterministicRiskGovernor
- seasonality.py
- RiskPolicy
- FreqtradeBacktestEngine
- PaperExecutionAdapter
- teacher.py
- backtest/__init__.py
- test_learning.py
- AgentContext
- ExecutionStatus
- WeightProfile
- compilerOptions
- adapters/freqtrade.py
- CouncilSignalStrategy
- scenarios.py
- test_issue15_adversarial.py
- What You Must Do When Invoked
- test_pipeline.py
- ProcessResult
- Instrument
- test_pr16_regressions.py
- model_validator
- model.ts
- test_context.py
- Path
- generate_typescript.py
- test_issue17_historical_pipeline.py
- _identity
- datetime
- HistoricalRequest
- cli.py
- pipeline.py
- .validate_result
- .normalize_public_datetimes
- api/__main__.py
- tools/__init__.py
- botnet-council
- config.py
- graphify reference: extra exports and benchmark
- agent_signal
- Contributor Covenant Code of Conduct
- model_validator
- graphify reference: query, path, explain
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- AGENTS.md
- extraction-spec.md
- Botnet Council
- Position
- Historical market data
- datetime
- architecture.md
- Authoritative backend data pipeline
- README.md
- Deterministic historical backtesting
- Blind historical experiments
- Extending the system
- Telemetry and read-only API
- Immutable experience cache and replay
- Local Freqtrade Docker boundary
- Historical recurrence specialist
- Historical acquisition and scenario API
- Librarian, weight profiles, and Teacher validation
- Seasonality specialist V0.1
- Issue 15 / PR 16 verification
- ProcessResult
- HistoricalScenarioCreate
- Q: How does the current market data pipeline ingest, cache, normalize, validate, and supply data to backtests, and where should issue 17 expansion fit?

## God Nodes (most connected - your core abstractions)
1. `MarketSnapshot` - 137 edges
2. `create_app()` - 111 edges
3. `PublicModel` - 72 edges
4. `AgentContext` - 68 edges
5. `HistoricalRequest` - 56 edges
6. `AgentSignal` - 56 edges
7. `MarketBar` - 53 edges
8. `ParquetMarketDataCache` - 50 edges
9. `BacktestEngine` - 48 edges
10. `to_jsonable()` - 46 edges

## Surprising Connections (you probably didn't know these)
- `test_future_decision_cannot_be_mapped_to_an_arbitrarily_old_candle()` --uses--> `CouncilDecisionStrategyAdapter`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/adapters/freqtrade.py
- `test_external_result_from_future_period_is_rejected()` --calls--> `FreqtradeBacktestEngine`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/backtest/freqtrade.py
- `test_recurrence_order_changes_fail_explicitly()` --uses--> `MarketSnapshot`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/schemas.py
- `test_recurrence_rejects_future_snapshot_bars()` --uses--> `MarketSnapshot`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/schemas.py
- `test_council_decision_adapter_writes_immutable_freqtrade_signals()` --calls--> `CouncilDecisionStrategyAdapter`  [INFERRED]
  tests/test_execution_and_adapters.py → src/botnet_council/adapters/freqtrade.py

## Import Cycles
- None detected.

## Communities (104 total, 9 thin omitted)

### Community 0 - "engine.py"
Cohesion: 0.06
Nodes (70): BacktestCancelledError, BacktestEngine, _build_agents(), _instrument(), _lifecycle(), _mark(), _MarketMark, Any (+62 more)

### Community 1 - "experience/models.py"
Cohesion: 0.07
Nodes (49): Connection, AgentVersion, AppliedWeight, CouncilReplay, _decision_material(), DecisionEvidence, episode_from_experiment(), _episode_material() (+41 more)

### Community 2 - "ParquetMarketDataCache"
Cohesion: 0.23
Nodes (8): CacheIntegrityError, ParquetMarketDataCache, Any, Path, Return contiguous ranges proven by validated immutable artifacts., A cache artifact failed deterministic content or metadata validation., historical_cache_key(), ProviderId

### Community 3 - "ExperimentContextBuilder"
Cohesion: 0.24
Nodes (7): HistoricalExperimentSelector, Select using only timestamps, availability, and completeness—not price values., ExperimentContextBuilder, Owns the historical provider but returns a provider-free blind object., RandomExperimentRequest, HistoricalOracle, test_seeded_selection_is_deterministic_and_excludes_incomplete_points()

### Community 4 - "validate.ts"
Cohesion: 0.17
Nodes (60): ACTIONS, adaptiveWeight(), api(), array(), asSignal(), boolean(), CAPABILITIES, council() (+52 more)

### Community 5 - "context/__init__.py"
Cohesion: 0.07
Nodes (45): Protocol, Provider-neutral specialist interface. Implementations receive market data plus…, Return an agent's declared history requirement without widening its protocol., SpecialistAgent, warmup_bars(), analyze_with_context(), _declaration(), optional_capabilities() (+37 more)

### Community 6 - "types.generated.ts"
Cohesion: 0.05
Nodes (54): AdaptiveWeightPayload, AgentDetailResponse, AgentPage, API_VERSION, ApiError, AppliedWeightPayload, ApprovedOrderPayload, BacktestPayload (+46 more)

### Community 7 - "weight_generation"
Cohesion: 0.16
Nodes (17): AdaptiveWeightPayload, EvaluationMetricsPayload, LearningReviewPayload, learning_reviews(), weight_generations(), _adaptive_weight(), _evaluation_metrics(), _json_value() (+9 more)

### Community 8 - "MarketSnapshot"
Cohesion: 0.15
Nodes (21): TrendAgent, run_demo(), CouncilConfig, DeterministicCouncil, BaseModel, field_validator, MarketSnapshot, Completed bars available at ``observed_at`` and capped by ``as_of``. (+13 more)

### Community 9 - "TelemetryEvent"
Cohesion: 0.07
Nodes (29): EventHandler, backtest(), decision(), run(), model_validator, Self, TelemetryEvent, Frontend-safe observability contracts and in-process transport. (+21 more)

### Community 10 - "App.tsx"
Cohesion: 0.06
Nodes (45): AgentSummary, RunSummary, StateResponse, TelemetryEvent, react, ApiProblem, bootstrap(), getUnknown() (+37 more)

### Community 11 - "serializers.py"
Cohesion: 0.06
Nodes (75): ExperimentBatchResponse, ExperimentRequestPayload, MarketContextPayload, PortfolioPayload, SnapshotPayload, AdaptiveWeightPayload, AgentDetailResponse, AgentPage (+67 more)

### Community 12 - "researchViews.tsx"
Cohesion: 0.08
Nodes (40): ExperienceDetailPayload, ExperienceSummaryPayload, ExperimentEvaluationPayload, ExperimentForecastPayload, ExperimentOraclePayload, ExperimentSummaryPayload, LearningReviewPayload, WeightGenerationPayload (+32 more)

### Community 13 - "ExperimentService"
Cohesion: 0.11
Nodes (28): create_app(), Any, Optional read-only HTTP/streaming boundary., InMemoryExperimentRepository, ExperimentService, _bars(), _provider(), Path (+20 more)

### Community 14 - "create_app"
Cohesion: 0.08
Nodes (34): ExperimentEvaluationPayload, ExperimentSummaryPayload, JSONResponse, Request, create_app(), acquire_historical(), cancel_historical_operation(), completed_historical_run() (+26 more)

### Community 15 - "KrakenHistoricalProvider"
Cohesion: 0.16
Nodes (11): JsonTransport, KrakenHistoricalProvider, ProviderError, ProviderRateLimitError, Any, datetime, Protocol, RuntimeError (+3 more)

### Community 16 - "schemas.py"
Cohesion: 0.16
Nodes (27): The stable extension point for deterministic, ML, local-LLM, or hosted agents., Canonical construction of built-in specialist agents., Built-in deterministic specialist agents., clamp(), direction_for(), mean(), timedelta, realized_volatility() (+19 more)

### Community 17 - "learning/models.py"
Cohesion: 0.17
Nodes (19): _bounded_move(), _episode_matches(), Librarian, datetime, Conservative, post-outcome weight proposal generation., _target_weight(), _utc(), AdaptiveWeight (+11 more)

### Community 18 - "test_market_data.py"
Cohesion: 0.32
Nodes (29): FakeTransport, provider(), Any, datetime, parametrize, Path, request(), response() (+21 more)

### Community 19 - "experiments/__init__.py"
Cohesion: 0.17
Nodes (21): aggregate_batch(), _configuration_id(), _configuration_performance(), Outcome-blind seeded selection and transparent batch aggregation., evaluate(), Transparent forecast-versus-outcome measurements., Blind historical experiment API., datetime (+13 more)

### Community 20 - "ExperimentRecord"
Cohesion: 0.23
Nodes (8): ExperimentRecord, ExperimentRepository, FileExperimentRepository, _protect_forecast(), Path, Protocol, Idempotent experiment persistence with immutable forecast enforcement., replace_records()

### Community 21 - "experiments/models.py"
Cohesion: 0.19
Nodes (17): build_agents(), Any, Build the configured agents through one deterministic registry., BlindForecaster, Forecast generation that has no oracle dependency or oracle parameter., AgentVersion, BlindInputProvenance, CouncilWeight (+9 more)

### Community 22 - "datetime"
Cohesion: 0.18
Nodes (8): JsonValue, Any, datetime, field_validator, Boundary helper; deterministic core methods accept explicit timestamps., _utc(), utc_now(), _validate_json_numbers()

### Community 23 - "package.json"
Cohesion: 0.07
Nodes (26): react-dom, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, vitest, dependencies (+18 more)

### Community 24 - "app.py"
Cohesion: 0.08
Nodes (40): FastAPI, Queue, _active_run_ids(), _agent_values(), _configured_experience_store(), _configured_weight_store(), agent(), agents() (+32 more)

### Community 25 - "backtest/freqtrade.py"
Cohesion: 0.28
Nodes (20): _canonical_json(), _effective_config_hash(), _fee_cost(), FreqtradeArtifactError, _load_result(), _normalize_equity(), _normalize_result(), _normalize_trade() (+12 more)

### Community 26 - "historical_recurrence.py"
Cohesion: 0.19
Nodes (18): _anniversary(), _annual_observation(), AnnualRecurrenceObservation, _daily_closes(), _DailyClose, _epochs(), HistoricalRecurrenceEvidence, _numeric_features() (+10 more)

### Community 27 - "_date"
Cohesion: 0.23
Nodes (25): _date(), _bar(), _overlapping_observations(), datetime, _signal(), _snapshot(), test_conflicting_years_reduce_stability_and_confidence(), test_consistent_independent_years_increase_confidence_gradually() (+17 more)

### Community 28 - "datetime"
Cohesion: 0.30
Nodes (3): datetime, field_validator, _utc()

### Community 29 - "EventType"
Cohesion: 0.20
Nodes (20): EventType, StagePayload, event(), datetime, TelemetryEvent, Event construction helpers with explicit causal metadata., build_pipeline(), opening() (+12 more)

### Community 30 - "datetime"
Cohesion: 0.44
Nodes (5): _json_value(), Any, datetime, field_validator, _utc()

### Community 31 - "DeterministicRiskGovernor"
Cohesion: 0.20
Nodes (11): Provider-agnostic market research and paper-trading council., PipelineResult, BaseModel, DeterministicRiskGovernor, datetime, Final, deterministic authority over every proposed order., Vetoes or produces the only order type accepted by execution adapters., CouncilDecision (+3 more)

### Community 32 - "seasonality.py"
Cohesion: 0.18
Nodes (16): _aggregate_years(), _candidate_metadata(), _CandidateMatch, _causal_exclusion_reason(), _confidence(), _exclusion_reason_counts(), _is_zero(), Deterministic prior-year calendar seasonality research signal. (+8 more)

### Community 33 - "RiskPolicy"
Cohesion: 0.23
Nodes (21): BaseModel, model_validator, Self, RiskPolicy, ExecutionCostBounds, RiskStatus, authorized_order(), decision_for() (+13 more)

### Community 34 - "FreqtradeBacktestEngine"
Cohesion: 0.25
Nodes (22): ProcessResult, FreqtradeBacktestEngine, FakeRunner, datetime, MonkeyPatch, parametrize, Path, request() (+14 more)

### Community 35 - "PaperExecutionAdapter"
Cohesion: 0.15
Nodes (17): ExecutionAdapter, datetime, Protocol, A deliberately narrow, paper-only execution boundary., PaperExecutionAdapter, _PaperPosition, datetime, Atomic in-memory simulator with an explicit next-bar-open fill policy. (+9 more)

### Community 36 - "teacher.py"
Cohesion: 0.18
Nodes (20): EvaluationMetrics, MetricComparison, StrEnum, TeacherDecision, apply_changes(), datetime, Immutable profile transformations and versioned local profile storage., reduced_changes() (+12 more)

### Community 37 - "backtest/__init__.py"
Cohesion: 0.12
Nodes (28): AuthoritativeBacktestEngine, AuthoritativeBacktestRequest, AuthoritativeBacktestResult, AuthoritativeModel, EngineProvenance, EquityPoint, NormalizedTrade, _plain_json() (+20 more)

### Community 38 - "test_learning.py"
Cohesion: 0.31
Nodes (17): TeacherConfig, Teacher, base_episode(), learning_episode(), librarian_proposal(), profile(), Path, test_librarian_counts_equivalent_reruns_once() (+9 more)

### Community 39 - "AgentContext"
Cohesion: 0.30
Nodes (13): HistoricalRecurrenceAgent, Compare a fixed calendar region across independent prior-year observations., AgentContext, Non-secret contextual data supplied to a specialist., annual_snapshot(), evidence(), test_agent_factory_and_evidence_serialization_support_new_kind(), test_full_history_recurrence_preserves_independent_years_and_paths() (+5 more)

### Community 40 - "ExecutionStatus"
Cohesion: 0.49
Nodes (14): ExecutionStatus, approved_order(), opening(), datetime, test_completed_bar_cannot_be_filled_retroactively_at_its_open(), test_execution_rejects_fill_before_account_state(), test_fee_and_slippage_authorization_boundaries(), test_freqtrade_translation_rejects_live_mode() (+6 more)

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

### Community 45 - "scenarios.py"
Cohesion: 0.10
Nodes (16): HistoricalAcquisitionRequest, HistoricalOperation, HistoricalScenario, HistoricalScenarioRequest, HistoricalScenarioService, progress(), _instrument(), OperationKind (+8 more)

### Community 46 - "test_issue15_adversarial.py"
Cohesion: 0.22
Nodes (13): Regression invariants from the issue 6 adversarial audit and issue 15 patch.…, repeated_trial(), teacher(), test_equivalent_reruns_cannot_satisfy_independent_holdout_minimum(), test_equivalent_reruns_do_not_create_full_librarian_confidence(), test_exact_duplicate_holdout_ids_are_rejected(), test_external_result_from_future_period_is_rejected(), test_future_decision_cannot_be_mapped_to_an_arbitrarily_old_candle() (+5 more)

### Community 47 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 48 - "test_pipeline.py"
Cohesion: 0.42
Nodes (9): InMemoryMarketDataProvider, build_pipeline(), opening(), datetime, SpyPaperExecutionAdapter, test_historical_snapshot_filters_bars_after_as_of(), test_historical_snapshot_filters_by_availability_not_interval_end(), test_pipeline_executes_only_after_approval() (+1 more)

### Community 49 - "ProcessResult"
Cohesion: 0.22
Nodes (5): CommandRunner, ProcessResult, Protocol, SubprocessCommandRunner, test_success_without_new_export_cannot_reuse_previous_result()

### Community 50 - "Instrument"
Cohesion: 0.15
Nodes (10): CompletedProcess, FreqtradeHistoricalProvider, Any, datetime, Path, Use Freqtrade only for download mechanics; expose canonical Council contracts., SubprocessCommandRunner, Instrument (+2 more)

### Community 51 - "test_pr16_regressions.py"
Cohesion: 0.13
Nodes (20): CouncilDecisionStrategyAdapter, Translate decisions without introducing Freqtrade types into Council contracts., Path, test_standalone_freqtrade_strategy_keeps_strategy_methods_and_version(), datetime, MonkeyPatch, parametrize, Path (+12 more)

### Community 52 - "model_validator"
Cohesion: 0.24
Nodes (3): model_validator, Self, snapshot_identity()

### Community 53 - "model.ts"
Cohesion: 0.24
Nodes (12): AgentSignalPayload, CouncilDecisionPayload, EventType, ExecutionReportPayload, MarketContextPayload, PortfolioPayload, ReconciliationPayload, RiskDecisionPayload (+4 more)

### Community 54 - "test_context.py"
Cohesion: 0.42
Nodes (9): datum(), FakeContextProvider, MacroRequiredAgent, datetime, request(), test_context_rejects_evidence_that_was_not_available_at_cutoff(), test_context_service_is_causal_deterministic_and_cached(), test_missing_optional_capability_is_attached_to_signal_telemetry() (+1 more)

### Community 55 - "Path"
Cohesion: 0.20
Nodes (12): DockerComposeCommandRunner, _file_sha256(), FreqtradeEngineError, FreqtradeProcessError, FreqtradeUnavailableError, _publish_artifact(), Path, RuntimeError (+4 more)

### Community 56 - "generate_typescript.py"
Cohesion: 0.42
Nodes (7): test_generated_typescript_is_current(), _literal(), main(), Any, Generate the frontend contract directly from the public Pydantic models., render(), typescript_type()

### Community 57 - "test_issue17_historical_pipeline.py"
Cohesion: 0.21
Nodes (20): OperationStatus, bars(), FakeFreqtradeRunner, FixtureProvider, datetime, Path, request(), RunnerResult (+12 more)

### Community 58 - "_identity"
Cohesion: 0.46
Nodes (3): _identity(), model_validator, Self

### Community 60 - "HistoricalRequest"
Cohesion: 0.08
Nodes (30): HistoricalDataProvider, HistoricalMarketDataProvider, MarketDataProvider, Any, datetime, Protocol, Discovery and acquisition boundary for substantial historical datasets., Exact-request Parquet cache with version and content-integrity validation. (+22 more)

### Community 61 - "cli.py"
Cohesion: 0.09
Nodes (29): LogRecord, Namespace, historical_cache(), _default_experiment_service(), download_market_data(), _instrument(), main(), _parse_datetime() (+21 more)

### Community 62 - "pipeline.py"
Cohesion: 0.14
Nodes (17): ApprovedOrderPayload, ExecutionReportPayload, ReconciliationPayload, RiskDecisionPayload, datetime, Composition layer for the unidirectional research-to-execution workflow., ResearchTradingPipeline, PipelineFailedPayload (+9 more)

### Community 64 - ".normalize_public_datetimes"
Cohesion: 0.40
Nodes (3): Any, datetime, field_validator

### Community 69 - "config.py"
Cohesion: 0.33
Nodes (9): AppConfig, ExecutionConfig, load_config(), LoggingConfig, Any, BaseModel, Path, Typed, strictly validated TOML configuration. (+1 more)

### Community 70 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 71 - "agent_signal"
Cohesion: 0.12
Nodes (19): AgentSignalPayload, CouncilDecisionPayload, ExperienceDetailPayload, ExperienceSummaryPayload, ExperimentForecastPayload, ExperimentOraclePayload, ExperimentProvenancePayload, experience_episode() (+11 more)

### Community 72 - "Contributor Covenant Code of Conduct"
Cohesion: 0.15
Nodes (12): 1. Correction, 2. Warning, 3. Temporary Ban, 4. Permanent Ban, Attribution, Contributor Covenant Code of Conduct, Enforcement, Enforcement Guidelines (+4 more)

### Community 73 - "model_validator"
Cohesion: 0.36
Nodes (3): model_validator, Self, timedelta

### Community 74 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 75 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 76 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 77 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 82 - "Botnet Council"
Cohesion: 0.22
Nodes (9): Architecture, Botnet Council, Extension points, Included, Non-goals for this scaffold, Optional Freqtrade runtime, Quick start, Repository map (+1 more)

### Community 83 - "Position"
Cohesion: 0.29
Nodes (6): Position, datetime, parametrize, test_market_prices_reject_non_finite_values(), test_portfolio_and_cost_inputs_reject_non_finite_values(), test_portfolio_rejects_incorrect_marked_equity()

### Community 84 - "Historical market data"
Cohesion: 0.25
Nodes (7): Cache and provenance, Causal timestamp translation, Coverage and refresh policy, Historical market data, Known limitations, Manual integration command, Quality and gaps

### Community 85 - "datetime"
Cohesion: 0.57
Nodes (4): datetime, field_validator, _utc(), ValidationInfo

### Community 86 - "architecture.md"
Cohesion: 0.33
Nodes (4): Architecture and safety invariants, Dependency rule, Determinism, Invariants

### Community 87 - "Authoritative backend data pipeline"
Cohesion: 0.29
Nodes (7): Adapter tests, Authoritative backend data pipeline, Context capabilities, Data and control flow, Episode and training boundary, Freqtrade boundary, Running Freqtrade

### Community 88 - "README.md"
Cohesion: 0.33
Nodes (3): Research dashboard, Store configuration, Views and authority

### Community 89 - "Deterministic historical backtesting"
Cohesion: 0.33
Nodes (6): Clock and causal ordering, Current limitations, Deterministic historical backtesting, Metrics and benchmark, Reproducibility and output, Warm-up and evaluation

### Community 90 - "Blind historical experiments"
Cohesion: 0.33
Nodes (6): API separation, Blind historical experiments, Deterministic sampling and batches, Information boundary, Lifecycle, Price and error conventions

### Community 91 - "Extending the system"
Cohesion: 0.33
Nodes (5): Add a backtest adapter, Add a specialist, Add market data, Extending the system, Integrate Freqtrade

### Community 92 - "Telemetry and read-only API"
Cohesion: 0.33
Nodes (6): Contract, Current data limitations, Representative envelopes, REST and WebSocket, Telemetry and read-only API, TypeScript generation

### Community 93 - "Immutable experience cache and replay"
Cohesion: 0.40
Nodes (4): Episode schema, Immutable experience cache and replay, Storage, Temporal training and held-out replay

### Community 94 - "Local Freqtrade Docker boundary"
Cohesion: 0.40
Nodes (4): Download immutable input data, Host prerequisite, Local Freqtrade Docker boundary, Supply Council signals

### Community 95 - "Historical recurrence specialist"
Cohesion: 0.40
Nodes (4): Annual observations, Causal replay, Historical recurrence specialist, Window evidence and safeguards

### Community 96 - "Historical acquisition and scenario API"
Cohesion: 0.40
Nodes (4): Cache behavior, Causality and persistence, Historical acquisition and scenario API, HTTP workflow

### Community 97 - "Librarian, weight profiles, and Teacher validation"
Cohesion: 0.40
Nodes (4): Librarian, Librarian, weight profiles, and Teacher validation, Teacher, Versioned profiles

### Community 98 - "Seasonality specialist V0.1"
Cohesion: 0.40
Nodes (4): Causality, Fixed inputs and matching, Seasonality specialist V0.1, Statistics, stability, and reliability

### Community 99 - "Issue 15 / PR 16 verification"
Cohesion: 0.50
Nodes (3): Corrected follow-up defects, Issue 15 / PR 16 verification, Validation and boundaries

### Community 101 - "ProcessResult"
Cohesion: 0.33
Nodes (3): CommandRunner, ProcessResult, Protocol

### Community 102 - "HistoricalScenarioCreate"
Cohesion: 0.33
Nodes (4): HistoricalAcquisitionCreate, HistoricalScenarioCreate, BaseModel, ScenarioApiModel

### Community 103 - "Q: How does the current market data pipeline ingest, cache, normalize, validate, and supply data to backtests, and where should issue 17 expansion fit?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: How does the current market data pipeline ingest, cache, normalize, validate, and supply data to backtests, and where should issue 17 expansion fit?, Source Nodes

## Knowledge Gaps
- **204 isolated node(s):** `TELEMETRY_SCHEMA_VERSION`, `API_VERSION`, `TelemetryPayload`, `TelemetryEventMap`, `TypedTelemetryEvent` (+199 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 517 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MarketSnapshot` connect `MarketSnapshot` to `engine.py`, `experience/models.py`, `ExperimentContextBuilder`, `context/__init__.py`, `serializers.py`, `KrakenHistoricalProvider`, `schemas.py`, `experiments/models.py`, `datetime`, `historical_recurrence.py`, `_date`, `EventType`, `DeterministicRiskGovernor`, `seasonality.py`, `RiskPolicy`, `FreqtradeBacktestEngine`, `PaperExecutionAdapter`, `AgentContext`, `test_issue15_adversarial.py`, `test_pipeline.py`, `Instrument`, `test_pr16_regressions.py`, `model_validator`, `test_context.py`, `test_issue17_historical_pipeline.py`, `HistoricalRequest`, `cli.py`, `pipeline.py`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Why does `create_app()` connect `create_app` to `experience/models.py`, `ExperimentContextBuilder`, `HistoricalScenarioCreate`, `weight_generation`, `agent_signal`, `TelemetryEvent`, `WeightProfile`, `serializers.py`, `ExperimentService`, `scenarios.py`, `Instrument`, `EventType`, `app.py`, `cli.py`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Why does `HistoricalRequest` connect `HistoricalRequest` to `engine.py`, `ParquetMarketDataCache`, `scenarios.py`, `ExperimentService`, `KrakenHistoricalProvider`, `Instrument`, `experiments/__init__.py`, `test_market_data.py`, `experiments/models.py`, `datetime`, `test_issue17_historical_pipeline.py`, `cli.py`, `.validate_result`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 65 inferred relationships involving `MarketSnapshot` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`MarketSnapshot` has 65 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `create_app()` (e.g. with `require_command_access()` and `HistoricalAcquisitionCreate`) actually correct?**
  _`create_app()` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `AgentContext` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`AgentContext` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `HistoricalRequest` (e.g. with `HistoricalDataProvider` and `HistoricalMarketDataProvider`) actually correct?**
  _`HistoricalRequest` has 8 INFERRED edges - model-reasoned connections that need verification._