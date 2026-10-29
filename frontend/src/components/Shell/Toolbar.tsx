import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import {
  Puzzle,
  SquarePen,
  Search,
  PanelLeft,
  NotebookPen,
  Briefcase,
  HeartPulse,
  UserRound,
  Settings,
  Library,
  MessageSquare,
  ScanFace,
  Gauge,
  FolderKanban,
  ChevronDown,
  Zap,
} from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { LiveOrb } from '../Live/LiveOrb';
import { ChatSections, ConversationList } from '../Sidebar/ConversationList';
import { UpdateButton } from './UpdateButton';
import { apiFetch } from '../../lib/api';
import { overallPercent } from '../../lib/plans';

// Nodes: a few dots, like the persistent agents they are.
function NodesIcon({ size = 20, strokeWidth = 1.5 }: { size?: number; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} aria-hidden="true">
      <circle cx="8" cy="9" r="4.2" />
      <circle cx="16.5" cy="15.5" r="3.2" />
      <circle cx="17.5" cy="6.5" r="1.6" />
    </svg>
  );
}

// Agent Swarm: many small agents at once.
function SwarmIcon({ size = 20, strokeWidth = 1.5 }: { size?: number; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} aria-hidden="true">
      <circle cx="12" cy="5" r="2" />
      <circle cx="5" cy="12" r="2" />
      <circle cx="19" cy="12" r="2" />
      <circle cx="8" cy="19" r="2" />
      <circle cx="16" cy="19" r="2" />
      <path d="M12 7v3.2M10.4 11.2 6.8 12M13.6 11.2l3.6.8M11 13.4l-2.2 3.8M13 13.4l2.2 3.8" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

// Sergio's parts, listed in the sidebar like ChatGPT lists GPTs and
// projects: plain monochrome icons and names. Simple first (owner, oct.
// 2026: a child of 5 and a grandmother of 84 must find their way): only the
// everyday ones are always visible; the rest wait under «Más».
export const TOOLBAR_ITEMS = [
  { path: '/chat', icon: MessageSquare, label: 'Chat', more: false },
  { path: '/nodes', icon: NodesIcon, label: 'Nodes', more: false },
  { path: '/salud', icon: HeartPulse, label: 'Salud', more: false },
  // Owner, 29 Oct 2026: «no veo dónde creas proyectos»: Proyectos in view;
  // Uso moves under «Más» (and stays on the notch).
  { path: '/proyectos', icon: FolderKanban, label: 'Proyectos', more: false },
  { path: '/uso', icon: Gauge, label: 'Uso', more: true },
  { path: '/swarm', icon: SwarmIcon, label: 'Agent Swarm', more: true },
  { path: '/workspace', icon: NotebookPen, label: 'Workspace', more: true },
  { path: '/cowork', icon: Briefcase, label: 'Cowork', more: true },
  { path: '/automatizar', icon: Zap, label: 'Automatizar', more: true },
  { path: '/biblioteca', icon: Library, label: 'Biblioteca', more: true },
  { path: '/extensiones', icon: Puzzle, label: 'Extensiones', more: true },
  { path: '/faces', icon: ScanFace, label: 'Rostros', more: true },
  { path: '/perfil', icon: UserRound, label: 'Perfil', more: true },
] as const;

const MORE_KEY = 'sergio-sidebar-more';

export function isActive(path: string, pathname: string): boolean {
  if (path === '/chat') return pathname === '/' || pathname === '/chat' || pathname.startsWith('/chat/');
  return pathname === path || pathname.startsWith(`${path}/`);
}

function Item({
  icon,
  label,
  hint,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  hint?: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" className="sb-item" aria-current={active ? 'page' : undefined} onClick={onClick} title={label} aria-label={label}>
      <span className="sb-ico">{icon}</span>
      <span className="sb-label">{label}</span>
      {hint && <kbd className="sb-kbd">{hint}</kbd>}
    </button>
  );
}

// The sidebar, like ChatGPT's: the mark and the toggle on top; new chat,
// search and the library; Sergio's parts; the chats; and at the foot the
// always-on conversation and the owner's row. Closed it folds into a rail
// of icons; on a phone it slides over the page.
export function Toolbar({ historyOpen, onToggleHistory }: { historyOpen: boolean; onToggleHistory: () => void }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const createConversation = useAppStore((s) => s.createConversation);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const mac = typeof navigator !== 'undefined' && navigator.platform.includes('Mac');
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  // The plan under the name, so the owner always sees which one is in force.
  // «Más»: the rarely used parts, folded; open by itself on one of them.
  const [moreChosen, setMoreChosen] = useState(() => {
    try {
      return localStorage.getItem(MORE_KEY) === '1';
    } catch {
      return false;
    }
  });
  const onMorePage = TOOLBAR_ITEMS.some((i) => i.more && isActive(i.path, pathname));
  const showMore = moreChosen || onMorePage;
  const toggleMore = () => {
    const next = !showMore;
    setMoreChosen(next);
    try {
      localStorage.setItem(MORE_KEY, next ? '1' : '0');
    } catch {
      // a convenience only
    }
  };
  const [planName, setPlanName] = useState('');
  const [usedToday, setUsedToday] = useState<number | null>(null);
  useEffect(() => {
    let live = true;
    apiFetch('/v1/plans/me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!live) return;
        setPlanName(d?.account?.plan_name || '');
        setUsedToday(d?.usage?.items ? overallPercent(d.usage.items) : null);
      })
      .catch(() => live && setPlanName(''));
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (searching && historyOpen) searchRef.current?.focus();
  }, [searching, historyOpen]);
  // Ctrl/⌘ ⇧ O starts a new chat, as in ChatGPT.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'o') {
        e.preventDefault();
        createConversation(useAppStore.getState().selectedModel);
        navigate('/chat');
      }
      // Ctrl/⌘ J: Quick Chat, for a quick question (its own section).
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        const st = useAppStore.getState();
        st.selectConversation(st.chatFor('rapido'));
        navigate('/chat');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [createConversation, navigate]);
  const narrow = () => typeof window !== 'undefined' && window.innerWidth < 768;
  const go = (path: string) => {
    navigate(path);
    if (narrow() && historyOpen) onToggleHistory();
  };

  return (
    <>
      {historyOpen && <div className="sb-scrim" onClick={onToggleHistory} aria-hidden="true" />}
      <nav className="sb" data-open={historyOpen || undefined} aria-label="Barra lateral">
        <div className="sb-head">
          <button
            type="button"
            className="sb-mark"
            aria-label={historyOpen ? 'Sergio, inicio' : 'Abrir la barra lateral'}
            title={historyOpen ? 'Inicio' : 'Abrir la barra lateral'}
            onClick={() => (historyOpen ? go('/') : onToggleHistory())}
          >
            <img className="sb-mark-s" src="/sergio.svg" alt="" width={26} height={26} />
            <PanelLeft className="sb-mark-panel" size={20} strokeWidth={1.6} />
          </button>
          <button
            type="button"
            className="sb-toggle"
            aria-label="Cerrar la barra lateral"
            title="Cerrar la barra lateral"
            onClick={onToggleHistory}
          >
            <PanelLeft size={20} strokeWidth={1.6} />
          </button>
        </div>

        <div className="sb-scroll">
          <div className="sb-group">
            <Item
              icon={<SquarePen size={18} strokeWidth={1.7} />}
              label="Nuevo chat"
              hint={mac ? '⇧⌘O' : 'Ctrl ⇧ O'}
              onClick={() => {
                // A new chat in the section on screen; the voice chat is one
                // continuous conversation, so «new» there means written.
                const kind = useAppStore.getState().chatKind;
                createConversation(selectedModel, kind === 'voz' ? 'texto' : kind);
                go('/chat');
              }}
            />
            <Item
              icon={<Search size={18} strokeWidth={1.7} />}
              label="Buscar chats"
              active={searching}
              onClick={() => {
                if (!historyOpen) onToggleHistory();
                setSearching((on) => (historyOpen ? !on : true));
                if (searching) setQuery('');
              }}
            />
          </div>

          <div className="sb-group">
            {TOOLBAR_ITEMS.filter((i) => i.path !== '/chat' && (!i.more || showMore)).map((item) => (
              <Item
                key={item.path}
                icon={<item.icon size={18} strokeWidth={1.7} />}
                label={item.label}
                active={isActive(item.path, pathname)}
                onClick={() => go(item.path)}
              />
            ))}
            <Item
              icon={<ChevronDown size={18} strokeWidth={1.7} className={showMore ? 'sb-more-open' : ''} />}
              label={showMore ? 'Menos' : 'Más'}
              onClick={toggleMore}
            />
          </div>

          <div className="sb-chats">
            {searching ? (
              <label className="sb-search">
                <Search size={14} strokeWidth={1.7} />
                <input
                  ref={searchRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Escape' && (setQuery(''), setSearching(false))}
                  placeholder="Buscar chats…"
                  aria-label="Buscar chats"
                />
              </label>
            ) : (
              <ChatSections />
            )}
            <div className="sb-list" onClick={() => narrow() && historyOpen && onToggleHistory()}>
              <ConversationList searchQuery={query} />
            </div>
          </div>
        </div>

        <div className="sb-foot">
          <div className="sb-live">
            <LiveOrb size="sm" />
            <span className="sb-label">Conversación</span>
          </div>
          <UpdateButton />
          <button
            type="button"
            className="sb-user"
            aria-label="Ajustes"
            title="Ajustes"
            aria-current={isActive('/settings', pathname) ? 'page' : undefined}
            onClick={() => go('/settings')}
          >
            <span className="sb-avatar" aria-hidden="true">
              S
            </span>
            <span className="sb-label">
              <b>Señor</b>
              <small>
                {planName ? `Plan ${planName}` : 'Ajustes'}
                {usedToday !== null ? ` · ${usedToday} % hoy` : ''}
              </small>
            </span>
            <Settings className="sb-user-gear" size={16} strokeWidth={1.7} />
          </button>
        </div>
      </nav>
    </>
  );
}
