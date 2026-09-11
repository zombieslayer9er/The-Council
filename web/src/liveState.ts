import type {
  AgentSummary,
  BootstrapResponse,
  RunSummary,
  StateResponse,
  TelemetryEvent,
} from '../../contracts/typescript/types.generated';

export type ConnectionStatus =
  | 'bootstrapping'
  | 'live'
  | 'resynchronizing'
  | 'disconnected'
  | 'malformed';

export const CLIENT_EVENT_LIMIT = 10_000;

export interface LiveState {
  status: ConnectionStatus;
  streamId: string | null;
  watermark: number;
  state: StateResponse | null;
  runs: readonly RunSummary[];
  agents: readonly AgentSummary[];
  events: readonly TelemetryEvent[];
  buffered: readonly TelemetryEvent[];
  error: string | null;
}

export function emptyLiveState(): LiveState {
  return { status: 'bootstrapping', streamId: null, watermark: 0, state: null, runs: [], agents: [], events: [], buffered: [], error: null };
}

export function beginResync(current: LiveState, initial = false): LiveState {
  return { ...current, status: initial ? 'bootstrapping' : 'resynchronizing', error: null };
}

export function bufferEvent(current: LiveState, event: TelemetryEvent): LiveState {
  if (current.status === 'live') return applyEvent(current, event);
  if (current.buffered.some((item) => item.stream_id === event.stream_id && item.sequence === event.sequence)) return current;
  return { ...current, buffered: [...current.buffered, event].slice(-CLIENT_EVENT_LIMIT) };
}

export function applyBootstrap(current: LiveState, bootstrap: BootstrapResponse): LiveState {
  let next: LiveState = {
    status: 'live', streamId: bootstrap.stream_id, watermark: bootstrap.sequence_watermark,
    state: bootstrap.state, runs: bootstrap.runs, agents: bootstrap.agents,
    events: dedupe(bootstrap.events).slice(-CLIENT_EVENT_LIMIT), buffered: [], error: null,
  };
  const newer = current.buffered
    .filter((event) => event.stream_id === bootstrap.stream_id && event.sequence > bootstrap.sequence_watermark)
    .sort((a, b) => a.sequence - b.sequence);
  for (const event of newer) {
    next = applyEvent(next, event);
    if (next.status !== 'live') break;
  }
  return next;
}

export function applyEvent(current: LiveState, event: TelemetryEvent): LiveState {
  if (current.streamId !== event.stream_id) {
    return { ...current, status: 'resynchronizing', buffered: [event], error: null };
  }
  if (event.sequence <= current.watermark) return current;
  if (event.sequence !== current.watermark + 1) {
    return { ...current, status: 'resynchronizing', buffered: [...current.buffered, event], error: 'Telemetry gap detected; resynchronizing.' };
  }
  const events = [...current.events, event].slice(-CLIENT_EVENT_LIMIT);
  const state = updateState(current.state, event);
  return {
    ...current, watermark: event.sequence, state, events,
    runs: updateRuns(current.runs, event), agents: updateAgents(current.agents, event),
  };
}

export function failLive(current: LiveState, status: 'disconnected' | 'malformed', message: string): LiveState {
  return { ...current, status, error: message };
}

function updateState(state: StateResponse | null, event: TelemetryEvent): StateResponse {
  const active = new Set(state?.active_runs ?? []);
  if (event.event_type === 'pipeline_started' || event.event_type === 'backtest_started') active.add(event.run_id);
  if (['pipeline_completed', 'pipeline_failed', 'backtest_completed'].includes(event.event_type)) active.delete(event.run_id);
  return {
    api_version: 'v1', stream_id: event.stream_id!, sequence_watermark: event.sequence,
    event_count: Math.min(CLIENT_EVENT_LIMIT, (state?.event_count ?? 0) + 1), last_sequence: event.sequence,
    latest_portfolio: event.event_type === 'portfolio_updated' ? event.payload : state?.latest_portfolio ?? null,
    latest_decision: event.event_type === 'council_decision_emitted' ? event.payload : state?.latest_decision ?? null,
    latest_risk_decision: event.event_type === 'risk_decision_emitted' || event.event_type === 'risk_vetoed' ? event.payload : state?.latest_risk_decision ?? null,
    active_runs: [...active].sort(),
  } as StateResponse;
}

function updateRuns(runs: readonly RunSummary[], event: TelemetryEvent): readonly RunSummary[] {
  const existing = runs.find((run) => run.run_id === event.run_id);
  const kind: 'pipeline' | 'backtest' = event.event_type.startsWith('backtest_') ? 'backtest' : existing?.run_kind ?? 'pipeline';
  const terminal = event.event_type === 'pipeline_failed' ? 'failed' : ['pipeline_completed','backtest_completed'].includes(event.event_type) ? 'completed' : existing?.status ?? 'running';
  const updated: RunSummary = {
    run_id: event.run_id, run_kind: kind,
    first_sequence: existing?.first_sequence ?? event.sequence, last_sequence: event.sequence,
    started_at: existing?.started_at ?? event.emitted_at, updated_at: event.emitted_at,
    event_count: (existing?.event_count ?? 0) + 1, status: terminal,
    symbol: existing?.symbol ?? event.symbol, timeframe: existing?.timeframe ?? event.timeframe,
  };
  return [updated, ...runs.filter((run) => run.run_id !== event.run_id)]
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
}

function updateAgents(agents: readonly AgentSummary[], event: TelemetryEvent): readonly AgentSummary[] {
  if (event.event_type !== 'agent_signal_emitted') return agents;
  const payload = event.payload as import('../../contracts/typescript/types.generated').AgentSignalPayload;
  const updated: AgentSummary = { agent_id: payload.agent_id, agent_version: payload.agent_version, latest_signal: event };
  return [...agents.filter((agent) => agent.agent_id !== payload.agent_id), updated]
    .sort((a, b) => a.agent_id.localeCompare(b.agent_id));
}

function dedupe(events: readonly TelemetryEvent[]): TelemetryEvent[] {
  const seen = new Set<string>();
  return [...events].sort((a, b) => a.sequence - b.sequence).filter((event) => {
    const key = `${event.stream_id}:${event.sequence}:${event.event_id}`;
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
}
