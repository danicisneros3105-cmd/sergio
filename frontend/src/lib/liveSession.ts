// The always-on conversation. There is no "call" to start: while Sergio is
// open he listens, answers out loud, and you can talk over him, like with a
// person. One session for the whole app (it survives changing pages), it
// reconnects by itself, and every spoken exchange is written into the chat
// so voice and text are the same conversation.
//
// Browsers only allow audio after a click, so the session starts on your
// first click or key press, and the microphone needs your permission once.
// It can be paused from the orb (mute) or switched off in Ajustes.

import { create } from 'zustand';
import { useAppStore } from './store';
import { VoiceCall, type VoiceState } from './liveVoice';

export type LiveStatus = VoiceState | 'off' | 'waiting' | 'blocked' | 'reconnecting';

const PREF = 'sergio.live';
const RETRY = [1000, 2000, 4000, 8000, 15000, 30000];

function readPref(): boolean {
  try {
    return localStorage.getItem(PREF) !== 'off';
  } catch {
    return true;
  }
}

function writePref(on: boolean): void {
  try {
    localStorage.setItem(PREF, on ? 'on' : 'off');
  } catch {
    // private window: the choice lasts this session
  }
}

interface LiveStore {
  enabled: boolean;
  status: LiveStatus;
  muted: boolean;
  heard: string;
  said: string;
  error: string;
  setEnabled: (on: boolean) => void;
  toggleMute: () => void;
  /** Start (or resume) the session; called on the first click/key press. */
  ensure: () => void;
  /** Tell the voice what was said in writing, so both share one context. */
  note: (text: string) => void;
}

let call: VoiceCall | null = null;
let attempt = 0;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let level = 0;
const levelListeners = new Set<(level: number) => void>();

/** The orb listens to the level directly: no React render per audio buffer. */
export function onLiveLevel(fn: (level: number) => void): () => void {
  levelListeners.add(fn);
  fn(level);
  return () => levelListeners.delete(fn);
}

function writeTurn(heard: string, said: string): void {
  const app = useAppStore.getState();
  let id = app.activeId;
  if (!id) id = app.createConversation(app.selectedModel);
  const now = Date.now();
  if (heard) {
    app.addMessage(id, { id: `v-${now}-u`, role: 'user', content: heard, timestamp: now, voice: true });
  }
  if (said) {
    app.addMessage(id, { id: `v-${now}-a`, role: 'assistant', content: said, timestamp: now + 1, voice: true });
  }
}

export const useLive = create<LiveStore>((set, get) => {
  const scheduleRetry = () => {
    if (retryTimer || !get().enabled) return;
    const wait = RETRY[Math.min(attempt, RETRY.length - 1)];
    attempt += 1;
    set({ status: 'reconnecting' });
    retryTimer = setTimeout(() => {
      retryTimer = null;
      if (get().enabled) connect();
    }, wait);
  };

  const connect = () => {
    if (call || !get().enabled) return;
    const language = (navigator.language || 'es').slice(0, 2).toLowerCase();
    let blocked = false;
    const c = new VoiceCall(
      {
        onState: (s) => {
          if (call !== c) return;
          if (s === 'listening') attempt = 0;
          if (s === 'error' || s === 'ended') {
            call = null;
            if (blocked) set({ status: 'blocked' });
            else scheduleRetry();
            return;
          }
          set({ status: s });
        },
        onHeard: (heard) => set({ heard, said: '' }),
        onSaid: (said) => set({ said }),
        onError: (message) => {
          blocked = /micr[oó]fono/i.test(message);
          set({ error: message });
        },
        onLevel: (l) => {
          level = l;
          levelListeners.forEach((fn) => fn(l));
        },
        onTurn: (heard, said) => {
          writeTurn(heard, said);
          set({ heard: '', said: '' });
        },
      },
      language,
    );
    call = c;
    c.setMuted(get().muted);
    set({ status: 'connecting', error: '' });
    void c.start();
  };

  return {
    enabled: readPref(),
    status: readPref() ? 'waiting' : 'off',
    muted: false,
    heard: '',
    said: '',
    error: '',
    setEnabled: (on) => {
      writePref(on);
      set({ enabled: on, status: on ? 'waiting' : 'off', error: '' });
      if (!on) {
        if (retryTimer) clearTimeout(retryTimer);
        retryTimer = null;
        const c = call;
        call = null;
        c?.stop(false);
      } else {
        attempt = 0;
        connect();
      }
    },
    toggleMute: () => {
      const muted = !get().muted;
      call?.setMuted(muted);
      set({ muted });
    },
    ensure: () => {
      if (!get().enabled) return;
      if (call) {
        call.resumeAudio();
        return;
      }
      if (get().status === 'blocked') attempt = 0;
      if (!retryTimer) connect();
    },
    note: (text) => call?.sendNote(text),
  };
});

/** Test hook: drop the session between tests. */
export function resetLiveForTests(): void {
  if (retryTimer) clearTimeout(retryTimer);
  retryTimer = null;
  call?.stop(false);
  call = null;
  attempt = 0;
}
