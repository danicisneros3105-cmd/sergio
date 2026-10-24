// Split screen: two parts of Sergio side by side (Chat and Nodes, Salud and
// the Workspace…). The second one lives in a pane of its own (the same app in
// «pane» mode, without the sidebar or the voice), so each keeps its scroll
// and state. On a foldable with two screens the split sits on the hinge.

import { create } from 'zustand';

const KEY = 'sergio-split';

export const SPLIT_PAGES = [
  { path: '/chat', label: 'Chat' },
  { path: '/nodes', label: 'Nodes' },
  { path: '/salud', label: 'Salud' },
  { path: '/workspace', label: 'Workspace' },
  { path: '/cowork', label: 'Cowork' },
  { path: '/uso', label: 'Uso' },
] as const;

export type Fold = 'none' | 'side' | 'stacked';

interface SplitState {
  open: boolean;
  path: string;
  /** Share of the width (or height when stacked) for the first pane, 0.25–0.75. */
  ratio: number;
  /** 'opening' and 'closing' run the Duo fold; 'still' otherwise. */
  phase: 'still' | 'opening' | 'closing';
  show: (path?: string) => void;
  hide: () => void;
  toggle: (path?: string) => void;
  setPath: (path: string) => void;
  setRatio: (ratio: number) => void;
  settle: () => void;
}

interface Saved {
  open?: boolean;
  path?: string;
  ratio?: number;
}

function load(): Saved {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}') as Saved;
  } catch {
    return {};
  }
}

function save(s: Saved): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    // a per-viewer convenience only
  }
}

export const clampRatio = (r: number) => Math.min(0.75, Math.max(0.25, Number.isFinite(r) ? r : 0.5));

/** A path the pane may show: one of Sergio's own pages, never another site. */
export function safePath(path: string | null | undefined): string {
  if (!path || !path.startsWith('/') || path.startsWith('//')) return '/chat';
  return path;
}

/** The pane's address: the same app, in pane mode. */
export function paneUrl(path: string): string {
  const p = safePath(path);
  return `${p}${p.includes('?') ? '&' : '?'}pane=1`;
}

/** True inside the second pane. */
export function inPane(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return new URLSearchParams(window.location.search).get('pane') === '1' && window.parent !== window;
  } catch {
    return false;
  }
}

const saved = load();
const reduced = () =>
  typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export const useSplit = create<SplitState>((set, get) => ({
  open: !!saved.open,
  path: safePath(saved.path),
  ratio: clampRatio(saved.ratio ?? 0.5),
  phase: 'still',
  show: (path) => {
    const next = safePath(path ?? get().path);
    set({ open: true, path: next, phase: reduced() ? 'still' : 'opening' });
    save({ open: true, path: next, ratio: get().ratio });
  },
  hide: () => {
    if (!get().open) return;
    if (reduced()) {
      set({ open: false, phase: 'still' });
    } else {
      set({ phase: 'closing' }); // SplitView calls settle() when the fold ends
    }
    save({ open: false, path: get().path, ratio: get().ratio });
  },
  toggle: (path) => (get().open && get().phase !== 'closing' ? get().hide() : get().show(path)),
  setPath: (path) => {
    const next = safePath(path);
    set({ path: next });
    save({ open: get().open, path: next, ratio: get().ratio });
  },
  setRatio: (ratio) => {
    const next = clampRatio(ratio);
    set({ ratio: next });
    save({ open: get().open, path: get().path, ratio: next });
  },
  settle: () => set((s) => (s.phase === 'closing' ? { open: false, phase: 'still' } : { phase: 'still' })),
}));

interface Segment {
  width: number;
  height: number;
  left?: number;
  top?: number;
}

/**
 * The device's screens: 'side' when two sit left and right of a hinge (a
 * book-style foldable, a dual-screen phone), 'stacked' when one is above the
 * other (half-folded on a table), 'none' on a single screen. Uses the Viewport
 * Segments API where the browser has it (SplitView asks again on every
 * resize and Device Posture change).
 */
export function foldOf(win: Window & { viewport?: { segments?: Segment[] } } = window): Fold {
  try {
    const segments = win.viewport?.segments;
    if (segments && segments.length === 2) {
      const [a, b] = segments;
      if (a.left !== undefined && b.left !== undefined && a.left !== b.left) return 'side';
      if (a.top !== undefined && b.top !== undefined && a.top !== b.top) return 'stacked';
      return a.width < win.innerWidth ? 'side' : 'stacked';
    }
    if (win.matchMedia?.('(horizontal-viewport-segments: 2)').matches) return 'side';
    if (win.matchMedia?.('(vertical-viewport-segments: 2)').matches) return 'stacked';
  } catch {
    // an old browser: one screen
  }
  return 'none';
}
