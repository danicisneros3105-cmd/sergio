// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { clearCrashes, crashReport, noteCrash, readCrashes } from './crashlog';

beforeEach(() => localStorage.clear());

describe('crashlog', () => {
  it('keeps what went wrong, where and when', () => {
    noteCrash(new Error('boom'), 1000);
    const [c] = readCrashes();
    expect(c.what).toBe('boom');
    expect(c.t).toBe(1000);
    expect(crashReport()).toContain('boom');
  });

  it('ignores browser noise and repeats in a burst', () => {
    noteCrash('ResizeObserver loop limit exceeded', 1);
    noteCrash(new Error('x'), 1000);
    noteCrash(new Error('x'), 2000);
    noteCrash(new Error('x'), 9000);
    expect(readCrashes().map((c) => c.what)).toEqual(['x', 'x']);
  });

  it('keeps only the last twenty and can be cleared', () => {
    for (let i = 0; i < 30; i++) noteCrash(new Error(`e${i}`), i * 10_000);
    const list = readCrashes();
    expect(list).toHaveLength(20);
    expect(list[19].what).toBe('e29');
    clearCrashes();
    expect(crashReport()).toMatch(/Sin errores/);
  });
});
