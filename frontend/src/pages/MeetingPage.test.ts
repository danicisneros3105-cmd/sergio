import { describe, expect, it } from 'vitest';
import { faceDown } from './MeetingPage';

describe('meeting recorder', () => {
  it('knows when the phone lies face down', () => {
    expect(faceDown(178, 3)).toBe(true);
    expect(faceDown(-175, -10)).toBe(true);
    expect(faceDown(10, 2)).toBe(false); // flat, screen up
    expect(faceDown(170, 60)).toBe(false); // on its side
    expect(faceDown(null, null)).toBe(false);
  });
});
