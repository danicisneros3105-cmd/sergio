import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  GripVertical,
  Lock,
  MoreHorizontal,
  History as HistoryIcon,
  Share2,
  Sparkles,
  Star,
  Trash2,
  Unlock,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';
import { toast } from 'sonner';
import { useWorkspace } from '../../lib/workspace/store';
import {
  block as makeBlock,
  mentions,
  shortcut,
  slashMatches,
  toMarkdown,
  type Block,
  type BlockType,
  type Page,
} from '../../lib/workspace/model';
import { seal, unseal, WrongPassphrase } from '../../lib/workspace/crypto';
import { askAboutPage, PAGE_ACTIONS, parseLines, type PageAction } from '../../lib/workspace/ai';
import { useAppStore } from '../../lib/store';
import { TableBlock } from './TableBlock';
import { ChartBlock } from './ChartBlock';
import { PomodoroBlock } from './PomodoroBlock';
import { MediaBlock } from './MediaBlock';
import { MindMapBlock } from './MindMapBlock';
import { ShareDialog, type ShareTarget } from './ShareDialog';
import { BookmarkView, EquationView, TocView } from './ExtraBlocks';
import { HistoryDialog } from './HistoryDialog';

const TEXTUAL: BlockType[] = ['text', 'h1', 'h2', 'h3', 'todo', 'bullet', 'number', 'quote', 'callout', 'code', 'toggle', 'equation', 'bookmark'];
const PLACEHOLDER: Partial<Record<BlockType, string>> = {
  text: 'Escriba, o «/» para insertar…',
  h1: 'Título 1',
  h2: 'Título 2',
  h3: 'Título 3',
  todo: 'Tarea',
  bullet: 'Lista',
  number: 'Lista',
  quote: 'Cita',
  callout: 'Nota',
  code: 'Código',
  toggle: 'Desplegable (la primera línea es el título)',
  equation: 'Fórmula en LaTeX, p. ej. E = mc^2 o \\frac{a}{b}',
  bookmark: 'Pegue un enlace: https://…',
};

// Passphrases of the pages unlocked in this visit: memory only, never stored.
const passphrases = new Map<string, string>();

function autosize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = '0px';
  el.style.height = `${el.scrollHeight}px`;
}

export function PageEditor({ pageId }: { pageId: string }) {
  const page = useWorkspace((s) => s.pages[pageId]);
  const pages = useWorkspace((s) => s.pages);
  const update = useWorkspace((s) => s.update);
  const unlockedBlocks = useWorkspace((s) => s.unlocked[pageId]);
  const setUnlocked = useWorkspace((s) => s.setUnlocked);
  const create = useWorkspace((s) => s.create);
  const open = useWorkspace((s) => s.open);
  const archive = useWorkspace((s) => s.archive);
  const remove = useWorkspace((s) => s.remove);
  const layout = useWorkspace((s) => s.layout);
  const model = useAppStore((s) => s.selectedModel);
  const refs = useRef(new Map<string, HTMLTextAreaElement>());
  const [focusAt, setFocusAt] = useState<{ id: string; pos: number } | null>(null);
  const [slash, setSlash] = useState<{ id: string; query: string; index: number } | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const [share, setShare] = useState<ShareTarget | null>(null);
  const [lockOpen, setLockOpen] = useState(false);
  const [showVault, setShowVault] = useState(false);
  const [thinking, setThinking] = useState(false);
  const resealTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sealed = !!page?.sealed;
  const blocks = useMemo(() => (sealed ? unlockedBlocks || [] : page?.blocks || []), [sealed, unlockedBlocks, page?.blocks]);

  const setBlocks = useCallback(
    (next: Block[]) => {
      if (!page) return;
      if (page.sealed) {
        setUnlocked(page.id, next);
        if (resealTimer.current) clearTimeout(resealTimer.current);
        resealTimer.current = setTimeout(async () => {
          const pass = passphrases.get(page.id);
          if (!pass) return;
          const sealedNow = await seal(next, pass);
          update(page.id, (p) => ({ ...p, blocks: [], sealed: sealedNow }));
        }, 600);
        return;
      }
      update(page.id, (p) => ({ ...p, blocks: next }));
    },
    [page, setUnlocked, update],
  );

  useLayoutEffect(() => {
    if (!focusAt) return;
    const el = refs.current.get(focusAt.id);
    if (el) {
      el.focus();
      const pos = Math.min(focusAt.pos, el.value.length);
      el.setSelectionRange(pos, pos);
    }
    setFocusAt(null);
  }, [focusAt, blocks]);

  useEffect(() => {
    for (const el of refs.current.values()) autosize(el);
  }, [blocks, layout.fontSize]);

  if (!page) return null;

  if (sealed && !unlockedBlocks) {
    return <UnlockScreen page={page} onOpen={(b, pass) => (passphrases.set(page.id, pass), setUnlocked(page.id, b))} />;
  }

  const index = (id: string) => blocks.findIndex((b) => b.id === id);
  const patch = (id: string, p: Partial<Block>) => setBlocks(blocks.map((b) => (b.id === id ? { ...b, ...p } : b)));
  const insertAfter = (id: string, b: Block) => {
    const i = index(id);
    setBlocks([...blocks.slice(0, i + 1), b, ...blocks.slice(i + 1)]);
    setFocusAt({ id: b.id, pos: 0 });
  };
  const turnInto = (id: string, type: BlockType, text?: string) => {
    const current = blocks[index(id)];
    const keep = text ?? current.text;
    if (type === 'page') {
      const child = create({ parent: null, title: keep || 'Página nueva', open: false });
      setBlocks(blocks.map((b) => (b.id === id ? { ...b, type: 'page', pageId: child.id, text: child.title } : b)));
      return;
    }
    const fresh = makeBlock(type, TEXTUAL.includes(type) ? keep : '');
    setBlocks(blocks.map((b) => (b.id === id ? { ...fresh, id } : b)));
    if (TEXTUAL.includes(type)) setFocusAt({ id, pos: keep.length });
  };
  const move = (id: string, dir: -1 | 1) => {
    const i = index(id);
    const j = i + dir;
    if (j < 0 || j >= blocks.length) return;
    const next = [...blocks];
    [next[i], next[j]] = [next[j], next[i]];
    setBlocks(next);
    setFocusAt({ id, pos: refs.current.get(id)?.selectionStart ?? 0 });
  };
  const focusNeighbour = (id: string, dir: -1 | 1, atEnd: boolean) => {
    let i = index(id) + dir;
    while (i >= 0 && i < blocks.length && !TEXTUAL.includes(blocks[i].type)) i += dir;
    if (i >= 0 && i < blocks.length) setFocusAt({ id: blocks[i].id, pos: atEnd ? blocks[i].text.length : 0 });
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>, b: Block) => {
    const el = e.currentTarget;
    if (slash && slash.id === b.id) {
      const options = slashMatches(slash.query);
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSlash({ ...slash, index: (slash.index + 1) % Math.max(1, options.length) });
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSlash({ ...slash, index: (slash.index - 1 + options.length) % Math.max(1, options.length) });
        return;
      }
      if (e.key === 'Enter' && options.length) {
        e.preventDefault();
        turnInto(b.id, options[slash.index].type, '');
        setSlash(null);
        return;
      }
      if (e.key === 'Escape') {
        setSlash(null);
        return;
      }
    }
    if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault();
      move(b.id, e.key === 'ArrowUp' ? -1 : 1);
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey && b.type !== 'code' && !e.nativeEvent.isComposing) {
      e.preventDefault();
      const at = el.selectionStart;
      const before = b.text.slice(0, at);
      const after = b.text.slice(at);
      const list = ['todo', 'bullet', 'number'].includes(b.type);
      if (list && !b.text) {
        turnInto(b.id, 'text'); // an empty list item ends the list
        return;
      }
      const nextType: BlockType = list ? b.type : 'text';
      const fresh = makeBlock(nextType, after);
      const i = index(b.id);
      setBlocks([...blocks.slice(0, i), { ...b, text: before }, fresh, ...blocks.slice(i + 1)]);
      setFocusAt({ id: fresh.id, pos: 0 });
      return;
    }
    if (e.key === 'Backspace' && el.selectionStart === 0 && el.selectionEnd === 0) {
      if (b.type !== 'text') {
        e.preventDefault();
        turnInto(b.id, 'text');
        return;
      }
      const i = index(b.id);
      let p = i - 1;
      while (p >= 0 && !TEXTUAL.includes(blocks[p].type)) p--;
      if (p < 0) return;
      e.preventDefault();
      const prev = blocks[p];
      const merged = { ...prev, text: prev.text + b.text };
      setBlocks(blocks.flatMap((x, k) => (k === p ? [merged] : k === i ? [] : [x])));
      setFocusAt({ id: prev.id, pos: prev.text.length });
      return;
    }
    if (e.key === 'ArrowUp' && el.selectionStart === 0) {
      e.preventDefault();
      focusNeighbour(b.id, -1, true);
    } else if (e.key === 'ArrowDown' && el.selectionStart === el.value.length) {
      e.preventDefault();
      focusNeighbour(b.id, 1, false);
    }
  };

  const onText = (b: Block, text: string) => {
    const sc = b.type === 'text' ? shortcut(text) : null;
    if (sc) {
      const fresh = makeBlock(sc.type, sc.text, sc.checked !== undefined ? { checked: sc.checked } : {});
      setBlocks(blocks.map((x) => (x.id === b.id ? { ...fresh, id: b.id } : x)));
      setFocusAt({ id: b.id, pos: sc.text.length });
      setSlash(null);
      return;
    }
    patch(b.id, { text });
    if (text.startsWith('/') && !text.includes(' ') && text.length <= 24) setSlash({ id: b.id, query: text.slice(1), index: 0 });
    else if (slash?.id === b.id) setSlash(null);
  };

  const titleOf = (id: string) => pages[id]?.title || '';
  const byTitle = new Map(Object.values(pages).map((p) => [p.title.trim().toLowerCase(), p.id]));
  const followLink = (title: string) => {
    const id = byTitle.get(title.toLowerCase());
    if (id) open(id);
    else open(create({ title, open: false }).id);
  };
  const backlinks = Object.values(pages).filter(
    (p) =>
      p.id !== page.id &&
      !p.sealed &&
      (mentions(p).some((t) => t.toLowerCase() === page.title.trim().toLowerCase() && page.title.trim()) ||
        p.blocks.some((b) => b.type === 'page' && b.pageId === page.id)),
  );
  const tables = blocks.filter((b) => b.type === 'table');
  const live = blocks.filter((b) => !b.archived);
  const vaulted = blocks.filter((b) => b.archived);
  let numberRun = 0;

  const runAI = async (action: PageAction) => {
    setThinking(true);
    try {
      const text = await askAboutPage({ ...page, blocks }, action, model);
      const lines = parseLines(text);
      if (!lines.length) {
        toast('Sergio no encontró nada que añadir.');
        return;
      }
      const heading = action === 'summary' ? [makeBlock('h3', 'Resumen')] : action === 'tasks' ? [makeBlock('h3', 'Tareas')] : [];
      setBlocks([...blocks, ...heading, ...lines.map((l) => makeBlock(l.kind, l.text))]);
      toast.success('Listo: Sergio lo añadió al final de la página.');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Sergio no respondió.');
    } finally {
      setThinking(false);
    }
  };

  const exportMd = () => {
    const blob = new Blob([toMarkdown({ ...page, blocks }, titleOf)], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${(page.title || 'pagina').replace(/[^\p{L}\p{N} _-]/gu, '').trim() || 'pagina'}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };

  return (
    <article
      className="ws-page"
      data-density={layout.density}
      style={{ ['--ws-font' as string]: `${layout.fontSize}px`, ['--ws-margin' as string]: `${layout.margin}px` }}
    >
      <div className="ws-page-tools">
        <button
          type="button"
          className="mac-icon-btn"
          aria-pressed={!!page.favorite}
          aria-label={page.favorite ? 'Quitar de favoritos' : 'Marcar como favorita'}
          title="Favorita"
          onClick={() => update(page.id, (p) => ({ ...p, favorite: !p.favorite }))}
        >
          <Star size={15} strokeWidth={1.5} fill={page.favorite ? 'currentColor' : 'none'} />
        </button>
        <button type="button" className="mac-icon-btn" aria-label={sealed ? 'Cifrado' : 'Cifrar'} title={sealed ? 'Cifrada de extremo a extremo' : 'Cifrar de extremo a extremo'} onClick={() => setLockOpen(true)}>
          {sealed ? <Lock size={15} strokeWidth={1.5} /> : <Unlock size={15} strokeWidth={1.5} />}
        </button>
        {!sealed && (
          <button type="button" className="mac-icon-btn" aria-label="Compartir" title="Compartir" onClick={() => setShare({ page: page.id, scope: 'page' })}>
            <Share2 size={15} strokeWidth={1.5} />
          </button>
        )}
        <span className="relative">
          <button type="button" className="mac-icon-btn" aria-label="Sergio" title="Pedir a Sergio" disabled={thinking} onClick={() => setMenu(menu === 'ai' ? null : 'ai')}>
            <Sparkles size={15} strokeWidth={1.5} className={thinking ? 'animate-pulse' : undefined} />
          </button>
          {menu === 'ai' && (
            <span className="ws-pop" role="menu" style={{ right: 0 }}>
              {PAGE_ACTIONS.map((a) => (
                <button key={a.key} type="button" role="menuitem" onClick={() => (setMenu(null), void runAI(a.key))}>
                  {a.label}
                </button>
              ))}
            </span>
          )}
        </span>
        <span className="relative">
          <button type="button" className="mac-icon-btn" aria-label="Más" onClick={() => setMenu(menu === 'more' ? null : 'more')}>
            <MoreHorizontal size={15} strokeWidth={1.5} />
          </button>
          {menu === 'more' && (
            <span className="ws-pop" role="menu" style={{ right: 0 }}>
              <button type="button" role="menuitem" onClick={() => (setMenu(null), exportMd())}>
                <Download size={13} /> Descargar en Markdown
              </button>
              <button type="button" role="menuitem" onClick={() => (setMenu(null), setHistory(true))}>
                <HistoryIcon size={13} /> Historial de versiones
              </button>
              <button type="button" role="menuitem" onClick={() => (setMenu(null), void archive(page.id))}>
                <Archive size={13} /> Mover al baúl
              </button>
              <button
                type="button"
                role="menuitem"
                style={{ color: 'var(--color-error)' }}
                onClick={() => {
                  setMenu(null);
                  if (window.confirm(`¿Borrar «${page.title || 'Sin título'}»? Queda 30 días en la papelera del servidor.`)) remove(page.id);
                }}
              >
                <Trash2 size={13} /> Borrar
              </button>
            </span>
          )}
        </span>
      </div>

      <textarea
        className="ws-title"
        value={page.title}
        placeholder="Sin título"
        rows={1}
        ref={(el) => autosize(el)}
        onChange={(e) => {
          update(page.id, (p) => ({ ...p, title: e.target.value.replace(/\n/g, ' ') }));
          autosize(e.currentTarget);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === 'ArrowDown') {
            e.preventDefault();
            const first = live.find((b) => TEXTUAL.includes(b.type));
            if (first) setFocusAt({ id: first.id, pos: 0 });
            else insertAfter(blocks[blocks.length - 1]?.id || '', makeBlock('text'));
          }
        }}
        aria-label="Título"
      />

      <div className="ws-blocks">
        {live.map((b) => {
          numberRun = b.type === 'number' ? numberRun + 1 : 0;
          const textual = TEXTUAL.includes(b.type);
          const links = textual ? [...b.text.matchAll(/\[\[([^\]\n]{1,120})\]\]/g)].map((m) => m[1].trim()) : [];
          const [summary, ...rest] = b.type === 'toggle' ? b.text.split('\n') : [b.text];
          return (
            <div key={b.id} className="ws-block" data-type={b.type} data-done={b.type === 'todo' && b.checked ? 'true' : undefined}>
              <span className="ws-gutter">
                <button type="button" className="ws-handle" aria-label="Opciones del bloque" onClick={() => setMenu(menu === b.id ? null : b.id)}>
                  <GripVertical size={14} strokeWidth={1.5} />
                </button>
                {menu === b.id && (
                  <span className="ws-pop" role="menu">
                    <span className="paper-label">Convertir en</span>
                    <span className="ws-pop-grid">
                      {(['text', 'h1', 'h2', 'h3', 'todo', 'bullet', 'number', 'quote', 'callout', 'code', 'toggle'] as BlockType[]).map((t) => (
                        <button key={t} type="button" role="menuitem" onClick={() => (setMenu(null), turnInto(b.id, t))}>
                          {slashMatches('').find((s) => s.type === t)?.label}
                        </button>
                      ))}
                    </span>
                    <button type="button" role="menuitem" onClick={() => (setMenu(null), move(b.id, -1))}>
                      <ArrowUp size={13} /> Subir (Alt+↑)
                    </button>
                    <button type="button" role="menuitem" onClick={() => (setMenu(null), move(b.id, 1))}>
                      <ArrowDown size={13} /> Bajar (Alt+↓)
                    </button>
                    <button type="button" role="menuitem" onClick={() => (setMenu(null), insertAfter(b.id, { ...structuredClone(b), id: makeBlock('text').id }))}>
                      <Copy size={13} /> Duplicar
                    </button>
                    {!sealed && (
                      <button type="button" role="menuitem" onClick={() => (setMenu(null), setShare({ page: page.id, scope: 'block', block: b.id }))}>
                        <Share2 size={13} /> Compartir solo este bloque
                      </button>
                    )}
                    <button
                      type="button"
                      role="menuitem"
                      style={{ color: 'var(--color-error)' }}
                      onClick={() => {
                        setMenu(null);
                        setBlocks(blocks.length > 1 ? blocks.filter((x) => x.id !== b.id) : [makeBlock('text')]);
                      }}
                    >
                      <Trash2 size={13} /> Borrar bloque
                    </button>
                  </span>
                )}
              </span>
              <div className="ws-body">
                {b.type === 'todo' && (
                  <input
                    type="checkbox"
                    className="ws-check"
                    checked={!!b.checked}
                    onChange={(e) => patch(b.id, { checked: e.target.checked, doneAt: e.target.checked ? Date.now() : undefined })}
                    aria-label="Hecha"
                  />
                )}
                {b.type === 'bullet' && <span className="ws-marker">•</span>}
                {b.type === 'number' && <span className="ws-marker">{numberRun}.</span>}
                {b.type === 'toggle' && (
                  <button type="button" className="ws-marker" onClick={() => patch(b.id, { open: !b.open })} aria-label={b.open ? 'Plegar' : 'Desplegar'} aria-expanded={!!b.open}>
                    {b.open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                )}
                {textual ? (
                  <div className="flex-1 min-w-0">
                    <textarea
                      ref={(el) => {
                        if (el) refs.current.set(b.id, el);
                        else refs.current.delete(b.id);
                      }}
                      className="ws-text"
                      rows={1}
                      spellCheck={b.type !== 'code' && b.type !== 'equation' && b.type !== 'bookmark'}
                      value={b.type === 'toggle' && !b.open ? summary : b.text}
                      placeholder={PLACEHOLDER[b.type]}
                      onChange={(e) => {
                        onText(b, b.type === 'toggle' && !b.open ? [e.target.value, ...rest].join('\n') : e.target.value);
                        autosize(e.currentTarget);
                      }}
                      onKeyDown={(e) => onKey(e, b)}
                      onBlur={() => setTimeout(() => setSlash((s) => (s?.id === b.id ? null : s)), 150)}
                      aria-label={PLACEHOLDER[b.type] || 'Texto'}
                    />
                    {b.type === 'equation' && <EquationView tex={b.text} />}
                    {b.type === 'bookmark' && <BookmarkView url={b.text} />}
                    {links.length > 0 && (
                      <div className="ws-links">
                        {links.map((l) => (
                          <button key={l} type="button" className="mac-chip" onClick={() => followLink(l)}>
                            → {l}
                            {!byTitle.has(l.toLowerCase()) && ' (crear)'}
                          </button>
                        ))}
                      </div>
                    )}
                    {slash?.id === b.id && (
                      <div className="ws-pop ws-slash" role="listbox" aria-label="Insertar bloque">
                        {slashMatches(slash.query).map((s, i) => (
                          <button
                            key={s.type}
                            type="button"
                            role="option"
                            aria-selected={i === slash.index}
                            onMouseDown={(e) => {
                              e.preventDefault();
                              turnInto(b.id, s.type, '');
                              setSlash(null);
                            }}
                          >
                            <strong>{s.label}</strong>
                            <span>{s.hint}</span>
                          </button>
                        ))}
                        {slashMatches(slash.query).length === 0 && <span className="px-3 py-2">Nada con «{slash.query}»</span>}
                      </div>
                    )}
                  </div>
                ) : b.type === 'divider' ? (
                  <hr className="paper-rule w-full my-3" />
                ) : b.type === 'toc' ? (
                  <TocView
                    blocks={live}
                    onJump={(id) => {
                      const el = refs.current.get(id);
                      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      el?.focus();
                    }}
                  />
                ) : b.type === 'table' && b.table ? (
                  <TableBlock
                    table={b.table}
                    onChange={(t) => patch(b.id, { table: t })}
                    onShareRows={sealed ? undefined : (rows) => setShare({ page: page.id, scope: 'rows', block: b.id, rows })}
                    onShareView={sealed ? undefined : (view) => setShare({ page: page.id, scope: 'view', block: b.id, view })}
                  />
                ) : b.type === 'chart' ? (
                  <ChartBlock block={b} tables={tables} onChange={(c) => patch(b.id, { chart: c })} />
                ) : b.type === 'pomodoro' ? (
                  <PomodoroBlock work={b.pomodoro?.work ?? 25} rest={b.pomodoro?.rest ?? 5} onChange={(p) => patch(b.id, { pomodoro: p })} />
                ) : b.type === 'audio' || b.type === 'image' ? (
                  <MediaBlock block={b} onMedia={(m) => patch(b.id, { media: m })} />
                ) : b.type === 'mindmap' ? (
                  <MindMapBlock nodes={b.mind || []} onChange={(m) => patch(b.id, { mind: m })} />
                ) : b.type === 'page' ? (
                  <button type="button" className="ws-pagelink" onClick={() => b.pageId && pages[b.pageId] && open(b.pageId)}>
                    ▤ {titleOf(b.pageId || '') || b.text || 'Página'}
                  </button>
                ) : null}
              </div>
            </div>
          );
        })}
        <button type="button" className="ws-add-block" onClick={() => insertAfter(blocks[blocks.length - 1]?.id || '', makeBlock('text'))}>
          + Añadir un bloque
        </button>
      </div>

      {vaulted.length > 0 && (
        <div className="ws-footer-note">
          <button type="button" className="paper-tab" onClick={() => setShowVault(!showVault)}>
            {vaulted.length} {vaulted.length === 1 ? 'tarea terminada' : 'tareas terminadas'} en el baúl {showVault ? '▴' : '▾'}
          </button>
          {showVault && (
            <ul className="mt-2 text-[13px]" style={{ color: 'var(--color-text-secondary)' }}>
              {vaulted.map((b) => (
                <li key={b.id} className="flex items-center gap-2">
                  ☑ {b.text}
                  <button type="button" className="paper-tab text-[11px]" onClick={() => patch(b.id, { archived: false })}>
                    devolver
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {backlinks.length > 0 && (
        <div className="ws-footer-note">
          <div className="paper-label mb-2">Mencionada en</div>
          <div className="flex flex-wrap gap-2">
            {backlinks.map((p) => (
              <button key={p.id} type="button" className="mac-chip" onClick={() => open(p.id)}>
                {p.title || 'Sin título'}
              </button>
            ))}
          </div>
        </div>
      )}

      {share && <ShareDialog target={share} onClose={() => setShare(null)} />}
      {history && (
        <HistoryDialog
          page={page}
          onClose={() => setHistory(false)}
          onRestore={(old) =>
            // The old content becomes the newest version (same id, current revision).
            update(page.id, (p) => ({ ...old, id: p.id, rev: p.rev, parent: p.parent, openedAt: p.openedAt, updatedAt: Date.now() }))
          }
        />
      )}
      {lockOpen && (
        <LockDialog
          page={page}
          blocks={blocks}
          onClose={() => setLockOpen(false)}
          onSealed={(s, pass) => {
            passphrases.set(page.id, pass);
            setUnlocked(page.id, blocks);
            update(page.id, (p) => ({ ...p, blocks: [], sealed: s }));
          }}
          onOpened={() => {
            passphrases.delete(page.id);
            setUnlocked(page.id, null);
            update(page.id, (p) => ({ ...p, blocks, sealed: null }));
          }}
          onLockNow={() => {
            passphrases.delete(page.id);
            setUnlocked(page.id, null);
          }}
        />
      )}
    </article>
  );
}

function UnlockScreen({ page, onOpen }: { page: Page; onOpen: (blocks: Block[], pass: string) => void }) {
  const [pass, setPass] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <article className="ws-page">
      <h2 className="ws-title" style={{ border: 0 }}>{page.title || 'Sin título'}</h2>
      <form
        className="ws-card flex flex-col gap-3 max-w-md"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          try {
            onOpen(await unseal(page.sealed!, pass), pass);
          } catch (err) {
            setError(err instanceof WrongPassphrase ? err.message : 'No se pudo abrir.');
          } finally {
            setBusy(false);
          }
        }}
      >
        <span className="flex items-center gap-2">
          <Lock size={15} /> Página cifrada de extremo a extremo
        </span>
        <input type="password" className="mac-field" value={pass} onChange={(e) => setPass(e.target.value)} placeholder="Su frase" autoFocus aria-label="Frase" />
        {error && <span style={{ color: 'var(--color-error)' }}>{error}</span>}
        <button type="submit" className="paper-button" disabled={!pass || busy}>
          {busy ? 'Abriendo…' : 'Abrir'}
        </button>
      </form>
    </article>
  );
}

function LockDialog({
  page,
  blocks,
  onClose,
  onSealed,
  onOpened,
  onLockNow,
}: {
  page: Page;
  blocks: Block[];
  onClose: () => void;
  onSealed: (s: NonNullable<Page['sealed']>, pass: string) => void;
  onOpened: () => void;
  onLockNow: () => void;
}) {
  const [pass, setPass] = useState('');
  const [again, setAgain] = useState('');
  const [sure, setSure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return (
    <div className="ws-modal" role="dialog" aria-modal="true" aria-label="Cifrado">
      <div className="ws-modal-sheet">
        {page.sealed ? (
          <>
            <h3 className="paper-title" style={{ fontSize: 16 }}>Cifrada</h3>
            <p className="text-[13.5px] my-3">
              Esta página está cifrada en su equipo antes de guardarse. El servidor y las copias solo tienen texto ilegible.
            </p>
            <div className="flex gap-2 justify-end">
              <button type="button" className="paper-button" data-variant="quiet" onClick={() => (onLockNow(), onClose())}>
                Cerrar con llave ahora
              </button>
              <button type="button" className="paper-button" data-variant="quiet" onClick={() => (onOpened(), onClose())}>
                Quitar el cifrado
              </button>
              <button type="button" className="paper-button" onClick={onClose}>
                Listo
              </button>
            </div>
          </>
        ) : (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (pass !== again) return setError('Las dos frases no coinciden.');
              setBusy(true);
              try {
                onSealed(await seal(blocks, pass), pass);
                onClose();
                toast.success('Página cifrada. Solo su frase la abre.');
              } catch (err) {
                setError(err instanceof Error ? err.message : 'No se pudo cifrar.');
              } finally {
                setBusy(false);
              }
            }}
            className="flex flex-col gap-3"
          >
            <h3 className="paper-title" style={{ fontSize: 16 }}>Cifrar de extremo a extremo</h3>
            <p className="text-[13.5px]">
              La página se cifra en este equipo con una frase que solo usted sabe (AES-256). Ni el servidor, ni las copias, ni
              Sergio pueden leerla sin ella. El título sigue visible.
            </p>
            <input type="password" className="mac-field" placeholder="Frase (8+ caracteres)" value={pass} onChange={(e) => setPass(e.target.value)} aria-label="Frase" autoFocus />
            <input type="password" className="mac-field" placeholder="Repita la frase" value={again} onChange={(e) => setAgain(e.target.value)} aria-label="Repita la frase" />
            <label className="flex items-start gap-2 text-[13px]">
              <input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} />
              Entiendo que si olvido la frase nadie puede recuperar esta página.
            </label>
            {error && <span style={{ color: 'var(--color-error)' }}>{error}</span>}
            <div className="flex gap-2 justify-end">
              <button type="button" className="paper-button" data-variant="quiet" onClick={onClose}>
                Cancelar
              </button>
              <button type="submit" className="paper-button" disabled={!sure || pass.length < 8 || busy}>
                {busy ? 'Cifrando…' : 'Cifrar'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
