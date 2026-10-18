import { describe, expect, it } from 'vitest';
import { fmt } from './salud';

describe('fmt', () => {
  it('writes values the way the owner reads them', () => {
    expect(fmt(null, 'kg')).toBe('—');
    expect(fmt(7.25, 'h', 1)).toBe('7,3 h');
    expect(fmt(97, '%')).toBe('97%');
    expect(fmt(4, '/5')).toBe('4/5');
    expect(fmt(58, 'lpm')).toBe('58 lpm');
  });
});
