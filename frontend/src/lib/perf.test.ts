import { describe, expect, it } from 'vitest';
import { freezeMeter, weakDevice } from './perf';

describe('light mode for slow devices', () => {
  it('starts light on a device short of memory or cores, or saving data', () => {
    expect(weakDevice({ deviceMemory: 2 })).toBe(true);
    expect(weakDevice({ hardwareConcurrency: 2 })).toBe(true);
    expect(weakDevice({ connection: { saveData: true } })).toBe(true);
    expect(weakDevice({ deviceMemory: 4, hardwareConcurrency: 8 })).toBe(true);
    expect(weakDevice({ hardwareConcurrency: 4 })).toBe(true);
    expect(weakDevice({ deviceMemory: 8, hardwareConcurrency: 8 })).toBe(false);
    expect(weakDevice({})).toBe(false);
  });

  it('goes light only after repeated freezes close together', () => {
    const tooMany = freezeMeter(3, 1000);
    expect(tooMany(0)).toBe(false);
    expect(tooMany(2000)).toBe(false); // the first one is forgotten
    expect(tooMany(2300)).toBe(false);
    expect(tooMany(2600)).toBe(true);
  });
});
