import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '../../lib/api';
import { openOnDesktop } from './DesktopSections';

const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

describe('openOnDesktop', () => {
  afterEach(() => vi.clearAllMocks());

  it('opens when the PC app answers', async () => {
    vi.mocked(apiFetch).mockResolvedValue(reply(200, { ok: true, companion: true }));
    expect(await openOnDesktop('gym')).toBe('');
  });

  it('says so when the PC app is closed instead of claiming it opened', async () => {
    vi.mocked(apiFetch).mockResolvedValue(reply(200, { ok: true, companion: false }));
    expect(await openOnDesktop('gym')).toMatch(/no está abierto/);
  });

  it('passes on the server error', async () => {
    vi.mocked(apiFetch).mockResolvedValue(reply(400, { detail: 'Sección desconocida.' }));
    expect(await openOnDesktop('nope')).toBe('Sección desconocida.');
  });
});
