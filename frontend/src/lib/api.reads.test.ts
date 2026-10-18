import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// apiFetch reads: shared in-flight GETs, retries while the server restarts,
// writes sent exactly once, and the hidden-window cache for polls.

const fetchMock = vi.fn<typeof fetch>();
let visibility: 'visible' | 'hidden' = 'visible';
const listeners: Array<() => void> = [];

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'test');
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} });
  visibility = 'visible';
  listeners.length = 0;
  vi.stubGlobal('document', {
    get visibilityState() {
      return visibility;
    },
    addEventListener: (_: string, fn: () => void) => listeners.push(fn),
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('apiFetch reads', () => {
  it('shares one request between identical GETs in flight', async () => {
    let release!: (r: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise((r) => (release = r)));
    const { apiFetch } = await import('./api');
    const a = apiFetch('/v1/salud');
    const b = apiFetch('/v1/salud');
    release(json({ n: 1 }));
    const [ra, rb] = await Promise.all([a, b]);
    expect(await ra.json()).toEqual({ n: 1 });
    expect(await rb.json()).toEqual({ n: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // Once answered, the next read goes to the server again.
    fetchMock.mockResolvedValueOnce(json({ n: 2 }));
    expect(await (await apiFetch('/v1/salud')).json()).toEqual({ n: 2 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('retries a dropped connection and a gateway page, not an app error', async () => {
    vi.useFakeTimers();
    fetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response('Bad gateway', { status: 502 }))
      .mockResolvedValueOnce(json({ ok: true }));
    const { apiFetch } = await import('./api');
    const pending = apiFetch('/v1/estado');
    await vi.runAllTimersAsync();
    expect((await pending).status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);

    fetchMock.mockReset();
    fetchMock.mockResolvedValue(json({ detail: 'falta un módulo' }, 503));
    const appError = await apiFetch('/v1/otro');
    expect(appError.status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('never repeats a write', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const { apiFetch } = await import('./api');
    await expect(apiFetch('/v1/notas', { method: 'POST', body: '{}' })).rejects.toThrow('Failed to fetch');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('gives up after a long silence instead of hanging', async () => {
    vi.useFakeTimers();
    fetchMock.mockReturnValue(new Promise(() => {}));
    const { apiFetch, ApiTimeoutError } = await import('./api');
    const pending = apiFetch('/v1/lento');
    const caught = pending.catch((e) => e);
    await vi.advanceTimersByTimeAsync(45_000);
    expect(await caught).toBeInstanceOf(ApiTimeoutError);
  });

  it('streams are never shared or timed out', async () => {
    let release!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise((r) => (release = r)));
    const { apiFetch } = await import('./api');
    void apiFetch('/v1/swarm/abc/events');
    void apiFetch('/v1/swarm/abc/events');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    release(json({}));
  });

  it('reuses polls while the window is hidden and reads fresh when it is back', async () => {
    const { apiFetch } = await import('./api');
    visibility = 'hidden';
    fetchMock.mockResolvedValueOnce(json({ n: 1 }));
    expect(await (await apiFetch('/v1/nodes')).json()).toEqual({ n: 1 });
    expect(await (await apiFetch('/v1/nodes')).json()).toEqual({ n: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    visibility = 'visible';
    listeners.forEach((fn) => fn());
    fetchMock.mockResolvedValueOnce(json({ n: 2 }));
    expect(await (await apiFetch('/v1/nodes')).json()).toEqual({ n: 2 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
