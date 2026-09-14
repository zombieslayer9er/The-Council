# Graph Report - BotnetCouncil  (2026-09-13)

## Corpus Check
- 158 files · ~92,660 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: (none) 5, .css 4, .toml 1)

## Summary
- 2228 nodes · 7116 edges · 119 communities (103 shown, 13 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 976 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `35d4fe15`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- engine.py
- experience/models.py
- MarketBar
- ExperimentRequest
- validate.ts
- MarketSnapshot
- types.generated.ts
- historicalView.tsx
- AgentSignal
- TelemetryEvent
- App.tsx
- contracts.py
- researchViews.tsx
- ExperimentService
- create_app
- KrakenHistoricalProvider
- schemas.py
- BacktestEngine
- test_market_data.py
- experiments/models.py
- ExperimentRecord
- backtest/freqtrade.py
- datetime
- package.json
- app.py
- test_api.py
- agents/__init__.py
- _date
- datetime
- weight_generation
- pipeline.py
- Forecast
- seasonality.py
- DeterministicRiskGovernor
- FreqtradeBacktestEngine
- PaperExecutionAdapter
- test_learning.py
- authoritative.py
- ContextCapability
- AgentContext
- ExecutionStatus
- serializers.py
- compilerOptions
- adapters/freqtrade.py
- CouncilSignalStrategy
- scenarios.py
- HistoricalRequest
- What You Must Do When Invoked
- test_pipeline.py
- ExperienceEpisode
- FreqtradeHistoricalProvider
- model.ts
- _of_type
- WeightProfile
- datetime
- DockerComposeCommandRunner
- agent_signal
- test_issue17_historical_pipeline.py
- test_issue15_adversarial.py
- teacher.py
- datetime
- cli.py
- test_pr16_regressions.py
- experiment_summary
- .normalize_public_datetimes
- api/__main__.py
- tools/__init__.py
- botnet-council
- graphify reference: extra exports and benchmark
- _json_value
- Contributor Covenant Code of Conduct
- experience_detail
- graphify reference: query, path, explain
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- AGENTS.md
- extraction-spec.md
- Botnet Council
- test_schemas.py
- Historical market data
- config.py
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
- field_validator
- _error
- Q: How does the current market data pipeline ingest, cache, normalize, validate, and supply data to backtests, and where should issue 17 expansion fit?
- _identity
- Q: Reference issue #17 for upgrading our data pipeline, use graphify to orient yourself and plan the expansion. Implement your plan adhering to the issues needs
- learning_review
- Path
- experiment_oracle
- experiment_batch
- websocket_events
- datetime
- .validate_result
- experiment_request
- experiment_evaluation
- .validate_contract
- Any
- EventType
- Path

## God Nodes (most connected - your core abstractions)
1. `MarketSnapshot` - 137 edges
2. `create_app()` - 73 edges
3. `PublicModel` - 72 edges
4. `AgentContext` - 68 edges
5. `HistoricalRequest` - 58 edges
6. `AgentSignal` - 56 edges
7. `MarketBar` - 56 edges
8. `ParquetMarketDataCache` - 50 edges
9. `BacktestEngine` - 48 edges
10. `to_jsonable()` - 48 edges

## Surprising Connections (you probably didn't know these)
- `test_recurrence_order_changes_fail_explicitly()` --uses--> `MarketSnapshot`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/schemas.py
- `test_recurrence_rejects_future_snapshot_bars()` --uses--> `MarketSnapshot`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/schemas.py
- `test_external_result_from_future_period_is_rejected()` --calls--> `FreqtradeBacktestEngine`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/backtest/freqtrade.py
- `test_future_decision_cannot_be_mapped_to_an_arbitrarily_old_candle()` --uses--> `CouncilDecisionStrategyAdapter`  [INFERRED]
  tests/test_issue15_adversarial.py → src/botnet_council/adapters/freqtrade.py
- `test_fractional_targets_are_not_silently_binary_trades()` --uses--> `CouncilDecisionStrategyAdapter`  [INFERRED]
  tests/test_pr16_regressions.py → src/botnet_council/adapters/freqtrade.py

## Import Cycles
- None detected.

## Communities (119 total, 13 thin omitted)

### Community 0 - "engine.py"
Cohesion: 0.13
Nodes (37): ReconciliationPayload, BacktestCancelledError, _build_agents(), _instrument(), _lifecycle(), _mark(), _MarketMark, Any (+29 more)

### Community 1 - "experience/models.py"
Cohesion: 0.07
Nodes (50): Connection, AgentVersion, AppliedWeight, CouncilReplay, _decision_material(), DecisionEvidence, episode_from_experiment(), _episode_material() (+42 more)

### Community 2 - "MarketBar"
Cohesion: 0.20
Nodes (12): CacheIntegrityError, ParquetMarketDataCache, Any, AvailabilityRange, Path, Return contiguous ranges proven by validated immutable artifacts., A cache artifact failed deterministic content or metadata validation., historical_cache_key() (+4 more)

### Community 3 - "ExperimentRequest"
Cohesion: 0.13
Nodes (17): build_agents(), Any, Build the configured agents through one deterministic registry., HistoricalExperimentSelector, Select using only timestamps, availability, and completeness—not price values., ExperimentContextBuilder, horizon_bars(), instrument() (+9 more)

### Community 4 - "validate.ts"
Cohesion: 0.17
Nodes (60): ACTIONS, adaptiveWeight(), api(), array(), asSignal(), boolean(), CAPABILITIES, council() (+52 more)

### Community 5 - "MarketSnapshot"
Cohesion: 0.09
Nodes (38): context_identity(), ContextDatum, ContextModel, ContextRequest, MarketContext, _plain_json(), BaseModel, model_validator (+30 more)

### Community 6 - "types.generated.ts"
Cohesion: 0.04
Nodes (54): AdaptiveWeightPayload, AgentDetailResponse, AgentPage, API_VERSION, ApiError, AppliedWeightPayload, ApprovedOrderPayload, BacktestPayload (+46 more)

### Community 7 - "historicalView.tsx"
Cohesion: 0.08
Nodes (55): BackendProblem, backendUrl(), backendWebSocketUrl(), isRecord(), requestJson(), targetsLoopback(), acquireHistorical(), auth() (+47 more)

### Community 8 - "AgentSignal"
Cohesion: 0.11
Nodes (25): CouncilDecisionStrategyAdapter, Translate decisions without introducing Freqtrade types into Council contracts., TrendAgent, CouncilConfig, DeterministicCouncil, BaseModel, field_validator, AgentSignal (+17 more)

### Community 9 - "TelemetryEvent"
Cohesion: 0.05
Nodes (51): EventHandler, datetime, ResearchTradingPipeline, EventType, model_validator, Self, StrEnum, RunKind (+43 more)

### Community 10 - "App.tsx"
Cohesion: 0.06
Nodes (45): AgentSummary, BootstrapResponse, RunSummary, StateResponse, TelemetryEvent, react, bootstrap(), isRecord() (+37 more)

### Community 11 - "contracts.py"
Cohesion: 0.12
Nodes (32): AgentDetailResponse, AgentPage, AgentSummary, ApiError, BacktestPayload, BootstrapResponse, DecisionDetailResponse, ErrorResponse (+24 more)

### Community 12 - "researchViews.tsx"
Cohesion: 0.08
Nodes (40): AgentSignalPayload, ExperienceDetailPayload, ExperienceSummaryPayload, ExperimentEvaluationPayload, ExperimentForecastPayload, ExperimentOraclePayload, ExperimentSummaryPayload, LearningReviewPayload (+32 more)

### Community 13 - "ExperimentService"
Cohesion: 0.11
Nodes (30): create_app(), Any, Optional read-only HTTP/streaming boundary., ExperimentAgentConfig, InMemoryExperimentRepository, ExperimentService, completed_experiment(), _bars() (+22 more)

### Community 14 - "create_app"
Cohesion: 0.08
Nodes (30): ExperimentService, FastAPI, create_app(), acquire_historical(), backtest(), cancel_historical_operation(), completed_historical_run(), decision() (+22 more)

### Community 15 - "KrakenHistoricalProvider"
Cohesion: 0.14
Nodes (14): JsonTransport, KrakenHistoricalProvider, ProviderError, ProviderRateLimitError, Any, datetime, Protocol, RuntimeError (+6 more)

### Community 16 - "schemas.py"
Cohesion: 0.15
Nodes (26): Canonical construction of built-in specialist agents., clamp(), direction_for(), mean(), timedelta, realized_volatility(), timeframe_delta(), MeanReversionAgent (+18 more)

### Community 17 - "BacktestEngine"
Cohesion: 0.14
Nodes (28): BacktestEngine, AgentConfig, RiskReconciliation, as_of(), datetime, rising_snapshot(), _fixture(), datetime (+20 more)

### Community 18 - "test_market_data.py"
Cohesion: 0.32
Nodes (29): FakeTransport, provider(), Any, datetime, parametrize, Path, request(), response() (+21 more)

### Community 19 - "experiments/models.py"
Cohesion: 0.14
Nodes (28): aggregate_batch(), _configuration_id(), _configuration_performance(), Outcome-blind seeded selection and transparent batch aggregation., evaluate(), Transparent forecast-versus-outcome measurements., Blind historical experiment API., datetime (+20 more)

### Community 20 - "ExperimentRecord"
Cohesion: 0.23
Nodes (8): ExperimentRecord, ExperimentRepository, FileExperimentRepository, _protect_forecast(), Path, Protocol, Idempotent experiment persistence with immutable forecast enforcement., replace_records()

### Community 21 - "backtest/freqtrade.py"
Cohesion: 0.17
Nodes (30): _canonical_json(), _effective_config_hash(), _fee_cost(), _file_sha256(), FreqtradeArtifactError, FreqtradeEngineError, FreqtradeProcessError, FreqtradeUnavailableError (+22 more)

### Community 22 - "datetime"
Cohesion: 0.10
Nodes (11): JsonValue, Any, datetime, field_validator, model_validator, Self, Boundary helper; deterministic core methods accept explicit timestamps., snapshot_identity() (+3 more)

### Community 23 - "package.json"
Cohesion: 0.07
Nodes (26): react-dom, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, vitest, dependencies (+18 more)

### Community 24 - "app.py"
Cohesion: 0.22
Nodes (20): Any, EventBusSnapshot, RunKind, _active_run_ids(), _agent_values(), backtests(), bootstrap(), runs() (+12 more)

### Community 25 - "test_api.py"
Cohesion: 0.19
Nodes (13): TelemetryEvent, _started(), test_bootstrap_is_atomic_and_runs_use_time_and_explicit_kind(), test_bounded_websocket_queue_marks_slow_consumer_for_resync(), test_empty_state_matches_the_public_response_contract(), test_health_and_collection_contracts_are_versioned(), test_private_site_origin_receives_scoped_local_backend_cors(), test_synthetic_secrets_and_private_paths_do_not_reach_rest_or_websocket() (+5 more)

### Community 26 - "agents/__init__.py"
Cohesion: 0.18
Nodes (19): _anniversary(), _annual_observation(), AnnualRecurrenceObservation, _daily_closes(), _DailyClose, _epochs(), HistoricalRecurrenceEvidence, _numeric_features() (+11 more)

### Community 27 - "_date"
Cohesion: 0.18
Nodes (28): Measure close-to-close returns near the same UTC date in prior years. V0.1…, Conservative calendar history needed by deterministic replay., SeasonalityAgent, _date(), _bar(), _overlapping_observations(), datetime, _signal() (+20 more)

### Community 28 - "datetime"
Cohesion: 0.42
Nodes (3): datetime, field_validator, _utc()

### Community 29 - "weight_generation"
Cohesion: 0.17
Nodes (16): AdaptiveWeightPayload, AdaptiveWeightPayload, ScopedAgentWeightPayload, WeightChangePayload, WeightGenerationPayload, WeightScopePayload, _adaptive_weight(), _json_value() (+8 more)

### Community 30 - "pipeline.py"
Cohesion: 0.15
Nodes (14): ApprovedOrderPayload, ExecutionReportPayload, RiskDecisionPayload, Provider-agnostic market research and paper-trading council., PipelineResult, BaseModel, Composition layer for the unidirectional research-to-execution workflow., datetime (+6 more)

### Community 31 - "Forecast"
Cohesion: 0.23
Nodes (9): BlindForecaster, Forecast generation that has no oracle dependency or oracle parameter., AgentVersion, CouncilWeight, ExperimentContext, Forecast, model_validator, Self (+1 more)

### Community 32 - "seasonality.py"
Cohesion: 0.25
Nodes (13): _aggregate_years(), _candidate_metadata(), _CandidateMatch, _causal_exclusion_reason(), _confidence(), _exclusion_reason_counts(), _is_zero(), Deterministic prior-year calendar seasonality research signal. (+5 more)

### Community 33 - "DeterministicRiskGovernor"
Cohesion: 0.19
Nodes (25): DeterministicRiskGovernor, BaseModel, model_validator, Self, Final, deterministic authority over every proposed order., Vetoes or produces the only order type accepted by execution adapters., RiskPolicy, ExecutionCostBounds (+17 more)

### Community 34 - "FreqtradeBacktestEngine"
Cohesion: 0.25
Nodes (22): ProcessResult, FreqtradeBacktestEngine, FakeRunner, datetime, MonkeyPatch, parametrize, Path, request() (+14 more)

### Community 35 - "PaperExecutionAdapter"
Cohesion: 0.13
Nodes (19): ExecutionAdapter, datetime, Protocol, A deliberately narrow, paper-only execution boundary., PaperExecutionAdapter, _PaperPosition, datetime, Atomic in-memory simulator with an explicit next-bar-open fill policy. (+11 more)

### Community 36 - "test_learning.py"
Cohesion: 0.33
Nodes (16): TeacherConfig, Teacher, learning_episode(), librarian_proposal(), profile(), Path, test_librarian_counts_equivalent_reruns_once(), test_librarian_proposes_bounded_slow_and_fast_changes_without_mutation() (+8 more)

### Community 37 - "authoritative.py"
Cohesion: 0.10
Nodes (27): AuthoritativeBacktestEngine, AuthoritativeBacktestRequest, AuthoritativeBacktestResult, AuthoritativeModel, EngineProvenance, EquityPoint, NormalizedTrade, _plain_json() (+19 more)

### Community 38 - "ContextCapability"
Cohesion: 0.22
Nodes (14): Protocol, The stable extension point for deterministic, ML, local-LLM, or hosted agents., Provider-neutral specialist interface. Implementations receive market data plus…, Return an agent's declared history requirement without widening its protocol., SpecialistAgent, warmup_bars(), analyze_with_context(), _declaration() (+6 more)

### Community 39 - "AgentContext"
Cohesion: 0.33
Nodes (13): HistoricalRecurrenceAgent, Compare a fixed calendar region across independent prior-year observations., AgentContext, Non-secret contextual data supplied to a specialist., annual_snapshot(), evidence(), test_agent_factory_and_evidence_serialization_support_new_kind(), test_full_history_recurrence_preserves_independent_years_and_paths() (+5 more)

### Community 40 - "ExecutionStatus"
Cohesion: 0.49
Nodes (14): ExecutionStatus, approved_order(), opening(), datetime, test_completed_bar_cannot_be_filled_retroactively_at_its_open(), test_execution_rejects_fill_before_account_state(), test_fee_and_slippage_authorization_boundaries(), test_freqtrade_translation_rejects_live_mode() (+6 more)

### Community 41 - "serializers.py"
Cohesion: 0.13
Nodes (21): MarketContextPayload, PortfolioPayload, SnapshotPayload, ApprovedOrderPayload, ContextDatumPayload, ContextProvenancePayload, ExecutionReportPayload, ExperimentLifecyclePayload (+13 more)

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
Cohesion: 0.07
Nodes (23): HistoricalAcquisitionCreate, HistoricalAcquisitionRequest, HistoricalOperation, HistoricalScenario, HistoricalScenarioCreate, HistoricalScenarioRequest, HistoricalScenarioService, progress() (+15 more)

### Community 46 - "HistoricalRequest"
Cohesion: 0.07
Nodes (32): _default_experiment_service(), HistoricalDataProvider, HistoricalMarketDataProvider, MarketDataProvider, Any, datetime, Protocol, Discovery and acquisition boundary for substantial historical datasets. (+24 more)

### Community 47 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 48 - "test_pipeline.py"
Cohesion: 0.49
Nodes (8): InMemoryMarketDataProvider, build_pipeline(), opening(), datetime, test_historical_snapshot_filters_bars_after_as_of(), test_historical_snapshot_filters_by_availability_not_interval_end(), test_pipeline_executes_only_after_approval(), test_veto_prevents_execution()

### Community 49 - "ExperienceEpisode"
Cohesion: 0.14
Nodes (27): ExperienceEpisode, _bounded_move(), _episode_matches(), Librarian, datetime, Conservative, post-outcome weight proposal generation., _target_weight(), _utc() (+19 more)

### Community 50 - "FreqtradeHistoricalProvider"
Cohesion: 0.10
Nodes (14): CompletedProcess, CommandRunner, FreqtradeHistoricalProvider, ProcessResult, Any, AvailabilityRange, datetime, Path (+6 more)

### Community 51 - "model.ts"
Cohesion: 0.26
Nodes (11): CouncilDecisionPayload, EventType, ExecutionReportPayload, MarketContextPayload, PortfolioPayload, ReconciliationPayload, RiskDecisionPayload, SnapshotPayload (+3 more)

### Community 52 - "_of_type"
Cohesion: 0.21
Nodes (11): EventType, HistoricalScenarioService, InMemoryEventBus, agent(), agents(), decisions(), get_portfolio(), _default_historical_service() (+3 more)

### Community 53 - "WeightProfile"
Cohesion: 0.28
Nodes (6): LearningReview, Immutable Librarian proposal joined to its Teacher decision., TeacherResult, WeightProfile, Path, WeightProfileStore

### Community 54 - "datetime"
Cohesion: 0.44
Nodes (5): _json_value(), Any, datetime, field_validator, _utc()

### Community 55 - "DockerComposeCommandRunner"
Cohesion: 0.15
Nodes (7): CommandRunner, DockerComposeCommandRunner, ProcessResult, Protocol, Run the external engine in the repository's isolated Compose service., SubprocessCommandRunner, test_success_without_new_export_cannot_reuse_previous_result()

### Community 56 - "agent_signal"
Cohesion: 0.20
Nodes (11): AgentSignalPayload, CouncilDecisionPayload, ExperimentForecastPayload, AgentSignalPayload, CouncilDecisionPayload, ExperimentForecastPayload, VolatilityPayload, agent_signal() (+3 more)

### Community 57 - "test_issue17_historical_pipeline.py"
Cohesion: 0.23
Nodes (21): OperationStatus, bars(), FakeFreqtradeRunner, FixtureProvider, datetime, Path, request(), RunnerResult (+13 more)

### Community 58 - "test_issue15_adversarial.py"
Cohesion: 0.22
Nodes (13): Regression invariants from the issue 6 adversarial audit and issue 15 patch.…, repeated_trial(), teacher(), test_equivalent_reruns_cannot_satisfy_independent_holdout_minimum(), test_equivalent_reruns_do_not_create_full_librarian_confidence(), test_exact_duplicate_holdout_ids_are_rejected(), test_external_result_from_future_period_is_rejected(), test_future_decision_cannot_be_mapped_to_an_arbitrarily_old_candle() (+5 more)

### Community 59 - "teacher.py"
Cohesion: 0.24
Nodes (14): EvaluationMetrics, apply_changes(), datetime, evaluate_profile(), _maximum_drawdown(), _passes(), datetime, Deterministic held-out validation for Librarian proposals. (+6 more)

### Community 60 - "datetime"
Cohesion: 0.57
Nodes (4): datetime, field_validator, _utc(), ValidationInfo

### Community 61 - "cli.py"
Cohesion: 0.20
Nodes (14): LogRecord, Namespace, ValidationKind, download_market_data(), _instrument(), main(), _parse_datetime(), datetime (+6 more)

### Community 62 - "test_pr16_regressions.py"
Cohesion: 0.18
Nodes (13): datetime, MonkeyPatch, Path, Reproductions for Devin's follow-up review of issue #15 / PR #16., blocked(), test_concurrent_context_misses_share_one_fetch(), test_external_export_requires_period_and_capital_binding(), test_fractional_targets_are_not_silently_binary_trades() (+5 more)

### Community 63 - "experiment_summary"
Cohesion: 0.20
Nodes (10): ExperimentCreateRequest, ExperimentRequest, ExperimentSummaryPayload, create_experiment(), experiment_status(), list_experiments(), run_experiment(), run_experiment_batch() (+2 more)

### Community 64 - ".normalize_public_datetimes"
Cohesion: 0.40
Nodes (3): Any, datetime, field_validator

### Community 70 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 71 - "_json_value"
Cohesion: 0.42
Nodes (5): _json_value(), Any, datetime, field_validator, _utc()

### Community 72 - "Contributor Covenant Code of Conduct"
Cohesion: 0.15
Nodes (12): 1. Correction, 2. Warning, 3. Temporary Ban, 4. Permanent Ban, Attribution, Contributor Covenant Code of Conduct, Enforcement, Enforcement Guidelines (+4 more)

### Community 73 - "experience_detail"
Cohesion: 0.25
Nodes (9): ExperienceDetailPayload, ExperienceSummaryPayload, experience_episodes(), AppliedWeightPayload, ExperienceDetailPayload, ExperienceSummaryPayload, experience_detail(), experience_summary() (+1 more)

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

### Community 83 - "test_schemas.py"
Cohesion: 0.60
Nodes (5): datetime, parametrize, test_market_prices_reject_non_finite_values(), test_portfolio_and_cost_inputs_reject_non_finite_values(), test_portfolio_rejects_incorrect_marked_equity()

### Community 84 - "Historical market data"
Cohesion: 0.25
Nodes (7): Cache and provenance, Causal timestamp translation, Coverage and refresh policy, Historical market data, Known limitations, Manual integration command, Quality and gaps

### Community 85 - "config.py"
Cohesion: 0.33
Nodes (9): AppConfig, ExecutionConfig, load_config(), LoggingConfig, Any, BaseModel, Path, Typed, strictly validated TOML configuration. (+1 more)

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

### Community 101 - "field_validator"
Cohesion: 0.31
Nodes (3): Any, datetime, field_validator

### Community 102 - "_error"
Cohesion: 0.25
Nodes (8): JSONResponse, Request, domain_validation_error(), http_error(), internal_error(), request_id(), validation_error(), _error()

### Community 103 - "Q: How does the current market data pipeline ingest, cache, normalize, validate, and supply data to backtests, and where should issue 17 expansion fit?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: How does the current market data pipeline ingest, cache, normalize, validate, and supply data to backtests, and where should issue 17 expansion fit?, Source Nodes

### Community 104 - "_identity"
Cohesion: 0.46
Nodes (3): _identity(), model_validator, Self

### Community 105 - "Q: Reference issue #17 for upgrading our data pipeline, use graphify to orient yourself and plan the expansion. Implement your plan adhering to the issues needs"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Reference issue #17 for upgrading our data pipeline, use graphify to orient yourself and plan the expansion. Implement your plan adhering to the issues needs, Source Nodes

### Community 106 - "learning_review"
Cohesion: 0.33
Nodes (6): EvaluationMetricsPayload, LearningReviewPayload, EvaluationMetricsPayload, LearningReviewPayload, _evaluation_metrics(), learning_review()

### Community 107 - "Path"
Cohesion: 0.33
Nodes (6): ExperienceStore, Path, _configured_experience_store(), _configured_weight_store(), test_optional_research_stores_are_reported_and_exposed_read_only(), WeightProfileStore

### Community 108 - "experiment_oracle"
Cohesion: 0.33
Nodes (6): ExperimentOraclePayload, ExperimentProvenancePayload, ExperimentOraclePayload, ExperimentProvenancePayload, experiment_oracle(), _experiment_provenance()

### Community 109 - "experiment_batch"
Cohesion: 0.40
Nodes (5): ExperimentBatchResponse, CalibrationBucketPayload, ConfigurationPerformancePayload, ExperimentBatchResponse, experiment_batch()

### Community 110 - "websocket_events"
Cohesion: 0.40
Nodes (5): Queue, websocket_events(), enqueue(), put(), _enqueue_or_lag()

### Community 113 - "experiment_request"
Cohesion: 0.40
Nodes (5): ExperimentRequestPayload, ExperimentAgentRequest, ExperimentCouncilRequest, ExperimentRequestPayload, experiment_request()

### Community 114 - "experiment_evaluation"
Cohesion: 0.50
Nodes (4): ExperimentEvaluationPayload, experiment_evaluation_result(), ExperimentEvaluationPayload, experiment_evaluation()

## Knowledge Gaps
- **216 isolated node(s):** `View`, `NAV`, `BootstrapData`, `StreamCallbacks`, `OperationStatus` (+211 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 550 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `BacktestEngine` (2× useful, score=1.98951841)
- `FreqtradeHistoricalProvider` (2× useful, score=1.98951841)
- `HistoricalScenarioService` (2× useful, score=1.98951841)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MarketSnapshot` connect `MarketSnapshot` to `engine.py`, `experience/models.py`, `ExperimentRequest`, `AgentSignal`, `TelemetryEvent`, `KrakenHistoricalProvider`, `schemas.py`, `BacktestEngine`, `experiments/models.py`, `datetime`, `agents/__init__.py`, `_date`, `pipeline.py`, `Forecast`, `seasonality.py`, `DeterministicRiskGovernor`, `FreqtradeBacktestEngine`, `PaperExecutionAdapter`, `ContextCapability`, `AgentContext`, `serializers.py`, `HistoricalRequest`, `test_pipeline.py`, `FreqtradeHistoricalProvider`, `test_issue17_historical_pipeline.py`, `test_issue15_adversarial.py`, `cli.py`, `test_pr16_regressions.py`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `HistoricalRequest` connect `HistoricalRequest` to `engine.py`, `experience/models.py`, `MarketBar`, `ExperimentRequest`, `scenarios.py`, `ExperimentService`, `KrakenHistoricalProvider`, `.validate_result`, `FreqtradeHistoricalProvider`, `experiments/models.py`, `test_market_data.py`, `test_issue17_historical_pipeline.py`, `datetime`, `cli.py`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `PortfolioState` connect `PaperExecutionAdapter` to `engine.py`, `experience/models.py`, `DeterministicRiskGovernor`, `ExperimentRequest`, `AgentSignal`, `serializers.py`, `schemas.py`, `experiments/models.py`, `test_schemas.py`, `datetime`, `pipeline.py`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Are the 65 inferred relationships involving `MarketSnapshot` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`MarketSnapshot` has 65 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `AgentContext` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`AgentContext` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `HistoricalRequest` (e.g. with `HistoricalDataProvider` and `HistoricalMarketDataProvider`) actually correct?**
  _`HistoricalRequest` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `View`, `NAV`, `BootstrapData` to the rest of the system?**
  _216 weakly-connected nodes found - possible documentation gaps or missing edges._