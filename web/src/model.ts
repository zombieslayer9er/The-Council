import type {
  AgentSignalPayload,
  CouncilDecisionPayload,
  EventType,
  ExecutionReportPayload,
  PortfolioPayload,
  ReconciliationPayload,
  RiskDecisionPayload,
  SnapshotPayload,
  TelemetryEvent,
} from '../../contracts/typescript/types.generated';

export interface RunProjection {
  events: readonly TelemetryEvent[];
  snapshot: SnapshotPayload | null;
  signals: readonly AgentSignalPayload[];
  decision: CouncilDecisionPayload | null;
  risk: RiskDecisionPayload | null;
  execution: ExecutionReportPayload | null;
  portfolio: PortfolioPayload | null;
  reconciliation: ReconciliationPayload | null;
}

export function project(events: readonly TelemetryEvent[]): RunProjection {
  const ordered = [...events].sort((a, b) => a.sequence - b.sequence);
  return {
    events: ordered,
    snapshot: lastPayload<SnapshotPayload>(ordered, 'snapshot_created'),
    signals: ordered
      .filter((event) => event.event_type === 'agent_signal_emitted')
      .map((event) => event.payload as AgentSignalPayload),
    decision: lastPayload<CouncilDecisionPayload>(ordered, 'council_decision_emitted'),
    risk: lastPayload<RiskDecisionPayload>(ordered, 'risk_decision_emitted'),
    execution: lastPayload<ExecutionReportPayload>(ordered, 'execution_report_emitted'),
    portfolio: lastPayload<PortfolioPayload>(ordered, 'portfolio_updated'),
    reconciliation: lastPayload<ReconciliationPayload>(ordered, 'reconciliation_completed'),
  };
}

function lastPayload<T>(events: readonly TelemetryEvent[], type: EventType): T | null {
  const event = [...events].reverse().find((item) => item.event_type === type);
  return event ? event.payload as T : null;
}

export function mergeEvents(current: readonly TelemetryEvent[], incoming: TelemetryEvent) {
  const byId = new Map(current.map((event) => [event.event_id, event]));
  byId.set(incoming.event_id, incoming);
  return [...byId.values()].sort((a, b) => a.sequence - b.sequence);
}

export function money(value: number | null | undefined, digits = 2) {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(value);
}

export function percent(value: number | null | undefined, signed = false) {
  if (value == null) return '—';
  const output = `${(Math.abs(value) * 100).toFixed(1)}%`;
  return signed && value !== 0 ? `${value > 0 ? '+' : '−'}${output}` : output;
}

export function shortTime(value: string | null | undefined) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-US', {
    month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC',
  }).format(new Date(value)).replace(',', '') + ' UTC';
}

export function agentLabel(id: string) {
  return id.split(/[-_]/).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}
