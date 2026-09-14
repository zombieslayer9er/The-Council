import { requestJson } from './backend';

export type OperationStatus = 'queued' | 'running' | 'completed' | 'cancelled' | 'failed';
export type LearningStatus = 'not_applicable' | 'pending' | 'accepted' | 'rejected';

export interface HistoricalProvider {
  provider: string;
  display_name: string;
  markets: readonly string[];
  timeframes: readonly string[];
  requires_credentials: boolean;
}

export interface HistoricalPair { base: string; quote: string }
export interface AvailabilityRange { start: string; end: string; source_version: string }
export interface HistoricalOperation {
  operation_id: string;
  kind: 'acquisition' | 'backtest';
  status: OperationStatus;
  created_at: string;
  updated_at: string;
  progress: number;
  current: number;
  total: number;
  scenario_id: string | null;
  result_run_id: string | null;
  error: string | null;
  learning_status: LearningStatus;
  learning_eligible: boolean;
  learning_episode_ids: readonly string[];
  learning_episodes_rejected: number;
  learning_message: string | null;
}

export interface HistoricalStatistics {
  total_tests_executed: number;
  successful_completed_tests: number;
  failed_cancelled_tests: number;
  learning_eligible_tests: number;
  learning_episodes_accepted: number;
  learning_episodes_rejected: number;
  user_initiated_learning_episodes: number;
  automated_learning_episodes: number;
  current_experience_set: number;
}

export interface HistoricalScenario {
  scenario_id: string;
  created_at: string;
  definition: {
    provider: string;
    market: string;
    blind_window_bars: number | null;
    deterministic_seed: number;
    config: Record<string, unknown>;
  };
}

export interface HistoricalCandle {
  opened_at: string;
  closed_at: string;
  available_at: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface HistoricalArtifacts {
  operation: HistoricalOperation;
  scenario: HistoricalScenario;
  candles: readonly HistoricalCandle[];
  run: {
    result: {
      run_id: string;
      evaluation_start: string;
      evaluation_end: string;
      event_count: number;
      trade_count: number;
      data_quality_status: string;
      warnings: readonly string[];
      market_data_provenance: Record<string, unknown>;
      metrics: Record<string, number>;
      benchmark: Record<string, number>;
    };
    ledger: { events: readonly HistoricalLedgerEvent[] };
  };
}

export interface HistoricalLedgerEvent {
  sequence: number;
  simulation_time: string;
  snapshot: Record<string, unknown> | null;
  signals: readonly Record<string, unknown>[];
  council_decision: Record<string, unknown> | null;
  risk_decision: Record<string, unknown> | null;
  execution_report: Record<string, unknown> | null;
  portfolio: Record<string, unknown>;
  measured: boolean;
}

export interface ScenarioDraft {
  provider: string;
  market: string;
  instrument: string;
  timeframe: string;
  start: string;
  end: string;
  startingCash: number;
  feeBps: number;
  slippageBps: number;
  blindWindowBars: number | null;
  deterministicSeed: number;
  agents: readonly string[];
}

function auth(token: string): HeadersInit {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}

export async function loadHistoricalProviders(signal?: AbortSignal): Promise<readonly HistoricalProvider[]> {
  return list(await requestJson('/api/historical/providers', { signal }), 'items').map(provider);
}

export async function loadHistoricalPairs(providerId: string, market: string, signal?: AbortSignal): Promise<readonly HistoricalPair[]> {
  const path = `/api/historical/providers/${encodeURIComponent(providerId)}/markets/${encodeURIComponent(market)}/pairs`;
  return list(await requestJson(path, { signal }), 'items').map(pair);
}

export async function loadAvailability(draft: Pick<ScenarioDraft, 'provider' | 'market' | 'instrument' | 'timeframe'>, signal?: AbortSignal): Promise<readonly AvailabilityRange[]> {
  const query = new URLSearchParams({ provider: draft.provider, market: draft.market, instrument: draft.instrument, timeframe: draft.timeframe });
  return list(await requestJson(`/api/historical/cache?${query}`, { signal }), 'items').map(availability);
}

export async function loadHistoricalOperations(signal?: AbortSignal): Promise<readonly HistoricalOperation[]> {
  return list(await requestJson('/api/historical/operations', { signal }), 'items').map(operation);
}

export async function loadHistoricalStatistics(signal?: AbortSignal): Promise<HistoricalStatistics> {
  return statistics(field(await requestJson('/api/historical/statistics', { signal }), 'statistics'));
}

export async function loadHistoricalOperation(id: string, signal?: AbortSignal): Promise<HistoricalOperation> {
  return operation(field(await requestJson(`/api/historical/operations/${encodeURIComponent(id)}`, { signal }), 'operation'));
}

export async function acquireHistorical(draft: ScenarioDraft, token: string): Promise<HistoricalOperation> {
  const [base, quote] = draft.instrument.split('/');
  const body = { provider: draft.provider, market: draft.market, instrument: { base, quote }, timeframe: draft.timeframe, start: draft.start, end: draft.end, as_of: draft.end };
  return operation(field(await requestJson('/api/control/historical/acquisitions', { method: 'POST', headers: auth(token), body: JSON.stringify(body) }), 'operation'));
}

export async function startHistorical(draft: ScenarioDraft, token: string): Promise<HistoricalOperation> {
  const scenarioBody = {
    provider: draft.provider,
    market: draft.market,
    blind_window_bars: draft.blindWindowBars,
    deterministic_seed: draft.deterministicSeed,
    config: {
      instrument: draft.instrument, timeframe: draft.timeframe, market: draft.market,
      start: draft.start, end: draft.end, starting_cash: draft.startingCash,
      fee_bps: draft.feeBps, slippage_bps: draft.slippageBps,
      agents: draft.agents.map((kind) => ({ kind, parameters: {} })), random_seed: draft.deterministicSeed,
    },
  };
  const created = await requestJson('/api/control/historical/scenarios', { method: 'POST', headers: auth(token), body: JSON.stringify(scenarioBody) });
  const scenario = field(created, 'scenario');
  const id = text(scenario, 'scenario_id');
  return operation(field(await requestJson(`/api/control/historical/scenarios/${encodeURIComponent(id)}/runs`, { method: 'POST', headers: auth(token) }), 'operation'));
}

export async function cancelHistorical(id: string, token: string): Promise<HistoricalOperation> {
  return operation(field(await requestJson(`/api/control/historical/operations/${encodeURIComponent(id)}/cancel`, { method: 'POST', headers: auth(token) }), 'operation'));
}

export async function loadHistoricalArtifacts(id: string, signal?: AbortSignal): Promise<HistoricalArtifacts> {
  const value = await requestJson(`/api/historical/operations/${encodeURIComponent(id)}/artifacts`, { signal });
  if (!record(value) || !record(value.run) || !record(value.run.result) || !record(value.run.ledger) || !Array.isArray(value.run.ledger.events)) throw new Error('Malformed historical artifacts');
  return {
    operation: operation(field(value, 'operation')),
    scenario: scenario(field(value, 'scenario')),
    candles: list(value, 'candles').map(candle),
    run: value.run as unknown as HistoricalArtifacts['run'],
  };
}

function record(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null; }
function field(value: unknown, key: string): Record<string, unknown> { if (!record(value) || !record(value[key])) throw new Error(`Malformed historical response: ${key}`); return value[key]; }
function list(value: unknown, key: string): unknown[] { if (!record(value) || !Array.isArray(value[key])) throw new Error(`Malformed historical response: ${key}`); return value[key]; }
function text(value: Record<string, unknown>, key: string): string { if (typeof value[key] !== 'string') throw new Error(`Malformed historical field: ${key}`); return value[key]; }
function number(value: Record<string, unknown>, key: string): number { if (typeof value[key] !== 'number' || !Number.isFinite(value[key])) throw new Error(`Malformed historical field: ${key}`); return value[key]; }
function nullableText(value: Record<string, unknown>, key: string): string | null { return value[key] === null ? null : text(value, key); }
function provider(value: unknown): HistoricalProvider { if (!record(value) || !Array.isArray(value.markets) || !Array.isArray(value.timeframes)) throw new Error('Malformed provider metadata'); return { provider: text(value, 'provider'), display_name: text(value, 'display_name'), markets: value.markets.map(String), timeframes: value.timeframes.map(String), requires_credentials: Boolean(value.requires_credentials) }; }
function pair(value: unknown): HistoricalPair { if (!record(value)) throw new Error('Malformed historical pair'); return { base: text(value, 'base'), quote: text(value, 'quote') }; }
function availability(value: unknown): AvailabilityRange { if (!record(value)) throw new Error('Malformed availability range'); return { start: text(value, 'start'), end: text(value, 'end'), source_version: text(value, 'source_version') }; }
function operation(value: unknown): HistoricalOperation { if (!record(value) || !Array.isArray(value.learning_episode_ids)) throw new Error('Malformed historical operation'); return { operation_id: text(value, 'operation_id'), kind: text(value, 'kind') as HistoricalOperation['kind'], status: text(value, 'status') as OperationStatus, created_at: text(value, 'created_at'), updated_at: text(value, 'updated_at'), progress: number(value, 'progress'), current: number(value, 'current'), total: number(value, 'total'), scenario_id: nullableText(value, 'scenario_id'), result_run_id: nullableText(value, 'result_run_id'), error: nullableText(value, 'error'), learning_status: text(value, 'learning_status') as LearningStatus, learning_eligible: Boolean(value.learning_eligible), learning_episode_ids: value.learning_episode_ids.map(String), learning_episodes_rejected: number(value, 'learning_episodes_rejected'), learning_message: nullableText(value, 'learning_message') }; }
function statistics(value: unknown): HistoricalStatistics { if (!record(value)) throw new Error('Malformed historical statistics'); return { total_tests_executed: number(value, 'total_tests_executed'), successful_completed_tests: number(value, 'successful_completed_tests'), failed_cancelled_tests: number(value, 'failed_cancelled_tests'), learning_eligible_tests: number(value, 'learning_eligible_tests'), learning_episodes_accepted: number(value, 'learning_episodes_accepted'), learning_episodes_rejected: number(value, 'learning_episodes_rejected'), user_initiated_learning_episodes: number(value, 'user_initiated_learning_episodes'), automated_learning_episodes: number(value, 'automated_learning_episodes'), current_experience_set: number(value, 'current_experience_set') }; }
function scenario(value: unknown): HistoricalScenario { if (!record(value) || !record(value.definition) || !record(value.definition.config)) throw new Error('Malformed historical scenario'); return value as unknown as HistoricalScenario; }
function candle(value: unknown): HistoricalCandle { if (!record(value)) throw new Error('Malformed historical candle'); return { opened_at: text(value, 'opened_at'), closed_at: text(value, 'closed_at'), available_at: text(value, 'available_at'), open: number(value, 'open'), high: number(value, 'high'), low: number(value, 'low'), close: number(value, 'close'), volume: number(value, 'volume') }; }
