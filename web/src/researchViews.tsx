import { useEffect, useRef, useState } from 'react';
import type {
  AgentSignalPayload,
  ExperienceDetailPayload,
  ExperimentEvaluationPayload,
  ExperimentForecastPayload,
  ExperimentOraclePayload,
  LearningReviewPayload,
  MarketContextPayload,
  WeightGenerationPayload,
} from '../../contracts/typescript/types.generated';
import type { ResearchData } from './api';
import { loadExperience, loadExperimentEvidence } from './api';
import { agentLabel, money, percent, shortTime } from './model';
import { councilContributions, evidenceRefreshKey, matchingExperienceId, recurrenceEvidence, type RecurrenceObservation } from './researchModel';

export function EvidenceView({ context, signals }: { context: MarketContextPayload | null; signals: readonly AgentSignalPayload[] }) {
  const contributions = councilContributions(signals);
  return <>
    <Header title="Decision evidence" subtitle="Causal inputs, specialist reasoning, and Council influence remain linked to one snapshot." />
    <ContextPanel context={context} />
    <section className="evidence-stack">
      {signals.map((signal) => <SpecialistInspector key={signal.signal_id} signal={signal} contribution={contributions[signal.agent_id] ?? null} />)}
      {!signals.length && <Empty title="No specialist evidence" text="Evidence appears after specialists emit validated signals." />}
    </section>
  </>;
}

export function ContextPanel({ context }: { context: MarketContextPayload | null }) {
  const requested = new Set([...(context?.requested_required ?? []), ...(context?.requested_optional ?? [])]);
  const available = new Set(context?.data.map((item) => item.capability) ?? []); available.add('price_history');
  const capabilities = [...new Set([...requested, ...available])].sort();
  return <section className="panel context-panel">
    <PanelTitle kicker="Rich market context" title="Availability at decision time" extra={context ? shortTime(context.as_of) : 'NOT EMITTED'} />
    {context ? <div className="context-grid">{capabilities.map((capability) => {
      const items = context.data.filter((item) => item.capability === capability);
      const missing = context.missing_required.includes(capability) || context.missing_optional.includes(capability);
      return <article className={`context-card ${missing ? 'unavailable' : ''}`} key={capability}>
        <div><span className={`availability ${missing ? 'missing' : 'available'}`} /> <strong>{label(capability)}</strong></div>
        {items.map((item) => <p key={`${item.name}:${item.provenance.source_id}`}><b>{item.name.replaceAll('_', ' ')}</b><span>{formatValue(item.value, item.unit)}</span><small>{item.provenance.provider} · vintage {item.provenance.vintage}</small></p>)}
        {!items.length && <p><b>{missing ? 'Unavailable' : 'Available'}</b><span>{capability === 'price_history' ? 'Snapshot bars' : 'No scalar summary'}</span></p>}
      </article>;
    })}</div> : <Empty title="Context telemetry unavailable" text="No market_context_ready event exists for this run. Missing context is not interpreted as neutral or zero." compact />}
  </section>;
}

export function LearningView({ research }: { research: ResearchData | null }) {
  const generations = research?.weights?.items ?? [];
  const reviews = research?.reviews?.items ?? [];
  const [leftId, setLeftId] = useState(''); const [rightId, setRightId] = useState('');
  useEffect(() => {
    if (!generations.length) return;
    setRightId((current) => current || research?.weights?.active_generation_id || generations.at(-1)!.generation_id);
    setLeftId((current) => current || generations.at(-2)?.generation_id || generations[0].generation_id);
  }, [generations, research?.weights?.active_generation_id]);
  const left = generations.find((item) => item.generation_id === leftId) ?? null;
  const right = generations.find((item) => item.generation_id === rightId) ?? null;
  return <>
    <Header title="Learning and weights" subtitle="Versioned policy evidence only. This console cannot promote, roll back, or mutate an active generation." />
    {!research?.weights ? <Empty title="Learning store unavailable" text="Set BOTNET_COUNCIL_WEIGHT_STORE on the API process to expose immutable generations and Teacher reviews." /> : <>
      <section className="panel generation-compare">
        <PanelTitle kicker="Generation comparison" title={research.weights.active_generation_id ? `Active ${research.weights.active_generation_id}` : 'No active generation'} />
        <div className="compare-controls"><GenerationSelect label="Baseline" value={leftId} generations={generations} onChange={setLeftId} /><GenerationSelect label="Comparison" value={rightId} generations={generations} onChange={setRightId} /></div>
        <WeightTable left={left} right={right} />
      </section>
      <section><Header title="Librarian / Teacher review ledger" subtitle="Proposal evidence and held-out Teacher decisions are immutable audit records." small />
        <div className="review-list">{reviews.map((review) => <ReviewCard review={review} key={review.result_id} />)}{!reviews.length && <Empty title="No learning reviews" text="Profiles are available, but no Librarian proposal has been recorded with a Teacher result." compact />}</div>
      </section>
    </>}
  </>;
}

export function OutcomesView({ research }: { research: ResearchData | null }) {
  const experiments = research?.experiments.items ?? [];
  const experiences = research?.experiences?.items ?? [];
  const [selected, setSelected] = useState<string>('');
  const [forecast, setForecast] = useState<ExperimentForecastPayload | null>(null);
  const [oracle, setOracle] = useState<ExperimentOraclePayload | null>(null);
  const [evaluation, setEvaluation] = useState<ExperimentEvaluationPayload | null>(null);
  const [episode, setEpisode] = useState<ExperienceDetailPayload | null>(null);
  const previousExperimentId = useRef<string | null>(null);
  useEffect(() => { if (!selected && experiments.length) setSelected(experiments[0].experiment_id); }, [experiments, selected]);
  const summary = experiments.find((item) => item.experiment_id === selected) ?? null;
  const matchingId = matchingExperienceId(experiences, summary?.experiment_id);
  const refreshKey = evidenceRefreshKey(summary, matchingId ?? null);
  useEffect(() => {
    if (previousExperimentId.current !== (summary?.experiment_id ?? null)) {
      setForecast(null); setOracle(null); setEvaluation(null); setEpisode(null);
      previousExperimentId.current = summary?.experiment_id ?? null;
    }
    if (!summary) return;
    const controller = new AbortController();
    void loadExperimentEvidence(summary.experiment_id, { forecast: summary.forecast_locked, oracle: summary.oracle_available, evaluation: summary.evaluation_available }, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setForecast(value.forecast?.forecast ?? null); setOracle(value.oracle?.oracle_outcome ?? null); setEvaluation(value.evaluation?.evaluation ?? null);
      })
      .catch(() => undefined);
    setEpisode(null);
    if (matchingId) void loadExperience(matchingId, controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setEpisode(value.episode);
    }).catch(() => undefined);
    return () => controller.abort();
  }, [refreshKey]);
  return <>
    <Header title="Judge outcomes" subtitle="Future outcomes appear only after the forecast lock and oracle lifecycle gates have completed." />
    <div className="outcome-layout">
      <section className="panel experiment-list"><PanelTitle kicker="Blind experiments" title={`${experiments.length} records`} />{experiments.map((item) => <button className={item.experiment_id === selected ? 'run active' : 'run'} key={item.experiment_id} onClick={() => setSelected(item.experiment_id)}><span className={`run-status ${item.state === 'complete' ? 'completed' : ''}`} /><span><strong>{item.request.instrument} · {item.request.forecast_horizon}</strong><small>{shortTime(item.request.evaluation_time)} · {item.state}</small></span></button>)}{!experiments.length && <Empty title="No experiments" text="No persisted blind experiments are available." compact />}</section>
      <section className="panel outcome-detail"><PanelTitle kicker="Forecast versus outcome" title={summary?.request.instrument ?? 'Select an experiment'} extra={summary?.state.toUpperCase()} />
        {summary && <div className="outcome-content">
          <div className="outcome-metrics"><Metric label="Prediction" value={forecast?.direction.toUpperCase() ?? (summary.forecast_locked ? 'Loading' : 'Not locked')} /><Metric label="Expected return" value={percent(forecast?.expected_return, true)} /><Metric label="Actual return" value={summary.oracle_available ? percent(oracle?.realized_return, true) : 'Hidden until locked'} /><Metric label="Judge" value={evaluation ? (evaluation.directional_correctness ? 'HIT' : 'MISS') : 'Pending'} /></div>
          {!summary.oracle_available && <div className="oracle-lock">Future outcome sealed · forecasting path has no oracle access</div>}
          {oracle && <div className="outcome-metrics"><Metric label="Maximum adverse" value={percent(oracle.maximum_adverse_excursion, true)} /><Metric label="Maximum favorable" value={percent(oracle.maximum_favorable_excursion, true)} /><Metric label="Start" value={money(oracle.start_price)} /><Metric label="Endpoint" value={money(oracle.endpoint_price)} /></div>}
          {evaluation && <div className="detail-grid"><Metric label="Absolute error" value={percent(evaluation.absolute_return_error)} /><Metric label="Signed error" value={percent(evaluation.signed_return_error, true)} /><Metric label="Calibration" value={evaluation.calibration_bucket} /><Metric label="Confidence" value={percent(evaluation.confidence)} /></div>}
          {episode && <details className="episode-replay"><summary>Replay evidence · {episode.weight_generation_id}</summary><p>This view reuses frozen specialist outputs and original weights; it does not call agents or providers.</p><div className="weight-pills">{episode.applied_weights.map((item) => <span key={item.agent_id}>{agentLabel(item.agent_id)} <b>{item.weight.toFixed(3)}</b></span>)}</div></details>}
        </div>}
      </section>
    </div>
  </>;
}

export function SpecialistInspector({ signal, contribution }: { signal: AgentSignalPayload; contribution: number | null }) {
  const recurrence = recurrenceEvidence(signal);
  return <details className="panel specialist-inspector" open={signal.agent_id === 'historical_recurrence'}><summary><span className="agent-icon">{signal.agent_id.slice(0, 2).toUpperCase()}</span><span><strong>{agentLabel(signal.agent_id)}</strong><small>{signal.forecast_direction} · {signal.validity.replaceAll('_', ' ')}</small></span><span>{percent(signal.confidence)} confidence</span></summary>
    <div className="inspector-body"><div className="outcome-metrics"><Metric label="Expected return" value={percent(signal.expected_return, true)} /><Metric label="Target exposure" value={percent(signal.target_exposure, true)} /><Metric label="Council contribution" value={contribution == null ? 'Advisory / unavailable' : percent(contribution, true)} /><Metric label="Forecast horizon" value={`${signal.horizon_bars} bars`} /></div><p>{signal.rationale}</p>{recurrence && <RecurrenceInspector evidence={recurrence} />}</div>
  </details>;
}

function RecurrenceInspector({ evidence }: { evidence: NonNullable<ReturnType<typeof recurrenceEvidence>> }) {
  const selected = evidence.windows.find((item) => item.horizon_days === evidence.selected_horizon_days) ?? evidence.windows[0];
  const usable = selected?.observations.filter((item) => item.status === 'usable' && item.normalized_path.length > 1) ?? [];
  const [visible, setVisible] = useState<ReadonlySet<number>>(new Set(usable.map((item) => item.annual_year)));
  useEffect(() => setVisible(new Set(usable.map((item) => item.annual_year))), [selected?.horizon_days]);
  if (!selected) return <Empty title="No recurrence windows" text="The specialist emitted no valid analogue windows." compact />;
  return <div className="recurrence"><div className="outcome-metrics"><Metric label="Candidate" value={`${selected.horizon_days} days`} /><Metric label="Raw evidence" value={percent(selected.raw_positive_hit_ratio)} /><Metric label="Regime matched" value={percent(selected.regime_matched_hit_ratio)} /><Metric label="Persistence" value={percent(selected.persistence_score)} /></div><AnalogueChart observations={usable.filter((item) => visible.has(item.annual_year))} />
    <div className="year-toggles">{usable.map((item) => <label key={item.annual_year}><input type="checkbox" checked={visible.has(item.annual_year)} onChange={() => setVisible(toggle(visible, item.annual_year))} />{item.annual_year}</label>)}</div>
    <div className="table-wrap"><table><thead><tr><th>Year / date</th><th>Regime</th><th>Similarity</th><th>Forward return</th><th>MAE</th><th>MFE</th><th>Outcome</th></tr></thead><tbody>{selected.observations.map((item) => <tr key={`${item.annual_year}:${item.candidate_date}`}><td>{item.annual_year} · {item.candidate_date}</td><td>{item.regime ?? 'Unavailable'}</td><td>{percent(item.regime_similarity)}</td><td>{percent(item.forward_return, true)}</td><td>{percent(item.maximum_adverse_excursion, true)}</td><td>{percent(item.maximum_favorable_excursion, true)}</td><td>{item.status}</td></tr>)}</tbody></table></div>
  </div>;
}

function AnalogueChart({ observations }: { observations: readonly RecurrenceObservation[] }) {
  if (!observations.length) return <div className="analogue-empty">No usable analogue traces</div>;
  const palette = ['#51dfbd','#65a8ff','#b79cff','#f2c86b','#ff8f9a','#82d173'];
  const paths = observations.map((item, index) => ({ item, color: palette[index % palette.length], points: linePoints(item.normalized_path) }));
  return <div className="analogue-chart" role="img" aria-label={`${observations.length} normalized historical analogue paths`}><svg viewBox="0 0 100 100" preserveAspectRatio="none">{paths.map(({ item, color, points }) => <polyline key={item.annual_year} points={points} fill="none" stroke={color} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />)}</svg></div>;
}

function GenerationSelect({ label: title, value, generations, onChange }: { label: string; value: string; generations: readonly WeightGenerationPayload[]; onChange: (value: string) => void }) { return <label>{title}<select value={value} onChange={(event) => onChange(event.target.value)}>{generations.map((item) => <option value={item.generation_id} key={item.generation_id}>{item.generation_id}</option>)}</select></label>; }
function WeightTable({ left, right }: { left: WeightGenerationPayload | null; right: WeightGenerationPayload | null }) { const ids = [...new Set([...(left?.entries.map((item) => item.agent_id) ?? []), ...(right?.entries.map((item) => item.agent_id) ?? [])])].sort(); return <div className="table-wrap"><table><thead><tr><th>Agent</th><th>Slow</th><th>Recent</th><th>Effective</th><th>Comparison</th><th>Delta</th></tr></thead><tbody>{ids.map((id) => { const a = left?.entries.find((item) => item.agent_id === id); const b = right?.entries.find((item) => item.agent_id === id); const delta = a && b ? b.weight.effective - a.weight.effective : null; return <tr key={id}><td>{agentLabel(id)}</td><td>{b?.weight.long_term.toFixed(3) ?? '—'}</td><td>{b?.weight.recent.toFixed(3) ?? '—'}</td><td>{a?.weight.effective.toFixed(3) ?? '—'}</td><td>{b?.weight.effective.toFixed(3) ?? '—'}</td><td className={delta != null && delta >= 0 ? 'good-text' : 'bad-text'}>{delta == null ? '—' : `${delta >= 0 ? '+' : ''}${delta.toFixed(3)}`}</td></tr>; })}</tbody></table></div>; }
function ReviewCard({ review }: { review: LearningReviewPayload }) { return <details className={`panel review ${review.decision}`}><summary><span className={`badge ${review.decision === 'reject' ? 'failed' : 'completed'}`}>{review.decision.replaceAll('_', ' ')}</span><strong>{review.base_generation_id}</strong><span>{review.changes.length} changes · {shortTime(review.evaluated_at)}</span></summary><div className="inspector-body"><div className="outcome-metrics"><Metric label="Training episodes" value={String(review.training_episode_count)} /><Metric label="Held-out episodes" value={String(review.held_out_episode_count)} /><Metric label="Baseline score" value={review.baseline.score.toFixed(4)} /><Metric label="Proposed score" value={review.proposed.score.toFixed(4)} /></div>{review.changes.map((change) => <p key={change.agent_id}><b>{agentLabel(change.agent_id)}</b> {change.current.effective.toFixed(3)} → {change.proposed.effective.toFixed(3)} · {change.sample_count} samples · {change.reason}</p>)}<p>{review.reasons.join(' · ')}</p></div></details>; }

function Header({ title, subtitle, small = false }: { title: string; subtitle: string; small?: boolean }) { return <div className={`section-title ${small ? 'small' : ''}`}><div><p className="eyebrow">Research workspace</p><h2>{title}</h2></div><p>{subtitle}</p></div>; }
function PanelTitle({ kicker, title, extra }: { kicker: string; title: string; extra?: string }) { return <div className="panel-title"><div><p className="eyebrow">{kicker}</p><h2>{title}</h2></div>{extra && <span>{extra}</span>}</div>; }
function Metric({ label: title, value }: { label: string; value: string }) { return <div className="metric"><span>{title}</span><strong>{value}</strong></div>; }
function Empty({ title, text, compact = false }: { title: string; text: string; compact?: boolean }) { return <div className={`empty-state ${compact ? 'compact' : 'panel'}`}><p className="eyebrow">Read-only evidence</p><h2>{title}</h2><p>{text}</p></div>; }
function label(value: string) { return value.split('_').map((part) => part[0].toUpperCase() + part.slice(1)).join(' '); }
function formatValue(value: unknown, unit: string) { if (typeof value === 'number') return `${value.toLocaleString()} ${unit}`; if (typeof value === 'string') return `${value} ${unit}`; return `${JSON.stringify(value)} ${unit}`; }
function toggle(values: ReadonlySet<number>, value: number) { const next = new Set(values); if (next.has(value)) next.delete(value); else next.add(value); return next; }
function linePoints(values: readonly number[]) { const min = Math.min(...values); const max = Math.max(...values); const range = max - min || 1; return values.map((value, index) => `${(index / (values.length - 1)) * 100},${92 - ((value - min) / range) * 84}`).join(' '); }
