// The shortcut palette (Ctrl/⌘ K): type a few words, Enter goes there.
// Reflexes answer at once in the browser; what the owner chose before for the
// same words is learned on the server and rises to the top; anything else is
// handed to Sergio in the chat.

import { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, MessageSquare, Search } from 'lucide-react';
import { learnedFor, rank, reinforce, type Ranked, type Shortcut } from '../../lib/connectome';
import { usePersonal, withAddress } from '../../lib/personal';
import './shortcuts.css';

const WHY: Record<Ranked['why'], string> = { reflejo: '', aprendido: 'aprendido', ambos: 'aprendido' };

export function ShortcutPalette({ onRun, onAsk, onClose }: { onRun: (s: Shortcut) => void; onAsk: (text: string) => void; onClose: () => void }) {
  const personal = usePersonal();
  const [query, setQuery] = useState('');
  const [learned, setLearned] = useState<Array<{ action: string; score: number }>>([]);
  const [at, setAt] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => input.current?.focus(), []);

  // Mushroom body: ask the server what these words led to before (debounced, cancelable).
  useEffect(() => {
    const ctrl = new AbortController();
    const t = window.setTimeout(() => {
      learnedFor(query, ctrl.signal).then(setLearned).catch(() => {});
    }, 90);
    return () => {
      window.clearTimeout(t);
      ctrl.abort();
    };
  }, [query]);

  const ranked = useMemo(() => rank(query, learned).slice(0, 9), [query, learned]);
  const ask = query.trim().length > 0;
  const total = ranked.length + (ask ? 1 : 0);

  useEffect(() => setAt(0), [query]);
  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-i="${at}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [at]);

  const pick = (i: number) => {
    if (i < ranked.length) {
      const chosen = ranked[i].shortcut;
      reinforce(query, chosen.id, 1);
      // A suggestion shown above the chosen one was a miss: a little less of it next time.
      if (i > 0 && query.trim()) reinforce(query, ranked[0].shortcut.id, -0.25);
      onRun(chosen);
    } else if (ask) {
      onAsk(query.trim());
    }
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setAt((n) => Math.min(total - 1, n + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setAt((n) => Math.max(0, n - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      pick(at);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  return (
    <div className="sc-backdrop" onMouseDown={onClose}>
      <div className="sc-palette" role="dialog" aria-label="Atajos" onMouseDown={(e) => e.stopPropagation()}>
        <label className="sc-search">
          <Search size={17} aria-hidden />
          <input
            ref={input}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKey}
            placeholder={`Adónde vamos${withAddress(personal, 'es')}`}
            aria-label="Buscar un atajo"
            aria-activedescendant={`sc-${at}`}
            role="combobox"
            aria-expanded
            aria-controls="sc-list"
          />
        </label>
        <ul className="sc-list" id="sc-list" role="listbox" ref={list}>
          {ranked.map((r, i) => (
            <li
              key={r.shortcut.id}
              id={`sc-${i}`}
              data-i={i}
              role="option"
              aria-selected={i === at}
              onMouseMove={() => setAt(i)}
              onClick={() => pick(i)}
            >
              <span className="sc-title">{r.shortcut.title}</span>
              <span className="sc-meta">
                {WHY[r.why] && <em>{WHY[r.why]}</em>}
                {r.shortcut.keys && <kbd>{r.shortcut.keys}</kbd>}
              </span>
            </li>
          ))}
          {ask && (
            <li
              id={`sc-${ranked.length}`}
              data-i={ranked.length}
              role="option"
              aria-selected={at === ranked.length}
              onMouseMove={() => setAt(ranked.length)}
              onClick={() => pick(ranked.length)}
              className="sc-ask"
            >
              <span className="sc-title">
                <MessageSquare size={14} aria-hidden /> Preguntar a Sergio: «{query.trim()}»
              </span>
              <span className="sc-meta">
                <CornerDownLeft size={13} aria-hidden />
              </span>
            </li>
          )}
        </ul>
        <footer className="sc-foot">
          <span>
            <kbd>↑</kbd> <kbd>↓</kbd> elegir
          </span>
          <span>
            <kbd>Enter</kbd> ir
          </span>
          <span>
            <kbd>G</kbd> + letra, sin abrir esto
          </span>
          <span>
            <kbd>Esc</kbd> ×3 detener todo
          </span>
        </footer>
      </div>
    </div>
  );
}
