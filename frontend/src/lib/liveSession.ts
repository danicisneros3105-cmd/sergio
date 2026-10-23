// The always-on conversation. There is no "call" to start: while Sergio is
// open he listens, answers out loud, and you can talk over him, like with a
// person. One session for the whole app (it survives changing pages), it
// reconnects by itself, and every spoken exchange is written into the chat
// so voice and text are the same conversation.
//
// Browsers only allow audio after a click, so the session starts on your
// first click or key press, and the microphone needs your permission once.
// It can be paused from the orb (mute) or switched off in Ajustes.
//
// One voice per computer: every Sergio window (chat, Nodes, a second tab)
// shares one lock (Web Locks). Only the window holding it opens the
// conversation; the others wait in line and take over by themselves when it
// closes. A click on the orb of another window moves the voice there. So no
// window ever kicks another one out of the conversation.

import { create } from 'zustand';
import { useAppStore } from './store';
import { VoiceCall, type VoiceState } from './liveVoice';

export type LiveStatus = VoiceState | 'off' | 'waiting' | 'blocked' | 'reconnecting' | 'replaced';

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

/** Sergio speaks Spanish unless the owner chose another language for him
 *  (localStorage `sergio.lang`); the browser's language is not a choice. */
export function voiceLanguage(): string {
  try {
    const chosen = (localStorage.getItem('sergio.lang') || '').trim().toLowerCase();
    if (/^[a-z]{2}$/.test(chosen)) return chosen;
  } catch {
    // private window
  }
  return 'es';
}

interface LiveStore {
  enabled: boolean;
  status: LiveStatus;
  muted: boolean;
  heard: string;
  said: string;
  error: string;
  /** Another Sergio window on this computer has the voice right now. */
  elsewhere: boolean;
  setEnabled: (on: boolean) => void;
  toggleMute: () => void;
  /** Start (or resume) the session; called on the first click/key press. */
  ensure: () => void;
  /** Take the conversation back from the other window (the owner chose to). */
  takeBack: () => void;
  /** Tell the voice what was said in writing, so both share one context. */
  note: (text: string) => void;
}

let call: VoiceCall | null = null;
let attempt = 0;

// -- one voice per computer (Web Locks) ----------------------------------------

const LOCK = 'sergio-voz';
type Locks = Pick<LockManager, 'request'>;
let lockManager: Locks | null | undefined;
let holding = false;
let heldBy = 0; // which request holds the lock now
let seq = 0;
let pending: AbortController | null = null; // a request waiting in line
let releaseLock: (() => void) | null = null;

function locks(): Locks | null {
  if (lockManager !== undefined) return lockManager;
  try {
    return typeof navigator !== 'undefined' && navigator.locks ? navigator.locks : null;
  } catch {
    return null;
  }
}

/** Test hook: a fake lock manager (null: none, like an old browser). */
export function setVoiceLocksForTests(manager: Locks | null | undefined): void {
  lockManager = manager;
  holding = false;
  heldBy = 0;
  pending = null;
  releaseLock = null;
}

/** Ask for the voice. *steal*: the owner chose this window, take it now. */
function requestVoice(steal: boolean, got: () => void, lost: () => void): void {
  const manager = locks();
  if (!manager || holding) {
    holding = true; // no Web Locks (old browser, plain http): one window anyway
    got();
    return;
  }
  if (pending && !steal) return; // already in line
  pending?.abort();
  pending = null;
  const id = ++seq;
  const line = !steal && typeof AbortController !== 'undefined' ? new AbortController() : null;
  pending = line;
  const options: LockOptions = steal ? { steal: true } : line ? { signal: line.signal } : {};
  manager
    .request(LOCK, options, () =>
      new Promise<void>((resolve) => {
        if (pending === line) pending = null;
        holding = true;
        heldBy = id;
        releaseLock = () => {
          if (heldBy === id) {
            holding = false;
            heldBy = 0;
          }
          releaseLock = null;
          resolve();
        };
        got();
      }),
    )
    .catch(() => {
      if (pending === line) pending = null;
      if (heldBy !== id) return; // left the line (replaced by a newer request)
      // Another window stole it: the owner moved the voice there.
      holding = false;
      heldBy = 0;
      releaseLock = null;
      lost();
    });
}

function giveUpVoice(): void {
  releaseLock?.();
}

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

  const gotVoice = () => {
    set({ elsewhere: false });
    if (get().enabled && get().status !== 'replaced') connect();
  };

  const lostVoice = () => {
    // The owner moved the voice to another window: stop quietly and wait in
    // line, so it comes back here by itself when that window closes.
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = null;
    const c = call;
    call = null;
    c?.stop(false);
    set({ elsewhere: true, status: get().enabled ? 'waiting' : 'off', heard: '', said: '' });
    if (get().enabled) requestVoice(false, gotVoice, lostVoice);
  };

  const connect = () => {
    if (call || !get().enabled) return;
    if (!holding) {
      requestVoice(false, gotVoice, lostVoice);
      // Still waiting a moment later: another window has it.
      setTimeout(() => {
        if (!holding && get().enabled) set({ elsewhere: true });
      }, 300);
      return;
    }
    const language = voiceLanguage();
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
          console.warn('[Sergio voz]', message);
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
        onReplaced: () => {
          if (call !== c) return;
          // Another window (the app, a tab) has the conversation now. Two open at
          // once would answer each other, so this one stays quiet until asked.
          call = null;
          if (retryTimer) clearTimeout(retryTimer);
          retryTimer = null;
          set({ status: 'replaced', heard: '', said: '' });
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
    elsewhere: false,
    setEnabled: (on) => {
      writePref(on);
      set({ enabled: on, status: on ? 'waiting' : 'off', error: '' });
      if (!on) {
        if (retryTimer) clearTimeout(retryTimer);
        retryTimer = null;
        const c = call;
        call = null;
        c?.stop(false);
        giveUpVoice();
        set({ elsewhere: false });
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
    takeBack: () => {
      if (!get().enabled || call) return;
      attempt = 0;
      if (get().status === 'replaced') set({ status: 'waiting' });
      if (holding) connect();
      else requestVoice(true, gotVoice, lostVoice);
    },
    ensure: () => {
      if (!get().enabled || get().status === 'replaced') return;
      if (get().elsewhere && !holding) return; // the other window has it
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

// Back from the background or from a dropped connection (Wi-Fi changed, the
// laptop woke up): reconnect now instead of waiting for the next retry.
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  const wake = () => {
    const live = useLive.getState();
    if (!live.enabled || live.status === 'replaced' || live.status === 'blocked') return;
    if (live.elsewhere && !holding) return;
    if (call) {
      call.resumeAudio();
      return;
    }
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = null;
    attempt = 0;
    live.ensure();
  };
  window.addEventListener('online', wake);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') wake();
  });
}

let suspensions = 0;

/** Another voice (a read-aloud reply) is playing: the microphone must not hear it and answer. */
export function suspendLive(on: boolean): void {
  suspensions = Math.max(0, suspensions + (on ? 1 : -1));
  call?.setSuspended(suspensions > 0);
}

/** Is Sergio's live voice talking right now? */
export function liveIsSpeaking(): boolean {
  return useLive.getState().status === 'speaking';
}

/** Test hook: drop the session between tests. */
export function resetLiveForTests(): void {
  if (retryTimer) clearTimeout(retryTimer);
  retryTimer = null;
  call?.stop(false);
  call = null;
  attempt = 0;
  suspensions = 0;
  setVoiceLocksForTests(undefined);
}
