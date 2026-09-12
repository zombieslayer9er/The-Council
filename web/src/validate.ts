import type {
  AgentPage,
  AgentSignalPayload,
  BootstrapResponse,
  EventType,
  ExperiencePage,
  ExperienceResponse,
  ExperimentEvaluationResponse,
  ExperimentForecastResponse,
  ExperimentOracleResponse,
  ExperimentPage,
  HealthResponse,
  LearningReviewPage,
  RunDetailResponse,
  RunPage,
  StateResponse,
  TelemetryEvent,
  WeightGenerationPage,
} from '../../contracts/typescript/types.generated';

const EVENT_TYPES = new Set<EventType>([
  'pipeline_started', 'snapshot_created', 'agent_started', 'agent_signal_emitted',
  'market_context_ready',
  'council_round_started', 'council_decision_emitted', 'risk_evaluation_started',
  'risk_decision_emitted', 'risk_vetoed', 'order_approved', 'execution_started',
  'execution_report_emitted', 'portfolio_updated', 'reconciliation_completed',
  'pipeline_completed', 'pipeline_failed', 'backtest_started', 'backtest_progress',
  'backtest_completed',
]);
const DIRECTIONS = new Set(['long', 'short', 'flat']);
const ACTIONS = new Set(['target_exposure', 'reduce_only', 'no_action', 'abstain']);
const VALIDITIES = new Set(['valid', 'invalid', 'insufficient_data']);
const SIGNAL_TYPES = new Set(['alpha', 'volatility', 'regime']);
const SIDES = new Set(['buy', 'sell']);
const CAPABILITIES = new Set(['telemetry_read', 'experiment_read', 'experience_read', 'learning_read', 'experiment_control']);

export class ContractError extends Error {}

export function parseBootstrap(value: unknown): BootstrapResponse {
  const root = record(value, 'bootstrap'); api(root); text(root.stream_id, 'stream_id');
  integer(root.sequence_watermark, 'sequence_watermark', 0);
  parseState(root.state); array(root.runs, 'runs').forEach(parseRunSummary);
  array(root.agents, 'agents').forEach(parseAgentSummary);
  array(root.events, 'events').forEach(parseTelemetryEvent);
  const state = root.state as StateResponse;
  if (state.stream_id !== root.stream_id || state.sequence_watermark !== root.sequence_watermark) {
    fail('bootstrap state does not match its watermark');
  }
  const sequences = new Set<number>(); const eventIds = new Set<string>();
  for (const event of root.events as TelemetryEvent[]) {
    if (event.stream_id !== root.stream_id || event.sequence > root.sequence_watermark) fail('bootstrap event exceeds watermark');
    if (sequences.has(event.sequence) || eventIds.has(event.event_id)) fail('bootstrap contains duplicate events');
    sequences.add(event.sequence); eventIds.add(event.event_id);
  }
  return root as unknown as BootstrapResponse;
}

export function parseHealth(value: unknown): HealthResponse {
  const root = record(value, 'health'); api(root);
  literal(root.status, 'ok', 'status'); literal(root.service, 'botnet-council-telemetry', 'service');
  text(root.backend_version, 'backend_version'); boolean(root.read_only, 'read_only');
  array(root.capabilities, 'capabilities').forEach((item) => enumValue(item, CAPABILITIES, 'capability'));
  enumValue(root.command_authentication, new Set(['disabled', 'bearer_token']), 'command_authentication');
  const control = (root.capabilities as unknown[]).includes('experiment_control');
  if (control === root.read_only || control !== (root.command_authentication === 'bearer_token')) {
    fail('health access policy fields disagree');
  }
  return root as unknown as HealthResponse;
}

export function parseState(value: unknown): StateResponse {
  const root = record(value, 'state'); api(root); text(root.stream_id, 'stream_id');
  integer(root.sequence_watermark, 'sequence_watermark', 0); integer(root.event_count, 'event_count', 0);
  integer(root.last_sequence, 'last_sequence', 0); nullable(root.latest_portfolio, portfolio, 'latest_portfolio');
  nullable(root.latest_decision, council, 'latest_decision'); nullable(root.latest_risk_decision, risk, 'latest_risk_decision');
  array(root.active_runs, 'active_runs').forEach((item) => text(item, 'active_runs item'));
  if (root.last_sequence !== root.sequence_watermark) fail('state sequence fields disagree');
  return root as unknown as StateResponse;
}

export function parseRunPage(value: unknown): RunPage {
  const root = page(value, 'run page'); array(root.items, 'items').forEach(parseRunSummary);
  return root as unknown as RunPage;
}

export function parseAgentPage(value: unknown): AgentPage {
  const root = page(value, 'agent page'); array(root.items, 'items').forEach(parseAgentSummary);
  return root as unknown as AgentPage;
}

export function parseRunDetail(value: unknown): RunDetailResponse {
  const root = record(value, 'run detail'); api(root); text(root.run_id, 'run_id');
  array(root.events, 'events').forEach(parseTelemetryEvent);
  return root as unknown as RunDetailResponse;
}

export function parseTelemetryEvent(value: unknown): TelemetryEvent {
  const event = record(value, 'telemetry event'); text(event.event_id, 'event_id');
  enumValue(event.event_type, EVENT_TYPES, 'event_type'); literal(event.schema_version, '1.2', 'schema_version');
  text(event.stream_id, 'stream_id'); integer(event.sequence, 'sequence', 1); text(event.run_id, 'run_id');
  nullable(event.symbol, text, 'symbol'); nullable(event.timeframe, text, 'timeframe'); timestamp(event.emitted_at, 'emitted_at');
  nullable(event.source_snapshot_id, text, 'source_snapshot_id'); nullable(event.correlation_id, text, 'correlation_id');
  const payload = record(event.payload, 'payload');
  validatePayload(event.event_type as EventType, payload);
  return event as unknown as TelemetryEvent;
}

function validatePayload(type: EventType, value: Record<string, unknown>) {
  if (['pipeline_started', 'agent_started', 'council_round_started', 'risk_evaluation_started', 'execution_started', 'pipeline_completed'].includes(type)) return stage(value);
  if (type === 'snapshot_created') return snapshot(value);
  if (type === 'market_context_ready') return marketContext(value);
  if (type === 'agent_signal_emitted') return signal(value);
  if (type === 'council_decision_emitted') return council(value);
  if (type === 'risk_decision_emitted' || type === 'risk_vetoed') return risk(value);
  if (type === 'order_approved') return order(value);
  if (type === 'execution_report_emitted') return execution(value);
  if (type === 'portfolio_updated') return portfolio(value);
  if (type === 'reconciliation_completed') return reconciliation(value);
  if (type === 'pipeline_failed') { text(value.stage, 'stage'); text(value.error_code, 'error_code'); text(value.message, 'message'); return; }
  enumValue(value.status, new Set(['started', 'in_progress', 'completed']), 'status'); integer(value.current, 'current', 0);
  nullable(value.total, (item, label) => integer(item, label, 0), 'total'); nullable(value.progress, finite, 'progress');
  nullable(value.event_count, (item, label) => integer(item, label, 0), 'event_count'); nullable(value.trade_count, (item, label) => integer(item, label, 0), 'trade_count');
}

function snapshot(value: Record<string, unknown>) {
  text(value.snapshot_id, 'snapshot_id'); text(value.symbol, 'symbol'); text(value.timeframe, 'timeframe');
  timestamp(value.as_of, 'as_of'); timestamp(value.observed_at, 'observed_at'); timestamp(value.latest_available_at, 'latest_available_at');
  array(value.bars, 'bars').forEach((item) => { const bar = record(item, 'bar'); timestamp(bar.opened_at, 'opened_at'); timestamp(bar.closed_at, 'closed_at'); timestamp(bar.available_at, 'available_at'); ['open','high','low','close','volume'].forEach((key) => finite(bar[key], key)); });
  nullable(value.provenance, provenance, 'provenance');
}
function provenance(item: unknown) { const value = record(item, 'provenance'); ['provider','instrument','timeframe','source_version','adapter_version','cache_key'].forEach((key) => text(value[key], key)); ['requested_start','requested_end','as_of','fetched_at','latest_observation_time','latest_available_at'].forEach((key) => timestamp(value[key], key)); boolean(value.coverage_complete, 'coverage_complete'); }
function marketContext(value: Record<string, unknown>) {
  ['context_id','snapshot_id'].forEach((key) => text(value[key], key)); timestamp(value.as_of, 'as_of');
  ['requested_required','requested_optional','missing_required','missing_optional'].forEach((key) => stringArray(value[key], key));
  array(value.data, 'data').forEach((item) => { const datum = record(item, 'context datum'); ['capability','instrument','name','unit'].forEach((key) => text(datum[key], key)); const source = record(datum.provenance, 'context provenance'); ['provider','source_id','vintage','source_version'].forEach((key) => text(source[key], key)); ['observed_at','provider_available_at','ingested_at'].forEach((key) => timestamp(source[key], key)); });
}

export function parseExperiencePage(value: unknown): ExperiencePage {
  const root = page(value, 'experience page'); array(root.items, 'items').forEach(experienceSummary);
  return root as unknown as ExperiencePage;
}

export function parseExperienceResponse(value: unknown): ExperienceResponse {
  const root = record(value, 'experience response'); api(root); const episode = record(root.episode, 'episode'); experienceSummary(episode);
  council(record(episode.decision, 'decision')); array(episode.specialist_outputs, 'specialist_outputs').forEach((item) => signal(record(item, 'signal')));
  array(episode.applied_weights, 'applied_weights').forEach((item) => { const weight = record(item, 'applied weight'); text(weight.agent_id, 'agent_id'); finite(weight.weight, 'weight'); });
  text(episode.backtest_run_id, 'backtest_run_id'); text(episode.risk_policy_version, 'risk_policy_version'); nullable(episode.truth_available_at, timestamp, 'truth_available_at');
  return root as unknown as ExperienceResponse;
}

export function parseWeightGenerationPage(value: unknown): WeightGenerationPage {
  const root = record(value, 'weight generation page'); api(root); nullable(root.active_generation_id, text, 'active_generation_id'); integer(root.total, 'total', 0);
  array(root.items, 'items').forEach((item) => { const generation = record(item, 'weight generation'); integer(generation.generation, 'generation', 0); ['generation_id','scoring_version','profile_id'].forEach((key) => text(generation[key], key)); nullable(generation.parent_generation_id, text, 'parent_generation_id'); timestamp(generation.created_at, 'created_at'); array(generation.entries, 'entries').forEach((entryItem) => { const entry = record(entryItem, 'weight entry'); text(entry.agent_id, 'agent_id'); weightScope(record(entry.scope, 'scope')); adaptiveWeight(record(entry.weight, 'weight')); }); });
  return root as unknown as WeightGenerationPage;
}

export function parseLearningReviewPage(value: unknown): LearningReviewPage {
  const root = record(value, 'learning review page'); api(root); integer(root.total, 'total', 0);
  array(root.items, 'items').forEach((item) => { const review = record(item, 'learning review'); ['result_id','proposal_id','base_generation_id','librarian_version','teacher_version','scoring_version'].forEach((key) => text(review[key], key)); enumValue(review.decision, new Set(['accept','reject','accept_reduced_update']), 'decision'); ['created_at','training_cutoff','evaluated_at'].forEach((key) => timestamp(review[key], key)); ['training_episode_count','held_out_episode_count'].forEach((key) => integer(review[key], key, 0)); array(review.changes, 'changes').forEach(weightChange); array(review.accepted_changes, 'accepted_changes').forEach(weightChange); metrics(record(review.baseline, 'baseline')); metrics(record(review.proposed, 'proposed')); stringArray(review.reasons, 'reasons'); });
  return root as unknown as LearningReviewPage;
}

export function parseExperimentPage(value: unknown): ExperimentPage {
  const root = page(value, 'experiment page'); array(root.items, 'items').forEach(experimentSummary);
  return root as unknown as ExperimentPage;
}

export function parseExperimentForecastResponse(value: unknown): ExperimentForecastResponse {
  const root = record(value, 'forecast response'); api(root); const forecast = record(root.forecast, 'forecast'); ['forecast_id','experiment_id','instrument','forecast_horizon','direction'].forEach((key) => text(forecast[key], key)); ['evaluation_time','finalized_at'].forEach((key) => timestamp(forecast[key], key)); nullable(forecast.expected_return, finite, 'expected_return'); finite(forecast.confidence, 'confidence'); array(forecast.agent_forecasts, 'agent_forecasts').forEach((item) => signal(record(item, 'agent forecast'))); council(record(forecast.council_decision, 'council_decision')); record(forecast.council_weights, 'council_weights');
  return root as unknown as ExperimentForecastResponse;
}

export function parseExperimentOracleResponse(value: unknown): ExperimentOracleResponse {
  const root = record(value, 'oracle response'); api(root); const oracle = record(root.oracle_outcome, 'oracle outcome'); ['experiment_id','price_convention'].forEach((key) => text(oracle[key], key)); ['evaluation_time','horizon_end'].forEach((key) => timestamp(oracle[key], key)); ['start_price','endpoint_price','realized_return','maximum_favorable_excursion','maximum_adverse_excursion'].forEach((key) => nullable(oracle[key], finite, key)); nullable(oracle.realized_direction, text, 'realized_direction'); boolean(oracle.horizon_complete, 'horizon_complete');
  return root as unknown as ExperimentOracleResponse;
}

export function parseExperimentEvaluationResponse(value: unknown): ExperimentEvaluationResponse {
  const root = record(value, 'evaluation response'); api(root); const evaluation = record(root.evaluation, 'evaluation'); ['experiment_id','forecast_id','forecast_direction','realized_direction','calibration_bucket'].forEach((key) => text(evaluation[key], key)); boolean(evaluation.directional_correctness, 'directional_correctness'); ['expected_return','absolute_return_error','signed_return_error'].forEach((key) => nullable(evaluation[key], finite, key)); finite(evaluation.realized_return, 'realized_return'); finite(evaluation.confidence, 'confidence'); timestamp(evaluation.evaluated_at, 'evaluated_at');
  return root as unknown as ExperimentEvaluationResponse;
}
function signal(value: Record<string, unknown>) {
  ['signal_id','domain_schema_version','agent_id','agent_version','symbol','timeframe','source_snapshot_id','rationale'].forEach((key) => text(value[key], key));
  enumValue(value.signal_type, SIGNAL_TYPES, 'signal_type');
  enumValue(value.forecast_direction, DIRECTIONS, 'forecast_direction'); enumValue(value.action, ACTIONS, 'action'); enumValue(value.validity, VALIDITIES, 'validity');
  ['source_as_of','generated_at','expires_at'].forEach((key) => timestamp(value[key], key)); nullable(value.expected_return, finite, 'expected_return'); nullable(value.target_exposure, finite, 'target_exposure'); finite(value.confidence, 'confidence'); integer(value.horizon_bars, 'horizon_bars', 0); nullable(value.volatility, volatility, 'volatility'); record(value.metadata, 'metadata');
}
function volatility(item: unknown) { const value = record(item, 'volatility'); ['estimator','units','source_snapshot_id','status'].forEach((key) => text(value[key], key)); integer(value.window_bars, 'window_bars', 0); timestamp(value.observed_at, 'observed_at'); nullable(value.value, finite, 'value'); }
function council(item: unknown) { const value = record(item, 'council'); ['decision_id','symbol','timeframe','source_snapshot_id','rationale'].forEach((key) => text(value[key], key)); timestamp(value.source_as_of, 'source_as_of'); timestamp(value.decided_at, 'decided_at'); timestamp(value.expires_at, 'expires_at'); enumValue(value.forecast_direction, DIRECTIONS, 'forecast_direction'); enumValue(value.action, ACTIONS, 'action'); nullable(value.expected_return, finite, 'expected_return'); nullable(value.target_exposure, finite, 'target_exposure'); finite(value.conviction, 'conviction'); finite(value.confidence, 'confidence'); stringArray(value.signal_ids, 'signal_ids'); stringArray(value.participating_agent_ids, 'participating_agent_ids'); }
function order(item: unknown) { const value = record(item, 'order'); ['order_id','decision_id','source_snapshot_id','symbol','timeframe'].forEach((key) => text(value[key], key)); enumValue(value.side, SIDES, 'side'); literal(value.fill_policy, 'next_bar_open', 'fill_policy'); ['reference_price','quantity','max_fee_bps','max_slippage_bps'].forEach((key) => finite(value[key], key)); ['authorized_at','earliest_fill_at','expires_at'].forEach((key) => timestamp(value[key], key)); boolean(value.reduce_only, 'reduce_only'); literal(value.paper_only, true, 'paper_only'); }
function risk(item: unknown) { const value = record(item, 'risk'); ['decision_id','source_snapshot_id'].forEach((key) => text(value[key], key)); enumValue(value.risk_status, new Set(['approved','vetoed']), 'risk_status'); boolean(value.approved, 'approved'); boolean(value.vetoed, 'vetoed'); stringArray(value.reasons, 'reasons'); stringArray(value.policy_check_ids, 'policy_check_ids'); timestamp(value.evaluated_at, 'evaluated_at'); nullable(value.approved_order, order, 'approved_order'); ['cash','equity','gross_exposure','position_quantity'].forEach((key) => finite(value[key], key)); }
function execution(value: Record<string, unknown>) { ['order_id','decision_id','symbol','message'].forEach((key) => text(value[key], key)); enumValue(value.side, SIDES, 'side'); enumValue(value.execution_status, new Set(['filled','rejected']), 'execution_status'); ['quantity','fees','slippage_bps'].forEach((key) => finite(value[key], key)); timestamp(value.submitted_at, 'submitted_at'); nullable(value.filled_at, timestamp, 'filled_at'); nullable(value.fill_price, finite, 'fill_price'); nullable(value.slippage_cost, finite, 'slippage_cost'); nullable(value.total_costs, finite, 'total_costs'); literal(value.paper_only, true, 'paper_only'); }
function position(item: unknown) { const value = record(item, 'position'); text(value.symbol, 'symbol'); ['quantity','average_entry_price','mark_price','market_value','unrealized_pnl','exposure'].forEach((key) => finite(value[key], key)); timestamp(value.mark_observed_at, 'mark_observed_at'); }
function portfolio(item: unknown) { const value = record(item, 'portfolio'); ['cash','equity','gross_exposure','unrealized_pnl'].forEach((key) => finite(value[key], key)); array(value.positions, 'positions').forEach(position); timestamp(value.valued_at, 'valued_at'); }
function experienceSummary(item: unknown) { const value = record(item, 'experience'); ['episode_id','backtest_run_id','symbol','timeframe','weight_generation_id','forecast_direction'].forEach((key) => text(value[key], key)); timestamp(value.decision_timestamp, 'decision_timestamp'); nullable(value.regime, text, 'regime'); boolean(value.training_eligible, 'training_eligible'); ['expected_return','realized_return','maximum_adverse_excursion','maximum_favorable_excursion'].forEach((key) => nullable(value[key], finite, key)); nullable(value.directional_correctness, boolean, 'directional_correctness'); }
function weightScope(value: Record<string, unknown>) { ['asset_class','symbol','regime'].forEach((key) => nullable(value[key], text, key)); nullable(value.horizon_bars, (item, label) => integer(item, label, 1), 'horizon_bars'); }
function adaptiveWeight(value: Record<string, unknown>) { ['long_term','recent','recent_mix','effective'].forEach((key) => finite(value[key], key)); }
function weightChange(item: unknown) { const value = record(item, 'weight change'); text(value.agent_id, 'agent_id'); weightScope(record(value.scope, 'scope')); adaptiveWeight(record(value.current, 'current')); adaptiveWeight(record(value.proposed, 'proposed')); integer(value.sample_count, 'sample_count', 0); finite(value.confidence, 'confidence'); nullable(value.long_term_accuracy, finite, 'long_term_accuracy'); nullable(value.recent_accuracy, finite, 'recent_accuracy'); text(value.reason, 'reason'); }
function metrics(value: Record<string, unknown>) { integer(value.episode_count, 'episode_count', 0); ['total_return','benchmark_relative_return','maximum_drawdown','hit_rate','mean_calibration_error','risk_adjusted_return','turnover','cost_adjusted_return','worst_slice_return','score'].forEach((key) => finite(value[key], key)); }
function experimentSummary(item: unknown) { const value = record(item, 'experiment'); ['experiment_id','state'].forEach((key) => text(value[key], key)); const request = record(value.request, 'experiment request'); ['instrument','provider','forecast_horizon','timeframe'].forEach((key) => text(request[key], key)); timestamp(request.evaluation_time, 'evaluation_time'); boolean(value.forecast_locked, 'forecast_locked'); boolean(value.oracle_available, 'oracle_available'); boolean(value.evaluation_available, 'evaluation_available'); nullable(value.error, text, 'error'); array(value.lifecycle, 'lifecycle').forEach((entry) => { const lifecycle = record(entry, 'lifecycle'); text(lifecycle.state, 'state'); timestamp(lifecycle.occurred_at, 'occurred_at'); string(lifecycle.message, 'message'); }); }
function reconciliation(value: Record<string, unknown>) { text(value.decision_id, 'decision_id'); text(value.order_id, 'order_id'); boolean(value.compliant, 'compliant'); timestamp(value.reconciled_at, 'reconciled_at'); stringArray(value.reasons, 'reasons'); }
function stage(value: Record<string, unknown>) { text(value.stage, 'stage'); string(value.message, 'message'); ['agent_id','agent_version','decision_id','order_id'].forEach((key) => nullable(value[key], text, key)); nullable(value.total_agents, (item, label) => integer(item, label, 0), 'total_agents'); }
function parseRunSummary(item: unknown) { const value = record(item, 'run summary'); text(value.run_id, 'run_id'); enumValue(value.run_kind, new Set(['pipeline','backtest']), 'run_kind'); integer(value.first_sequence, 'first_sequence', 1); integer(value.last_sequence, 'last_sequence', 1); timestamp(value.started_at, 'started_at'); timestamp(value.updated_at, 'updated_at'); integer(value.event_count, 'event_count', 1); enumValue(value.status, new Set(['running','completed','failed']), 'status'); nullable(value.symbol, text, 'symbol'); nullable(value.timeframe, text, 'timeframe'); }
function parseAgentSummary(item: unknown) { const value = record(item, 'agent summary'); text(value.agent_id, 'agent_id'); text(value.agent_version, 'agent_version'); const event = parseTelemetryEvent(value.latest_signal); if (event.event_type !== 'agent_signal_emitted') fail('latest_signal has wrong event type'); }
function page(item: unknown, label: string) { const value = record(item, label); api(value); integer(value.total, 'total', 0); integer(value.limit, 'limit', 1); integer(value.offset, 'offset', 0); return value; }
function api(value: Record<string, unknown>) { literal(value.api_version, 'v1', 'api_version'); }
function record(value: unknown, label: string): Record<string, unknown> { if (typeof value !== 'object' || value === null || Array.isArray(value)) fail(`${label} must be an object`); return value as Record<string, unknown>; }
function array(value: unknown, label: string): unknown[] { if (!Array.isArray(value)) fail(`${label} must be an array`); return value; }
function text(value: unknown, label: string) { if (typeof value !== 'string' || !value) fail(`${label} must be a non-empty string`); }
function string(value: unknown, label: string) { if (typeof value !== 'string') fail(`${label} must be a string`); }
function boolean(value: unknown, label: string) { if (typeof value !== 'boolean') fail(`${label} must be boolean`); }
function finite(value: unknown, label: string) { if (typeof value !== 'number' || !Number.isFinite(value)) fail(`${label} must be finite`); }
function integer(value: unknown, label: string, minimum: number) { if (!Number.isInteger(value) || (value as number) < minimum) fail(`${label} must be an integer >= ${minimum}`); }
function timestamp(value: unknown, label: string) { text(value, label); if (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value as string) || !Number.isFinite(Date.parse(value as string))) fail(`${label} must be an ISO timestamp with an offset`); }
function nullable(value: unknown, validator: (item: unknown, label: string) => void, label: string) { if (value !== null) validator(value, label); }
function stringArray(value: unknown, label: string) { array(value, label).forEach((item) => text(item, `${label} item`)); }
function enumValue<T>(value: unknown, values: Set<T>, label: string) { if (!values.has(value as T)) fail(`${label} has an unsupported value`); }
function literal<T>(value: unknown, expected: T, label: string) { if (value !== expected) fail(`${label} must equal ${String(expected)}`); }
function fail(message: string): never { throw new ContractError(message); }

export function asSignal(value: TelemetryEvent): AgentSignalPayload {
  if (value.event_type !== 'agent_signal_emitted') fail('event is not an agent signal');
  return value.payload as AgentSignalPayload;
}
