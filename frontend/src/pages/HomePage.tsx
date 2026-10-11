import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  Briefcase,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  HeartPulse,
  LayoutGrid,
  List,
  Lock,
  MessageSquarePlus,
  Network,
  FilePlus2,
  UserRound,
} from 'lucide-react';
import { PaperHead } from '../components/Paper/PaperPage';
import { useAppStore } from '../lib/store';
import { useWorkspace } from '../lib/workspace/store';
import {
  conversationItems,
  FILTERS,
  filterItems,
  loadMarks,
  pageItems,
  paginate,
  saveMarks,
  SORTS,
  sortItems,
  toggleMark,
  type FilterKey,
  type LibraryItem,
  type SortKey,
} from '../lib/library';

const ICONS: Record<string, typeof Briefcase> = { briefcase: Briefcase, network: Network, heart: HeartPulse, user: UserRound, lock: Lock };
const PER_PAGE = 8;

// The bookmark ribbon of a marked document (top right of its tile).
function Ribbon({ on, onToggle, label }: { on: boolean; onToggle: () => void; label: string }) {
  return (
    <span
      role="button"
      tabIndex={0}
      className="paper-mark"
      aria-pressed={on}
      aria-label={on ? `Quitar «${label}» de Marcados` : `Marcar «${label}»`}
      title={on ? 'Quitar de Marcados' : 'Marcar'}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.stopPropagation();
          onToggle();
        }
      }}
      style={{ opacity: on ? 1 : undefined }}
    >
      <svg viewBox="0 0 12 18" width="12" height="18" aria-hidden="true">
        <path d="M1 0h10v17l-5-4-5 4z" fill={on ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1" />
      </svg>
    </span>
  );
}

function Thumb({ item }: { item: LibraryItem }) {
  if (item.kind === 'section' || (item.icon && !item.lines.length)) {
    const Icon = ICONS[item.icon || ''] || Briefcase;
    return <Icon size={34} strokeWidth={1.05} />;
  }
  return (
    <span className="paper-insert" aria-hidden="true">
      {item.lines.slice(0, 7).map((line, i) => (
        <span key={i} className="block truncate" style={{ fontSize: i === 0 ? 7.5 : 6.5, lineHeight: 1.55, fontWeight: i === 0 ? 600 : 400, color: 'var(--color-text-secondary)' }}>
          {line}
        </span>
      ))}
    </span>
  );
}

function Shelf({
  items,
  marks,
  onToggle,
  onOpen,
  view,
}: {
  items: LibraryItem[];
  marks: string[];
  onToggle: (id: string) => void;
  onOpen: (item: LibraryItem) => void;
  view: 'grid' | 'list';
}) {
  if (view === 'list') {
    return (
      <div className="paper-list">
        {items.map((item) => (
          <button key={item.id} type="button" className="paper-list-row" onClick={() => onOpen(item)}>
            <span className="paper-list-thumb">
              <Thumb item={item} />
            </span>
            <span className="min-w-0 flex-1 text-left">
              <span className="paper-name block truncate">{item.title}</span>
              <span className="paper-meta block truncate">{item.meta}</span>
            </span>
            <Ribbon on={marks.includes(item.id)} onToggle={() => onToggle(item.id)} label={item.title} />
          </button>
        ))}
      </div>
    );
  }
  return (
    <div className="paper-grid">
      {items.map((item) => (
        <button key={item.id} type="button" className="paper-card" onClick={() => onOpen(item)}>
          <span className="paper-thumb">
            <Thumb item={item} />
            <Ribbon on={marks.includes(item.id)} onToggle={() => onToggle(item.id)} label={item.title} />
          </span>
          <span className="min-w-0">
            <span className="paper-name block truncate">{item.title}</span>
            <span className="paper-meta block truncate">{item.meta}</span>
          </span>
        </button>
      ))}
    </div>
  );
}

function SortSelect({ value, onChange }: { value: SortKey; onChange: (s: SortKey) => void }) {
  return (
    <label className="paper-select">
      <select value={value} onChange={(e) => onChange(e.target.value as SortKey)} aria-label="Ordenar">
        {SORTS.map((s) => (
          <option key={s.key} value={s.key}>
            {s.label}
          </option>
        ))}
      </select>
      <ChevronDown size={12} style={{ marginLeft: -14, pointerEvents: 'none' }} />
    </label>
  );
}

// Inicio: the e-paper home screen. «Marcados» on top, then everything you
// keep (conversations and pages) with tabs, a sort and pages. The sections
// are only icons, in the toolbar.
export function HomePage() {
  const navigate = useNavigate();
  const conversations = useAppStore((s) => s.conversations);
  const selectConversation = useAppStore((s) => s.selectConversation);
  const createConversation = useAppStore((s) => s.createConversation);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const pages = useWorkspace((s) => s.pages);
  const ready = useWorkspace((s) => s.ready);
  const load = useWorkspace((s) => s.load);
  const create = useWorkspace((s) => s.create);
  const [marks, setMarks] = useState<string[]>(() => loadMarks());
  const [allMarked, setAllMarked] = useState(false);
  const [markSort, setMarkSort] = useState<SortKey>('recent');
  const [sort, setSort] = useState<SortKey>('recent');
  const [filter, setFilter] = useState<FilterKey>('all');
  const [page, setPage] = useState(1);
  const [view, setView] = useState<'grid' | 'list'>(() => {
    try {
      return localStorage.getItem('sergio-home-view') === 'list' ? 'list' : 'grid';
    } catch {
      return 'grid';
    }
  });

  useEffect(() => {
    if (!ready) void load();
  }, [ready, load]);

  const everything = useMemo(
    () => [...conversationItems(conversations), ...pageItems(Object.values(pages))],
    [conversations, pages],
  );
  const marked = sortItems(everything.filter((i) => marks.includes(i.id)), markSort);
  const shown = paginate(sortItems(filterItems(everything, filter), sort), page, PER_PAGE);

  const toggle = (id: string) => {
    const next = toggleMark(marks, id);
    setMarks(next);
    saveMarks(next);
  };
  const openItem = (item: LibraryItem) => {
    if (item.kind === 'conversation') {
      selectConversation(item.id.slice('conversation:'.length));
      navigate('/chat');
    } else navigate(item.path);
  };
  const setViewKept = (v: 'grid' | 'list') => {
    setView(v);
    try {
      localStorage.setItem('sergio-home-view', v);
    } catch {
      // per-viewer convenience only
    }
  };

  return (
    <div className="paper-page">
      <div className="paper-page-inner">
        <PaperHead
          title="Inicio"
          right={
            <>
              <button type="button" className="mac-icon-btn" aria-label="Nueva conversación" title="Nueva conversación" onClick={() => (createConversation(selectedModel), navigate('/chat'))}>
                <MessageSquarePlus size={17} strokeWidth={1.3} />
              </button>
              <button type="button" className="mac-icon-btn" aria-label="Nueva página" title="Nueva página" onClick={() => navigate(`/workspace/${create({ open: true }).id}`)}>
                <FilePlus2 size={17} strokeWidth={1.3} />
              </button>
              <button
                type="button"
                className="mac-icon-btn"
                aria-label={view === 'grid' ? 'Ver como lista' : 'Ver como cuadrícula'}
                title={view === 'grid' ? 'Lista' : 'Cuadrícula'}
                onClick={() => setViewKept(view === 'grid' ? 'list' : 'grid')}
              >
                {view === 'grid' ? <List size={17} strokeWidth={1.3} /> : <LayoutGrid size={17} strokeWidth={1.3} />}
              </button>
            </>
          }
        />

        <section aria-label="Marcados">
          <div className="paper-bar">
            <div className="paper-tabs">
              <span className="paper-tab" aria-selected="true">
                Marcados
              </span>
              {marked.length > 4 && (
                <button type="button" className="paper-select" onClick={() => setAllMarked(!allMarked)}>
                  {allMarked ? 'Ver menos' : 'Ver todo'} <ChevronDown size={12} style={{ transform: allMarked ? 'rotate(180deg)' : undefined }} />
                </button>
              )}
            </div>
            <SortSelect value={markSort} onChange={setMarkSort} />
          </div>
          {marked.length ? (
            <Shelf items={allMarked ? marked : marked.slice(0, 4)} marks={marks} onToggle={toggle} onOpen={openItem} view={view} />
          ) : (
            <p className="paper-empty">Marque cualquier documento con la cinta de su esquina y aparecerá aquí.</p>
          )}
        </section>

        <section aria-label="Todo" style={{ marginTop: 40 }}>
          <div className="paper-bar">
            <div className="paper-tabs" role="tablist">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  role="tab"
                  className="paper-tab"
                  aria-selected={filter === f.key}
                  onClick={() => (setFilter(f.key), setPage(1))}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <SortSelect value={sort} onChange={(s) => (setSort(s), setPage(1))} />
          </div>
          {shown.items.length ? (
            <Shelf items={shown.items} marks={marks} onToggle={toggle} onOpen={openItem} view={view} />
          ) : (
            <p className="paper-empty">
              {filter === 'page' ? 'Aún no hay páginas: cree la primera con el botón de arriba.' : 'Aún no hay nada aquí.'}
            </p>
          )}
          {shown.pages > 1 && (
            <nav className="paper-pager" aria-label="Páginas">
              <button type="button" disabled={shown.page <= 1} onClick={() => setPage(shown.page - 1)} aria-label="Anterior">
                <ChevronLeft size={14} />
              </button>
              <span>
                {shown.page} de {shown.pages}
              </span>
              <button type="button" disabled={shown.page >= shown.pages} onClick={() => setPage(shown.page + 1)} aria-label="Siguiente">
                <ChevronRight size={14} />
              </button>
            </nav>
          )}
        </section>
      </div>
    </div>
  );
}

export default HomePage;
