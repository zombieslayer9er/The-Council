import type {
  AgentSignalPayload,
  BootstrapResponse,
  CouncilDecisionPayload,
  HealthResponse,
  MarketBarPayload,
  PortfolioPayload,
  RiskDecisionPayload,
  StagePayload,
  TelemetryEvent,
  TelemetryPayload,
} from '../../contracts/typescript/types.generated';

export interface DemoCouncilRun {
  health: HealthResponse;
  bootstrap: BootstrapResponse;
}

const STEP_MS = 5 * 60 * 1_000;

export function createDemoCouncilRun(now = new Date(), runId = `browser-demo-${now.getTime()}`): DemoCouncilRun {
  const evaluatedAt = new Date(Math.floor(now.getTime() / STEP_MS) * STEP_MS);
  const emittedAt = evaluatedAt.toISOString();
  const streamId = `demo-stream-${runId}`;
  const snapshotId = `${runId}-snapshot`;
  const decisionId = `${runId}-decision`;
  const orderId = `${runId}-order`;
  const bars = createBars(evaluatedAt);
  const signalSpecs = [
    ['trend', 'alpha', 'long', 0.78, 0.014, 0.3, 'Price remains above its rising medium-window baseline.'],
    ['mean-reversion', 'alpha', 'short', 0.55, -0.004, -0.1, 'The latest close is modestly extended from the short-window mean.'],
    ['volatility', 'volatility', 'flat', 0.73, null, null, 'Realized volatility remains inside the configured paper-risk band.'],
    ['regime', 'regime', 'long', 0.69, null, null, 'The demonstration window is classified as a steady trend regime.'],
  ] as const;
  const signals: AgentSignalPayload[] = signalSpecs.map(([agentId, signalType, direction, confidence, expectedReturn, targetExposure, rationale]) => ({
    signal_id: `${runId}-${agentId}-signal`, domain_schema_version: '1.1', agent_id: agentId, agent_version: 'browser-demo-1',
    signal_type: signalType, symbol: 'DEMO/USD', timeframe: '5m', source_snapshot_id: snapshotId, source_as_of: emittedAt,
    forecast_direction: direction, expected_return: expectedReturn, target_exposure: targetExposure,
    action: signalType === 'alpha' ? (direction === 'long' ? 'increase_long' : 'decrease_long') : 'hold',
    validity: 'valid', confidence, horizon_bars: 6, generated_at: emittedAt,
    expires_at: new Date(evaluatedAt.getTime() + 30 * 60 * 1_000).toISOString(), rationale,
    volatility: signalType === 'volatility' ? { estimator: 'close_to_close', window_bars: 20, units: 'annualized', observed_at: emittedAt, source_snapshot_id: snapshotId, status: 'valid', value: 0.21 } : null,
    metadata: { execution_mode: 'browser_demo' },
  }));
  const decision: CouncilDecisionPayload = {
    decision_id: decisionId, symbol: 'DEMO/USD', timeframe: '5m', source_snapshot_id: snapshotId, source_as_of: emittedAt,
    forecast_direction: 'long', expected_return: 0.006, target_exposure: 0.2, action: 'increase_long', conviction: 0.46, confidence: 0.7,
    decided_at: emittedAt, expires_at: new Date(evaluatedAt.getTime() + 30 * 60 * 1_000).toISOString(),
    rationale: 'Trend evidence outweighs the smaller mean-reversion counter-signal; context advisers do not vote directionally.',
    signal_ids: signals.map((signal) => signal.signal_id), participating_agent_ids: signals.slice(0, 2).map((signal) => signal.agent_id),
  };
  const approvedOrder = {
    order_id: orderId, decision_id: decisionId, source_snapshot_id: snapshotId, symbol: 'DEMO/USD', timeframe: '5m', side: 'buy', quantity: 153.846154,
    reference_price: 130, authorized_at: emittedAt, earliest_fill_at: emittedAt,
    expires_at: new Date(evaluatedAt.getTime() + STEP_MS).toISOString(), fill_policy: 'next_bar_open', max_fee_bps: 5,
    max_slippage_bps: 10, reduce_only: false, paper_only: true as const,
  };
  const risk: RiskDecisionPayload = {
    risk_status: 'approved', approved: true, vetoed: false, reasons: ['All deterministic paper-risk checks passed.'],
    policy_check_ids: ['paper_only', 'symbol_allowed', 'exposure_bounded', 'observation_fresh'], evaluated_at: emittedAt,
    decision_id: decisionId, source_snapshot_id: snapshotId, approved_order: approvedOrder, cash: 100_000, equity: 100_000, gross_exposure: 0, position_quantity: 0,
  };
  const portfolio: PortfolioPayload = {
    cash: 79_976.92, equity: 99_976.92,
    positions: [{ symbol: 'DEMO/USD', quantity: approvedOrder.quantity, average_entry_price: 130.13, mark_price: 130, mark_observed_at: emittedAt, market_value: 20_000, unrealized_pnl: -20, exposure: 0.200046 }],
    gross_exposure: 20_000, unrealized_pnl: -20, valued_at: emittedAt,
  };
  const events: TelemetryEvent[] = [];
  const emit = (eventType: TelemetryEvent['event_type'], payload: TelemetryPayload, correlationId: string | null = null) => {
    events.push({ event_id: `${runId}-${events.length + 1}`, event_type: eventType, schema_version: '1.1', stream_id: streamId, sequence: events.length + 1, run_id: runId, symbol: 'DEMO/USD', timeframe: '5m', emitted_at: emittedAt, source_snapshot_id: eventType === 'pipeline_started' ? null : snapshotId, correlation_id: correlationId, payload });
  };
  const stage = (name: string, extras: Partial<StagePayload> = {}): StagePayload => ({ stage: name, message: '', agent_id: null, agent_version: null, decision_id: null, order_id: null, total_agents: null, ...extras });
  emit('pipeline_started', stage('pipeline', { total_agents: signals.length }));
  emit('snapshot_created', { snapshot_id: snapshotId, symbol: 'DEMO/USD', timeframe: '5m', as_of: emittedAt, observed_at: emittedAt, latest_available_at: emittedAt, bars, provenance: null });
  for (const signal of signals) emit('agent_signal_emitted', signal, signal.agent_id);
  emit('council_round_started', stage('council', { total_agents: signals.length }), decisionId);
  emit('council_decision_emitted', decision, decisionId);
  emit('risk_evaluation_started', stage('risk', { decision_id: decisionId }), decisionId);
  emit('risk_decision_emitted', risk, decisionId);
  emit('order_approved', approvedOrder, decisionId);
  emit('execution_started', stage('execution', { decision_id: decisionId, order_id: orderId }), decisionId);
  emit('execution_report_emitted', { order_id: orderId, decision_id: decisionId, symbol: 'DEMO/USD', side: 'buy', quantity: approvedOrder.quantity, submitted_at: emittedAt, filled_at: emittedAt, fill_price: 130.13, fees: 3, slippage_bps: 10, slippage_cost: 20, total_costs: 23, execution_status: 'filled', message: 'Deterministic browser demonstration fill.', paper_only: true }, decisionId);
  emit('reconciliation_completed', { decision_id: decisionId, order_id: orderId, compliant: true, reconciled_at: emittedAt, reasons: ['Paper fill remained within the authorized bounds.'] }, decisionId);
  emit('portfolio_updated', portfolio, decisionId);
  emit('pipeline_completed', stage('pipeline', { decision_id: decisionId }), decisionId);

  const last = events.at(-1)!;
  return {
    health: { api_version: 'v1', status: 'ok', service: 'botnet-council-telemetry', backend_version: 'browser-demo', read_only: true, capabilities: ['telemetry_read', 'experiment_read'], command_authentication: 'disabled' },
    bootstrap: {
      api_version: 'v1', stream_id: streamId, sequence_watermark: last.sequence,
      state: { api_version: 'v1', stream_id: streamId, sequence_watermark: last.sequence, event_count: events.length, last_sequence: last.sequence, latest_portfolio: portfolio, latest_decision: decision, latest_risk_decision: risk, active_runs: [] },
      runs: [{ run_id: runId, run_kind: 'pipeline', first_sequence: 1, last_sequence: last.sequence, started_at: emittedAt, updated_at: emittedAt, event_count: events.length, status: 'completed', symbol: 'DEMO/USD', timeframe: '5m' }],
      agents: signals.map((signal) => ({ agent_id: signal.agent_id, agent_version: signal.agent_version, latest_signal: events.find((event) => event.event_type === 'agent_signal_emitted' && (event.payload as AgentSignalPayload).agent_id === signal.agent_id)! })),
      events,
    },
  };
}

function createBars(evaluatedAt: Date): MarketBarPayload[] {
  return Array.from({ length: 30 }, (_, index) => {
    const openedAt = new Date(evaluatedAt.getTime() - (30 - index) * STEP_MS);
    const closedAt = new Date(openedAt.getTime() + STEP_MS);
    const close = Number((108 + index * 0.73 + Math.sin(index / 2.4) * 1.35).toFixed(2));
    const open = Number((close - 0.38 - Math.sin(index) * 0.22).toFixed(2));
    return { opened_at: openedAt.toISOString(), closed_at: closedAt.toISOString(), available_at: closedAt.toISOString(), open, high: Number((Math.max(open, close) + 0.72).toFixed(2)), low: Number((Math.min(open, close) - 0.68).toFixed(2)), close, volume: 1_200 + index * 17 };
  });
}
