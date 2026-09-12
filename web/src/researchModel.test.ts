import { describe, expect, it } from 'vitest';
import type { AgentSignalPayload } from '../../contracts/typescript/types.generated';
import { councilContributions, recurrenceEvidence } from './researchModel';

function signal(overrides: Partial<AgentSignalPayload> = {}): AgentSignalPayload {
  return {
    signal_id: 'signal-1', domain_schema_version: '1.1', agent_id: 'trend', agent_version: '1',
    signal_type: 'alpha', symbol: 'BTC/USD', timeframe: '1h', source_snapshot_id: 'snapshot-1',
    source_as_of: '2026-01-01T00:00:00Z', forecast_direction: 'long', expected_return: 0.02,
    target_exposure: 0.6, action: 'target_exposure', validity: 'valid', confidence: 1,
    horizon_bars: 2, generated_at: '2026-01-01T00:00:00Z', expires_at: '2026-01-01T01:00:00Z',
    rationale: 'fixture', volatility: null, metadata: {}, ...overrides,
  };
}

describe('research evidence projections', () => {
  it('parses complete Historical Recurrence evidence and rejects malformed observations', () => {
    const recurrence = signal({
      agent_id: 'historical_recurrence',
      metadata: { historical_recurrence: {
        selected_horizon_days: 30, current_regime: 'bull', windows: [{
          horizon_days: 30, usable_observations: 1, total_annual_observations: 1,
          raw_positive_hit_ratio: 1, regime_matched_hit_ratio: 1, median_forward_return: .12,
          mean_forward_return: .12, median_maximum_adverse_excursion: -.03,
          median_maximum_favorable_excursion: .17, persistence_score: .8,
          observations: [{ annual_year: 2024, candidate_date: '2024-01-01', status: 'usable',
            normalized_path: [1, 1.1], forward_return: .12, maximum_adverse_excursion: -.03,
            maximum_favorable_excursion: .17, regime: 'bull', regime_similarity: .9 }],
        }],
      } },
    });

    expect(recurrenceEvidence(recurrence)?.windows[0].observations[0].annual_year).toBe(2024);
    expect(recurrenceEvidence(signal({ agent_id: 'historical_recurrence', metadata: {
      historical_recurrence: { windows: [{ observations: [{ normalized_path: ['bad'] }] }] },
    } }))).toBeNull();
  });

  it('matches the Council eligibility and weighted-contribution rules', () => {
    const values = councilContributions([
      signal({ agent_id: 'trend', target_exposure: .6 }),
      signal({ agent_id: 'mean_reversion', target_exposure: -.3 }),
      signal({ agent_id: 'regime', signal_type: 'regime', target_exposure: 1 }),
      signal({ agent_id: 'invalid', validity: 'invalid', target_exposure: 1 }),
    ], { trend: 2, mean_reversion: 1 });

    expect(values.trend).toBeCloseTo(.4);
    expect(values.mean_reversion).toBeCloseTo(-.1);
    expect(Object.keys(values)).toEqual(['trend', 'mean_reversion']);
  });
});
