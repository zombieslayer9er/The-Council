import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadAvailability, loadHistoricalOperations, startHistorical, type ScenarioDraft } from './historicalApi';

afterEach(() => vi.unstubAllGlobals());

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));

describe('historical API contracts', () => {
  it('parses cache provenance without inventing a bar count', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ items: [{
      provider: 'kraken', market: 'kraken', instrument: { base: 'BTC', quote: 'USD' },
      timeframe: '1h', start: '2026-01-01T00:00:00Z', end: '2026-01-02T00:00:00Z',
      source_version: 'kraken-ohlcv-v1', adapter_semantic_version: '1',
    }] })));
    await expect(loadAvailability({ provider: 'kraken', market: 'kraken', instrument: 'BTC/USD', timeframe: '1h' })).resolves.toEqual([{
      start: '2026-01-01T00:00:00Z', end: '2026-01-02T00:00:00Z', source_version: 'kraken-ohlcv-v1',
    }]);
  });

  it('rejects malformed persisted operation state', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ items: [{ operation_id: 'missing-fields' }] })));
    await expect(loadHistoricalOperations()).rejects.toThrow('Malformed historical');
  });

  it('uses the bearer token only on control requests', async () => {
    const fetch = vi.fn()
      .mockImplementationOnce(() => json({ scenario: { scenario_id: 'scenario-1' } }, 201))
      .mockImplementationOnce(() => json({ operation: operation() }, 202));
    vi.stubGlobal('fetch', fetch);
    await startHistorical(draft(), 'secret-token');
    expect(fetch).toHaveBeenCalledTimes(2);
    for (const [, init] of fetch.mock.calls) expect((init.headers as Record<string, string>).Authorization).toBe('Bearer secret-token');
  });
});

function operation() {
  return { operation_id: 'operation-1', kind: 'backtest', status: 'queued', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', progress: 0, current: 0, total: 0, scenario_id: 'scenario-1', result_run_id: null, error: null, learning_status: 'pending', learning_eligible: false, learning_episode_ids: [], learning_episodes_rejected: 0, learning_message: null };
}

function draft(): ScenarioDraft {
  return { provider: 'kraken', market: 'kraken', instrument: 'BTC/USD', timeframe: '1h', start: '2026-01-01T00:00:00Z', end: '2026-01-02T00:00:00Z', startingCash: 10_000, feeBps: 10, slippageBps: 5, blindWindowBars: null, deterministicSeed: 0, agents: ['trend'] };
}
