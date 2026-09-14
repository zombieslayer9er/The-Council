import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('configured backend transport', () => {
  it('sends Access cookies to a configured HTTPS API without changing the URL contract', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://council-api.example.com/');
    const fetch = vi.fn(() => Promise.resolve(
      new Response('{}', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ));
    vi.stubGlobal('fetch', fetch);
    const { backendWebSocketUrl, requestJson } = await import('./backend');

    await requestJson('/api/health');

    expect(fetch).toHaveBeenCalledWith(
      'https://council-api.example.com/api/health',
      expect.objectContaining({ credentials: 'include' }),
    );
    expect(backendWebSocketUrl('/ws/events')).toBe('wss://council-api.example.com/ws/events');
  });
});
