import { beforeEach, expect, it, vi } from 'vitest';

const calls = vi.hoisted(() => [] as Array<{ cb: Record<string, (...a: unknown[]) => void>; language: string; started: number; stopped: number }>);

vi.mock('./liveVoice', () => ({
  VoiceCall: class {
    started = 0;
    stopped = 0;
    constructor(
      public cb: Record<string, (...a: unknown[]) => void>,
      public language: string,
    ) {
      calls.push(this);
    }
    start() {
      this.started++;
      return Promise.resolve();
    }
    stop() {
      this.stopped++;
    }
    setMuted() {}
    resumeAudio() {}
    sendNote() {}
  },
}));

const store = vi.hoisted(() => {
  const data = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  });
  return data;
});

import { resetLiveForTests, useLive, voiceLanguage } from './liveSession';
import { useAppStore } from './store';

beforeEach(() => {
  resetLiveForTests();
  calls.length = 0;
  store.clear();
  useLive.setState({ enabled: true, status: 'waiting', muted: false, heard: '', said: '', error: '' });
});

it('speaks Spanish unless the owner chose another language', () => {
  expect(voiceLanguage()).toBe('es');
  store.set('sergio.lang', 'en');
  expect(voiceLanguage()).toBe('en');
});

it('starts once on the first click and writes each spoken exchange into the chat', () => {
  useLive.getState().ensure();
  useLive.getState().ensure();
  expect(calls).toHaveLength(1);
  expect(calls[0].language).toBe('es');
  calls[0].cb.onState('listening');
  expect(useLive.getState().status).toBe('listening');
  calls[0].cb.onTurn('¿Cuánto es doce por doce?', 'Ciento cuarenta y cuatro, señor.');
  const msgs = useAppStore.getState().messages;
  expect(msgs.slice(-2).map((m) => [m.role, m.content, m.voice])).toEqual([
    ['user', '¿Cuánto es doce por doce?', true],
    ['assistant', 'Ciento cuarenta y cuatro, señor.', true],
  ]);
});

it('reconnects by itself after a drop, but waits for a click when the microphone is refused', () => {
  vi.useFakeTimers();
  useLive.getState().ensure();
  calls[0].cb.onState('error');
  expect(useLive.getState().status).toBe('reconnecting');
  vi.advanceTimersByTime(1100);
  expect(calls).toHaveLength(2);
  calls[1].cb.onError('Necesito permiso para el micrófono.');
  calls[1].cb.onState('error');
  expect(useLive.getState().status).toBe('blocked');
  vi.advanceTimersByTime(60000);
  expect(calls).toHaveLength(2);
  useLive.getState().ensure();
  expect(calls).toHaveLength(3);
  vi.useRealTimers();
});

it('switching it off stops the session and remembers the choice', () => {
  useLive.getState().ensure();
  useLive.getState().setEnabled(false);
  expect(calls[0].stopped).toBe(1);
  expect(store.get('sergio.live')).toBe('off');
  useLive.getState().ensure();
  expect(calls).toHaveLength(1);
});
