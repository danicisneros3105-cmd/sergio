// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CELEBRATE_EVENT, celebrate, chimeNotes } from './celebrate';
import { withEffort, modelName } from './modelChoice';
import { useAppStore } from './store';

describe('celebrations', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('each moment has its own short, quiet, rising sound', () => {
    for (const kind of ['plan', 'model', 'connector'] as const) {
      const notes = chimeNotes(kind);
      expect(notes.length).toBeGreaterThan(1);
      const end = Math.max(...notes.map((n) => n.at + n.dur));
      expect(end).toBeLessThan(1.5); // never a fanfare
      expect(Math.max(...notes.map((n) => n.gain))).toBeLessThanOrEqual(0.1);
      const tones = notes.filter((n) => n.freq < 2000).map((n) => n.freq);
      expect(tones).toEqual([...tones].sort((a, b) => a - b));
    }
    expect(chimeNotes('plan')).not.toEqual(chimeNotes('model'));
  });

  it('shows the moment and stays silent when sounds are off', () => {
    const made: string[] = [];
    class FakeAudio {
      state = 'running';
      currentTime = 0;
      destination = {};
      createOscillator() {
        made.push('osc');
        return { type: '', frequency: { value: 0 }, connect: (g: unknown) => g, start() {}, stop() {} };
      }
      createGain() {
        return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect: (d: unknown) => d };
      }
    }
    vi.stubGlobal('AudioContext', FakeAudio);
    const seen: unknown[] = [];
    const on = (e: Event) => seen.push((e as CustomEvent).detail);
    window.addEventListener(CELEBRATE_EVENT, on);
    useAppStore.getState().updateSettings({ soundEffects: false });
    celebrate({ kind: 'model', title: 'Gemini 3.6 Flash' });
    expect(made).toEqual([]);
    expect(seen).toHaveLength(1);
    window.removeEventListener(CELEBRATE_EVENT, on);
    useAppStore.getState().updateSettings({ soundEffects: true });
  });

  it('sends the chosen effort with the model, never twice', () => {
    expect(withEffort('gemini-3.6-flash', 'auto')).toBe('gemini-3.6-flash');
    expect(withEffort('gemini-3.6-flash', 'high')).toBe('gemini-3.6-flash@high');
    expect(withEffort('gemini-3.6-flash@low', 'high')).toBe('gemini-3.6-flash@low');
    expect(withEffort('', 'high')).toBe('');
    expect(modelName('gemini-3.1-pro-preview')).toBe('Gemini 3.1 Pro Preview');
  });
});
