import { describe, expect, it } from 'vitest';
import { createDemoCouncilRun } from './demoCouncil';
import { project } from './model';

describe('browser council demonstration', () => {
  it('produces a complete, ordered paper-only run for the telemetry UI', () => {
    const demo = createDemoCouncilRun(new Date('2026-09-11T12:34:56Z'), 'demo-test');
    const events = demo.bootstrap.events;
    const result = project(events);

    expect(events.map((event) => event.sequence)).toEqual(events.map((_, index) => index + 1));
    expect(events.at(-1)?.event_type).toBe('pipeline_completed');
    expect(demo.bootstrap.runs[0]).toMatchObject({ run_id: 'demo-test', status: 'completed' });
    expect(result.signals).toHaveLength(4);
    expect(result.decision?.forecast_direction).toBe('long');
    expect(result.risk?.approved_order?.paper_only).toBe(true);
    expect(result.execution?.paper_only).toBe(true);
    expect(result.reconciliation?.compliant).toBe(true);
    expect(result.portfolio?.positions).toHaveLength(1);
  });
});
