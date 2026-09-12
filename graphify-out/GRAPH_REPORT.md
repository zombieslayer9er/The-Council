# Graph Report - BotnetCouncil  (2026-09-12)

## Corpus Check
- 153 files · ~87,815 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 10 file(s) not represented in the graph (top: (none) 5, .css 3, .toml 1)

## Summary
- 2149 nodes · 6777 edges · 96 communities (82 shown, 12 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 966 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `525d63dd`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- BacktestEngine
- experience/models.py
- ParquetMarketDataCache
- ExperimentRequest
- validate.ts
- test_pr16_regressions.py
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
- teacher.py
- test_market_data.py
- experiments/models.py
- ExperimentRecord
- engine.py
- datetime
- package.json
- _of_type
- api.ts
- agents/__init__.py
- SignalValidity
- datetime
- pipeline.py
- backtest/models.py
- field_validator
- seasonality.py
- DeterministicRiskGovernor
- backtest/freqtrade.py
- PaperExecutionAdapter
- websocket_events
- authoritative.py
- rising_snapshot
- AgentContext
- ExecutionStatus
- metrics.py
- compilerOptions
- CouncilDecision
- CouncilSignalStrategy
- scenarios.py
- .validate_contract
- What You Must Do When Invoked
- test_pipeline.py
- .validate_limits
- FreqtradeHistoricalProvider
- model_validator
- generate_typescript.py
- test_issue17_historical_pipeline.py
- HistoricalRequest
- cli.py
- risk_decision
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
- Q: How does the current market data pipeline ingest, cache, normalize, validate, and supply data to backtests, and where should issue 17 expansion fit?

## God Nodes (most connected - your core abstractions)
1. `MarketSnapshot` - 120 edges
2. `create_app()` - 100 edges
3. `PublicModel` - 72 edges
4. `AgentContext` - 66 edges
5. `HistoricalRequest` - 56 edges
6. `AgentSignal` - 52 edges
7. `ParquetMarketDataCache` - 48 edges
8. `to_jsonable()` - 46 edges
9. `TelemetryEvent` - 46 edges
10. `Instrument` - 43 edges

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

## Communities (96 total, 12 thin omitted)

### Community 0 - "BacktestEngine"
Cohesion: 0.16
Nodes (26): BacktestEngine, EventPublisher, MarketBar, A completed candle with an explicit provider-derived availability time., _fixture(), datetime, MonkeyPatch, Path (+18 more)

### Community 1 - "experience/models.py"
Cohesion: 0.08
Nodes (48): Connection, AgentVersion, AppliedWeight, CouncilReplay, _decision_material(), DecisionEvidence, episode_from_experiment(), _episode_material() (+40 more)

### Community 2 - "ParquetMarketDataCache"
Cohesion: 0.21
Nodes (10): MarketDataQualityError, CacheIntegrityError, ParquetMarketDataCache, Any, MarketBar, Path, Return contiguous ranges proven by validated immutable artifacts., A cache artifact failed deterministic content or metadata validation. (+2 more)

### Community 3 - "ExperimentRequest"
Cohesion: 0.13
Nodes (18): build_agents(), Any, Build the configured agents through one deterministic registry., HistoricalExperimentSelector, Select using only timestamps, availability, and completeness—not price values., ExperimentContextBuilder, horizon_bars(), instrument() (+10 more)

### Community 4 - "validate.ts"
Cohesion: 0.17
Nodes (60): ACTIONS, adaptiveWeight(), api(), array(), asSignal(), boolean(), CAPABILITIES, council() (+52 more)

### Community 5 - "test_pr16_regressions.py"
Cohesion: 0.05
Nodes (64): Protocol, Provider-neutral specialist interface. Implementations receive market data plus…, Return an agent's declared history requirement without widening its protocol., SpecialistAgent, warmup_bars(), analyze_with_context(), _declaration(), optional_capabilities() (+56 more)

### Community 6 - "types.generated.ts"
Cohesion: 0.05
Nodes (53): AdaptiveWeightPayload, AgentDetailResponse, AgentPage, AgentSignalPayload, API_VERSION, ApiError, AppliedWeightPayload, ApprovedOrderPayload (+45 more)

### Community 7 - "weight_generation"
Cohesion: 0.16
Nodes (17): AdaptiveWeightPayload, EvaluationMetricsPayload, LearningReviewPayload, learning_reviews(), weight_generations(), _adaptive_weight(), _evaluation_metrics(), _json_value() (+9 more)

### Community 8 - "MarketSnapshot"
Cohesion: 0.12
Nodes (24): CouncilDecisionStrategyAdapter, Translate decisions without introducing Freqtrade types into Council contracts., TrendAgent, CouncilConfig, DeterministicCouncil, BaseModel, field_validator, MarketSnapshot (+16 more)

### Community 9 - "TelemetryEvent"
Cohesion: 0.09
Nodes (19): EventHandler, backtest(), decision(), run(), model_validator, Self, TelemetryEvent, Frontend-safe observability contracts and in-process transport. (+11 more)

### Community 10 - "App.tsx"
Cohesion: 0.07
Nodes (36): AgentSummary, RunSummary, StateResponse, react, App(), BacktestsView(), EventRow(), HistoryView() (+28 more)

### Community 11 - "serializers.py"
Cohesion: 0.07
Nodes (79): ExperimentBatchResponse, ExperimentRequestPayload, MarketContextPayload, PortfolioPayload, SnapshotPayload, FastAPI application backed exclusively by public telemetry events., AdaptiveWeightPayload, AgentDetailResponse (+71 more)

### Community 12 - "researchViews.tsx"
Cohesion: 0.08
Nodes (39): ExperienceDetailPayload, ExperienceSummaryPayload, ExperimentEvaluationPayload, ExperimentForecastPayload, ExperimentOraclePayload, ExperimentSummaryPayload, LearningReviewPayload, WeightGenerationPayload (+31 more)

### Community 13 - "ExperimentService"
Cohesion: 0.10
Nodes (33): create_app(), Any, Optional read-only HTTP/streaming boundary., ExperimentAgentConfig, RandomExperimentRequest, InMemoryExperimentRepository, ExperimentService, completed_experiment() (+25 more)

### Community 14 - "create_app"
Cohesion: 0.06
Nodes (51): ExperienceStore, ExperimentEvaluationPayload, ExperimentRequest, ExperimentService, ExperimentSummaryPayload, FastAPI, JSONResponse, Request (+43 more)

### Community 15 - "KrakenHistoricalProvider"
Cohesion: 0.12
Nodes (14): _default_experiment_service(), JsonTransport, KrakenHistoricalProvider, ProviderError, ProviderRateLimitError, Any, datetime, Protocol (+6 more)

### Community 16 - "schemas.py"
Cohesion: 0.14
Nodes (29): The stable extension point for deterministic, ML, local-LLM, or hosted agents., Canonical construction of built-in specialist agents., clamp(), direction_for(), mean(), timedelta, realized_volatility(), timeframe_delta() (+21 more)

### Community 17 - "teacher.py"
Cohesion: 0.05
Nodes (79): _bounded_move(), _episode_matches(), Librarian, datetime, Conservative, post-outcome weight proposal generation., _target_weight(), _utc(), AdaptiveWeight (+71 more)

### Community 18 - "test_market_data.py"
Cohesion: 0.32
Nodes (29): FakeTransport, provider(), Any, datetime, parametrize, Path, request(), response() (+21 more)

### Community 19 - "experiments/models.py"
Cohesion: 0.14
Nodes (32): aggregate_batch(), _configuration_id(), _configuration_performance(), Outcome-blind seeded selection and transparent batch aggregation., evaluate(), Transparent forecast-versus-outcome measurements., BlindForecaster, Forecast generation that has no oracle dependency or oracle parameter. (+24 more)

### Community 20 - "ExperimentRecord"
Cohesion: 0.23
Nodes (8): ExperimentRecord, ExperimentRepository, FileExperimentRepository, _protect_forecast(), Path, Protocol, Idempotent experiment persistence with immutable forecast enforcement., replace_records()

### Community 21 - "engine.py"
Cohesion: 0.14
Nodes (25): ApprovedOrder, InMemoryMarketDataProvider, PaperExecutionAdapter, PortfolioState, SpecialistAgent, BacktestCancelledError, _build_agents(), _instrument() (+17 more)

### Community 22 - "datetime"
Cohesion: 0.18
Nodes (8): JsonValue, Any, datetime, field_validator, Boundary helper; deterministic core methods accept explicit timestamps., _utc(), utc_now(), _validate_json_numbers()

### Community 23 - "package.json"
Cohesion: 0.08
Nodes (25): react-dom, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, dependencies, react (+17 more)

### Community 24 - "_of_type"
Cohesion: 0.10
Nodes (27): EventBusSnapshot, InMemoryEventBus, _active_run_ids(), _agent_values(), agent(), agents(), backtests(), bootstrap() (+19 more)

### Community 25 - "api.ts"
Cohesion: 0.12
Nodes (24): BootstrapResponse, ExperiencePage, ExperienceResponse, ExperimentEvaluationResponse, ExperimentForecastResponse, ExperimentOracleResponse, ExperimentPage, HealthResponse (+16 more)

### Community 26 - "agents/__init__.py"
Cohesion: 0.18
Nodes (19): _anniversary(), _annual_observation(), AnnualRecurrenceObservation, _daily_closes(), _DailyClose, _epochs(), HistoricalRecurrenceEvidence, _numeric_features() (+11 more)

### Community 27 - "SignalValidity"
Cohesion: 0.19
Nodes (29): Measure close-to-close returns near the same UTC date in prior years. V0.1…, Conservative calendar history needed by deterministic replay., SeasonalityAgent, _date(), SignalValidity, _bar(), _overlapping_observations(), datetime (+21 more)

### Community 28 - "datetime"
Cohesion: 0.42
Nodes (3): datetime, field_validator, _utc()

### Community 29 - "pipeline.py"
Cohesion: 0.11
Nodes (35): ExecutionReportPayload, ReconciliationPayload, datetime, Composition layer for the unidirectional research-to-execution workflow., ResearchTradingPipeline, RiskReconciliation, EventType, PipelineFailedPayload (+27 more)

### Community 30 - "backtest/models.py"
Cohesion: 0.24
Nodes (16): AgentConfig, BacktestDataProvenance, BacktestEvent, BacktestLedger, BacktestModel, BacktestResult, BacktestRun, BenchmarkMetrics (+8 more)

### Community 31 - "field_validator"
Cohesion: 0.31
Nodes (3): Any, datetime, field_validator

### Community 32 - "seasonality.py"
Cohesion: 0.25
Nodes (13): _aggregate_years(), _candidate_metadata(), _CandidateMatch, _causal_exclusion_reason(), _confidence(), _exclusion_reason_counts(), _is_zero(), Deterministic prior-year calendar seasonality research signal. (+5 more)

### Community 33 - "DeterministicRiskGovernor"
Cohesion: 0.28
Nodes (23): DeterministicRiskGovernor, BaseModel, Vetoes or produces the only order type accepted by execution adapters., RiskPolicy, ExecutionCostBounds, RiskStatus, authorized_order(), decision_for() (+15 more)

### Community 34 - "backtest/freqtrade.py"
Cohesion: 0.07
Nodes (65): AuthoritativeBacktestRequest, AuthoritativeBacktestResult, EquityPoint, NormalizedTrade, ProcessResult, _canonical_json(), CommandRunner, DockerComposeCommandRunner (+57 more)

### Community 35 - "PaperExecutionAdapter"
Cohesion: 0.14
Nodes (17): ExecutionAdapter, datetime, Protocol, A deliberately narrow, paper-only execution boundary., PaperExecutionAdapter, _PaperPosition, datetime, Atomic in-memory simulator with an explicit next-bar-open fill policy. (+9 more)

### Community 36 - "websocket_events"
Cohesion: 0.25
Nodes (8): Queue, websocket_events(), enqueue(), put(), _enqueue_or_lag(), _event_json(), _parse_event_types(), EventType

### Community 37 - "authoritative.py"
Cohesion: 0.09
Nodes (32): AuthoritativeBacktestEngine, AuthoritativeBacktestRequest, AuthoritativeBacktestResult, AuthoritativeModel, EngineProvenance, EquityPoint, _json_value(), NormalizedTrade (+24 more)

### Community 38 - "rising_snapshot"
Cohesion: 0.83
Nodes (3): as_of(), datetime, rising_snapshot()

### Community 39 - "AgentContext"
Cohesion: 0.24
Nodes (15): HistoricalRecurrenceAgent, Compare a fixed calendar region across independent prior-year observations., AgentContext, Non-secret contextual data supplied to a specialist., MacroRequiredAgent, test_missing_required_capability_abstains_without_calling_agent(), annual_snapshot(), evidence() (+7 more)

### Community 40 - "ExecutionStatus"
Cohesion: 0.49
Nodes (14): ExecutionStatus, approved_order(), opening(), datetime, test_completed_bar_cannot_be_filled_retroactively_at_its_open(), test_execution_rejects_fill_before_account_state(), test_fee_and_slippage_authorization_boundaries(), test_freqtrade_translation_rejects_live_mode() (+6 more)

### Community 42 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, esModuleInterop, isolatedModules, jsx, lib, module, moduleResolution (+8 more)

### Community 43 - "CouncilDecision"
Cohesion: 0.11
Nodes (18): PaperMode, FreqtradeOrderRequest, FreqtradeStrategySignal, datetime, Path, timedelta, Pure translation into Freqtrade-shaped paper/backtest requests. No Freqtrade…, Write immutable input for a Freqtrade strategy's signal merge step. (+10 more)

### Community 44 - "CouncilSignalStrategy"
Cohesion: 0.21
Nodes (10): DataFrame, CouncilSignalStrategy, _parse_datetime(), Any, datetime, timedelta, Standalone Freqtrade strategy consuming a frozen Council signal artifact. This…, _timeframe_duration() (+2 more)

### Community 45 - "scenarios.py"
Cohesion: 0.08
Nodes (23): CouncilDecision, HistoricalAcquisitionCreate, HistoricalAcquisitionRequest, HistoricalOperation, HistoricalScenario, HistoricalScenarioCreate, HistoricalScenarioRequest, HistoricalScenarioService (+15 more)

### Community 47 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 48 - "test_pipeline.py"
Cohesion: 0.45
Nodes (9): InMemoryMarketDataProvider, build_pipeline(), opening(), datetime, SpyPaperExecutionAdapter, test_historical_snapshot_filters_bars_after_as_of(), test_historical_snapshot_filters_by_availability_not_interval_end(), test_pipeline_executes_only_after_approval() (+1 more)

### Community 50 - "FreqtradeHistoricalProvider"
Cohesion: 0.11
Nodes (11): CompletedProcess, _default_historical_service(), CommandRunner, FreqtradeHistoricalProvider, ProcessResult, Any, datetime, Path (+3 more)

### Community 52 - "model_validator"
Cohesion: 0.24
Nodes (3): model_validator, Self, snapshot_identity()

### Community 56 - "generate_typescript.py"
Cohesion: 0.42
Nodes (7): test_generated_typescript_is_current(), _literal(), main(), Any, Generate the frontend contract directly from the public Pydantic models., render(), typescript_type()

### Community 57 - "test_issue17_historical_pipeline.py"
Cohesion: 0.19
Nodes (22): OperationStatus, bars(), FakeFreqtradeRunner, FixtureProvider, datetime, MarketBar, MarketSnapshot, Path (+14 more)

### Community 60 - "HistoricalRequest"
Cohesion: 0.07
Nodes (39): HistoricalDataProvider, HistoricalMarketDataProvider, MarketDataProvider, Any, datetime, MarketSnapshot, Protocol, Discovery and acquisition boundary for substantial historical datasets. (+31 more)

### Community 61 - "cli.py"
Cohesion: 0.20
Nodes (15): LogRecord, Namespace, ValidationKind, download_market_data(), _instrument(), main(), _parse_datetime(), datetime (+7 more)

### Community 62 - "risk_decision"
Cohesion: 0.50
Nodes (4): ApprovedOrderPayload, RiskDecisionPayload, approved_order(), risk_decision()

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
Cohesion: 0.11
Nodes (20): AgentSignalPayload, CouncilDecisionPayload, ExperienceDetailPayload, ExperienceSummaryPayload, ExperimentForecastPayload, ExperimentOraclePayload, ExperimentProvenancePayload, experience_episode() (+12 more)

### Community 72 - "Contributor Covenant Code of Conduct"
Cohesion: 0.15
Nodes (12): 1. Correction, 2. Warning, 3. Temporary Ban, 4. Permanent Ban, Attribution, Contributor Covenant Code of Conduct, Enforcement, Enforcement Guidelines (+4 more)

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

### Community 103 - "Q: How does the current market data pipeline ingest, cache, normalize, validate, and supply data to backtests, and where should issue 17 expansion fit?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: How does the current market data pipeline ingest, cache, normalize, validate, and supply data to backtests, and where should issue 17 expansion fit?, Source Nodes

## Knowledge Gaps
- **204 isolated node(s):** `Architecture`, `Included`, `Optional Freqtrade runtime`, `Telemetry dashboard`, `Extension points` (+199 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 532 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `create_app` to `websocket_events`, `weight_generation`, `agent_signal`, `TelemetryEvent`, `serializers.py`, `scenarios.py`, `ExperimentService`, `KrakenHistoricalProvider`, `FreqtradeHistoricalProvider`, `_of_type`, `test_issue17_historical_pipeline.py`, `HistoricalRequest`, `pipeline.py`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `MarketSnapshot` connect `MarketSnapshot` to `BacktestEngine`, `experience/models.py`, `ExperimentRequest`, `test_pr16_regressions.py`, `serializers.py`, `KrakenHistoricalProvider`, `schemas.py`, `teacher.py`, `experiments/models.py`, `datetime`, `agents/__init__.py`, `SignalValidity`, `pipeline.py`, `seasonality.py`, `DeterministicRiskGovernor`, `backtest/freqtrade.py`, `PaperExecutionAdapter`, `rising_snapshot`, `AgentContext`, `CouncilDecision`, `test_pipeline.py`, `model_validator`, `HistoricalRequest`, `cli.py`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Why does `HistoricalRequest` connect `HistoricalRequest` to `ParquetMarketDataCache`, `ExperimentRequest`, `scenarios.py`, `ExperimentService`, `KrakenHistoricalProvider`, `FreqtradeHistoricalProvider`, `experiments/models.py`, `test_market_data.py`, `engine.py`, `datetime`, `test_issue17_historical_pipeline.py`, `cli.py`, `backtest/models.py`, `.validate_result`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Are the 58 inferred relationships involving `MarketSnapshot` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`MarketSnapshot` has 58 INFERRED edges - model-reasoned connections that need verification._
- **Are the 32 inferred relationships involving `create_app()` (e.g. with `require_command_access()` and `HistoricalAcquisitionCreate`) actually correct?**
  _`create_app()` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `AgentContext` (e.g. with `SpecialistAgent` and `HistoricalRecurrenceAgent`) actually correct?**
  _`AgentContext` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `HistoricalRequest` (e.g. with `HistoricalDataProvider` and `HistoricalMarketDataProvider`) actually correct?**
  _`HistoricalRequest` has 8 INFERRED edges - model-reasoned connections that need verification._