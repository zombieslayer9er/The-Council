import type { AgentSignalPayload } from '../../contracts/typescript/types.generated';

export interface RecurrenceObservation {
  annual_year: number;
  candidate_date: string;
  status: string;
  normalized_path: readonly number[];
  forward_return: number | null;
  maximum_adverse_excursion: number | null;
  maximum_favorable_excursion: number | null;
  regime: string | null;
  regime_similarity: number | null;
}

export interface RecurrenceWindow {
  horizon_days: number;
  usable_observations: number;
  total_annual_observations: number;
  raw_positive_hit_ratio: number | null;
  regime_matched_hit_ratio: number | null;
  median_forward_return: number | null;
  mean_forward_return: number | null;
  median_maximum_adverse_excursion: number | null;
  median_maximum_favorable_excursion: number | null;
  persistence_score: number;
  observations: readonly RecurrenceObservation[];
}

export interface RecurrenceEvidence {
  selected_horizon_days: number | null;
  current_regime: string | null;
  windows: readonly RecurrenceWindow[];
}

export function recurrenceEvidence(signal: AgentSignalPayload): RecurrenceEvidence | null {
  if (signal.agent_id !== 'historical_recurrence') return null;
  const root = object(signal.metadata.historical_recurrence);
  if (!root || !Array.isArray(root.windows)) return null;
  const windows = root.windows.map(parseWindow);
  if (windows.some((item) => item === null)) return null;
  return {
    selected_horizon_days: nullableNumber(root.selected_horizon_days),
    current_regime: nullableString(root.current_regime),
    windows: windows as RecurrenceWindow[],
  };
}

export function councilContributions(
  signals: readonly AgentSignalPayload[],
  weights: Readonly<Record<string, number>> = {},
): Readonly<Record<string, number>> {
  const eligible = signals.filter((signal) => signal.signal_type === 'alpha'
    && signal.validity === 'valid'
    && ['target_exposure', 'reduce_only'].includes(signal.action));
  const denominator = eligible.reduce((sum, signal) => sum + (weights[signal.agent_id] ?? 1) * signal.confidence, 0);
  return Object.fromEntries(eligible.map((signal) => [
    signal.agent_id,
    denominator === 0 ? 0 : ((weights[signal.agent_id] ?? 1) * signal.confidence * (signal.target_exposure ?? 0)) / denominator,
  ]));
}

function parseWindow(value: unknown): RecurrenceWindow | null {
  const item = object(value);
  if (!item || !Array.isArray(item.observations)) return null;
  const observations = item.observations.map(parseObservation);
  if (observations.some((observation) => observation === null)) return null;
  const horizon = number(item.horizon_days); const usable = number(item.usable_observations); const total = number(item.total_annual_observations); const persistence = number(item.persistence_score);
  if (horizon === null || usable === null || total === null || persistence === null) return null;
  return {
    horizon_days: horizon,
    usable_observations: usable,
    total_annual_observations: total,
    raw_positive_hit_ratio: nullableNumber(item.raw_positive_hit_ratio),
    regime_matched_hit_ratio: nullableNumber(item.regime_matched_hit_ratio),
    median_forward_return: nullableNumber(item.median_forward_return),
    mean_forward_return: nullableNumber(item.mean_forward_return),
    median_maximum_adverse_excursion: nullableNumber(item.median_maximum_adverse_excursion),
    median_maximum_favorable_excursion: nullableNumber(item.median_maximum_favorable_excursion),
    persistence_score: persistence,
    observations: observations as RecurrenceObservation[],
  };
}

function parseObservation(value: unknown): RecurrenceObservation | null {
  const item = object(value); const year = item ? number(item.annual_year) : null;
  if (!item || year === null || typeof item.candidate_date !== 'string' || typeof item.status !== 'string' || !Array.isArray(item.normalized_path) || !item.normalized_path.every(isNumber)) return null;
  return {
    annual_year: year,
    candidate_date: item.candidate_date,
    status: item.status,
    normalized_path: item.normalized_path,
    forward_return: nullableNumber(item.forward_return),
    maximum_adverse_excursion: nullableNumber(item.maximum_adverse_excursion),
    maximum_favorable_excursion: nullableNumber(item.maximum_favorable_excursion),
    regime: nullableString(item.regime),
    regime_similarity: nullableNumber(item.regime_similarity),
  };
}

function object(value: unknown): Record<string, unknown> | null { return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null; }
function number(value: unknown): number | null { return isNumber(value) ? value : null; }
function nullableNumber(value: unknown): number | null { return value == null ? null : number(value); }
function nullableString(value: unknown): string | null { return value == null ? null : typeof value === 'string' ? value : null; }
function isNumber(value: unknown): value is number { return typeof value === 'number' && Number.isFinite(value); }
