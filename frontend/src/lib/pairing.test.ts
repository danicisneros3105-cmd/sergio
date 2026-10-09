import { describe, expect, it } from 'vitest';
import { consumePairFragment, readPairToken } from './pairing';

const TOKEN = 'sm_abcdefghijklmnopqrstuvwxyz0123456789-_';

describe('readPairToken', () => {
  it('finds the token in the fragment', () => {
    expect(readPairToken(`#pair=${TOKEN}`)).toBe(TOKEN);
    expect(readPairToken(`#x=1&pair=${TOKEN}`)).toBe(TOKEN);
  });

  it('ignores anything that does not look like a token', () => {
    expect(readPairToken('')).toBe('');
    expect(readPairToken('#pair=')).toBe('');
    expect(readPairToken('#pair=<script>alert(1)</script>')).toBe('');
    expect(readPairToken('#other=abc')).toBe('');
  });
});

// No DOM in these tests: a tiny stand-in for the bits of window it touches.
function fakeWindow(url: string, settings?: object) {
  const store = new Map<string, string>();
  if (settings) store.set('openjarvis-settings', JSON.stringify(settings));
  const parsed = new URL(url, 'https://x.trycloudflare.com');
  const win = {
    location: { pathname: parsed.pathname, search: parsed.search, hash: parsed.hash },
    localStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    },
    history: {
      replaceState: (_s: unknown, _t: string, next: string) => {
        const u = new URL(next, 'https://x.trycloudflare.com');
        win.location = { pathname: u.pathname, search: u.search, hash: u.hash };
      },
    },
  };
  return { win, store };
}

describe('consumePairFragment', () => {
  it('stores the key, keeps other settings and wipes the fragment', () => {
    const { win, store } = fakeWindow(`/chat?x=1#pair=${TOKEN}`, { theme: 'dark' });
    expect(consumePairFragment(win as unknown as Window)).toBe(true);
    expect(JSON.parse(store.get('openjarvis-settings')!)).toEqual({ theme: 'dark', apiKey: TOKEN });
    expect(win.location.hash).toBe('');
    expect(win.location.pathname + win.location.search).toBe('/chat?x=1');
  });

  it('does nothing without a pairing fragment', () => {
    const { win, store } = fakeWindow('/chat');
    expect(consumePairFragment(win as unknown as Window)).toBe(false);
    expect(store.size).toBe(0);
  });
});
