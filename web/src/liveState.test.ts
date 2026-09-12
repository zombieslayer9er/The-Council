import { describe, expect, it } from 'vitest';
import type { BootstrapResponse, PortfolioPayload, TelemetryEvent } from '../../contracts/typescript/types.generated';
import { applyBootstrap, applyEvent, bufferEvent, emptyLiveState } from './liveState';
import { money, percent } from './model';
import { RequestGate } from './requestGate';
import { ContractError, parseBootstrap, parseTelemetryEvent } from './validate';

const at = '2026-09-11T12:00:00Z';

function portfolio(equity: number): PortfolioPayload {
  return { cash: equity, equity, positions: [], gross_exposure: 0, unrealized_pnl: 0, valued_at: at };
}

function stageEvent(streamId: string, sequence: number, eventId = `e-${sequence}`, runId = 'opaque-a'): TelemetryEvent {
  return {
    event_id: eventId, event_type: 'pipeline_started', schema_version: '1.2', stream_id: streamId,
    sequence, run_id: runId, symbol: 'BTC/USD', timeframe: '5m', emitted_at: at,
    source_snapshot_id: null, correlation_id: null,
    payload: { stage: 'pipeline', message: '', agent_id: null, agent_version: null, decision_id: null, order_id: null, total_agents: null },
  };
}

function portfolioEvent(streamId: string, sequence: number, equity: number): TelemetryEvent {
  return { ...stageEvent(streamId, sequence), event_id: `portfolio-${sequence}`, event_type: 'portfolio_updated', payload: portfolio(equity) };
}

function snapshot(streamId: string, watermark: number, equity: number): BootstrapResponse {
  return {
    api_version: 'v1', stream_id: streamId, sequence_watermark: watermark,
    state: { api_version: 'v1', stream_id: streamId, sequence_watermark: watermark, event_count: watermark, last_sequence: watermark, latest_portfolio: portfolio(equity), latest_decision: null, latest_risk_decision: null, active_runs: [] },
    runs: [], agents: [], events: [],
  };
}

describe('generation-aware live state', () => {
  it('keeps a newer websocket value when bootstrap resolves later', () => {
    let state = emptyLiveState();
    state = bufferEvent(state, portfolioEvent('stream-a', 11, 200));
    state = applyBootstrap(state, snapshot('stream-a', 10, 100));
    expect(state.watermark).toBe(11);
    expect(state.state?.latest_portfolio?.equity).toBe(200);
  });

  it('accepts sequence one after a server generation reset', () => {
    let state = applyBootstrap(emptyLiveState(), snapshot('old', 100, 100));
    state = bufferEvent(state, portfolioEvent('new', 1, 200));
    expect(state.status).toBe('resynchronizing');
    state = applyBootstrap(state, snapshot('new', 0, 150));
    expect(state.streamId).toBe('new');
    expect(state.watermark).toBe(1);
    expect(state.state?.latest_portfolio?.equity).toBe(200);
  });

  it('detects a gap and recovers missed state from bootstrap', () => {
    let state = applyBootstrap(emptyLiveState(), snapshot('same', 10, 100));
    state = applyEvent(state, portfolioEvent('same', 12, 300));
    expect(state.status).toBe('resynchronizing');
    expect(state.watermark).toBe(10);
    state = applyBootstrap(state, snapshot('same', 12, 300));
    expect(state.status).toBe('live');
    expect(state.state?.latest_portfolio?.equity).toBe(300);
  });

  it('deduplicates before accounting and updates live registries', () => {
    let state = applyBootstrap(emptyLiveState(), snapshot('same', 0, 100));
    const started = stageEvent('same', 1, 'one', 'hash-run');
    state = applyEvent(state, started);
    state = applyEvent(state, started);
    expect(state.state?.event_count).toBe(1);
    expect(state.runs).toHaveLength(1);
    expect(state.state?.active_runs).toEqual(['hash-run']);

    const agent = { ...stageEvent('same', 2, 'two', 'hash-run'), event_type: 'agent_signal_emitted', payload: { agent_id: 'trend', agent_version: '1.0' } } as unknown as TelemetryEvent;
    state = applyEvent(state, agent);
    expect(state.agents.map((item) => item.agent_id)).toEqual(['trend']);
  });

  it('keeps replay data outside the authoritative live container', () => {
    const live = applyBootstrap(emptyLiveState(), snapshot('same', 10, 100));
    const replayEvents = [portfolioEvent('same', 2, 5)];
    expect(live.state?.latest_portfolio?.equity).toBe(100);
    expect(replayEvents[0].payload).toMatchObject({ equity: 5 });
    expect(live.watermark).toBe(10);
  });
});

describe('request and contract boundaries', () => {
  it('prevents a slower earlier history request from winning', () => {
    const gate = new RequestGate(); const a = gate.begin(); const b = gate.begin();
    expect(a.signal.aborted).toBe(true); expect(gate.isCurrent(a.generation)).toBe(false); expect(gate.isCurrent(b.generation)).toBe(true);
  });

  it('rejects malformed websocket payloads', () => {
    expect(parseTelemetryEvent(stageEvent('same', 1)).sequence).toBe(1);
    expect(() => parseTelemetryEvent({ ...stageEvent('same', 1), sequence: -1 })).toThrow(ContractError);
    expect(() => parseTelemetryEvent({ ...stageEvent('same', 1), event_type: 'made_up' })).toThrow(ContractError);
  });

  it('rejects malformed REST portfolio state without returning a partial result', () => {
    const bad = structuredClone(snapshot('same', 0, 100)) as unknown as Record<string, any>;
    bad.state.latest_portfolio.gross_exposure = '1000';
    expect(() => parseBootstrap(bad)).toThrow(ContractError);
  });

  it('formats monetary exposure as currency and fractional values as percent', () => {
    expect(money(12_500)).toBe('$12,500.00');
    expect(percent(0.125)).toBe('12.5%');
  });
});
