// A short moment with sound for three things people should feel happened:
// a new plan, a model change and a new connector (owner, 26 Oct 2026: «una
// animación con sonido para cuando subes de plan, otra cuando cambias de
// modelo, y otra cuando agregas un conector MCP donde aparecerá el logo»).
//
// The sounds are synthesised here (no audio files, nothing downloaded): a few
// soft notes, quieter than a notification. They respect «Sonidos» in
// Configuración; the animation respects reduced motion and light mode
// (lib/perf.ts) — then it is a plain fade.

import { useAppStore } from './store';

export type CelebrationKind = 'plan' | 'model' | 'connector';

export interface Celebration {
  kind: CelebrationKind;
  title: string;
  detail?: string;
  /** For a connector: its name and id, so the layer can draw its logo. */
  brand?: { name: string; id?: string };
}

export interface Note {
  freq: number;
  at: number; // seconds after the start
  dur: number;
  type: OscillatorType;
  gain: number;
}

const C5 = 523.25, E5 = 659.25, G5 = 783.99, A5 = 880, B5 = 987.77, C6 = 1046.5, E6 = 1318.51;

/** The notes of each moment: rising, short, never a fanfare. */
export function chimeNotes(kind: CelebrationKind): Note[] {
  if (kind === 'plan') {
    // An arpeggio up an octave, the last note held: «something opened up».
    return [C5, E5, G5, C6].map((freq, i) => ({ freq, at: i * 0.09, dur: i === 3 ? 0.9 : 0.35, type: 'triangle', gain: 0.07 }));
  }
  if (kind === 'connector') {
    // A soft click (it snapped in), then two bright notes.
    return [
      { freq: 2200, at: 0, dur: 0.03, type: 'square', gain: 0.025 },
      { freq: A5, at: 0.06, dur: 0.3, type: 'sine', gain: 0.08 },
      { freq: E6, at: 0.16, dur: 0.55, type: 'sine', gain: 0.06 },
    ];
  }
  // Model: two notes a fifth apart, like a gear shifting up.
  return [
    { freq: E5, at: 0, dur: 0.28, type: 'sine', gain: 0.08 },
    { freq: B5, at: 0.12, dur: 0.6, type: 'sine', gain: 0.07 },
  ];
}

let audio: AudioContext | null = null;

export function playChime(kind: CelebrationKind): void {
  if (typeof window === 'undefined' || document.hidden) return;
  if (!useAppStore.getState().settings.soundEffects) return;
  const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return;
  try {
    audio = audio ?? new Ctx();
    if (audio.state === 'suspended') void audio.resume();
    const now = audio.currentTime + 0.02;
    for (const n of chimeNotes(kind)) {
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.type = n.type;
      osc.frequency.value = n.freq;
      // A quick attack and a soft exponential release: no clicks.
      gain.gain.setValueAtTime(0.0001, now + n.at);
      gain.gain.exponentialRampToValueAtTime(n.gain, now + n.at + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + n.at + n.dur);
      osc.connect(gain).connect(audio.destination);
      osc.start(now + n.at);
      osc.stop(now + n.at + n.dur + 0.05);
    }
  } catch {
    /* audio blocked by the browser: the animation still shows */
  }
}

export const CELEBRATE_EVENT = 'sergio:celebrate';

/** Show the moment and play its sound. */
export function celebrate(c: Celebration): void {
  if (typeof window === 'undefined') return;
  playChime(c.kind);
  window.dispatchEvent(new CustomEvent<Celebration>(CELEBRATE_EVENT, { detail: c }));
}
