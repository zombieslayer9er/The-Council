import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadExperimentEvidence } from './api';
import { parseHealth } from './validate';

afterEach(() => vi.unstubAllGlobals());

describe('blind experiment evidence loading', () => {
  it('does not request forecast, oracle, or evaluation before lifecycle gates open', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);

    const result = await loadExperimentEvidence(
      'experiment-1',
      { forecast: false, oracle: false, evaluation: false },
    );

    expect(fetch).not.toHaveBeenCalled();
    expect(result).toEqual({ forecast: null, oracle: null, evaluation: null });
  });
});

describe('health capability reporting', () => {
  it('accepts accurately reported authenticated control without granting UI commands', () => {
    expect(parseHealth({
      api_version: 'v1', status: 'ok', service: 'botnet-council-telemetry', backend_version: '0.1.0',
      read_only: false, capabilities: ['telemetry_read', 'experiment_read', 'experiment_control'],
      command_authentication: 'bearer_token',
    }).read_only).toBe(false);
  });

  it('rejects inconsistent access-policy fields', () => {
    expect(() => parseHealth({
      api_version: 'v1', status: 'ok', service: 'botnet-council-telemetry', backend_version: '0.1.0',
      read_only: true, capabilities: ['telemetry_read', 'experiment_read', 'experiment_control'],
      command_authentication: 'disabled',
    })).toThrow('health access policy fields disagree');
  });
});
