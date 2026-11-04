// @vitest-environment jsdom
// Browser lifecycle test: Node 24's native navigator.locks otherwise changes
// the baseline; lock-specific cases below explicitly install FakeLocks.
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

import { resetLiveForTests, setVoiceLocksForTests, useLive, voiceLanguage } from './liveSession';
import { useAppStore } from './store';

beforeEach(() => {
  resetLiveForTests();
  calls.length = 0;
  store.clear();
  useLive.setState({ enabled: true, status: 'waiting', muted: false, heard: '', said: '', error: '', elsewhere: false });
});

it('speaks Spanish unless the owner chose another language', () => {
  expect(voiceLanguage()).toBe('es');
  store.set('sergio.lang', 'en');
  expect(voiceLanguage()).toBe('en');
});

// Since 24 Oct. 2026 (owner: text, voice and Quick Chat apart) spoken turns go
// to the voice chat, never into the written chat on screen.
it('starts once on the first click and writes each spoken exchange into the voice chat', () => {
  useLive.getState().ensure();
  useLive.getState().ensure();
  expect(calls).toHaveLength(1);
  expect(calls[0].language).toBe('es');
  calls[0].cb.onState('listening');
  expect(useLive.getState().status).toBe('listening');
  const written = useAppStore.getState().createConversation('m');
  calls[0].cb.onTurn('¿Cuánto es doce por doce?', 'Ciento cuarenta y cuatro, señor.');
  const app = useAppStore.getState();
  const voice = app.conversations.find((c) => c.kind === 'voz');
  expect(voice?.messages.slice(-2).map((m) => [m.role, m.content, m.voice])).toEqual([
    ['user', '¿Cuánto es doce por doce?', true],
    ['assistant', 'Ciento cuarenta y cuatro, señor.', true],
  ]);
  expect(app.activeId).toBe(written);
  expect(app.messages).toEqual([]);
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

/** Web Locks as the browser does it: one holder, a line, «steal». */
class FakeLocks {
  holder: { reject: (e: unknown) => void } | null = null;
  line: Array<{ grant: () => void; reject: (e: unknown) => void }> = [];

  request(_name: string, options: { steal?: boolean; signal?: AbortSignal }, cb: () => Promise<void>) {
    return new Promise<void>((resolve, reject) => {
      const grant = () => {
        const entry = { reject };
        this.holder = entry;
        void cb().then(() => {
          if (this.holder === entry) {
            this.holder = null;
            this.line.shift()?.grant();
          }
          resolve();
        });
      };
      if (options.steal) {
        const old = this.holder;
        this.holder = null;
        old?.reject(new DOMException('stolen', 'AbortError'));
        grant();
      } else if (!this.holder) {
        grant();
      } else {
        const waiting = { grant, reject };
        this.line.push(waiting);
        options.signal?.addEventListener('abort', () => {
          this.line = this.line.filter((w) => w !== waiting);
          reject(new DOMException('aborted', 'AbortError'));
        });
      }
    });
  }
}

const tick = () => new Promise((r) => setTimeout(r, 0));

it('one voice per computer: waits while another window has it, takes over when that one closes', async () => {
  const locks = new FakeLocks();
  setVoiceLocksForTests(locks as unknown as LockManager);
  let closeOther = () => {};
  void locks.request('sergio-voz', {}, () => new Promise<void>((r) => (closeOther = r)));
  useLive.getState().ensure();
  await new Promise((r) => setTimeout(r, 350));
  expect(calls).toHaveLength(0); // never two conversations at once
  expect(useLive.getState().elsewhere).toBe(true);
  closeOther(); // the other window was closed
  await tick();
  expect(calls).toHaveLength(1);
  expect(useLive.getState().elsewhere).toBe(false);
});

it('a click in another window moves the voice there, and a click here brings it back', async () => {
  const locks = new FakeLocks();
  setVoiceLocksForTests(locks as unknown as LockManager);
  useLive.getState().ensure();
  await tick();
  expect(calls).toHaveLength(1);
  // the owner clicks the orb in the Nodes window
  let closeOther = () => {};
  void locks.request('sergio-voz', { steal: true }, () => new Promise<void>((r) => (closeOther = r))).catch(() => {});
  await tick();
  expect(calls[0].stopped).toBe(1);
  expect(useLive.getState().elsewhere).toBe(true);
  expect(useLive.getState().status).toBe('waiting');
  useLive.getState().takeBack(); // and back here
  await tick();
  expect(calls).toHaveLength(2);
  expect(useLive.getState().elsewhere).toBe(false);
  closeOther();
});
