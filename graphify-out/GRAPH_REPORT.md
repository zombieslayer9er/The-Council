# Graph Report - BotnetCouncil  (2026-09-12)

## Corpus Check
- 147 files · ~82,243 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1854 nodes · 6325 edges · 82 communities (72 shown, 9 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 938 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2d4bbe39`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- engine.py
- experience/models.py
- MarketBar
- ExperimentRequest
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
- KrakenHistoricalProvider
- schemas.py
- ExperienceEpisode
- test_market_data.py
- experiments/models.py
- ExperimentRecord
- api.ts
- datetime
- package.json
- Any
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
- PortfolioState
- teacher.py
- backtest/__init__.py
- test_learning.py
- AgentContext
- PaperExecutionAdapter
- WeightProfile
- compilerOptions
- CouncilDecisionStrategyAdapter
- CouncilSignalStrategy
- model_validator
- test_issue15_adversarial.py
- What You Must Do When Invoked
- test_pipeline.py
- ProcessResult
- Timeframe
- test_pr16_regressions.py
- config.py
- market_data/__init__.py
- Position
- DockerComposeCommandRunner
- generate_typescript.py
- websocket_events
- _identity
- WeightProposal
- HistoricalRequest
- cli.py
- sanitize_exception
- .validate_result
- .normalize_public_datetimes
- api/__main__.py
- tools/__init__.py
- botnet-council
- ExperimentModel
- graphify reference: extra exports and benchmark
- experience_detail
- InMemoryHistoricalProvider
- model_validator
- graphify reference: query, path, explain
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- AGENTS.md
- extraction-spec.md

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

## Communities (82 total, 9 thin omitted)

### Community 0 - "engine.py"
Cohesion: 0.06
Nodes (65): BacktestEngine, _build_agents(), _instrument(), _lifecycle(), _mark(), _MarketMark, Any, datetime (+57 more)

### Community 1 - "experience/models.py"
Cohesion: 0.07
Nodes (49): Connection, Convert frozen domain containers into canonical JSON-compatible values., to_jsonable(), AgentVersion, AppliedWeight, CouncilReplay, _decision_material(), DecisionEvidence (+41 more)

### Community 2 - "MarketBar"
Cohesion: 0.23
Nodes (11): CacheIntegrityError, ParquetMarketDataCache, Any, Path, A cache artifact failed deterministic content or metadata validation., HistoricalBars, MarketDataQualityError, ValueError (+3 more)

### Community 3 - "ExperimentRequest"
Cohesion: 0.11
Nodes (22): build_agents(), Any, Build the configured agents through one deterministic registry., HistoricalExperimentSelector, Select using only timestamps, availability, and completeness—not price values., ExperimentContextBuilder, horizon_bars(), instrument() (+14 more)

### Community 4 - "validate.ts"
Cohesion: 0.17
Nodes (60): ACTIONS, adaptiveWeight(), api(), array(), asSignal(), boolean(), CAPABILITIES, council() (+52 more)

### Community 5 - "context/__init__.py"
Cohesion: 0.06
Nodes (53): Protocol, Provider-neutral specialist interface. Implementations receive market data plus…, Return an agent's declared history requirement without widening its protocol., SpecialistAgent, warmup_bars(), analyze_with_context(), _declaration(), optional_capabilities() (+45 more)

### Community 6 - "types.generated.ts"
Cohesion: 0.05
Nodes (53): AdaptiveWeightPayload, AgentDetailResponse, AgentPage, AgentSignalPayload, API_VERSION, ApiError, AppliedWeightPayload, ApprovedOrderPayload (+45 more)

### Community 7 - "serializers.py"
Cohesion: 0.06
Nodes (62): AdaptiveWeightPayload, AgentSignalPayload, ApprovedOrderPayload, CouncilDecisionPayload, EvaluationMetricsPayload, ExecutionReportPayload, ExperimentForecastPayload, ExperimentProvenancePayload (+54 more)

### Community 8 - "MarketSnapshot"
Cohesion: 0.13
Nodes (25): TrendAgent, run_demo(), CouncilConfig, DeterministicCouncil, BaseModel, field_validator, AgentSignal, MarketSnapshot (+17 more)

### Community 9 - "TelemetryEvent"
Cohesion: 0.08
Nodes (22): EventHandler, backtest(), decision(), run(), _last(), _of_type(), Structured logging without an external dependency., model_validator (+14 more)

### Community 10 - "App.tsx"
Cohesion: 0.07
Nodes (36): AgentSummary, RunSummary, StateResponse, react, App(), BacktestsView(), EventRow(), HistoryView() (+28 more)

### Community 11 - "app.py"
Cohesion: 0.10
Nodes (48): ExperimentBatchResponse, ExperimentRequestPayload, SnapshotPayload, run_experiment_batch(), _experiment_request(), FastAPI application backed exclusively by public telemetry events., AgentDetailResponse, AgentPage (+40 more)

### Community 12 - "researchViews.tsx"
Cohesion: 0.08
Nodes (39): ExperienceDetailPayload, ExperienceSummaryPayload, ExperimentEvaluationPayload, ExperimentForecastPayload, ExperimentOraclePayload, ExperimentSummaryPayload, LearningReviewPayload, WeightGenerationPayload (+31 more)

### Community 13 - "ExperimentService"
Cohesion: 0.12
Nodes (28): create_app(), Any, InMemoryExperimentRepository, ExperimentService, _bars(), _provider(), Path, _request() (+20 more)

### Community 14 - "create_app"
Cohesion: 0.06
Nodes (41): ExperimentEvaluationPayload, ExperimentOraclePayload, ExperimentSummaryPayload, FastAPI, JSONResponse, Request, _configured_experience_store(), _configured_weight_store() (+33 more)

### Community 15 - "KrakenHistoricalProvider"
Cohesion: 0.16
Nodes (10): JsonTransport, KrakenHistoricalProvider, ProviderError, ProviderRateLimitError, Any, datetime, Protocol, RuntimeError (+2 more)

### Community 16 - "schemas.py"
Cohesion: 0.14
Nodes (26): The stable extension point for deterministic, ML, local-LLM, or hosted agents., Canonical construction of built-in specialist agents., Built-in deterministic specialist agents., timedelta, realized_volatility(), timeframe_delta(), MeanReversionAgent, RegimeClassificationAgent (+18 more)

### Community 17 - "ExperienceEpisode"
Cohesion: 0.16
Nodes (21): ExperienceEpisode, _bounded_move(), _episode_matches(), Librarian, datetime, Conservative, post-outcome weight proposal generation., _target_weight(), _utc() (+13 more)

### Community 18 - "test_market_data.py"
Cohesion: 0.32
Nodes (29): FakeTransport, provider(), Any, datetime, parametrize, Path, request(), response() (+21 more)

### Community 19 - "experiments/models.py"
Cohesion: 0.17
Nodes (23): aggregate_batch(), _configuration_id(), _configuration_performance(), Outcome-blind seeded selection and transparent batch aggregation., evaluate(), Transparent forecast-versus-outcome measurements., Blind historical experiment API., datetime (+15 more)

### Community 20 - "ExperimentRecord"
Cohesion: 0.23
Nodes (8): ExperimentRecord, ExperimentRepository, FileExperimentRepository, _protect_forecast(), Path, Protocol, Idempotent experiment persistence with immutable forecast enforcement., replace_records()

### Community 21 - "api.ts"
Cohesion: 0.12
Nodes (24): BootstrapResponse, ExperiencePage, ExperienceResponse, ExperimentEvaluationResponse, ExperimentForecastResponse, ExperimentOracleResponse, ExperimentPage, HealthResponse (+16 more)

### Community 22 - "datetime"
Cohesion: 0.18
Nodes (8): JsonValue, Any, datetime, field_validator, Boundary helper; deterministic core methods accept explicit timestamps., _utc(), utc_now(), _validate_json_numbers()

### Community 23 - "package.json"
Cohesion: 0.08
Nodes (25): react-dom, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, dependencies, react (+17 more)

### Community 24 - "Any"
Cohesion: 0.13
Nodes (21): _active_run_ids(), _agent_values(), backtests(), bootstrap(), decisions(), get_portfolio(), runs(), snapshot() (+13 more)

### Community 25 - "backtest/freqtrade.py"
Cohesion: 0.19
Nodes (26): _canonical_json(), _effective_config_hash(), _fee_cost(), _file_sha256(), FreqtradeArtifactError, FreqtradeProcessError, _load_result(), _normalize_equity() (+18 more)

### Community 26 - "historical_recurrence.py"
Cohesion: 0.19
Nodes (18): _anniversary(), _annual_observation(), AnnualRecurrenceObservation, _daily_closes(), _DailyClose, _epochs(), HistoricalRecurrenceEvidence, _numeric_features() (+10 more)

### Community 27 - "_date"
Cohesion: 0.18
Nodes (28): Measure close-to-close returns near the same UTC date in prior years. V0.1…, Conservative calendar history needed by deterministic replay., SeasonalityAgent, _date(), _bar(), _overlapping_observations(), datetime, _signal() (+20 more)

### Community 28 - "datetime"
Cohesion: 0.33
Nodes (4): ExperimentAgentConfig, datetime, field_validator, _utc()

### Community 29 - "EventType"
Cohesion: 0.16
Nodes (25): datetime, ResearchTradingPipeline, EventType, PipelineFailedPayload, StagePayload, event(), datetime, TelemetryEvent (+17 more)

### Community 30 - "datetime"
Cohesion: 0.44
Nodes (5): _json_value(), Any, datetime, field_validator, _utc()

### Community 31 - "DeterministicRiskGovernor"
Cohesion: 0.20
Nodes (11): Provider-agnostic market research and paper-trading council., PipelineResult, BaseModel, DeterministicRiskGovernor, datetime, Final, deterministic authority over every proposed order., Vetoes or produces the only order type accepted by execution adapters., CouncilDecision (+3 more)

### Community 32 - "seasonality.py"
Cohesion: 0.20
Nodes (16): clamp(), direction_for(), mean(), _aggregate_years(), _candidate_metadata(), _CandidateMatch, _causal_exclusion_reason(), _confidence() (+8 more)

### Community 33 - "RiskPolicy"
Cohesion: 0.23
Nodes (21): BaseModel, model_validator, Self, RiskPolicy, ExecutionCostBounds, RiskStatus, authorized_order(), decision_for() (+13 more)

### Community 34 - "FreqtradeBacktestEngine"
Cohesion: 0.28
Nodes (20): FreqtradeBacktestEngine, FakeRunner, datetime, MonkeyPatch, parametrize, Path, request(), result_payload() (+12 more)

### Community 35 - "PortfolioState"
Cohesion: 0.14
Nodes (15): ExecutionAdapter, datetime, Protocol, A deliberately narrow, paper-only execution boundary., _PaperPosition, datetime, ApprovedOrder, DomainModel (+7 more)

### Community 36 - "teacher.py"
Cohesion: 0.18
Nodes (19): EvaluationMetrics, MetricComparison, StrEnum, TeacherDecision, apply_changes(), datetime, Immutable profile transformations and versioned local profile storage., reduced_changes() (+11 more)

### Community 37 - "backtest/__init__.py"
Cohesion: 0.12
Nodes (28): AuthoritativeBacktestEngine, AuthoritativeBacktestRequest, AuthoritativeBacktestResult, AuthoritativeModel, EngineProvenance, EquityPoint, NormalizedTrade, _plain_json() (+20 more)

### Community 38 - "test_learning.py"
Cohesion: 0.31
Nodes (17): TeacherConfig, Teacher, base_episode(), learning_episode(), librarian_proposal(), profile(), Path, test_librarian_counts_equivalent_reruns_once() (+9 more)

### Community 39 - "AgentContext"
Cohesion: 0.33
Nodes (13): HistoricalRecurrenceAgent, Compare a fixed calendar region across independent prior-year observations., AgentContext, Non-secret contextual data supplied to a specialist., annual_snapshot(), evidence(), test_agent_factory_and_evidence_serialization_support_new_kind(), test_full_history_recurrence_preserves_independent_years_and_paths() (+5 more)

### Community 40 - "PaperExecutionAdapter"
Cohesion: 0.46
Nodes (16): PaperExecutionAdapter, Atomic in-memory simulator with an explicit next-bar-open fill policy., ExecutionStatus, approved_order(), opening(), datetime, test_completed_bar_cannot_be_filled_retroactively_at_its_open(), test_execution_rejects_fill_before_account_state() (+8 more)

### Community 41 - "WeightProfile"
Cohesion: 0.28
Nodes (6): LearningReview, Immutable Librarian proposal joined to its Teacher decision., TeacherResult, WeightProfile, Path, WeightProfileStore

### Community 42 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, esModuleInterop, isolatedModules, jsx, lib, module, moduleResolution (+8 more)

### Community 43 - "CouncilDecisionStrategyAdapter"
Cohesion: 0.15
Nodes (16): PaperMode, CouncilDecisionStrategyAdapter, FreqtradeOrderRequest, FreqtradeStrategySignal, datetime, Path, timedelta, Pure translation into Freqtrade-shaped paper/backtest requests. No Freqtrade… (+8 more)

### Community 44 - "CouncilSignalStrategy"
Cohesion: 0.21
Nodes (10): DataFrame, CouncilSignalStrategy, _parse_datetime(), Any, datetime, timedelta, Standalone Freqtrade strategy consuming a frozen Council signal artifact. This…, _timeframe_duration() (+2 more)

### Community 45 - "model_validator"
Cohesion: 0.24
Nodes (3): model_validator, Self, snapshot_identity()

### Community 46 - "test_issue15_adversarial.py"
Cohesion: 0.22
Nodes (13): Regression invariants from the issue 6 adversarial audit and issue 15 patch.…, repeated_trial(), teacher(), test_equivalent_reruns_cannot_satisfy_independent_holdout_minimum(), test_equivalent_reruns_do_not_create_full_librarian_confidence(), test_exact_duplicate_holdout_ids_are_rejected(), test_external_result_from_future_period_is_rejected(), test_future_decision_cannot_be_mapped_to_an_arbitrarily_old_candle() (+5 more)

### Community 47 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 48 - "test_pipeline.py"
Cohesion: 0.45
Nodes (9): InMemoryMarketDataProvider, build_pipeline(), opening(), datetime, SpyPaperExecutionAdapter, test_historical_snapshot_filters_bars_after_as_of(), test_historical_snapshot_filters_by_availability_not_interval_end(), test_pipeline_executes_only_after_approval() (+1 more)

### Community 49 - "ProcessResult"
Cohesion: 0.22
Nodes (7): CommandRunner, ProcessResult, Protocol, SubprocessCommandRunner, run(), test_success_without_new_export_cannot_reuse_previous_result(), run()

### Community 50 - "Timeframe"
Cohesion: 0.19
Nodes (11): _default_experiment_service(), CachedHistoricalProvider, datetime, Caching decorator for a historical market-data provider., Kraken Spot REST OHLC adapter with explicit causal timestamp translation., Asset, Instrument, StrEnum (+3 more)

### Community 51 - "test_pr16_regressions.py"
Cohesion: 0.25
Nodes (10): Path, Reproductions for Devin's follow-up review of issue #15 / PR #16., blocked(), test_experience_summary_exposes_exact_origin(), test_external_export_requires_period_and_capital_binding(), test_fractional_targets_are_not_silently_binary_trades(), test_native_runner_receives_absolute_paths(), run() (+2 more)

### Community 52 - "config.py"
Cohesion: 0.33
Nodes (9): AppConfig, ExecutionConfig, load_config(), LoggingConfig, Any, BaseModel, Path, Typed, strictly validated TOML configuration. (+1 more)

### Community 53 - "market_data/__init__.py"
Cohesion: 0.19
Nodes (5): HistoricalMarketDataProvider, MarketDataProvider, datetime, Protocol, ProviderMetadata

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

### Community 60 - "HistoricalRequest"
Cohesion: 0.19
Nodes (16): Exact-request Parquet cache with version and content-integrity validation., DataGap, DataQualityReport, historical_cache_key(), HistoricalRequest, MarketDataModel, ProviderId, BaseModel (+8 more)

### Community 61 - "cli.py"
Cohesion: 0.24
Nodes (12): LogRecord, Namespace, download_market_data(), _instrument(), main(), _parse_datetime(), datetime, Deterministic demo, historical download, and backtest commands. (+4 more)

### Community 62 - "sanitize_exception"
Cohesion: 0.40
Nodes (5): Exception, Central policy for safe, low-detail public error messages., Return a stable public description while retaining no raw exception text., sanitize_exception(), SanitizedError

### Community 64 - ".normalize_public_datetimes"
Cohesion: 0.40
Nodes (3): Any, datetime, field_validator

### Community 69 - "ExperimentModel"
Cohesion: 0.38
Nodes (9): BlindForecaster, Forecast generation that has no oracle dependency or oracle parameter., AgentVersion, CouncilWeight, ExperimentContext, ExperimentModel, Forecast, BaseModel (+1 more)

### Community 70 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 71 - "experience_detail"
Cohesion: 0.25
Nodes (9): ExperienceDetailPayload, ExperienceSummaryPayload, experience_episode(), experience_episodes(), AppliedWeightPayload, ExperienceDetailPayload, ExperienceSummaryPayload, experience_detail() (+1 more)

### Community 72 - "InMemoryHistoricalProvider"
Cohesion: 0.22
Nodes (3): InMemoryHistoricalProvider, datetime, Deterministic historical provider for synthetic research fixtures.

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

## Knowledge Gaps
- **128 isolated node(s):** `Usage`, `What graphify is for`, `Step 0 - GitHub repos and multi-path merge (only if a URL or several paths)`, `Step 1 - Ensure graphify is installed`, `Step 2 - Detect files` (+123 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 417 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MarketSnapshot` connect `MarketSnapshot` to `engine.py`, `experience/models.py`, `ExperimentRequest`, `context/__init__.py`, `serializers.py`, `app.py`, `KrakenHistoricalProvider`, `schemas.py`, `experiments/models.py`, `datetime`, `historical_recurrence.py`, `_date`, `EventType`, `DeterministicRiskGovernor`, `seasonality.py`, `RiskPolicy`, `FreqtradeBacktestEngine`, `PortfolioState`, `AgentContext`, `model_validator`, `test_issue15_adversarial.py`, `test_pipeline.py`, `Timeframe`, `market_data/__init__.py`, `HistoricalRequest`, `cli.py`, `ExperimentModel`, `InMemoryHistoricalProvider`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Why does `KrakenHistoricalProvider` connect `KrakenHistoricalProvider` to `MarketBar`, `MarketSnapshot`, `app.py`, `Timeframe`, `test_market_data.py`, `market_data/__init__.py`, `HistoricalRequest`, `cli.py`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Why does `MarketBar` connect `MarketBar` to `engine.py`, `experience/models.py`, `MarketSnapshot`, `ExperimentService`, `KrakenHistoricalProvider`, `schemas.py`, `datetime`, `historical_recurrence.py`, `_date`, `EventType`, `seasonality.py`, `PortfolioState`, `test_learning.py`, `AgentContext`, `model_validator`, `test_pipeline.py`, `Timeframe`, `Position`, `HistoricalRequest`, `cli.py`, `InMemoryHistoricalProvider`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Are the 63 inferred relationships involving `MarketSnapshot` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`MarketSnapshot` has 63 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `create_app()` (e.g. with `require_command_access()` and `AgentDetailResponse`) actually correct?**
  _`create_app()` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `AgentContext` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`AgentContext` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `AgentSignal` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`AgentSignal` has 19 INFERRED edges - model-reasoned connections that need verification._