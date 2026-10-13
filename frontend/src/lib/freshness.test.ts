import { describe, expect, it } from 'vitest';
import { isStale } from './freshness';

describe('freshness', () => {
  it('an old copy is replaced by the server build', () => {
    expect(isStale('b2', 'b1')).toBe(true);
    expect(isStale('b1', 'b1')).toBe(false);
  });
  it('offline, empty answers and dev builds never reload', () => {
    expect(isStale('', 'b1')).toBe(false);
    expect(isStale(null, 'b1')).toBe(false);
    expect(isStale('b2', 'dev')).toBe(false);
  });
});
