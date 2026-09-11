import type {
  AgentPage,
  AgentSignalPayload,
  BootstrapResponse,
  EventType,
  HealthResponse,
  RunDetailResponse,
  RunPage,
  StateResponse,
  TelemetryEvent,
} from '../../contracts/typescript/types.generated';

const EVENT_TYPES = new Set<EventType>([
  'pipeline_started', 'snapshot_created', 'agent_started', 'agent_signal_emitted',
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
  text(root.backend_version, 'backend_version'); literal(root.read_only, true, 'read_only');
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
  enumValue(event.event_type, EVENT_TYPES, 'event_type'); literal(event.schema_version, '1.1', 'schema_version');
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
