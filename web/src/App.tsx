import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  AgentSignalPayload,
  HealthResponse,
  RunSummary,
  StateResponse,
  TelemetryEvent,
} from '../../contracts/typescript/types.generated';
import { bootstrap, loadResearch, loadRun, openEventStream, type ResearchData } from './api';
import { ContractError } from './validate';
import { applyBootstrap, beginResync, bufferEvent, emptyLiveState, failLive, type ConnectionStatus } from './liveState';
import { RequestGate } from './requestGate';
import { agentLabel, money, percent, project, shortTime } from './model';
import { EvidenceView, LearningView, OutcomesView } from './researchViews';
import { HistoricalView } from './historicalView';

type View = 'historical' | 'live' | 'evidence' | 'learning' | 'outcomes' | 'history' | 'backtests' | 'portfolio' | 'system';

const NAV: { key: View; label: string; icon: string }[] = [
  { key: 'historical', label: 'Historical Lab', icon: '◩' },
  { key: 'live', label: 'Live Council', icon: '⬡' },
  { key: 'evidence', label: 'Evidence', icon: '⊛' },
  { key: 'learning', label: 'Learning', icon: '⌁' },
  { key: 'outcomes', label: 'Outcomes', icon: '◎' },
  { key: 'history', label: 'History', icon: '◫' },
  { key: 'backtests', label: 'Backtests', icon: '◇' },
  { key: 'portfolio', label: 'Portfolio', icon: '◉' },
  { key: 'system', label: 'System', icon: '⊡' },
];

export default function App() {
  const [view, setView] = useState<View>(() => viewFromHash());
  const [menuOpen, setMenuOpen] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [live, setLive] = useState(emptyLiveState);
  const [replayEvents, setReplayEvents] = useState<readonly TelemetryEvent[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [loadingRun, setLoadingRun] = useState(false);
  const [research, setResearch] = useState<ResearchData | null>(null);
  const [researchError, setResearchError] = useState<string | null>(null);
  const bootstrapGate = useRef(new RequestGate());
  const researchGate = useRef(new RequestGate());
  const replayGate = useRef(new RequestGate());
  const hasBootstrapped = useRef(false);

  const resync = useCallback(async (initial = false) => {
    const request = bootstrapGate.current.begin();
    setLive((current) => beginResync(current, initial));
    try {
      const data = await bootstrap(request.signal);
      if (!bootstrapGate.current.isCurrent(request.generation)) return;
      setHealth(data.health);
      setLive((current) => applyBootstrap(current, data.bootstrap));
      const researchRequest = researchGate.current.begin();
      void loadResearch(data.health.capabilities, researchRequest.signal).then((value) => {
        if (researchGate.current.isCurrent(researchRequest.generation)) {
          setResearch(value);
          setResearchError(null);
        }
      }).catch((cause: unknown) => {
        if (!researchRequest.signal.aborted && researchGate.current.isCurrent(researchRequest.generation)) {
          setResearchError(cause instanceof Error ? cause.message : 'Unable to load research evidence.');
        }
      });
      hasBootstrapped.current = true;
    } catch (cause) {
      if (request.signal.aborted || !bootstrapGate.current.isCurrent(request.generation)) return;
      const malformed = cause instanceof ContractError;
      setLive((current) => failLive(current, malformed ? 'malformed' : 'disconnected', cause instanceof Error ? cause.message : 'Unable to reach the telemetry API.'));
    }
  }, []);

  useEffect(() => openEventStream({
    onOpen: () => void resync(!hasBootstrapped.current),
    onEvent: (event) => setLive((current) => {
      const next = bufferEvent(current, event);
      if (current.status === 'live' && next.status === 'resynchronizing') queueMicrotask(() => void resync(false));
      return next;
    }),
    onDisconnect: () => setLive((current) => failLive(current, 'disconnected', 'Telemetry connection lost.')),
    onMalformed: (message) => setLive((current) => failLive(current, 'malformed', message)),
  }), [resync]);
  useEffect(() => {
    const handler = () => setView(viewFromHash());
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);

  const selectView = (next: View) => { location.hash = next; setView(next); setMenuOpen(false); };
  const selectRun = async (runId: string) => {
    const request = replayGate.current.begin();
    setSelectedRun(runId); setLoadingRun(true);
    try {
      const result = await loadRun(runId, request.signal);
      if (replayGate.current.isCurrent(request.generation)) setReplayEvents(result.events);
    } catch (cause) {
      if (!request.signal.aborted && replayGate.current.isCurrent(request.generation)) setLive((current) => ({ ...current, error: cause instanceof Error ? cause.message : 'Unable to load run.' }));
    } finally { if (replayGate.current.isCurrent(request.generation)) setLoadingRun(false); }
  };
  const data = useMemo(() => {
    const projected = project(live.events);
    return {
      ...projected,
      decision: projected.decision ?? live.state?.latest_decision ?? null,
      risk: projected.risk ?? live.state?.latest_risk_decision ?? null,
      portfolio: projected.portfolio ?? live.state?.latest_portfolio ?? null,
    };
  }, [live.events, live.state]);
  const displayStatus: ConnectionStatus | 'replay' = view === 'history' ? 'replay' : live.status;

  return (
    <div className="shell">
      <aside className={menuOpen ? 'sidebar open' : 'sidebar'}>
        <div className="brand">
          <div className="brand-mark">BC</div>
          <div><strong>BOTNET COUNCIL</strong><span>Telemetry console</span></div>
        </div>
        <nav aria-label="Primary">
          {NAV.map((item) => (
            <button key={item.key} className={view === item.key ? 'nav-item active' : 'nav-item'} onClick={() => selectView(item.key)}>
              <span aria-hidden="true">{item.icon}</span>{item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <StatusDot status={displayStatus} />
          <div className="paper-card"><strong>PAPER / RESEARCH</strong><span>{health?.capabilities.includes('historical_control') ? 'Authenticated experiments. No live orders.' : 'Read-only. No live orders.'}</span></div>
        </div>
      </aside>

      <main id="main" className="main">
        <header className="topbar">
          <button className="menu" aria-label="Toggle navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>☰</button>
          <div>
            <p className="eyebrow">{NAV.find((item) => item.key === view)?.label}</p>
            <h1>{pageTitle(view, data.decision?.symbol)}</h1>
          </div>
          <div className="top-actions">
            {view !== 'historical' && <><span className="sequence">{live.streamId ? `GEN ${live.streamId.slice(0, 8)} · ` : ''}SEQ {live.watermark.toLocaleString()}</span><button className="secondary" onClick={() => void resync(false)}>↻ Resync</button></>}
          </div>
        </header>

        {live.error && view !== 'historical' && <div className="error-banner" role="alert"><span>{live.error}</span><button onClick={() => void resync(false)}>Retry</button></div>}
        {researchError && <div className="error-banner research-error" role="status"><span>Research evidence: {researchError}</span><button onClick={() => void resync(false)}>Retry</button></div>}

        <div className="content">
          {view === 'historical' && <HistoricalView controlEnabled={health?.capabilities.includes('historical_control') ?? false} onConnect={() => resync(false)} />}
          {view === 'live' && <LiveView data={data} connection={live.status} loading={live.status === 'bootstrapping' || live.status === 'resynchronizing'} />}
          {view === 'evidence' && <EvidenceView context={data.context} signals={data.signals} />}
          {view === 'learning' && <LearningView research={research} />}
          {view === 'outcomes' && <OutcomesView research={research} />}
          {view === 'history' && <HistoryView runs={live.runs} selected={selectedRun} events={replayEvents} onSelect={selectRun} loading={loadingRun} />}
          {view === 'backtests' && <BacktestsView runs={live.runs} />}
          {view === 'portfolio' && <PortfolioView portfolio={data.portfolio ?? live.state?.latest_portfolio ?? null} />}
          {view === 'system' && <SystemView health={health} state={live.state} events={live.events} connection={live.status} />}
        </div>
      </main>
    </div>
  );
}

function LiveView({ data, connection, loading }: { data: ReturnType<typeof project>; connection: ConnectionStatus; loading: boolean }) {
  const { snapshot, decision, signals, risk, execution, reconciliation } = data;
  const latest = snapshot?.bars.at(-1);
  const previous = snapshot?.bars.at(-2);
  const delta = latest && previous ? (latest.close - previous.close) / previous.close : null;
  const alpha = signals.filter((signal) => signal.signal_type === 'alpha');
  const advisory = signals.filter((signal) => signal.signal_type !== 'alpha');

  if (!data.events.length && !loading) {
    const authoritative = connection === 'live';
    return <EmptyState title={authoritative ? 'Awaiting the first council run' : 'Telemetry API unavailable'} text={authoritative ? 'The console is connected to an authoritative read-only snapshot. Start a configured local pipeline to populate this workspace.' : 'Reconnect the local API to inspect deterministic telemetry. This interface never substitutes generated browser data.'} />;
  }
  return <>
    <section className="market-strip panel">
      <div><p className="eyebrow">Instrument</p><h2>{snapshot?.symbol ?? decision?.symbol ?? '—'} <small>{snapshot?.timeframe ?? decision?.timeframe ?? ''}</small></h2></div>
      <Metric label="Last close" value={money(latest?.close)} tone="bright" />
      <Metric label="Bar change" value={percent(delta, true)} tone={delta != null && delta >= 0 ? 'good' : 'bad'} />
      <Metric label="Observed" value={shortTime(snapshot?.observed_at)} />
      <Metric label="Provider" value={snapshot?.provenance?.provider ?? 'Unavailable'} />
      <div className="mode-chip"><i /> PAPER ONLY</div>
    </section>

    <section className="hero-grid">
      <div className="panel chart-panel">
        <PanelTitle kicker="Market context" title="Causal price window" extra={`${snapshot?.bars.length ?? 0} bars`} />
        <PriceChart bars={snapshot?.bars ?? []} />
        <div className="chart-foot"><span>Availability boundary preserved</span><span>Latest available {shortTime(snapshot?.latest_available_at)}</span></div>
      </div>
      <div className="panel decision-panel">
        <PanelTitle kicker="Council output" title="Deterministic consensus" />
        {decision ? <>
          <div className="decision-direction"><Direction direction={decision.forecast_direction} /><strong>{decision.action.replaceAll('_', ' ')}</strong></div>
          <div className="meters"><Meter label="Confidence" value={decision.confidence} /><Meter label="Signed conviction" value={Math.abs(decision.conviction)} signed={decision.conviction} /></div>
          <div className="metric-grid"><Metric label="Expected return" value={percent(decision.expected_return, true)} /><Metric label="Target exposure" value={percent(decision.target_exposure, true)} /></div>
          <blockquote>{decision.rationale}</blockquote>
          <p className="fine">Decision {decision.decision_id} · {shortTime(decision.decided_at)}</p>
        </> : <InlineEmpty text="No council decision has been emitted yet." />}
      </div>
    </section>

    <section>
      <SectionTitle title="Council chamber" subtitle="Directional specialists vote. Context specialists advise." />
      <div className="agent-columns">
        <div><p className="column-label">ALPHA SPECIALISTS · {alpha.length}</p><div className="agent-grid">{alpha.map((signal) => <AgentCard key={signal.signal_id} signal={signal} />)}{!alpha.length && <InlineEmpty text="No alpha signals available." />}</div></div>
        <div><p className="column-label advisory">CONTEXT ADVISERS · {advisory.length}</p><div className="agent-grid">{advisory.map((signal) => <AgentCard key={signal.signal_id} signal={signal} advisory />)}{!advisory.length && <InlineEmpty text="No advisory signals available." />}</div></div>
      </div>
    </section>

    <section className="risk-grid">
      <div className={risk?.vetoed ? 'panel risk-card veto' : 'panel risk-card approved'}>
        <PanelTitle kicker="Independent authority" title="Risk gate" extra={risk?.risk_status.toUpperCase() ?? 'WAITING'} />
        {risk ? <>
          <div className="risk-verdict"><span>{risk.vetoed ? '×' : '✓'}</span><div><strong>{risk.vetoed ? 'Proposal vetoed' : 'Proposal authorized'}</strong><p>{risk.reasons.join(' · ')}</p></div></div>
          <div className="metric-grid"><Metric label="Equity at check" value={money(risk.equity)} /><Metric label="Gross exposure" value={money(risk.gross_exposure)} /></div>
        </> : <InlineEmpty text="Risk evaluation has not completed." />}
      </div>
      <div className="panel">
        <PanelTitle kicker="Paper broker" title="Execution" extra={execution?.execution_status.toUpperCase() ?? 'NO REPORT'} />
        {execution ? <div className="detail-list"><Detail label="Side / quantity" value={`${execution.side.toUpperCase()} ${execution.quantity}`} /><Detail label="Fill" value={execution.fill_price == null ? 'Not filled' : money(execution.fill_price)} /><Detail label="Costs" value={money(execution.total_costs)} /><Detail label="Slippage" value={`${execution.slippage_bps.toFixed(1)} bps`} /></div> : <InlineEmpty text={risk?.vetoed ? 'No execution by design after veto.' : 'No execution report is available.'} />}
      </div>
      <div className="panel">
        <PanelTitle kicker="Post-trade control" title="Reconciliation" extra={reconciliation ? (reconciliation.compliant ? 'COMPLIANT' : 'EXCEPTION') : 'PENDING'} />
        {reconciliation ? <div className="risk-verdict"><span>{reconciliation.compliant ? '✓' : '!'}</span><div><strong>{reconciliation.compliant ? 'Authorization matched' : 'Review required'}</strong><p>{reconciliation.reasons.join(' · ')}</p></div></div> : <InlineEmpty text="No reconciliation record is available." />}
      </div>
    </section>

    <p className="sr-only" aria-live="polite">Connection status: {connection}</p>
  </>;
}

function HistoryView({ runs, selected, events, onSelect, loading }: { runs: readonly RunSummary[]; selected: string | null; events: readonly TelemetryEvent[]; onSelect: (id: string) => void; loading: boolean }) {
  return <div className="history-layout">
    <section className="panel run-list"><PanelTitle kicker="Replay mode · isolated" title={`${runs.length} runs`} />
      {runs.map((run) => <button key={run.run_id} className={selected === run.run_id ? 'run active' : 'run'} onClick={() => onSelect(run.run_id)}>
        <span className={`run-status ${run.status}`} /><span><strong>{run.symbol ?? 'System run'} · {run.timeframe ?? '—'}</strong><small>{shortTime(run.updated_at)} · {run.event_count} events</small></span><code>#{run.last_sequence}</code>
      </button>)}
      {!runs.length && <InlineEmpty text="No recorded runs in this process." />}
    </section>
    <section className="panel event-ledger"><PanelTitle kicker="Ordered replay" title={selected ? `Run ${selected}` : 'Select a run'} extra={loading ? 'LOADING' : `${events.length} EVENTS`} />
      <div className="timeline">{events.map((event) => <EventRow key={event.event_id} event={event} />)}{!events.length && <InlineEmpty text="Replay events appear here in authoritative sequence order." />}</div>
    </section>
  </div>;
}

function BacktestsView({ runs }: { runs: readonly RunSummary[] }) {
  const backtests = runs.filter((run) => run.run_kind === 'backtest');
  return <><SectionTitle title="Backtest runs" subtitle="The API currently exposes lifecycle telemetry; ledger analytics remain authoritative in saved artifacts." />
    <div className="cards">{backtests.map((run) => <div className="panel summary-card" key={run.run_id}><span className={`badge ${run.status}`}>{run.status}</span><h3>{run.symbol ?? 'Research universe'}</h3><p>{run.timeframe ?? 'mixed timeframe'} · {run.event_count} events</p><Detail label="Started" value={shortTime(run.started_at)} /><Detail label="Updated" value={shortTime(run.updated_at)} /></div>)}{!backtests.length && <EmptyState title="No backtests in this process" text="Run a backtest with telemetry publishing enabled. Progress and completion events will appear here without inventing unavailable performance metrics." />}</div>
  </>;
}

function PortfolioView({ portfolio }: { portfolio: StateResponse['latest_portfolio'] }) {
  if (!portfolio) return <EmptyState title="Portfolio unavailable" text="The API has not received a valued portfolio state. No exposure or P&L is inferred from orders." />;
  return <><section className="portfolio-hero panel"><div><p className="eyebrow">Marked account</p><h2>{money(portfolio.equity)}</h2><span>Valued {shortTime(portfolio.valued_at)}</span></div><Metric label="Cash" value={money(portfolio.cash)} /><Metric label="Gross exposure" value={money(portfolio.gross_exposure)} /><Metric label="Unrealized P&L" value={money(portfolio.unrealized_pnl)} tone={portfolio.unrealized_pnl >= 0 ? 'good' : 'bad'} /></section>
    <section className="panel table-panel"><PanelTitle kicker="Current book" title="Marked positions" extra={`${portfolio.positions.length} POSITIONS`} /><div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Quantity</th><th>Average entry</th><th>Mark</th><th>Market value</th><th>Exposure</th><th>Unrealized P&L</th></tr></thead><tbody>{portfolio.positions.map((position) => <tr key={position.symbol}><td><strong>{position.symbol}</strong></td><td>{position.quantity}</td><td>{money(position.average_entry_price)}</td><td>{money(position.mark_price)}</td><td>{money(position.market_value)}</td><td>{money(position.exposure)}</td><td className={position.unrealized_pnl >= 0 ? 'good-text' : 'bad-text'}>{money(position.unrealized_pnl)}</td></tr>)}</tbody></table></div>{!portfolio.positions.length && <InlineEmpty text="The portfolio is currently flat." />}</section>
  </>;
}

function SystemView({ health, state, events, connection }: { health: HealthResponse | null; state: StateResponse | null; events: readonly TelemetryEvent[]; connection: ConnectionStatus }) {
  return <><section className="system-grid"><div className="panel summary-card"><p className="eyebrow">Service</p><h3>{health?.service ?? 'Telemetry API'}</h3><Detail label="Connection" value={connection.toUpperCase()} /><Detail label="API contract" value={health?.api_version ?? '—'} /><Detail label="Backend" value={health?.backend_version ?? '—'} /><Detail label="Access" value={health ? (health.read_only ? 'READ ONLY' : 'AUTHENTICATED CONTROL') : '—'} /></div><div className="panel summary-card"><p className="eyebrow">Event bus</p><h3>{(state?.event_count ?? 0).toLocaleString()} events</h3><Detail label="Generation" value={state?.stream_id ?? '—'} /><Detail label="Last sequence" value={String(state?.sequence_watermark ?? 0)} /><Detail label="Active runs" value={String(state?.active_runs.length ?? 0)} /><Detail label="Local replay" value={`${events.length} events`} /></div></section>
    <section className="panel event-ledger"><PanelTitle kicker="Recent activity" title="Telemetry stream" extra="NEWEST FIRST" /><div className="timeline">{[...events].reverse().slice(0, 50).map((event) => <EventRow key={event.event_id} event={event} />)}{!events.length && <InlineEmpty text="No events received." />}</div></section>
  </>;
}

function AgentCard({ signal, advisory = false }: { signal: AgentSignalPayload; advisory?: boolean }) {
  return <article className={`panel agent-card ${advisory ? 'advisory' : ''}`}>
    <div className="agent-head"><div className="agent-icon">{signal.agent_id.slice(0, 2).toUpperCase()}</div><div><h3>{agentLabel(signal.agent_id)}</h3><span>{signal.agent_id} · v{signal.agent_version}</span></div><span className={`badge ${signal.signal_type}`}>{signal.signal_type}</span></div>
    <div className="agent-state"><Direction direction={signal.forecast_direction} /><span className={`badge ${signal.validity}`}>{signal.validity.replace('_', ' ')}</span></div>
    <Meter label="Confidence" value={signal.confidence} />
    <div className="metric-grid"><Metric label="Expected return" value={percent(signal.expected_return, true)} /><Metric label="Target exposure" value={percent(signal.target_exposure, true)} /></div>
    <p className="rationale">{signal.rationale}</p>
  </article>;
}

function PriceChart({ bars }: { bars: readonly { close: number; high: number; low: number }[] }) {
  if (bars.length < 2) return <div className="chart-empty">Price bars unavailable</div>;
  const values = bars.slice(-48); const min = Math.min(...values.map((bar) => bar.low)); const max = Math.max(...values.map((bar) => bar.high));
  const range = max - min || 1; const points = values.map((bar, index) => `${(index / (values.length - 1)) * 100},${95 - ((bar.close - min) / range) * 82}`).join(' ');
  const area = `0,100 ${points} 100,100`;
  return <div className="chart" role="img" aria-label={`Price chart from ${money(values[0].close)} to ${money(values.at(-1)?.close)}`}><svg viewBox="0 0 100 100" preserveAspectRatio="none"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3dd6b4" stopOpacity=".28"/><stop offset="1" stopColor="#3dd6b4" stopOpacity="0"/></linearGradient></defs><polygon points={area} fill="url(#area)"/><polyline points={points} fill="none" stroke="#51dfbd" strokeWidth="1.25" vectorEffect="non-scaling-stroke"/></svg><span className="chart-high">{money(max)}</span><span className="chart-low">{money(min)}</span></div>;
}

function EventRow({ event }: { event: TelemetryEvent }) {
  return <div className="event-row"><span className="event-seq">{String(event.sequence).padStart(4, '0')}</span><span className={`event-node ${event.event_type.includes('failed') || event.event_type.includes('veto') ? 'bad' : ''}`} /><div><strong>{event.event_type.replaceAll('_', ' ')}</strong><p>{event.symbol ?? 'system'} · {shortTime(event.emitted_at)}</p></div><code>{event.correlation_id ?? event.run_id}</code></div>;
}

function StatusDot({ status }: { status: ConnectionStatus | 'replay' }) { return <div className={`connection ${status}`}><i /><span>{status}</span></div>; }
function Direction({ direction }: { direction: string }) { const safe = ['long', 'short', 'flat'].includes(direction) ? direction : 'flat'; return <span className={`direction ${safe}`}>{safe === 'long' ? '▲' : safe === 'short' ? '▼' : '→'} {safe.toUpperCase()}</span>; }
function Meter({ label, value, signed }: { label: string; value: number; signed?: number }) { return <div className="meter"><div><span>{label}</span><strong>{signed == null ? percent(value) : percent(signed, true)}</strong></div><div className="track"><i style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }} /></div></div>; }
function Metric({ label, value, tone }: { label: string; value: string; tone?: 'bright' | 'good' | 'bad' }) { return <div className={`metric ${tone ?? ''}`}><span>{label}</span><strong>{value}</strong></div>; }
function Detail({ label, value }: { label: string; value: string }) { return <div className="detail"><span>{label}</span><strong>{value}</strong></div>; }
function PanelTitle({ kicker, title, extra }: { kicker: string; title: string; extra?: string }) { return <div className="panel-title"><div><p className="eyebrow">{kicker}</p><h2>{title}</h2></div>{extra && <span>{extra}</span>}</div>; }
function SectionTitle({ title, subtitle }: { title: string; subtitle: string }) { return <div className="section-title"><div><p className="eyebrow">Research workspace</p><h2>{title}</h2></div><p>{subtitle}</p></div>; }
function InlineEmpty({ text }: { text: string }) { return <div className="inline-empty">{text}</div>; }
function EmptyState({ title, text, action }: { title: string; text: string; action?: React.ReactNode }) { return <div className="empty-state panel"><div className="empty-orbit"><i /></div><p className="eyebrow">Paper research workspace</p><h2>{title}</h2><p>{text}</p>{action ?? <code>python -m botnet_council</code>}</div>; }
function viewFromHash(): View { const value = location.hash.slice(1) as View; return NAV.some((item) => item.key === value) ? value : 'historical'; }
function pageTitle(view: View, symbol?: string) { return view === 'live' ? `${symbol ?? 'Council'} research session` : NAV.find((item) => item.key === view)?.label ?? 'Console'; }
