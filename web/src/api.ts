import type { BootstrapResponse, ExperiencePage, ExperienceResponse, ExperimentEvaluationResponse, ExperimentForecastResponse, ExperimentOracleResponse, ExperimentPage, HealthResponse, LearningReviewPage, RunDetailResponse, TelemetryEvent, WeightGenerationPage } from '../../contracts/typescript/types.generated';
import { BackendProblem, backendWebSocketUrl, requestJson } from './backend';
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

export { BackendProblem as ApiProblem };

export async function bootstrap(signal?: AbortSignal): Promise<BootstrapData> {
  const [health, snapshot] = await Promise.all([requestJson('/api/health', { signal }), requestJson('/api/bootstrap', { signal })]);
  return { health: parseHealth(health), bootstrap: parseBootstrap(snapshot) };
}

export async function loadRun(runId: string, signal?: AbortSignal): Promise<RunDetailResponse> {
  return parseRunDetail(await requestJson(`/api/runs/${encodeURIComponent(runId)}`, { signal }));
}

export async function loadResearch(capabilities: readonly string[], signal?: AbortSignal): Promise<ResearchData> {
  const [experiments, experiences, weights, reviews] = await Promise.all([
    requestJson('/api/experiments?limit=500', { signal }).then(parseExperimentPage),
    capabilities.includes('experience_read') ? requestJson('/api/experiences?limit=500', { signal }).then(parseExperiencePage) : null,
    capabilities.includes('learning_read') ? requestJson('/api/weight-generations', { signal }).then(parseWeightGenerationPage) : null,
    capabilities.includes('learning_read') ? requestJson('/api/learning-reviews', { signal }).then(parseLearningReviewPage) : null,
  ]);
  return { experiments, experiences, weights, reviews };
}

export async function loadExperience(episodeId: string, signal?: AbortSignal): Promise<ExperienceResponse> {
  return parseExperienceResponse(await requestJson(`/api/experiences/${encodeURIComponent(episodeId)}`, { signal }));
}

export async function loadExperimentEvidence(experimentId: string, availability: { forecast: boolean; oracle: boolean; evaluation: boolean }, signal?: AbortSignal) {
  const [forecast, oracle, evaluation] = await Promise.all([
    availability.forecast ? requestJson(`/api/experiments/${encodeURIComponent(experimentId)}/forecast`, { signal }).then(parseExperimentForecastResponse) : null,
    availability.oracle ? requestJson(`/api/experiments/${encodeURIComponent(experimentId)}/oracle`, { signal }).then(parseExperimentOracleResponse) : null,
    availability.evaluation ? requestJson(`/api/experiments/${encodeURIComponent(experimentId)}/evaluation`, { signal }).then(parseExperimentEvaluationResponse) : null,
  ]);
  return { forecast: forecast as ExperimentForecastResponse | null, oracle: oracle as ExperimentOracleResponse | null, evaluation: evaluation as ExperimentEvaluationResponse | null };
}

export function openEventStream(callbacks: StreamCallbacks): () => void {
  let socket: WebSocket | null = null; let timer = 0; let stopped = false; let attempt = 0;
  const connect = () => {
    if (stopped) return;
    socket = new WebSocket(backendWebSocketUrl('/ws/events'));
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
