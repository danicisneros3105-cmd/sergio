import { describe, expect, it } from 'vitest';
import { downsample, liveUrl, pcmToFloat, rms } from './liveVoice';

describe('voice mode audio', () => {
  it('connects to the same live call as the desktop app', () => {
    expect(liveUrl('', 'https://sergio.local:8000')).toBe('wss://sergio.local:8000/v1/live');
    expect(liveUrl('http://127.0.0.1:8000', 'https://x')).toBe('ws://127.0.0.1:8000/v1/live');
  });

  it('turns 48 kHz float audio into 16 kHz 16-bit PCM', () => {
    const input = new Float32Array(4800).fill(0.5);
    const out = downsample(input, 48000);
    expect(out.length).toBe(1600);
    expect(out[0]).toBe(Math.floor(0.5 * 0x7fff));
    expect(downsample(new Float32Array([2, -2, 2]), 16000)[1]).toBe(-0x8000); // clipped, not wrapped
  });

  it('reads 24 kHz PCM back as floats and measures loudness', () => {
    const bytes = new ArrayBuffer(5); // an odd byte is dropped
    const view = new DataView(bytes);
    view.setInt16(0, 0x4000, true);
    view.setInt16(2, -0x8000, true);
    const floats = pcmToFloat(bytes);
    expect(Array.from(floats)).toEqual([0.5, -1]);
    expect(rms(new Float32Array([0.5, -0.5]))).toBeCloseTo(0.5);
    expect(rms(new Float32Array())).toBe(0);
  });
});
