import { describe, expect, it } from 'vitest';
import { DEFAULT_LOCK, shouldLock } from './appLock';

describe('app lock', () => {
  it('is off until the person turns it on', () => {
    expect(DEFAULT_LOCK.on).toBe(false);
    expect(shouldLock(DEFAULT_LOCK, 24 * 60 * 60_000)).toBe(false);
  });
  it('locks only after the chosen minutes without use', () => {
    expect(shouldLock({ on: true, minutes: 15 }, 14 * 60_000)).toBe(false);
    expect(shouldLock({ on: true, minutes: 15 }, 15 * 60_000)).toBe(true);
  });
  it('never locks by time when off or «only when asked»', () => {
    expect(shouldLock({ on: false, minutes: 5 }, 60 * 60_000)).toBe(false);
    expect(shouldLock({ on: true, minutes: 0 }, 60 * 60_000)).toBe(false);
  });
});
