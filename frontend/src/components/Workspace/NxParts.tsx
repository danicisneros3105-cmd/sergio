// The pieces of a page that make it look and feel like the familiar notes
// app: cover and icon, comments, the grouped «/» menu, the block menu, the
// formatting bar and inline-formatted text. PageEditor puts them together.

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlignLeft,
  ArrowDown,
  ArrowUp,
  AtSign,
  Bold,
  BookMarked,
  ChevronRight,
  Code,
  Copy,
  FileText,
  Film,
  FormInput,
  Hash,
  Heading1,
  Heading2,
  Heading3,
  Image as ImageIcon,
  Italic,
  LayoutDashboard,
  Link2,
  List,
  ListChecks,
  ListOrdered,
  ListTree,
  MessageSquare,
  Minus,
  Mic,
  MousePointerClick,
  Network,
  PieChart,
  Quote,
  Share2,
  Sigma,
  Smile,
  Strikethrough,
  Table2,
  Timer,
  Trash2,
  Underline,
  Lightbulb,
  ChevronsRight,
} from 'lucide-react';
import type { Block, BlockType, Comment, Page } from '../../lib/workspace/model';
import { newId, slashMatches } from '../../lib/workspace/model';
import { COLORS, COVERS, EMOJI, SLASH_GROUPS, coverCss, groupOf, parseInline, randomEmoji } from '../../lib/workspace/notion';
import { mediaUrl, saveMedia } from '../../lib/workspace/store';

export const TYPE_ICON: Record<BlockType, typeof FileText> = {
  text: AlignLeft,
  h1: Heading1,
  h2: Heading2,
  h3: Heading3,
  todo: ListChecks,
  bullet: List,
  number: ListOrdered,
  quote: Quote,
  callout: Lightbulb,
  code: Code,
  divider: Minus,
  toggle: ChevronsRight,
  table: Table2,
  chart: PieChart,
  pomodoro: Timer,
  audio: Mic,
  image: ImageIcon,
  mindmap: Network,
  equation: Sigma,
  toc: ListTree,
  bookmark: BookMarked,
  page: FileText,
  form: FormInput,
  button: MousePointerClick,
  dashboard: LayoutDashboard,
  video: Film,
};

// -- cover and icon ---------------------------------------------------------------
function useCoverImage(cover: string | null | undefined): string {
  const [url, setUrl] = useState('');
  useEffect(() => {
    if (!cover?.startsWith('file:')) return setUrl('');
    let gone = false;
    const file = cover.slice(5);
    void mediaUrl({ file, name: 'portada', mime: 'image/*' }).then((u) => !gone && setUrl(u));
    return () => {
      gone = true;
    };
  }, [cover]);
  return url;
}

export function PageHeader({
  page,
  readOnly,
  onChange,
  onComment,
}: {
  page: Page;
  readOnly: boolean;
  onChange: (change: Partial<Page>) => void;
  onComment: () => void;
}) {
  const [picker, setPicker] = useState<null | 'icon' | 'cover'>(null);
  const image = useCoverImage(page.cover);
  const css = coverCss(page.cover);
  const hasCover = !!page.cover && (!!css || !!image);
  return (
    <div className="nx-head" data-cover={hasCover || undefined} data-icon={!!page.icon || undefined}>
      {hasCover && (
        <div
          className="nx-cover"
          style={image ? { backgroundImage: `url(${image})`, backgroundPosition: `center ${page.coverY ?? 50}%` } : { background: css }}
        >
          {!readOnly && (
            <span className="nx-cover-tools">
              <button type="button" onClick={() => setPicker('cover')}>
                Cambiar portada
              </button>
              {image && (
                <button type="button" onClick={() => onChange({ coverY: ((page.coverY ?? 50) + 25) % 125 })}>
                  Reposicionar
                </button>
              )}
            </span>
          )}
        </div>
      )}
      <div className="nx-head-inner">
        {page.icon && (
          <button type="button" className="nx-page-icon" aria-label="Cambiar icono" disabled={readOnly} onClick={() => setPicker('icon')}>
            {page.icon}
          </button>
        )}
        {!readOnly && (
          <div className="nx-head-actions">
            {!page.icon && (
              <button type="button" onClick={() => onChange({ icon: randomEmoji() })}>
                <Smile size={15} /> Añadir icono
              </button>
            )}
            {!hasCover && (
              <button type="button" onClick={() => onChange({ cover: COVERS[Math.floor(Math.random() * 6)].key })}>
                <ImageIcon size={15} /> Añadir portada
              </button>
            )}
            <button type="button" onClick={onComment}>
              <MessageSquare size={15} /> Añadir comentario
            </button>
          </div>
        )}
        {picker === 'icon' && (
          <div className="nx-menu nx-emoji-picker" role="dialog" aria-label="Icono">
            <div className="nx-menu-head">
              <span>Emoji</span>
              <button type="button" onClick={() => (onChange({ icon: '' }), setPicker(null))}>
                Quitar
              </button>
            </div>
            <div className="nx-emoji-grid">
              {EMOJI.map((e) => (
                <button key={e} type="button" onClick={() => (onChange({ icon: e }), setPicker(null))}>
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}
        {picker === 'cover' && (
          <div className="nx-menu nx-cover-picker" role="dialog" aria-label="Portada">
            <div className="nx-menu-head">
              <span>Galería</span>
              <span className="flex gap-2">
                <label className="nx-link-btn">
                  Subir
                  <input
                    type="file"
                    accept="image/*"
                    hidden
                    onChange={async (e) => {
                      const f = e.target.files?.[0];
                      if (!f) return;
                      const m = await saveMedia(f, f.name);
                      onChange({ cover: `file:${m.file}`, coverY: 50 });
                      setPicker(null);
                    }}
                  />
                </label>
                <button type="button" onClick={() => (onChange({ cover: null }), setPicker(null))}>
                  Quitar
                </button>
              </span>
            </div>
            <div className="nx-cover-grid">
              {COVERS.map((c) => (
                <button key={c.key} type="button" title={c.name} style={{ background: c.css }} onClick={() => (onChange({ cover: c.key }), setPicker(null))} />
              ))}
            </div>
          </div>
        )}
        {picker && <button type="button" className="nx-click-away" aria-label="Cerrar" onClick={() => setPicker(null)} />}
      </div>
    </div>
  );
}

// -- comments --------------------------------------------------------------------
export function Comments({
  comments,
  blocks,
  focus,
  onChange,
}: {
  comments: Comment[];
  blocks: Block[];
  focus: boolean;
  onChange: (next: Comment[]) => void;
}) {
  const [text, setText] = useState('');
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (focus) box.current?.focus();
  }, [focus]);
  const open = comments.filter((c) => !c.resolved);
  if (!open.length && !focus) return null;
  return (
    <section className="nx-comments" aria-label="Comentarios">
      {open.map((c) => {
        const quoted = c.block ? blocks.find((b) => b.id === c.block)?.text : '';
        return (
          <div key={c.id} className="nx-comment">
            <span className="nx-avatar">S</span>
            <div className="min-w-0 flex-1">
              <div className="nx-comment-meta">
                <strong>Señor</strong>
                <span>{new Date(c.at).toLocaleString('es', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
              </div>
              {quoted && <div className="nx-comment-quote">{quoted.slice(0, 120)}</div>}
              <div className="nx-comment-text">{c.text}</div>
            </div>
            <button type="button" className="nx-icon" title="Resolver" aria-label="Resolver" onClick={() => onChange(comments.map((x) => (x.id === c.id ? { ...x, resolved: true } : x)))}>
              ✓
            </button>
          </div>
        );
      })}
      <form
        className="nx-comment nx-comment-new"
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim()) return;
          onChange([...comments, { id: newId('m'), text: text.trim(), at: Date.now() }]);
          setText('');
        }}
      >
        <span className="nx-avatar">S</span>
        <textarea
          ref={box}
          rows={1}
          value={text}
          placeholder="Añadir un comentario…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          aria-label="Comentario"
        />
      </form>
    </section>
  );
}

// -- «/» menu --------------------------------------------------------------------
export function SlashMenu({ query, index, onPick }: { query: string; index: number; onPick: (type: BlockType) => void }) {
  const options = slashOrder(query);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
  }, [index]);
  let shown = '';
  return (
    <div ref={ref} className="nx-menu nx-slash" role="listbox" aria-label="Insertar bloque">
      {options.length === 0 && <div className="nx-menu-empty">Sin resultados</div>}
      {options.map((s, i) => {
        const group = query ? 'Resultados' : groupOf(s.type);
        const head = group !== shown ? (shown = group) : null;
        const Icon = TYPE_ICON[s.type] ?? FileText;
        return (
          <div key={s.type}>
            {head && <div className="nx-menu-group">{head}</div>}
            <button
              type="button"
              role="option"
              aria-selected={i === index}
              onMouseDown={(e) => {
                e.preventDefault();
                onPick(s.type);
              }}
            >
              <span className="nx-slash-icon">
                <Icon size={20} strokeWidth={1.4} />
              </span>
              <span className="min-w-0">
                <span className="nx-slash-label">{s.label}</span>
                <span className="nx-slash-hint">{s.hint}</span>
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}

// Orders the «/» list the way the menu shows it (grouped), so the arrow keys
// walk it in the same order.
export function slashOrder(query: string) {
  const all = slashMatches(query);
  if (query) return all;
  return SLASH_GROUPS.flatMap((g) => all.filter((s) => groupOf(s.type) === g.name));
}

// -- «@» menu --------------------------------------------------------------------
export function MentionMenu({ pages, query, onPick }: { pages: Page[]; query: string; onPick: (p: Page) => void }) {
  const q = query.toLowerCase();
  const found = pages.filter((p) => !p.archived && (p.title || 'sin título').toLowerCase().includes(q)).slice(0, 8);
  return (
    <div className="nx-menu nx-mention" role="listbox" aria-label="Mencionar una página">
      <div className="nx-menu-group">
        <AtSign size={12} className="inline mr-1" />
        Páginas
      </div>
      {found.length === 0 && <div className="nx-menu-empty">Sin páginas con «{query}»</div>}
      {found.map((p) => (
        <button
          key={p.id}
          type="button"
          role="option"
          onMouseDown={(e) => {
            e.preventDefault();
            onPick(p);
          }}
        >
          <span className="nx-mention-icon">{p.icon || <FileText size={15} />}</span>
          {p.title || 'Sin título'}
        </button>
      ))}
    </div>
  );
}

// -- block menu (the ⋮⋮ handle) -----------------------------------------------------
export function BlockMenu({
  block,
  canShare,
  onTurnInto,
  onColor,
  onMove,
  onDuplicate,
  onDelete,
  onShare,
  onComment,
  onClose,
}: {
  block: Block;
  canShare: boolean;
  onTurnInto: (t: BlockType) => void;
  onColor: (c: string) => void;
  onMove: (dir: -1 | 1) => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onShare: () => void;
  onComment: () => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState('');
  const [sub, setSub] = useState<null | 'turn' | 'color'>(null);
  const actions = useMemo(
    () =>
      [
        { key: 'delete', label: 'Borrar', hint: 'Supr', icon: Trash2, run: onDelete },
        { key: 'dup', label: 'Duplicar', hint: 'Ctrl+D', icon: Copy, run: onDuplicate },
        { key: 'turn', label: 'Convertir en', icon: Hash, sub: 'turn' as const },
        { key: 'color', label: 'Color', icon: PaintIcon, sub: 'color' as const },
        { key: 'comment', label: 'Comentar', icon: MessageSquare, run: onComment },
        { key: 'up', label: 'Subir', hint: 'Alt+↑', icon: ArrowUp, run: () => onMove(-1) },
        { key: 'down', label: 'Bajar', hint: 'Alt+↓', icon: ArrowDown, run: () => onMove(1) },
        ...(canShare ? [{ key: 'share', label: 'Compartir solo este bloque', icon: Share2, run: onShare }] : []),
      ].filter((a) => !q || a.label.toLowerCase().includes(q.toLowerCase())),
    [q, canShare, onDelete, onDuplicate, onComment, onMove, onShare],
  );
  return (
    <div className="nx-menu nx-block-menu" role="menu" onKeyDown={(e) => e.key === 'Escape' && onClose()}>
      <input autoFocus className="nx-menu-search" placeholder="Buscar acciones…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar acciones" />
      {actions.map((a) => (
        <button
          key={a.key}
          type="button"
          role="menuitem"
          className={a.key === 'delete' ? 'nx-danger' : undefined}
          onMouseEnter={() => setSub('sub' in a && a.sub ? a.sub : null)}
          onClick={() => ('sub' in a && a.sub ? setSub(a.sub) : (a.run?.(), onClose()))}
        >
          <a.icon size={16} strokeWidth={1.5} />
          <span className="flex-1">{a.label}</span>
          {'hint' in a && a.hint && <span className="nx-menu-hint">{a.hint}</span>}
          {'sub' in a && a.sub && <ChevronRight size={14} />}
        </button>
      ))}
      {sub === 'turn' && (
        <div className="nx-menu nx-submenu" role="menu">
          {(['text', 'h1', 'h2', 'h3', 'page', 'todo', 'bullet', 'number', 'toggle', 'code', 'quote', 'callout'] as BlockType[]).map((t) => {
            const Icon = TYPE_ICON[t];
            return (
              <button key={t} type="button" role="menuitem" aria-checked={block.type === t} onClick={() => (onTurnInto(t), onClose())}>
                <Icon size={16} strokeWidth={1.5} />
                <span className="flex-1">{slashMatches('').find((s) => s.type === t)?.label}</span>
                {block.type === t && '✓'}
              </button>
            );
          })}
        </div>
      )}
      {sub === 'color' && (
        <div className="nx-menu nx-submenu" role="menu">
          <div className="nx-menu-group">Color</div>
          <button type="button" role="menuitem" onClick={() => (onColor(''), onClose())}>
            <span className="nx-swatch">A</span> Predeterminado
          </button>
          {COLORS.map((c) => (
            <button key={c.key} type="button" role="menuitem" onClick={() => (onColor(c.key), onClose())}>
              <span className="nx-swatch" data-color={c.key}>
                A
              </span>
              {c.name}
            </button>
          ))}
          <div className="nx-menu-group">Fondo</div>
          {COLORS.map((c) => (
            <button key={`${c.key}_bg`} type="button" role="menuitem" onClick={() => (onColor(`${c.key}_bg`), onClose())}>
              <span className="nx-swatch" data-bg={c.key}>
                A
              </span>
              Fondo {c.name.toLowerCase()}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function PaintIcon(props: { size?: number; strokeWidth?: number }) {
  return (
    <span className="nx-paint" style={{ width: props.size, height: props.size }}>
      A
    </span>
  );
}

// -- formatting bar (appears over a selection) -------------------------------------
export function FormatBar({
  onMark,
  onLink,
  onComment,
  onTurn,
  type,
}: {
  onMark: (m: 'bold' | 'italic' | 'underline' | 'strike' | 'code') => void;
  onLink: () => void;
  onComment: () => void;
  onTurn: () => void;
  type: BlockType;
}) {
  const label = slashMatches('').find((s) => s.type === type)?.label || 'Texto';
  const keep = (e: React.MouseEvent) => e.preventDefault(); // keep the selection
  return (
    <div className="nx-formatbar" role="toolbar" aria-label="Formato" onMouseDown={keep}>
      <button type="button" onClick={onTurn}>
        {label} <ChevronRight size={12} className="rotate-90" />
      </button>
      <span className="nx-sep" />
      <button type="button" onClick={onLink} aria-label="Enlace">
        <Link2 size={15} />
      </button>
      <span className="nx-sep" />
      <button type="button" onClick={() => onMark('bold')} aria-label="Negrita" title="Negrita (Ctrl+B)">
        <Bold size={15} />
      </button>
      <button type="button" onClick={() => onMark('italic')} aria-label="Cursiva" title="Cursiva (Ctrl+I)">
        <Italic size={15} />
      </button>
      <button type="button" onClick={() => onMark('underline')} aria-label="Subrayado" title="Subrayado (Ctrl+U)">
        <Underline size={15} />
      </button>
      <button type="button" onClick={() => onMark('strike')} aria-label="Tachado" title="Tachado (Ctrl+Mayús+S)">
        <Strikethrough size={15} />
      </button>
      <button type="button" onClick={() => onMark('code')} aria-label="Código" title="Código (Ctrl+E)">
        <Code size={15} />
      </button>
      <span className="nx-sep" />
      <button type="button" onClick={onComment} aria-label="Comentar">
        <MessageSquare size={15} />
      </button>
    </div>
  );
}

// -- text shown formatted when not being edited ------------------------------------
export function RichText({ text, onPage, onClick }: { text: string; onPage: (title: string) => void; onClick: () => void }) {
  return (
    <div className="nx-rich" onClick={onClick}>
      {parseInline(text).map((p, i) => {
        switch (p.kind) {
          case 'bold':
            return <strong key={i}>{p.text}</strong>;
          case 'italic':
            return <em key={i}>{p.text}</em>;
          case 'underline':
            return <u key={i}>{p.text}</u>;
          case 'strike':
            return <s key={i}>{p.text}</s>;
          case 'code':
            return (
              <code key={i} className="nx-inline-code">
                {p.text}
              </code>
            );
          case 'link':
            return (
              <a key={i} href={p.href} target="_blank" rel="noreferrer" className="nx-a" onClick={(e) => e.stopPropagation()}>
                {p.text}
              </a>
            );
          case 'page':
            return (
              <button
                key={i}
                type="button"
                className="nx-page-mention"
                onClick={(e) => {
                  e.stopPropagation();
                  onPage(p.text);
                }}
              >
                <FileText size={14} className="inline" /> {p.text}
              </button>
            );
          default:
            return <span key={i}>{p.text}</span>;
        }
      })}
    </div>
  );
}

