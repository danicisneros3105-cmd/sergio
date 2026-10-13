import { describe, expect, it } from 'vitest';
import { bucket, castOf, lookKey, webglAvailable } from './dots3d';

describe('dots3d', () => {
  it('older shapes are drawn as one of the cast', () => {
    expect(castOf('rhino')).toBe('rhino');
    expect(castOf('frog')).toBe('dalmatian');
    expect(castOf('heart')).toBe('glove');
    expect(castOf('bean')).toBe('rhino');
    expect(castOf('planet')).toBe('orb');
    expect(castOf('whatever')).toBe('orb');
  });
  it('sizes share a few image buckets', () => {
    expect(bucket(30)).toBe(64);
    expect(bucket(100)).toBe(128);
    expect(bucket(300)).toBe(512);
    expect(bucket(2000)).toBe(768);
    const look = { shape: 'frog' as const, color: '#AABBCC', accessory: 'none' as const, eyes: 'dots' as const };
    expect(lookKey(look, 40)).toBe('dalmatian|#aabbcc|none|dots|64');
  });
  it('without WebGL (tests, old browsers) the flat drawing is used', () => {
    expect(webglAvailable()).toBe(false);
  });
});
