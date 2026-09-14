const configuredBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/+$/, '') ?? '';

export class BackendProblem extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

export async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  const url = backendUrl(path);
  const options: RequestInit & { targetAddressSpace?: 'loopback' } = {
    ...(configuredBaseUrl ? { credentials: 'include' as const } : {}),
    ...init,
    headers: { Accept: 'application/json', ...init?.headers },
  };
  if (targetsLoopback(url)) options.targetAddressSpace = 'loopback';

  const response = await fetch(url, options);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = isRecord(body) && isRecord(body.error) ? body.error : null;
    throw new BackendProblem(
      error && typeof error.message === 'string' ? error.message : `Request failed (${response.status})`,
      response.status,
    );
  }
  return body;
}

export function backendUrl(path: string): string {
  if (!configuredBaseUrl) return path;
  return `${configuredBaseUrl}${path.startsWith('/') ? path : `/${path}`}`;
}

export function backendWebSocketUrl(path: string): string {
  const httpUrl = configuredBaseUrl
    ? new URL(backendUrl(path))
    : new URL(path, location.href);
  httpUrl.protocol = httpUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  return httpUrl.toString();
}

function targetsLoopback(url: string): boolean {
  if (!configuredBaseUrl) return false;
  const hostname = new URL(url).hostname;
  return hostname === '127.0.0.1' || hostname === 'localhost' || hostname === '[::1]';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
