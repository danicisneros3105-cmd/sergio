// Keyboard shortcuts for the whole app, wired like the fly brain (lib/connectome.ts):
// Ctrl/⌘ K opens the palette, G then a letter jumps straight to a section, and
// Esc three times within a second is the escape reflex that stops Sergio.

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useAppStore } from '../../lib/store';
import { SHORTCUTS, escape, type Shortcut } from '../../lib/connectome';
import { ShortcutPalette } from './ShortcutPalette';

/** "g s" sequences, from the shortcut list. */
const SEQUENCES: Record<string, Shortcut> = Object.fromEntries(
  SHORTCUTS.filter((s) => s.keys?.startsWith('g ')).map((s) => [s.keys!.slice(2), s]),
);

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName);
}

export function Shortcuts() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const leader = useRef(0); // when G was pressed
  const escapes = useRef<number[]>([]);

  const run = useCallback(
    (s: Shortcut) => {
      setOpen(false);
      const r = s.run;
      if (r.kind === 'go') {
        navigate(r.to);
        return;
      }
      if (r.kind === 'chat') {
        navigate('/chat');
        window.setTimeout(() => window.dispatchEvent(new CustomEvent('sergio:prefill', { detail: r.text })), 150);
        return;
      }
      if (r.name === 'sergio:new-chat') {
        const st = useAppStore.getState();
        st.createConversation(st.selectedModel);
        navigate('/chat');
      } else if (r.name === 'sergio:model-picker') {
        useAppStore.getState().setCommandPaletteOpen(true);
      } else if (r.name === 'sergio:escape') {
        void stopAll();
      } else {
        window.dispatchEvent(new CustomEvent(r.name));
      }
    },
    [navigate],
  );

  const ask = useCallback(
    (text: string) => run({ id: 'chat', title: 'Chat', words: [], group: 'Ir a', run: { kind: 'chat', text } }),
    [run],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Ctrl/⌘ K: the palette (the model picker is one of its shortcuts).
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        e.stopImmediatePropagation();
        useAppStore.getState().setCommandPaletteOpen(false);
        setOpen((v) => !v);
        return;
      }
      // Giant fiber: Esc, Esc, Esc within a second, from anywhere.
      if (e.key === 'Escape') {
        const now = Date.now();
        escapes.current = [...escapes.current.filter((t) => now - t < 1000), now];
        if (escapes.current.length >= 3) {
          escapes.current = [];
          void stopAll();
        }
        return;
      }
      if (open || e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
      const key = e.key.toLowerCase();
      if (leader.current && Date.now() - leader.current < 1200) {
        leader.current = 0;
        const s = SEQUENCES[key];
        if (s) {
          e.preventDefault();
          run(s);
        }
        return;
      }
      if (key === 'g') {
        leader.current = Date.now();
      } else if (e.key === '?') {
        e.preventDefault();
        navigate('/atajos');
      }
    };
    // Capture: runs before the older Ctrl+K handler, which now only opens the model picker on request.
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [open, run, navigate]);

  return open ? <ShortcutPalette onRun={run} onAsk={ask} onClose={() => setOpen(false)} /> : null;
}

async function stopAll() {
  const stopped = await escape();
  if (!stopped) {
    toast('Detenido aquí. No pude avisar al servidor.');
    return;
  }
  const n = stopped.nodes + stopped.swarm + stopped.cowork;
  toast(n ? `Detenido: ${n} ${n === 1 ? 'tarea' : 'tareas'} en curso.` : 'Nada en curso. Todo quieto.');
}
