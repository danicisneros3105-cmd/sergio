import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import {
  SquarePen,
  Search,
  PanelLeft,
  NotebookPen,
  Briefcase,
  HeartPulse,
  UserRound,
  Settings,
  Shapes,
  Library,
  MessageSquare,
  ScanFace,
} from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { LiveOrb } from '../Live/LiveOrb';
import { ConversationList } from '../Sidebar/ConversationList';

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
// projects: plain monochrome icons and names.
export const TOOLBAR_ITEMS = [
  { path: '/chat', icon: MessageSquare, label: 'Chat' },
  { path: '/nodes', icon: NodesIcon, label: 'Nodes' },
  { path: '/swarm', icon: SwarmIcon, label: 'Agent Swarm' },
  { path: '/workspace', icon: NotebookPen, label: 'Workspace' },
  { path: '/creator', icon: Shapes, label: 'Creator' },
  { path: '/cowork', icon: Briefcase, label: 'Cowork' },
  { path: '/faces', icon: ScanFace, label: 'Rostros' },
  { path: '/salud', icon: HeartPulse, label: 'Salud' },
  { path: '/perfil', icon: UserRound, label: 'Perfil' },
] as const;

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
            <span className="sb-mark-s">S</span>
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
                createConversation(selectedModel);
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
            <Item
              icon={<Library size={18} strokeWidth={1.7} />}
              label="Biblioteca"
              active={isActive('/biblioteca', pathname)}
              onClick={() => go('/biblioteca')}
            />
          </div>

          <div className="sb-group">
            {TOOLBAR_ITEMS.filter((i) => i.path !== '/chat').map((item) => (
              <Item
                key={item.path}
                icon={<item.icon size={18} strokeWidth={1.7} />}
                label={item.label}
                active={isActive(item.path, pathname)}
                onClick={() => go(item.path)}
              />
            ))}
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
              <h2 className="sb-section">Chats</h2>
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
              <small>Ajustes</small>
            </span>
            <Settings className="sb-user-gear" size={16} strokeWidth={1.7} />
          </button>
        </div>
      </nav>
    </>
  );
}
