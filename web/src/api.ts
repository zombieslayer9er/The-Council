import type { BootstrapResponse, ExperiencePage, ExperienceResponse, ExperimentEvaluationResponse, ExperimentForecastResponse, ExperimentOracleResponse, ExperimentPage, HealthResponse, LearningReviewPage, RunDetailResponse, TelemetryEvent, WeightGenerationPage } from '../../contracts/typescript/types.generated';
import { ContractError, parseBootstrap, parseExperiencePage, parseExperienceResponse, parseExperimentEvaluationResponse, parseExperimentForecastResponse, parseExperimentOracleResponse, parseExperimentPage, parseHealth, parseLearningReviewPage, parseRunDetail, parseTelemetryEvent, parseWeightGenerationPage } from './validate';

export interface BootstrapData { health: HealthResponse; bootstrap: BootstrapResponse }
export interface StreamCallbacks {
  onEvent: (event: TelemetryEvent) => void;
  onOpen: () => void;
  onDisconnect: () => void;
  onMalformed: (message: string) => void;
}
export interface ResearchData {
  experiments: ExperimentPage;
  experiences: ExperiencePage | null;
  weights: WeightGenerationPage | null;
  reviews: LearningReviewPage | null;
}

export class ApiProblem extends Error {
  constructor(message: string, readonly status?: number) { super(message); }
}

async function getUnknown(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { signal, headers: { Accept: 'application/json' } });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = isRecord(body) && isRecord(body.error) ? body.error : null;
    throw new ApiProblem(error && typeof error.message === 'string' ? error.message : `Request failed (${response.status})`, response.status);
  }
  return body;
}

export async function bootstrap(signal?: AbortSignal): Promise<BootstrapData> {
  const [health, snapshot] = await Promise.all([getUnknown('/api/health', signal), getUnknown('/api/bootstrap', signal)]);
  return { health: parseHealth(health), bootstrap: parseBootstrap(snapshot) };
}

export async function loadRun(runId: string, signal?: AbortSignal): Promise<RunDetailResponse> {
  return parseRunDetail(await getUnknown(`/api/runs/${encodeURIComponent(runId)}`, signal));
}

export async function loadResearch(capabilities: readonly string[], signal?: AbortSignal): Promise<ResearchData> {
  const [experiments, experiences, weights, reviews] = await Promise.all([
    getUnknown('/api/experiments?limit=500', signal).then(parseExperimentPage),
    capabilities.includes('experience_read') ? getUnknown('/api/experiences?limit=500', signal).then(parseExperiencePage) : null,
    capabilities.includes('learning_read') ? getUnknown('/api/weight-generations', signal).then(parseWeightGenerationPage) : null,
    capabilities.includes('learning_read') ? getUnknown('/api/learning-reviews', signal).then(parseLearningReviewPage) : null,
  ]);
  return { experiments, experiences, weights, reviews };
}

export async function loadExperience(episodeId: string, signal?: AbortSignal): Promise<ExperienceResponse> {
  return parseExperienceResponse(await getUnknown(`/api/experiences/${encodeURIComponent(episodeId)}`, signal));
}

export async function loadExperimentEvidence(experimentId: string, availability: { forecast: boolean; oracle: boolean; evaluation: boolean }, signal?: AbortSignal) {
  const [forecast, oracle, evaluation] = await Promise.all([
    availability.forecast ? getUnknown(`/api/experiments/${encodeURIComponent(experimentId)}/forecast`, signal).then(parseExperimentForecastResponse) : null,
    availability.oracle ? getUnknown(`/api/experiments/${encodeURIComponent(experimentId)}/oracle`, signal).then(parseExperimentOracleResponse) : null,
    availability.evaluation ? getUnknown(`/api/experiments/${encodeURIComponent(experimentId)}/evaluation`, signal).then(parseExperimentEvaluationResponse) : null,
  ]);
  return { forecast: forecast as ExperimentForecastResponse | null, oracle: oracle as ExperimentOracleResponse | null, evaluation: evaluation as ExperimentEvaluationResponse | null };
}

export function openEventStream(callbacks: StreamCallbacks): () => void {
  let socket: WebSocket | null = null; let timer = 0; let stopped = false; let attempt = 0;
  const connect = () => {
    if (stopped) return;
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${protocol}//${location.host}/ws/events`);
    socket.onopen = () => { attempt = 0; callbacks.onOpen(); };
    socket.onmessage = (message) => {
      try {
        const value: unknown = JSON.parse(String(message.data));
        if (isRecord(value) && value.type === 'stream_error') {
          callbacks.onMalformed(typeof value.message === 'string' ? value.message : 'Telemetry resynchronization required.');
          socket?.close(); return;
        }
        callbacks.onEvent(parseTelemetryEvent(value));
      } catch (error) {
        callbacks.onMalformed(error instanceof ContractError ? `Malformed telemetry: ${error.message}` : 'Malformed telemetry message.');
      }
    };
    socket.onerror = () => socket?.close();
    socket.onclose = () => {
      if (stopped) return;
      callbacks.onDisconnect(); attempt += 1;
      timer = window.setTimeout(connect, Math.min(30_000, 750 * 2 ** Math.min(attempt, 5)));
    };
  };
  connect();
  return () => { stopped = true; window.clearTimeout(timer); socket?.close(); };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
