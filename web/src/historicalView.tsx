import { useCallback, useEffect, useState } from 'react';
import {
  acquireHistorical,
  cancelHistorical,
  loadAvailability,
  loadHistoricalArtifacts,
  loadHistoricalOperation,
  loadHistoricalOperations,
  loadHistoricalPairs,
  loadHistoricalProviders,
  loadHistoricalStatistics,
  startHistorical,
  type AvailabilityRange,
  type HistoricalArtifacts,
  type HistoricalCandle,
  type HistoricalOperation,
  type HistoricalProvider,
  type HistoricalStatistics,
  type ScenarioDraft,
} from './historicalApi';
import { money, percent, shortTime } from './model';

const AGENTS = ['trend', 'mean_reversion', 'volatility', 'regime', 'seasonality', 'historical_recurrence'] as const;
const SPEEDS = [1, 2, 10, 100, Number.POSITIVE_INFINITY] as const;

export function HistoricalView({ controlEnabled }: { controlEnabled: boolean }) {
  const [providers, setProviders] = useState<readonly HistoricalProvider[]>([]);
  const [pairs, setPairs] = useState<readonly { base: string; quote: string }[]>([]);
  const [ranges, setRanges] = useState<readonly AvailabilityRange[]>([]);
  const [operations, setOperations] = useState<readonly HistoricalOperation[]>([]);
  const [statistics, setStatistics] = useState<HistoricalStatistics | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<HistoricalArtifacts | null>(null);
  const [token, setToken] = useState(() => sessionStorage.getItem('council-control-token') ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(10);
  const [visibleCount, setVisibleCount] = useState(1);
  const [selectedCandle, setSelectedCandle] = useState(0);
  const [zoom, setZoom] = useState(60);
  const [pan, setPan] = useState(0);
  const [draft, setDraft] = useState<ScenarioDraft>(() => defaultDraft());

  const refreshOperations = useCallback(async (signal?: AbortSignal) => {
    const [values, counts] = await Promise.all([
      loadHistoricalOperations(signal),
      loadHistoricalStatistics(signal),
    ]);
    setOperations(values);
    setStatistics(counts);
    setSelectedId((current) => current ?? [...values].reverse().find((item) => item.kind === 'backtest')?.operation_id ?? null);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([loadHistoricalProviders(controller.signal), refreshOperations(controller.signal)])
      .then(([values]) => {
        setProviders(values);
        const first = values[0];
        if (first) setDraft((current) => ({ ...current, provider: first.provider, market: first.markets[0] ?? first.provider, timeframe: first.timeframes[0] ?? current.timeframe }));
      }).catch((cause: unknown) => { if (!controller.signal.aborted) setError(message(cause)); });
    return () => controller.abort();
  }, [refreshOperations]);

  useEffect(() => {
    const provider = providers.find((item) => item.provider === draft.provider);
    if (!provider || !draft.market) return;
    const controller = new AbortController();
    loadHistoricalPairs(draft.provider, draft.market, controller.signal).then((values) => {
      setPairs(values);
      if (values.length) setDraft((current) => values.some((item) => symbol(item) === current.instrument) ? current : { ...current, instrument: symbol(values[0]) });
    }).catch((cause: unknown) => { if (!controller.signal.aborted) setError(message(cause)); });
    return () => controller.abort();
  }, [draft.provider, draft.market, providers]);

  const selected = operations.find((item) => item.operation_id === selectedId) ?? null;
  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    const update = async () => {
      try {
        const operation = await loadHistoricalOperation(selectedId, controller.signal);
        setOperations((current) => replaceOperation(current, operation));
        if (operation.status === 'completed' && operation.kind === 'backtest') {
          const [value, counts] = await Promise.all([
            loadHistoricalArtifacts(selectedId, controller.signal),
            loadHistoricalStatistics(controller.signal),
          ]);
          setStatistics(counts);
          setArtifacts(value); setVisibleCount(1); setSelectedCandle(0); setPlaying(false);
        }
      } catch (cause) { if (!controller.signal.aborted) setError(message(cause)); }
    };
    void update();
    const timer = selected?.status === 'queued' || selected?.status === 'running' ? window.setInterval(() => void update(), 750) : 0;
    return () => { controller.abort(); if (timer) window.clearInterval(timer); };
  }, [selectedId, selected?.status]);

  useEffect(() => {
    if (!playing || !artifacts) return;
    if (speed === Number.POSITIVE_INFINITY) { setVisibleCount(artifacts.candles.length); setPlaying(false); return; }
    const timer = window.setInterval(() => setVisibleCount((count) => {
      const next = Math.min(artifacts.candles.length, count + speed);
      if (next === artifacts.candles.length) setPlaying(false);
      return next;
    }), 250);
    return () => window.clearInterval(timer);
  }, [playing, speed, artifacts]);

  const inspectCache = async () => {
    setBusy(true); setError(null);
    try { setRanges(await loadAvailability(draft)); } catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  };
  const runCommand = async (kind: 'acquire' | 'start') => {
    if (!controlEnabled) { setError('Historical control is disabled by the backend.'); return; }
    if (!token) { setError('Enter the configured bearer token for this local session.'); return; }
    setBusy(true); setError(null); sessionStorage.setItem('council-control-token', token);
    try {
      const value = kind === 'acquire' ? await acquireHistorical(draft, token) : await startHistorical(draft, token);
      setOperations((current) => replaceOperation(current, value)); setSelectedId(value.operation_id); setArtifacts(null);
    } catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!selected) return;
    setBusy(true); setError(null);
    try {
      const value = await cancelHistorical(selected.operation_id, token);
      setOperations((current) => replaceOperation(current, value));
    } catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  };

  const visible = artifacts?.candles.slice(0, visibleCount) ?? [];
  const coverage = coverageLabel(ranges, draft.start, draft.end);
  const event = [...(artifacts?.run.ledger.events ?? [])].reverse().find((item) => new Date(item.simulation_time).getTime() <= new Date(visible.at(-1)?.closed_at ?? 0).getTime()) ?? null;
  const decision = event?.council_decision;
  const metrics = artifacts?.run.result.metrics;

  return <div className="historical-lab">
    {error && <div className="error-banner historical-error" role="alert"><span>{error}</span><button onClick={() => setError(null)}>Dismiss</button></div>}
    <section className="scenario-grid">
      <div className="panel scenario-panel">
        <div className="panel-title"><div><p className="eyebrow">Authoritative inputs</p><h2>Historical scenario</h2></div><span>{coverage}</span></div>
        <div className="form-grid">
          <Field label="Provider"><select value={draft.provider} onChange={(e) => selectProvider(e.target.value, providers, setDraft)}>{providers.map((item) => <option key={item.provider} value={item.provider}>{item.display_name}</option>)}</select></Field>
          <Field label="Exchange / market"><select value={draft.market} onChange={(e) => setDraft({ ...draft, market: e.target.value })}>{(providers.find((item) => item.provider === draft.provider)?.markets ?? []).map((item) => <option key={item}>{item}</option>)}</select></Field>
          <Field label="Trading pair"><select value={draft.instrument} onChange={(e) => setDraft({ ...draft, instrument: e.target.value })}>{pairs.map((item) => <option key={symbol(item)}>{symbol(item)}</option>)}</select></Field>
          <Field label="Candle timeframe"><select value={draft.timeframe} onChange={(e) => setDraft({ ...draft, timeframe: e.target.value })}>{(providers.find((item) => item.provider === draft.provider)?.timeframes ?? []).map((item) => <option key={item}>{item}</option>)}</select></Field>
          <Field label="Historical start"><input type="datetime-local" value={localDate(draft.start)} onChange={(e) => setDraft({ ...draft, start: isoDate(e.target.value) })}/></Field>
          <Field label="Historical end"><input type="datetime-local" value={localDate(draft.end)} onChange={(e) => setDraft({ ...draft, end: isoDate(e.target.value) })}/></Field>
          <Field label="Scenario mode"><select value={draft.blindWindowBars == null ? 'normal' : 'blind'} onChange={(e) => setDraft({ ...draft, blindWindowBars: e.target.value === 'blind' ? 120 : null })}><option value="normal">Normal interval</option><option value="blind">Blind / seeded window</option></select></Field>
          <Field label="Evaluation bars"><input type="number" min="2" disabled={draft.blindWindowBars == null} value={draft.blindWindowBars ?? 120} onChange={(e) => setDraft({ ...draft, blindWindowBars: Number(e.target.value) })}/></Field>
          <Field label="Starting paper cash"><input type="number" min="1" value={draft.startingCash} onChange={(e) => setDraft({ ...draft, startingCash: Number(e.target.value) })}/></Field>
          <Field label="Deterministic seed"><input type="number" value={draft.deterministicSeed} onChange={(e) => setDraft({ ...draft, deterministicSeed: Number(e.target.value) })}/></Field>
        </div>
        <fieldset className="agent-picker"><legend>Specialists</legend>{AGENTS.map((agent) => <label key={agent}><input type="checkbox" checked={draft.agents.includes(agent)} onChange={() => setDraft({ ...draft, agents: draft.agents.includes(agent) ? draft.agents.filter((item) => item !== agent) : [...draft.agents, agent] })}/>{agent.replaceAll('_', ' ')}</label>)}</fieldset>
        <Field label="Local control token"><input type="password" autoComplete="off" value={token} placeholder={controlEnabled ? 'Bearer token for this session' : 'Control disabled by backend'} onChange={(e) => setToken(e.target.value)}/></Field>
        <div className="command-row"><button className="secondary" disabled={busy} onClick={() => void inspectCache()}>Inspect cache</button><button className="secondary" disabled={busy || !controlEnabled} onClick={() => void runCommand('acquire')}>Acquire missing data</button><button className="primary-command" disabled={busy || !controlEnabled || draft.agents.length === 0} onClick={() => void runCommand('start')}>Start Council backtest</button></div>
        <div className="coverage-list">{ranges.map((range) => <code key={`${range.start}-${range.end}`}>{shortTime(range.start)} → {shortTime(range.end)} · source {range.source_version}</code>)}{!ranges.length && <span>No cached intervals reported for this selection.</span>}</div>
      </div>
      <div className="panel operation-panel">
        <div className="panel-title"><div><p className="eyebrow">Persistent identity</p><h2>Runs and acquisitions</h2></div><button className="secondary" onClick={() => void refreshOperations()}>Refresh</button></div>
        <div className="operation-list">{[...operations].reverse().map((item) => <button key={item.operation_id} className={item.operation_id === selectedId ? 'operation active' : 'operation'} onClick={() => { setSelectedId(item.operation_id); setArtifacts(null); }}><span className={`run-status ${item.status}`}/><span><strong>{item.kind} · {item.status}</strong><small>{shortTime(item.updated_at)} · {(item.progress * 100).toFixed(0)}%</small></span><code>{item.operation_id.slice(0, 10)}</code></button>)}</div>
        {statistics && <div className="operation-actions"><Detail label="Experiments run" value={String(statistics.total_tests_executed)}/><Detail label="Learning episodes" value={String(statistics.learning_episodes_accepted)}/><Detail label="User experiments" value={String(statistics.user_initiated_learning_episodes)}/><Detail label="Experience set" value={String(statistics.current_experience_set)}/></div>}
        {selected && <div className="operation-actions"><progress max="1" value={selected.progress}/><span>{selected.current.toLocaleString()} / {selected.total.toLocaleString()}</span>{(selected.status === 'queued' || selected.status === 'running') && <button className="danger-command" disabled={busy} onClick={() => void cancel()}>Stop / cancel</button>}<Detail label="Run ID" value={selected.result_run_id ?? 'pending'}/><Detail label="Learning" value={selected.learning_status}/><Detail label="Learning detail" value={selected.learning_message ?? 'pending'}/><Detail label="Error" value={selected.error ?? 'none'}/></div>}
      </div>
    </section>

    {artifacts ? <>
      <section className="panel playback-bar"><div><p className="eyebrow">Recorded artifact replay</p><strong>{artifacts.run.result.run_id}</strong></div><button onClick={() => { setVisibleCount(1); setPlaying(false); }}>Reset</button><button onClick={() => setPlaying(!playing)}>{playing ? 'Pause' : 'Replay'}</button><button onClick={() => setVisibleCount((count) => Math.min(artifacts.candles.length, count + 1))}>Step one candle</button><select value={String(speed)} onChange={(e) => setSpeed(e.target.value === 'Infinity' ? Number.POSITIVE_INFINITY : Number(e.target.value))}>{SPEEDS.map((item) => <option key={String(item)} value={String(item)}>{item === Number.POSITIVE_INFINITY ? 'maximum' : `${item}×`}</option>)}</select><span>{visibleCount} / {artifacts.candles.length} revealed</span></section>
      <section className="historical-output-grid">
        <div className="panel historical-chart-panel"><div className="panel-title"><div><p className="eyebrow">Council-visible history</p><h2>OHLCV candles</h2></div><span>future withheld beyond boundary</span></div><CandleChart candles={visible} selected={selectedCandle} onSelect={setSelectedCandle} zoom={zoom} pan={pan}/><div className="chart-controls"><label>Zoom <input type="range" min="10" max="200" value={zoom} onChange={(e) => setZoom(Number(e.target.value))}/></label><button onClick={() => setPan(Math.max(0, pan - zoom))}>Pan earlier</button><button onClick={() => setPan(Math.min(Math.max(0, visible.length - zoom), pan + zoom))}>Pan later</button></div></div>
        <div className="panel"><div className="panel-title"><div><p className="eyebrow">Prediction snapshot</p><h2>Council decision</h2></div><span>{event?.measured ? 'evaluated' : 'warmup'}</span></div>{decision ? <div className="artifact-details"><Detail label="Direction" value={String(decision.forecast_direction ?? '—')}/><Detail label="Action" value={String(decision.action ?? '—')}/><Detail label="Confidence" value={percent(asNumber(decision.confidence))}/><Detail label="Expected return" value={percent(asNumber(decision.expected_return), true)}/><Detail label="Decision ID" value={String(decision.decision_id ?? '—')}/><p>{String(decision.rationale ?? '')}</p></div> : <p className="inline-empty">No measured Council decision at the current reveal boundary.</p>}</div>
      </section>
      <section className="summary-grid"><Summary title="Prediction vs actual" values={[['Council expected return', percent(asNumber(decision?.expected_return), true)], ['Realized return', percent(metric(metrics, 'total_return'), true)], ['Benchmark return', percent(metric(artifacts.run.result.benchmark, 'total_return'), true)], ['Drawdown', percent(metric(metrics, 'maximum_drawdown'))]]}/><Summary title="Run summary" values={[['Instrument', String(artifacts.scenario.definition.config.instrument ?? '—')], ['Interval', `${shortTime(artifacts.run.result.evaluation_start)} → ${shortTime(artifacts.run.result.evaluation_end)}`], ['Trades', String(artifacts.run.result.trade_count)], ['Wins / losses', `${metric(metrics, 'win_count') ?? 0} / ${metric(metrics, 'loss_count') ?? 0}`], ['Data quality', artifacts.run.result.data_quality_status]]}/><Summary title="Learning status" values={[['Recorded run', 'yes'], ['Acceptance', artifacts.operation.learning_status], ['Episodes accepted', String(artifacts.operation.learning_episode_ids.length)], ['Episodes rejected', String(artifacts.operation.learning_episodes_rejected)], ['Replay mutation', 'none']]}/></section>
      <section className="panel table-panel"><div className="panel-title"><div><p className="eyebrow">Exact recorded data</p><h2>Raw candle inspector</h2></div><span>{visible.length} revealed</span></div><div className="table-wrap"><table><thead><tr><th>Timestamp</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr></thead><tbody>{visible.map((bar, index) => <tr key={bar.opened_at} className={index === selectedCandle ? 'selected-row' : ''} onClick={() => setSelectedCandle(index)}><td>{shortTime(bar.opened_at)}</td><td>{money(bar.open)}</td><td>{money(bar.high)}</td><td>{money(bar.low)}</td><td>{money(bar.close)}</td><td>{bar.volume.toLocaleString()}</td></tr>)}</tbody></table></div></section>
    </> : <div className="empty-state panel"><p className="eyebrow">Historical laboratory</p><h2>Configure, execute, and inspect</h2><p>Completed runs load immutable candles, ledger events, Council decisions, execution evidence, metrics, and provenance. Playback never reruns or relearns an experiment.</p></div>}
  </div>;
}

function CandleChart({ candles, selected, onSelect, zoom, pan }: { candles: readonly HistoricalCandle[]; selected: number; onSelect: (index: number) => void; zoom: number; pan: number }) {
  if (!candles.length) return <div className="chart-empty">No candles revealed</div>;
  const start = Math.min(Math.max(0, pan), Math.max(0, candles.length - zoom)); const values = candles.slice(start, start + zoom);
  const low = Math.min(...values.map((item) => item.low)); const high = Math.max(...values.map((item) => item.high)); const spread = high - low || 1; const width = 100 / values.length;
  return <div className="candle-chart"><svg viewBox="0 0 100 100" preserveAspectRatio="none">{values.map((bar, index) => { const x = index * width + width / 2; const y = (value: number) => 96 - ((value - low) / spread) * 90; const up = bar.close >= bar.open; const absolute = start + index; return <g key={bar.opened_at} className={absolute === selected ? 'selected-candle' : ''} onClick={() => onSelect(absolute)}><line x1={x} x2={x} y1={y(bar.high)} y2={y(bar.low)} /><rect x={x - width * .28} width={Math.max(.3, width * .56)} y={Math.min(y(bar.open), y(bar.close))} height={Math.max(.7, Math.abs(y(bar.open) - y(bar.close)))} className={up ? 'up' : 'down'}/></g>; })}<line className="crosshair" x1={Math.max(0, (selected - start) * width + width / 2)} x2={Math.max(0, (selected - start) * width + width / 2)} y1="0" y2="100" /></svg><span className="chart-high">{money(high)}</span><span className="chart-low">{money(low)}</span></div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="field"><span>{label}</span>{children}</label>; }
function Detail({ label, value }: { label: string; value: string }) { return <div className="detail"><span>{label}</span><strong>{value}</strong></div>; }
function Summary({ title, values }: { title: string; values: readonly (readonly [string, string])[] }) { return <section className="panel summary-card"><p className="eyebrow">Recorded artifact</p><h3>{title}</h3>{values.map(([label, value]) => <Detail key={label} label={label} value={value}/>)}</section>; }
function symbol(value: { base: string; quote: string }) { return `${value.base}/${value.quote}`; }
function replaceOperation(values: readonly HistoricalOperation[], value: HistoricalOperation) { return [...values.filter((item) => item.operation_id !== value.operation_id), value]; }
function message(value: unknown) { return value instanceof Error ? value.message : 'Historical operation failed.'; }
function metric(value: Record<string, number> | undefined, key: string) { const item = value?.[key]; return typeof item === 'number' ? item : null; }
function asNumber(value: unknown) { return typeof value === 'number' ? value : null; }
function localDate(value: string) { const date = new Date(value); const offset = date.getTimezoneOffset() * 60_000; return new Date(date.getTime() - offset).toISOString().slice(0, 16); }
function isoDate(value: string) { return new Date(value).toISOString(); }
function defaultDraft(): ScenarioDraft { const end = new Date(); end.setUTCMinutes(0, 0, 0); const start = new Date(end.getTime() - 7 * 86_400_000); return { provider: '', market: '', instrument: 'BTC/USD', timeframe: '1h', start: start.toISOString(), end: end.toISOString(), startingCash: 10_000, feeBps: 10, slippageBps: 5, blindWindowBars: null, deterministicSeed: 0, agents: ['trend', 'mean_reversion', 'volatility', 'regime'] }; }
function selectProvider(id: string, providers: readonly HistoricalProvider[], setDraft: React.Dispatch<React.SetStateAction<ScenarioDraft>>) { const provider = providers.find((item) => item.provider === id); setDraft((current) => ({ ...current, provider: id, market: provider?.markets[0] ?? id, timeframe: provider?.timeframes[0] ?? current.timeframe })); }
function coverageLabel(ranges: readonly AvailabilityRange[], start: string, end: string) { const from = new Date(start).getTime(); const to = new Date(end).getTime(); if (ranges.some((item) => new Date(item.start).getTime() <= from && new Date(item.end).getTime() >= to)) return 'cached'; if (ranges.some((item) => new Date(item.end).getTime() > from && new Date(item.start).getTime() < to)) return 'partially cached'; return 'requires download'; }
