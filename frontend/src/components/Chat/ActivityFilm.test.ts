import { describe, expect, it } from 'vitest';
import { mergeFilm, type Film } from './ActivityFilm';

const frame = (n: number) => ({ n, at: n, caption: `paso ${n}`, jpeg_b64: '' });

describe('mergeFilm', () => {
  it('adds only new pictures and starts over with a new task', () => {
    const a: Film = { task: 1, state: 'working', goal: 'Amazon', result: '', frames: [frame(1), frame(2)] };
    const b: Film = { ...a, frames: [frame(2), frame(3)] };
    expect(mergeFilm(a, b).frames.map((f) => f.n)).toEqual([1, 2, 3]);
    const other: Film = { ...a, task: 2, frames: [frame(1)] };
    expect(mergeFilm(a, other).frames.map((f) => f.n)).toEqual([1]);
    expect(mergeFilm(null, a)).toBe(a);
  });
});
