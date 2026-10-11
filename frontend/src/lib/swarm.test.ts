import { describe, expect, it } from 'vitest';
import { checkIssues, elapsed, hasTables, host, progress } from './swarm';

const counts = (done: number, running: number, queued: number) => ({ done, running, queued, failed: 0, cancelled: 0 });
const subs = (n: number) => Array.from({ length: n }) as never[];

describe('swarm progress', () => {
  it('moves from plan to agents to supervisor', () => {
    expect(progress({ status: 'planning', counts: counts(0, 0, 0), subtasks: [] })).toBeLessThan(0.1);
    const half = progress({ status: 'running', counts: counts(5, 3, 2), subtasks: subs(10) });
    expect(half).toBeGreaterThan(0.4);
    expect(half).toBeLessThan(0.6);
    expect(progress({ status: 'synthesizing', counts: counts(10, 0, 0), subtasks: subs(10) })).toBe(0.92);
    expect(progress({ status: 'done', counts: counts(10, 0, 0), subtasks: subs(10) })).toBe(1);
  });

  it('formats time and hosts', () => {
    expect(elapsed(42)).toBe('42 s');
    expect(elapsed(125)).toBe('2 min 05 s');
    expect(host('https://www.example.com/a?b')).toBe('example.com');
    expect(host('no-url')).toBe('no-url');
  });

  it('knows the scout and the code check, finds tables and counts problems', () => {
    expect(progress({ status: 'scouting', counts: counts(0, 0, 0), subtasks: [] })).toBeLessThan(0.05);
    expect(progress({ status: 'checking', counts: counts(10, 0, 0), subtasks: subs(10) })).toBe(0.97);
    expect(hasTables('Hola\n\n| A | B |\n|---|---|\n| 1 | 2 |')).toBe(true);
    expect(hasTables('Sin | tablas')).toBe(false);
    expect(checkIssues({})).toBe(0);
    expect(
      checkIssues({
        links: 2,
        links_unverified: ['https://x.test'],
        figures: 3,
        figures_unbacked: ['990', '12,5'],
        documents: 0,
        documents_unread: [],
        documents_unmentioned: [],
        ok: false,
      }),
    ).toBe(3);
  });
});
