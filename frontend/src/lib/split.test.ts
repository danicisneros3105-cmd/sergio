import { beforeEach, describe, expect, it } from 'vitest';
import { clampRatio, foldOf, paneUrl, safePath, useSplit } from './split';

describe('split screen', () => {
  beforeEach(() => {
    useSplit.setState({ open: false, path: '/chat', ratio: 0.5, phase: 'still' });
  });

  it('only shows Sergio pages in the pane', () => {
    expect(safePath('/nodes')).toBe('/nodes');
    expect(safePath('https://evil.example')).toBe('/chat');
    expect(safePath('//evil.example/x')).toBe('/chat');
    expect(paneUrl('/salud?tab=mente')).toBe('/salud?tab=mente&pane=1');
    expect(paneUrl('/nodes')).toBe('/nodes?pane=1');
  });

  it('keeps the division between a quarter and three quarters', () => {
    expect(clampRatio(0.1)).toBe(0.25);
    expect(clampRatio(0.9)).toBe(0.75);
    expect(clampRatio(Number.NaN)).toBe(0.5);
  });

  it('opens with the fold and closes only when the fold ends', () => {
    const s = useSplit.getState();
    s.show('/nodes');
    expect(useSplit.getState()).toMatchObject({ open: true, path: '/nodes' });
    useSplit.getState().hide();
    // still on screen while the second pane folds away
    expect(useSplit.getState().open).toBe(true);
    useSplit.getState().settle();
    expect(useSplit.getState().open).toBe(false);
  });

  it('remembers the choice', () => {
    const memory = new Map<string, string>();
    const g = globalThis as unknown as { localStorage?: unknown };
    g.localStorage = { getItem: (k: string) => memory.get(k) ?? null, setItem: (k: string, v: string) => memory.set(k, v) };
    useSplit.getState().show('/salud');
    useSplit.getState().setRatio(0.6);
    expect(JSON.parse(memory.get('sergio-split') || '{}')).toMatchObject({ open: true, path: '/salud', ratio: 0.6 });
    g.localStorage = undefined;
  });

  it('reads the screens of a foldable', () => {
    const one = { innerWidth: 800, matchMedia: () => ({ matches: false }) } as unknown as Window;
    expect(foldOf(one)).toBe('none');
    const book = {
      innerWidth: 1100,
      viewport: { segments: [{ width: 540, height: 720, left: 0, top: 0 }, { width: 540, height: 720, left: 560, top: 0 }] },
      matchMedia: () => ({ matches: false }),
    } as unknown as Window;
    expect(foldOf(book)).toBe('side');
    const table = {
      innerWidth: 900,
      viewport: { segments: [{ width: 900, height: 400, left: 0, top: 0 }, { width: 900, height: 400, left: 0, top: 420 }] },
      matchMedia: () => ({ matches: false }),
    } as unknown as Window;
    expect(foldOf(table)).toBe('stacked');
    const media = { innerWidth: 900, matchMedia: (q: string) => ({ matches: q.includes('horizontal-viewport-segments') }) } as unknown as Window;
    expect(foldOf(media)).toBe('side');
  });
});
