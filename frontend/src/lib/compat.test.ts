import { afterEach, describe, expect, it, vi } from 'vitest';
import { mediaProblem, newUuid } from './compat';

describe('any device', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('makes ids where the browser hides crypto.randomUUID (http on a phone)', () => {
    vi.stubGlobal('crypto', { getRandomValues: (a: Uint8Array) => a.fill(7) });
    expect(newUuid()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });

  it('says why the microphone cannot open on plain http', () => {
    vi.stubGlobal('navigator', {});
    vi.stubGlobal('window', { isSecureContext: false });
    expect(mediaProblem('micrófono')).toMatch(/micrófono con conexión segura/);
  });

  it('says nothing when the browser can ask for it', () => {
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: () => Promise.resolve() } });
    expect(mediaProblem('cámara')).toBe('');
  });
});
