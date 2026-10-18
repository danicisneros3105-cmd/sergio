import { useCallback, useEffect, useRef, useState } from 'react';
import { Minus, Pin, Plus, StickyNote as StickyIcon, Trash2, X } from 'lucide-react';
import { apiFetch } from '../../lib/api';

export interface StickyNoteItem {
  id: string;
  title: string;
  content: string;
  color: 'yellow' | 'rose' | 'mint' | 'sky' | 'kraft';
  x: number;
  y: number;
  pinned: boolean;
  minimized: boolean;
}

const PAPER_THEMES: Record<
  StickyNoteItem['color'],
  { bg: string; fold: string; border: string; ink: string; accent: string; label: string }
> = {
  yellow: {
    bg: 'linear-gradient(165deg, #FFF8B8 0%, #FDF092 65%, #F7E472 100%)',
    fold: 'linear-gradient(135deg, transparent 50%, #DFC952 50%)',
    border: '#E5D36B',
    ink: '#2A2512',
    accent: '#9E8214',
    label: 'Canario',
  },
  rose: {
    bg: 'linear-gradient(165deg, #FFE6EA 0%, #FAD0D8 65%, #F3BFC9 100%)',
    fold: 'linear-gradient(135deg, transparent 50%, #DDA0AE 50%)',
    border: '#E8B3BE',
    ink: '#33181E',
    accent: '#A64B5D',
    label: 'Rosa',
  },
  mint: {
    bg: 'linear-gradient(165deg, #E3F9EC 0%, #C9F0DA 65%, #B6E6CB 100%)',
    fold: 'linear-gradient(135deg, transparent 50%, #8FC9A9 50%)',
    border: '#A7DEC0',
    ink: '#142E20',
    accent: '#2E6F40',
    label: 'Menta',
  },
  sky: {
    bg: 'linear-gradient(165deg, #E6F3FF 0%, #CCE4FA 65%, #B8D8F5 100%)',
    fold: 'linear-gradient(135deg, transparent 50%, #8EB8DF 50%)',
    border: '#A9CEEE',
    ink: '#142536',
    accent: '#2B5B84',
    label: 'Cielo',
  },
  kraft: {
    bg: 'linear-gradient(165deg, #F5EBDD 0%, #EADAC3 65%, #DFCBB0 100%)',
    fold: 'linear-gradient(135deg, transparent 50%, #C4AC8D 50%)',
    border: '#D3BEA0',
    ink: '#2A2118',
    accent: '#8C6239',
    label: 'Kraft',
  },
};

export function StickyNotesLayer() {
  const [notes, setNotes] = useState<StickyNoteItem[]>([]);
  const [visible, setVisible] = useState<boolean>(() => {
    try {
      return localStorage.getItem('sergio-stickies-open') === '1';
    } catch {
      return false;
    }
  });
  const dragRef = useRef<{
    id: string;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
    moved: boolean;
    title: HTMLInputElement | null;
  } | null>(null);

  const loadNotes = useCallback(async () => {
    try {
      const res = await apiFetch('/v1/desktop/sticky-notes');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.notes)) setNotes(data.notes);
      }
    } catch {
      // Offline fallback
    }
  }, []);

  useEffect(() => {
    void loadNotes();
    const onRefresh = () => {
      setVisible(true);
      try {
        localStorage.setItem('sergio-stickies-open', '1');
      } catch {}
      void loadNotes();
    };
    const onToggle = () => {
      setVisible((v) => {
        const next = !v;
        try {
          localStorage.setItem('sergio-stickies-open', next ? '1' : '0');
        } catch {}
        return next;
      });
    };
    window.addEventListener('sergio:sticky-notes', onRefresh);
    window.addEventListener('sergio:sticky-notes-toggle', onToggle);
    return () => {
      window.removeEventListener('sergio:sticky-notes', onRefresh);
      window.removeEventListener('sergio:sticky-notes-toggle', onToggle);
    };
  }, [loadNotes]);

  const saveNote = async (note: StickyNoteItem) => {
    setNotes((prev) => prev.map((n) => (n.id === note.id ? note : n)));
    try {
      await apiFetch('/v1/desktop/sticky-notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(note),
      });
    } catch {}
  };

  const addNote = async () => {
    const colors: StickyNoteItem['color'][] = ['yellow', 'rose', 'mint', 'sky', 'kraft'];
    const color = colors[notes.length % colors.length];
    const offset = (notes.length % 5) * 28;
    const fresh: StickyNoteItem = {
      id: `note-${Date.now().toString(36)}`,
      title: 'Nota rápida',
      content: '',
      color,
      x: Math.min(window.innerWidth - 280, 120 + offset),
      y: Math.min(window.innerHeight - 260, 90 + offset),
      pinned: true,
      minimized: false,
    };
    setVisible(true);
    setNotes((prev) => [...prev, fresh]);
    await saveNote(fresh);
  };

  const removeNote = async (id: string) => {
    setNotes((prev) => prev.filter((n) => n.id !== id));
    try {
      await apiFetch(`/v1/desktop/sticky-notes/${encodeURIComponent(id)}`, { method: 'DELETE' });
    } catch {}
  };

  const notesRef = useRef(notes);
  notesRef.current = notes;

  const startDrag = (e: React.PointerEvent, note: StickyNoteItem) => {
    const el = e.target as HTMLElement;
    // Buttons and the colour dots keep their own click; everything else on the header moves the note.
    if (el.closest('button')) return;
    if (e.button !== 0 && e.pointerType === 'mouse') return;
    const header = e.currentTarget as HTMLElement;
    header.setPointerCapture(e.pointerId);
    const title = el instanceof HTMLInputElement ? el : null;
    dragRef.current = { id: note.id, startX: e.clientX, startY: e.clientY, origX: note.x, origY: note.y, moved: false, title };
    e.preventDefault();
  };
  const moveDrag = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    if (!drag.moved && Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 4) return;
    drag.moved = true;
    const nx = Math.max(8, Math.min(window.innerWidth - 120, drag.origX + (e.clientX - drag.startX)));
    const ny = Math.max(8, Math.min(window.innerHeight - 48, drag.origY + (e.clientY - drag.startY)));
    setNotes((prev) => prev.map((n) => (n.id === drag.id ? { ...n, x: nx, y: ny } : n)));
  };
  const endDrag = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // already released
    }
    // A click (no movement) on the title still lets you edit it.
    if (!drag.moved) {
      drag.title?.focus();
      return;
    }
    const found = notesRef.current.find((n) => n.id === drag.id);
    if (found) void saveNote(found);
  };

  // A window resize must not strand a note off screen.
  useEffect(() => {
    const keepInside = () =>
      setNotes((prev) =>
        prev.map((n) => ({
          ...n,
          x: Math.max(8, Math.min(window.innerWidth - 120, n.x)),
          y: Math.max(8, Math.min(window.innerHeight - 48, n.y)),
        })),
      );
    window.addEventListener('resize', keepInside);
    return () => window.removeEventListener('resize', keepInside);
  }, []);

  if (!visible) return null;

  return (
    <div
      aria-label="Notas adhesivas de Sergio"
      style={{
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 65,
      }}
    >
      {/* Floating mini dock for Post-its */}
      <div
        style={{
          position: 'fixed',
          top: 14,
          right: 64,
          pointerEvents: 'auto',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 10px',
          borderRadius: 999,
          background: 'var(--color-surface, #fff)',
          border: '1px solid var(--color-border, #e5e5e5)',
          boxShadow: '0 6px 20px rgba(20, 20, 19, 0.08)',
          fontSize: 12,
          fontWeight: 600,
          color: 'var(--color-text, #111)',
        }}
      >
        <StickyIcon size={14} />
        <span>Post-its ({notes.length})</span>
        <button
          type="button"
          onClick={addNote}
          title="Nueva nota adhesiva"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 3,
            padding: '2px 8px',
            borderRadius: 999,
            background: 'var(--color-text, #111)',
            color: 'var(--color-bg, #fff)',
            border: 'none',
            cursor: 'pointer',
            fontSize: 11.5,
          }}
        >
          <Plus size={12} /> Nueva
        </button>
        <button
          type="button"
          onClick={() => {
            setVisible(false);
            try {
              localStorage.setItem('sergio-stickies-open', '0');
            } catch {}
          }}
          title="Ocultar notas adhesivas"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-tertiary, #777)',
            cursor: 'pointer',
            padding: 2,
          }}
        >
          <X size={14} />
        </button>
      </div>

      {notes.map((note) => {
        const theme = PAPER_THEMES[note.color] || PAPER_THEMES.yellow;
        return (
          <article
            key={note.id}
            style={{
              position: 'fixed',
              left: note.x,
              top: note.y,
              width: note.minimized ? 210 : 255,
              minHeight: note.minimized ? 44 : 215,
              pointerEvents: 'auto',
              background: theme.bg,
              border: `1px solid ${theme.border}`,
              borderRadius: '4px 4px 18px 4px',
              boxShadow:
                '0 14px 28px rgba(20, 20, 19, 0.14), 0 3px 6px rgba(20, 20, 19, 0.08), inset 0 1px 0 rgba(255,255,255,0.65)',
              color: theme.ink,
              display: 'flex',
              flexDirection: 'column',
              transform: 'rotate(-0.6deg)',
              transition: 'box-shadow 0.15s ease',
              overflow: 'hidden',
            }}
          >
            {/* Top adhesive strip (draggable) */}
            <header
              onPointerDown={(e) => startDrag(e, note)}
              onPointerMove={moveDrag}
              onPointerUp={endDrag}
              onPointerCancel={endDrag}
              title="Arrastre para mover la nota"
              style={{
                cursor: 'grab',
                touchAction: 'none',
                padding: '7px 10px 6px',
                background: 'rgba(255, 255, 255, 0.34)',
                borderBottom: '1px dashed rgba(0,0,0,0.08)',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                userSelect: 'none',
              }}
            >
              <Pin size={12} style={{ color: theme.accent, flexShrink: 0 }} />
              <input
                value={note.title}
                onChange={(e) => setNotes((prev) => prev.map((n) => (n.id === note.id ? { ...n, title: e.target.value } : n)))}
                onBlur={() => void saveNote(note)}
                aria-label="Título de la nota"
                style={{
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  fontWeight: 700,
                  fontSize: 12.5,
                  color: theme.ink,
                  width: '100%',
                  fontFamily: "'Segoe Print', 'Bradley Hand', 'Caveat', cursive, sans-serif",
                }}
              />
              {/* Color dots */}
              <div style={{ display: 'flex', gap: 3 }}>
                {(['yellow', 'rose', 'mint', 'sky', 'kraft'] as const).map((c) => (
                  <button
                    key={c}
                    type="button"
                    aria-label={`Color ${PAPER_THEMES[c].label}`}
                    onClick={() => void saveNote({ ...note, color: c })}
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      border: note.color === c ? `1.5px solid ${theme.ink}` : '1px solid rgba(0,0,0,0.2)',
                      background:
                        c === 'yellow'
                          ? '#F7E472'
                          : c === 'rose'
                            ? '#F3BFC9'
                            : c === 'mint'
                              ? '#B6E6CB'
                              : c === 'sky'
                                ? '#B8D8F5'
                                : '#DFCBB0',
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  />
                ))}
              </div>
              <button
                type="button"
                aria-label="Minimizar nota"
                onClick={() => void saveNote({ ...note, minimized: !note.minimized })}
                style={{ background: 'transparent', border: 'none', color: theme.ink, cursor: 'pointer', padding: 2 }}
              >
                <Minus size={12} />
              </button>
              <button
                type="button"
                aria-label="Borrar nota"
                onClick={() => void removeNote(note.id)}
                style={{ background: 'transparent', border: 'none', color: theme.ink, cursor: 'pointer', padding: 2 }}
              >
                <Trash2 size={12} />
              </button>
            </header>

            {!note.minimized && (
              <textarea
                value={note.content}
                onChange={(e) =>
                  setNotes((prev) => prev.map((n) => (n.id === note.id ? { ...n, content: e.target.value } : n)))
                }
                onBlur={() => void saveNote(note)}
                placeholder="Escribe una nota rápida…"
                style={{
                  flex: 1,
                  width: '100%',
                  padding: '10px 12px 18px',
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  resize: 'none',
                  color: theme.ink,
                  fontSize: 14.5,
                  lineHeight: 1.45,
                  fontFamily: "'Segoe Print', 'Bradley Hand', 'Caveat', 'Comic Sans MS', cursive, sans-serif",
                }}
              />
            )}

            {/* Realistic dog-ear folded bottom-right corner */}
            {!note.minimized && (
              <span
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  right: 0,
                  bottom: 0,
                  width: 22,
                  height: 22,
                  background: theme.fold,
                  boxShadow: '-2px -2px 5px rgba(0,0,0,0.08)',
                  borderTopLeftRadius: 6,
                }}
              />
            )}
          </article>
        );
      })}
    </div>
  );
}
