import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  Brain,
  ChevronDown,
  ChevronRight,
  Download,
  FileDown,
  FileText,
  GripVertical,
  History as HistoryIcon,
  Lock,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Plus,
  Printer,
  Replace,
  Sparkles,
  Star,
  Trash2,
  Unlock,
} from 'lucide-react';
import { apiFetch } from '../../lib/api';
import { inferTable, parseGrid } from '../../lib/workspace/brain';
import { ButtonBlock, DashboardBlock, FormBlock, MediaLook, VideoBlock } from './SmartBlocks';
import { IntelPanel } from './IntelPanel';
import { toast } from 'sonner';
import { useWorkspace } from '../../lib/workspace/store';
import {
  block as makeBlock,
  mentions,
  newId,
  shortcut,
  toMarkdown,
  type Block,
  type BlockType,
  type Comment,
  type Page,
} from '../../lib/workspace/model';
import {
  ancestors,
  colorParts,
  editedAgo,
  hasInline,
  insertMention,
  linkSelection,
  mentionQuery,
  toggleMark,
} from '../../lib/workspace/notion';
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
import { BlockMenu, Comments, FormatBar, MentionMenu, PageHeader, RichText, SlashMenu, slashOrder } from './NxParts';

const TEXTUAL: BlockType[] = ['text', 'h1', 'h2', 'h3', 'todo', 'bullet', 'number', 'quote', 'callout', 'code', 'toggle', 'equation', 'bookmark'];
const PLACEHOLDER: Partial<Record<BlockType, string>> = {
  text: 'Escriba «/» para ver los comandos…',
  h1: 'Encabezado 1',
  h2: 'Encabezado 2',
  h3: 'Encabezado 3',
  todo: 'Tarea pendiente',
  bullet: 'Lista',
  number: 'Lista',
  quote: 'Cita',
  callout: 'Escriba algo…',
  code: 'Código',
  toggle: 'Desplegable (la primera línea es el título)',
  equation: 'Fórmula en LaTeX, p. ej. E = mc^2 o \\frac{a}{b}',
  bookmark: 'Pegue un enlace: https://…',
};
// Formatting is shown (not raw Markdown) except while a block is edited.
const RICH: BlockType[] = ['text', 'h1', 'h2', 'h3', 'todo', 'bullet', 'number', 'quote', 'callout'];

// Passphrases of the pages unlocked in this visit: memory only, never stored.
const passphrases = new Map<string, string>();

function autosize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = '0px';
  el.style.height = `${el.scrollHeight}px`;
}

export function PageEditor({
  pageId,
  onOpen,
  sidebarOpen = true,
  onToggleSidebar,
}: {
  pageId: string;
  onOpen?: (id: string) => void;
  sidebarOpen?: boolean;
  onToggleSidebar?: () => void;
}) {
  const page = useWorkspace((s) => s.pages[pageId]);
  const pages = useWorkspace((s) => s.pages);
  const update = useWorkspace((s) => s.update);
  const unlockedBlocks = useWorkspace((s) => s.unlocked[pageId]);
  const setUnlocked = useWorkspace((s) => s.setUnlocked);
  const create = useWorkspace((s) => s.create);
  const openStore = useWorkspace((s) => s.open);
  const archive = useWorkspace((s) => s.archive);
  const remove = useWorkspace((s) => s.remove);
  const layout = useWorkspace((s) => s.layout);
  const model = useAppStore((s) => s.selectedModel);
  const refs = useRef(new Map<string, HTMLTextAreaElement>());
  const [focusAt, setFocusAt] = useState<{ id: string; pos: number; end?: number } | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [slash, setSlash] = useState<{ id: string; query: string; index: number } | null>(null);
  const [mention, setMention] = useState<{ id: string; query: string } | null>(null);
  const [selection, setSelection] = useState<{ id: string; start: number; end: number } | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const [share, setShare] = useState<ShareTarget | null>(null);
  const [lockOpen, setLockOpen] = useState(false);
  const [showVault, setShowVault] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [intel, setIntel] = useState(false);
  const [finder, setFinder] = useState<{ find: string; with: string } | null>(null);
  const [commenting, setCommenting] = useState(false);
  const [showRefs, setShowRefs] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [dropAt, setDropAt] = useState<{ id: string; after: boolean } | null>(null);
  const resealTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const draggingRef = useRef<string | null>(null); // the block being dragged (read at drop time)

  const open = useCallback((id: string) => (onOpen ? onOpen(id) : openStore(id)), [onOpen, openStore]);
  const sealed = !!page?.sealed;
  const locked = !!page?.style?.locked;
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
      el.setSelectionRange(pos, Math.min(focusAt.end ?? pos, el.value.length));
      setFocusAt(null);
    } else if (editing !== focusAt.id) {
      setEditing(focusAt.id); // shown formatted: switch it to editing first
    }
  }, [focusAt, blocks, editing]);

  useEffect(() => {
    for (const el of refs.current.values()) autosize(el);
  }, [blocks, layout.fontSize, editing]);

  if (!page) return null;

  if (sealed && !unlockedBlocks) {
    return <UnlockScreen page={page} onOpen={(b, pass) => (passphrases.set(page.id, pass), setUnlocked(page.id, b))} />;
  }

  const setPage = (change: Partial<Page>) => update(page.id, (p) => ({ ...p, ...change }));
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
      const child = create({ parent: page.id, title: keep || 'Página nueva', open: false });
      setBlocks(blocks.map((b) => (b.id === id ? { ...b, type: 'page', pageId: child.id, text: child.title } : b)));
      return;
    }
    const fresh = makeBlock(type, TEXTUAL.includes(type) ? keep : '');
    setBlocks(blocks.map((b) => (b.id === id ? { ...fresh, id, color: current.color } : b)));
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
  const moveTo = (id: string, target: string, after: boolean) => {
    if (id === target) return;
    const moving = blocks[index(id)];
    const rest = blocks.filter((b) => b.id !== id);
    const t = rest.findIndex((b) => b.id === target);
    if (!moving || t < 0) return;
    setBlocks([...rest.slice(0, t + (after ? 1 : 0)), moving, ...rest.slice(t + (after ? 1 : 0))]);
  };
  const focusNeighbour = (id: string, dir: -1 | 1, atEnd: boolean) => {
    let i = index(id) + dir;
    while (i >= 0 && i < blocks.length && !TEXTUAL.includes(blocks[i].type)) i += dir;
    if (i >= 0 && i < blocks.length) setFocusAt({ id: blocks[i].id, pos: atEnd ? blocks[i].text.length : 0 });
  };
  const comments = page.comments || [];
  const addComment = (c: Omit<Comment, 'id' | 'at'>) => setPage({ comments: [...comments, { id: newId('m'), at: Date.now(), ...c }] });

  const applyMark = (b: Block, mark: 'bold' | 'italic' | 'underline' | 'strike' | 'code') => {
    const el = refs.current.get(b.id);
    if (!el) return;
    const r = toggleMark(b.text, el.selectionStart, el.selectionEnd, mark);
    patch(b.id, { text: r.text });
    setFocusAt({ id: b.id, pos: r.start, end: r.end });
  };
  const applyLink = (b: Block) => {
    const el = refs.current.get(b.id);
    if (!el) return;
    const href = window.prompt('Dirección del enlace (https://…)');
    if (!href || !/^https?:\/\//.test(href)) return;
    patch(b.id, { text: linkSelection(b.text, el.selectionStart, el.selectionEnd, href) });
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>, b: Block) => {
    const el = e.currentTarget;
    if (slash && slash.id === b.id) {
      const options = slashOrder(slash.query);
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
    if (mention && mention.id === b.id && e.key === 'Escape') {
      setMention(null);
      return;
    }
    const mod = e.ctrlKey || e.metaKey;
    if (mod && !e.altKey) {
      const k = e.key.toLowerCase();
      const mark = k === 'b' ? 'bold' : k === 'i' ? 'italic' : k === 'u' ? 'underline' : k === 'e' ? 'code' : k === 's' && e.shiftKey ? 'strike' : null;
      if (mark && el.selectionStart !== el.selectionEnd) {
        e.preventDefault();
        applyMark(b, mark);
        return;
      }
      if (k === 'k' && el.selectionStart !== el.selectionEnd) {
        e.preventDefault();
        applyLink(b);
        return;
      }
      if (k === 'd') {
        e.preventDefault();
        insertAfter(b.id, { ...structuredClone(b), id: newId('b') });
        return;
      }
    }
    if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault();
      move(b.id, e.key === 'ArrowUp' ? -1 : 1);
      return;
    }
    if (e.key === 'Tab' && ['bullet', 'number', 'todo'].includes(b.type)) {
      e.preventDefault(); // keep focus in the page (nesting is shown by type, not depth)
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

  const onText = (b: Block, text: string, caret: number) => {
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
    const q = mentionQuery(text, caret);
    setMention(q !== null ? { id: b.id, query: q } : null);
  };

  const titleOf = (id: string) => pages[id]?.title || '';
  const byTitle = new Map(Object.values(pages).map((p) => [p.title.trim().toLowerCase(), p.id]));
  const followLink = (title: string) => {
    const id = byTitle.get(title.toLowerCase());
    if (id) open(id);
    else open(create({ title, parent: page.id, open: false }).id);
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

  const fileName = (page.title || 'pagina').replace(/[^\p{L}\p{N} _-]/gu, '').trim() || 'pagina';
  const exportMd = () => {
    const blob = new Blob([toMarkdown({ ...page, blocks }, titleOf)], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${fileName}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };

  const exportDocx = async () => {
    const r = await apiFetch(`/v1/workspace/pages/${page.id}/docx`).catch(() => null);
    if (!r || !r.ok) return toast.error('Para Word, su servidor de Sergio debe estar encendido.');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await r.blob());
    a.download = `${fileName}.docx`;
    a.click();
  };
  const replaceAll = (find: string, by: string) => {
    if (!find) return 0;
    let n = 0;
    const re = new RegExp(find.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    setBlocks(
      blocks.map((b) => {
        if (!b.text || !re.test(b.text)) return b;
        n += (b.text.match(re) || []).length;
        return { ...b, text: b.text.replace(re, by) };
      }),
    );
    return n;
  };
  const words = live.reduce((n, b) => n + (b.text.match(/\S+/g) || []).length, 0);
  const onPasteGrid = (e: React.ClipboardEvent<HTMLTextAreaElement>, b: Block) => {
    const text = e.clipboardData.getData('text/plain');
    const lines = text.trim().split('\n');
    const tabular = lines.length >= 2 && (lines.every((l) => l.includes('\t')) || lines.every((l) => /^\s*\|.*\|\s*$/.test(l)));
    if (!tabular || b.text) return;
    e.preventDefault();
    const t = inferTable(parseGrid(text));
    setBlocks(blocks.map((x) => (x.id === b.id ? { ...makeBlock('table'), id: b.id, table: t } : x)));
    toast.success(`Tabla de ${t.rows.length} filas con columnas tipadas.`);
  };
  const path = ancestors(pages, page.id);
  const style = page.style || {};
  const setStyle = (s: Partial<NonNullable<Page['style']>>) => setPage({ style: { ...style, ...s } });

  const renderBody = (b: Block, textual: boolean, links: string[], summary: string, rest: string[]) => {
    if (textual) {
      const showRich = RICH.includes(b.type) && editing !== b.id && hasInline(b.text) && !(b.type === 'toggle');
      return (
        <div className="flex-1 min-w-0 relative">
          {showRich ? (
            <RichText text={b.text} onPage={followLink} onClick={() => !locked && setFocusAt({ id: b.id, pos: b.text.length })} />
          ) : (
            <textarea
              ref={(el) => {
                if (el) refs.current.set(b.id, el);
                else refs.current.delete(b.id);
              }}
              className="ws-text"
              rows={1}
              readOnly={locked}
              spellCheck={b.type !== 'code' && b.type !== 'equation' && b.type !== 'bookmark'}
              value={b.type === 'toggle' && !b.open ? summary : b.text}
              placeholder={PLACEHOLDER[b.type]}
              onFocus={() => setEditing(b.id)}
              onChange={(e) => {
                onText(b, b.type === 'toggle' && !b.open ? [e.target.value, ...rest].join('\n') : e.target.value, e.target.selectionStart);
                autosize(e.currentTarget);
              }}
              onSelect={(e) => {
                const el = e.currentTarget;
                setSelection(el.selectionEnd > el.selectionStart ? { id: b.id, start: el.selectionStart, end: el.selectionEnd } : null);
              }}
              onKeyDown={(e) => onKey(e, b)}
              onPaste={(e) => onPasteGrid(e, b)}
              onBlur={() =>
                setTimeout(() => {
                  setSlash((s) => (s?.id === b.id ? null : s));
                  setMention((m) => (m?.id === b.id ? null : m));
                  setSelection((s) => (s?.id === b.id ? null : s));
                  setEditing((x) => (x === b.id ? null : x));
                }, 150)
              }
              aria-label={PLACEHOLDER[b.type] || 'Texto'}
            />
          )}
          {b.type === 'equation' && <EquationView tex={b.text} />}
          {b.type === 'bookmark' && <BookmarkView url={b.text} />}
          {!showRich && editing !== b.id && links.length > 0 && (
            <div className="ws-links">
              {links.map((l) => (
                <button key={l} type="button" className="nx-page-mention" onClick={() => followLink(l)}>
                  <FileText size={14} className="inline" /> {l}
                  {!byTitle.has(l.toLowerCase()) && ' (crear)'}
                </button>
              ))}
            </div>
          )}
          {selection?.id === b.id && !locked && (
            <FormatBar
              type={b.type}
              onMark={(m) => applyMark(b, m)}
              onLink={() => applyLink(b)}
              onComment={() => (addComment({ text: `«${b.text.slice(selection.start, selection.end)}»`, block: b.id }), setCommenting(true))}
              onTurn={() => setMenu(b.id)}
            />
          )}
          {slash?.id === b.id && (
            <SlashMenu
              query={slash.query}
              index={slash.index}
              onPick={(t) => {
                turnInto(b.id, t, '');
                setSlash(null);
              }}
            />
          )}
          {mention?.id === b.id && (
            <MentionMenu
              pages={Object.values(pages).filter((p) => p.id !== page.id)}
              query={mention.query}
              onPick={(p) => {
                const el = refs.current.get(b.id);
                const r = insertMention(b.text, el?.selectionStart ?? b.text.length, p.title || 'Sin título');
                patch(b.id, { text: r.text });
                setMention(null);
                setFocusAt({ id: b.id, pos: r.caret });
              }}
            />
          )}
        </div>
      );
    }
    if (b.type === 'divider') return <hr className="nx-divider" />;
    if (b.type === 'toc')
      return (
        <TocView
          blocks={live}
          onJump={(id) => {
            const el = refs.current.get(id);
            el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el?.focus();
          }}
        />
      );
    if (b.type === 'table' && b.table)
      return (
        <TableBlock
          table={b.table}
          onChange={(t) => patch(b.id, { table: t })}
          onEffects={(fx) => {
            fx.notes.forEach((n) => toast(n));
            if (fx.todos.length) {
              const i = index(b.id);
              setBlocks([...blocks.slice(0, i + 1), ...fx.todos.map((t) => makeBlock('todo', t)), ...blocks.slice(i + 1)]);
            }
          }}
          onShareRows={sealed ? undefined : (rows) => setShare({ page: page.id, scope: 'rows', block: b.id, rows })}
          onShareView={sealed ? undefined : (view) => setShare({ page: page.id, scope: 'view', block: b.id, view })}
        />
      );
    if (b.type === 'chart') return <ChartBlock block={b} tables={tables} onChange={(c) => patch(b.id, { chart: c })} />;
    if (b.type === 'pomodoro') return <PomodoroBlock work={b.pomodoro?.work ?? 25} rest={b.pomodoro?.rest ?? 5} onChange={(p) => patch(b.id, { pomodoro: p })} />;
    if (b.type === 'image' && b.media)
      return (
        <div className="ws-image-edit">
          <div style={{ filter: b.media.edit?.filter || undefined, transform: `rotate(${b.media.edit?.rotate || 0}deg)${b.media.edit?.flip ? ' scaleX(-1)' : ''}` }}>
            <MediaBlock block={b} onMedia={(m) => patch(b.id, { media: m })} />
          </div>
          <div className="ws-media-tools">
            <MediaLook media={b.media} onMedia={(m) => patch(b.id, { media: m })} />
          </div>
        </div>
      );
    if (b.type === 'audio' || b.type === 'image') return <MediaBlock block={b} onMedia={(m) => patch(b.id, { media: m })} />;
    if (b.type === 'video') return <VideoBlock block={b} onMedia={(m) => patch(b.id, { media: m })} />;
    if (b.type === 'form')
      return (
        <FormBlock
          block={b}
          tables={tables}
          onChange={(f) => patch(b.id, { form: f })}
          onSubmitRow={(tableId, t) => patch(tableId, { table: t })}
          onShare={sealed ? undefined : () => setShare({ page: page.id, scope: 'page' })}
        />
      );
    if (b.type === 'button')
      return (
        <ButtonBlock
          block={b}
          page={{ ...page, blocks }}
          tables={tables}
          onChange={(spec) => patch(b.id, { button: spec })}
          onRun={(p) => setBlocks(p.blocks)}
          onOpenPage={followLink}
        />
      );
    if (b.type === 'dashboard') return <DashboardBlock tables={tables} />;
    if (b.type === 'mindmap') return <MindMapBlock nodes={b.mind || []} onChange={(m) => patch(b.id, { mind: m })} />;
    if (b.type === 'page') {
      const child = b.pageId ? pages[b.pageId] : undefined;
      return (
        <button type="button" className="nx-subpage" onClick={() => child && open(child.id)}>
          <span className="nx-subpage-icon">{child?.icon || <FileText size={18} strokeWidth={1.6} />}</span>
          <span className="nx-subpage-title">{titleOf(b.pageId || '') || b.text || 'Página'}</span>
        </button>
      );
    }
    return null;
  };

  return (
    <article
      className="ws-page nx-page"
      data-density={layout.density}
      data-font={style.font || 'default'}
      data-small={style.small || undefined}
      data-full={style.full || undefined}
      data-locked={locked || undefined}
      style={{ ['--ws-font' as string]: `${style.small ? Math.max(13, layout.fontSize - 1.5) : layout.fontSize}px` }}
    >
      <header className="nx-topbar">
        {!sidebarOpen && onToggleSidebar && (
          <button type="button" className="nx-icon" aria-label="Mostrar la barra" title="Mostrar la barra" onClick={onToggleSidebar}>
            <Menu size={17} />
          </button>
        )}
        <nav className="nx-crumbs" aria-label="Ruta">
          {path.map((p, i) => (
            <span key={p.id} className="nx-crumb-wrap">
              {i > 0 && <span className="nx-crumb-sep">/</span>}
              <button type="button" className="nx-crumb" onClick={() => open(p.id)}>
                {p.icon && <span className="nx-crumb-icon">{p.icon}</span>}
                <span className="truncate">{p.title || 'Sin título'}</span>
              </button>
            </span>
          ))}
          {locked && (
            <button type="button" className="nx-crumb nx-locked" onClick={() => setStyle({ locked: false })} title="Desbloquear">
              <Lock size={12} /> Bloqueada
            </button>
          )}
        </nav>
        <span className="nx-edited">{editedAgo(page.updatedAt)}</span>
        {!sealed && (
          <button type="button" className="nx-text-btn" onClick={() => setShare({ page: page.id, scope: 'page' })}>
            Compartir
          </button>
        )}
        <button type="button" className="nx-icon" aria-label="Comentarios" title="Comentarios" onClick={() => setCommenting(!commenting)}>
          <MessageSquare size={17} strokeWidth={1.6} />
        </button>
        <button type="button" className="nx-icon" aria-pressed={intel} aria-label="Sergio en esta página" title="Sergio en esta página" onClick={() => setIntel(!intel)}>
          <Brain size={17} strokeWidth={1.6} />
        </button>
        <span className="relative">
          <button type="button" className="nx-icon" aria-label="Pedir a Sergio" title="Pedir a Sergio" disabled={thinking} onClick={() => setMenu(menu === 'ai' ? null : 'ai')}>
            <Sparkles size={17} strokeWidth={1.6} className={thinking ? 'animate-pulse' : undefined} />
          </button>
          {menu === 'ai' && (
            <div className="nx-menu" role="menu" style={{ right: 0, left: 'auto', top: 34 }}>
              <div className="nx-menu-group">Sergio</div>
              {PAGE_ACTIONS.map((a) => (
                <button key={a.key} type="button" role="menuitem" onClick={() => (setMenu(null), void runAI(a.key))}>
                  <Sparkles size={15} /> {a.label}
                </button>
              ))}
            </div>
          )}
        </span>
        <button
          type="button"
          className="nx-icon"
          aria-pressed={!!page.favorite}
          aria-label={page.favorite ? 'Quitar de favoritos' : 'Añadir a favoritos'}
          title="Favorito"
          onClick={() => update(page.id, (p) => ({ ...p, favorite: !p.favorite }))}
        >
          <Star size={17} strokeWidth={1.6} fill={page.favorite ? '#f5c000' : 'none'} color={page.favorite ? '#f5c000' : 'currentColor'} />
        </button>
        <span className="relative">
          <button type="button" className="nx-icon" aria-label="Más" onClick={() => setMenu(menu === 'more' ? null : 'more')}>
            <MoreHorizontal size={18} />
          </button>
          {menu === 'more' && (
            <div className="nx-menu nx-more" role="menu" style={{ right: 0, left: 'auto', top: 34 }}>
              <div className="nx-fonts" role="group" aria-label="Letra">
                {(['default', 'serif', 'mono'] as const).map((f) => (
                  <button key={f} type="button" data-font={f} aria-pressed={(style.font || 'default') === f} onClick={() => setStyle({ font: f })}>
                    <span className="nx-font-ag">Ag</span>
                    <span>{f === 'default' ? 'Predeterminada' : f === 'serif' ? 'Serif' : 'Mono'}</span>
                  </button>
                ))}
              </div>
              <label className="nx-switch-row">
                Texto pequeño
                <input type="checkbox" checked={!!style.small} onChange={(e) => setStyle({ small: e.target.checked })} />
              </label>
              <label className="nx-switch-row">
                Ancho completo
                <input type="checkbox" checked={!!style.full} onChange={(e) => setStyle({ full: e.target.checked })} />
              </label>
              <label className="nx-switch-row">
                Bloquear página
                <input type="checkbox" checked={locked} onChange={(e) => setStyle({ locked: e.target.checked })} />
              </label>
              <div className="nx-menu-rule" />
              <button type="button" role="menuitem" onClick={() => (setMenu(null), setLockOpen(true))}>
                {sealed ? <Lock size={15} /> : <Unlock size={15} />} {sealed ? 'Cifrado de extremo a extremo' : 'Cifrar de extremo a extremo'}
              </button>
              <button type="button" role="menuitem" onClick={() => (setMenu(null), setFinder({ find: '', with: '' }))}>
                <Replace size={15} /> Buscar y reemplazar
              </button>
              <button type="button" role="menuitem" onClick={() => (setMenu(null), setHistory(true))}>
                <HistoryIcon size={15} /> Historial de versiones
              </button>
              <div className="nx-menu-rule" />
              <button type="button" role="menuitem" onClick={() => (setMenu(null), exportMd())}>
                <Download size={15} /> Exportar a Markdown
              </button>
              <button type="button" role="menuitem" onClick={() => (setMenu(null), void exportDocx())}>
                <FileDown size={15} /> Exportar a Word
              </button>
              <button type="button" role="menuitem" onClick={() => (setMenu(null), window.print())}>
                <Printer size={15} /> Imprimir o PDF
              </button>
              <div className="nx-menu-rule" />
              <button type="button" role="menuitem" onClick={() => (setMenu(null), void archive(page.id))}>
                <Archive size={15} /> Mover al baúl
              </button>
              <button
                type="button"
                role="menuitem"
                className="nx-danger"
                onClick={() => {
                  setMenu(null);
                  if (window.confirm(`¿Borrar «${page.title || 'Sin título'}»? Queda 30 días en la papelera del servidor.`)) remove(page.id);
                }}
              >
                <Trash2 size={15} /> Borrar
              </button>
              <div className="nx-menu-rule" />
              <div className="nx-menu-foot">
                Recuento de palabras: {words.toLocaleString('es')} · {Math.max(1, Math.round(words / 220))} min de lectura
                <br />
                {editedAgo(page.updatedAt)}
              </div>
            </div>
          )}
        </span>
      </header>

      <div className="nx-scroller">
        <PageHeader page={page} readOnly={locked} onChange={setPage} onComment={() => setCommenting(true)} />

        <div className="nx-content">
          <textarea
            className="ws-title nx-title"
            value={page.title}
            placeholder="Sin título"
            rows={1}
            readOnly={locked}
            autoFocus={!page.title && Date.now() - page.createdAt < 5000}
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

          {backlinks.length > 0 && (
            <div className="nx-backlinks">
              <button type="button" className="nx-text-btn nx-muted" onClick={() => setShowRefs(!showRefs)}>
                ↗ {backlinks.length} {backlinks.length === 1 ? 'referencia' : 'referencias'}
              </button>
              {showRefs &&
                backlinks.map((p) => (
                  <button key={p.id} type="button" className="nx-page-mention" onClick={() => open(p.id)}>
                    {p.icon || '📄'} {p.title || 'Sin título'}
                  </button>
                ))}
            </div>
          )}

          <Comments comments={comments} blocks={blocks} focus={commenting} onChange={(next) => setPage({ comments: next })} />

          <div className="ws-blocks nx-blocks">
            {live.map((b) => {
              numberRun = b.type === 'number' ? numberRun + 1 : 0;
              const textual = TEXTUAL.includes(b.type);
              const links = textual ? [...b.text.matchAll(/\[\[([^\]\n]{1,120})\]\]/g)].map((m) => m[1].trim()) : [];
              const [summary, ...rest] = b.type === 'toggle' ? b.text.split('\n') : [b.text];
              const { text: fg, bg } = colorParts(b.color);
              const commentCount = comments.filter((c) => c.block === b.id && !c.resolved).length;
              return (
                <div
                  key={b.id}
                  className="ws-block nx-block"
                  data-type={b.type}
                  data-color={fg || undefined}
                  data-bg={bg || undefined}
                  data-dragging={dragging === b.id || undefined}
                  data-drop={dropAt?.id === b.id ? (dropAt.after ? 'after' : 'before') : undefined}
                  data-conflict={b.conflict || undefined}
                  data-done={b.type === 'todo' && b.checked ? 'true' : undefined}
                  onDragOver={(e) => {
                    if (!draggingRef.current) return;
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                    const r = e.currentTarget.getBoundingClientRect();
                    const after = e.clientY > r.top + r.height / 2;
                    if (dropAt?.id !== b.id || dropAt.after !== after) setDropAt({ id: b.id, after });
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    const r = e.currentTarget.getBoundingClientRect();
                    if (draggingRef.current) moveTo(draggingRef.current, b.id, e.clientY > r.top + r.height / 2);
                    draggingRef.current = null;
                    setDragging(null);
                    setDropAt(null);
                  }}
                >
                  {b.conflict && (
                    <span className="ws-conflict">
                      Editado a la vez
                      <button type="button" className="paper-tab" onClick={() => patch(b.id, { conflict: undefined })}>
                        Quedarse
                      </button>
                      <button type="button" className="paper-tab" onClick={() => setBlocks(blocks.filter((x) => x.id !== b.id))}>
                        Descartar
                      </button>
                    </span>
                  )}
                  {!locked && (
                    <span className="nx-gutter">
                      <button
                        type="button"
                        className="nx-gutter-btn"
                        aria-label="Añadir un bloque debajo"
                        title="Clic para añadir un bloque debajo"
                        onClick={() => {
                          const fresh = makeBlock('text', '/');
                          insertAfter(b.id, fresh);
                          setSlash({ id: fresh.id, query: '', index: 0 });
                          setFocusAt({ id: fresh.id, pos: 1 });
                        }}
                      >
                        <Plus size={16} strokeWidth={1.6} />
                      </button>
                      <button
                        type="button"
                        className="nx-gutter-btn nx-drag"
                        draggable
                        aria-label="Arrastre para mover · clic para el menú"
                        title="Arrastre para mover · clic para abrir el menú"
                        onDragStart={(e) => {
                          draggingRef.current = b.id;
                          setDragging(b.id);
                          e.dataTransfer.effectAllowed = 'move';
                          e.dataTransfer.setData('text/plain', b.text || ' ');
                        }}
                        onDragEnd={() => ((draggingRef.current = null), setDragging(null), setDropAt(null))}
                        onClick={() => setMenu(menu === b.id ? null : b.id)}
                      >
                        <GripVertical size={16} strokeWidth={1.6} />
                      </button>
                      {menu === b.id && (
                        <BlockMenu
                          block={b}
                          canShare={!sealed}
                          onTurnInto={(t) => turnInto(b.id, t)}
                          onColor={(c) => patch(b.id, { color: c || undefined })}
                          onMove={(dir) => move(b.id, dir)}
                          onDuplicate={() => insertAfter(b.id, { ...structuredClone(b), id: newId('b') })}
                          onDelete={() => setBlocks(blocks.length > 1 ? blocks.filter((x) => x.id !== b.id) : [makeBlock('text')])}
                          onShare={() => setShare({ page: page.id, scope: 'block', block: b.id })}
                          onComment={() => (addComment({ text: `Sobre «${(b.text || b.type).slice(0, 60)}»`, block: b.id }), setCommenting(true))}
                          onClose={() => setMenu(null)}
                        />
                      )}
                    </span>
                  )}
                  <div className="ws-body nx-body">
                    {b.type === 'todo' && (
                      <input
                        type="checkbox"
                        className="ws-check nx-check"
                        checked={!!b.checked}
                        disabled={locked}
                        onChange={(e) => patch(b.id, { checked: e.target.checked, doneAt: e.target.checked ? Date.now() : undefined })}
                        aria-label="Hecha"
                      />
                    )}
                    {b.type === 'bullet' && <span className="ws-marker nx-marker">•</span>}
                    {b.type === 'number' && <span className="ws-marker nx-marker">{numberRun}.</span>}
                    {b.type === 'callout' && <span className="nx-callout-icon">💡</span>}
                    {b.type === 'toggle' && (
                      <button type="button" className="ws-marker nx-marker" onClick={() => patch(b.id, { open: !b.open })} aria-label={b.open ? 'Plegar' : 'Desplegar'} aria-expanded={!!b.open}>
                        {b.open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      </button>
                    )}
                    {renderBody(b, textual, links, summary, rest)}
                    {commentCount > 0 && (
                      <button type="button" className="nx-block-comments" onClick={() => setCommenting(true)} aria-label={`${commentCount} comentarios`}>
                        <MessageSquare size={13} /> {commentCount}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
            {!locked && (
              <button
                type="button"
                className="nx-tail"
                aria-label="Añadir un bloque al final"
                onClick={() => {
                  const last = live[live.length - 1];
                  if (last && last.type === 'text' && !last.text) setFocusAt({ id: last.id, pos: 0 });
                  else insertAfter(blocks[blocks.length - 1]?.id || '', makeBlock('text'));
                }}
              />
            )}
          </div>

          {vaulted.length > 0 && (
            <div className="ws-footer-note">
              <button type="button" className="nx-text-btn nx-muted" onClick={() => setShowVault(!showVault)}>
                {vaulted.length} {vaulted.length === 1 ? 'tarea terminada' : 'tareas terminadas'} en el baúl {showVault ? '▴' : '▾'}
              </button>
              {showVault && (
                <ul className="mt-2 text-[13px]" style={{ color: 'var(--nx-text-2)' }}>
                  {vaulted.map((b) => (
                    <li key={b.id} className="flex items-center gap-2">
                      ☑ {b.text}
                      <button type="button" className="nx-text-btn" onClick={() => patch(b.id, { archived: false })}>
                        devolver
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>

      {menu && <button type="button" className="nx-click-away" aria-label="Cerrar" onClick={() => setMenu(null)} />}

      {finder && (
        <div className="ws-finder" role="dialog" aria-label="Buscar y reemplazar">
          <input autoFocus className="ws-mini-input" placeholder="Buscar" value={finder.find} onChange={(e) => setFinder({ ...finder, find: e.target.value })} />
          <input className="ws-mini-input" placeholder="Reemplazar por" value={finder.with} onChange={(e) => setFinder({ ...finder, with: e.target.value })} />
          <span className="text-[12px]">{finder.find ? live.reduce((n, b) => n + (b.text.toLowerCase().split(finder.find.toLowerCase()).length - 1), 0) : 0}</span>
          <button type="button" className="paper-tab" onClick={() => toast.success(`${replaceAll(finder.find, finder.with)} cambios.`)}>
            Reemplazar todo
          </button>
          <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={() => setFinder(null)}>
            ×
          </button>
        </div>
      )}

      {intel && <IntelPanel page={page} blocks={blocks} onBlocks={setBlocks} onClose={() => setIntel(false)} />}

      {share && <ShareDialog target={share} onClose={() => setShare(null)} />}
      {history && (
        <HistoryDialog
          page={{ ...page, blocks }}
          onBlocks={setBlocks}
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
