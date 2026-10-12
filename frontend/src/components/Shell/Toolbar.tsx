import { useLocation, useNavigate } from 'react-router';
import {
  SquarePen,
  Search,
  PanelLeft,
  MessageSquare,
  NotebookPen,
  Briefcase,
  HeartPulse,
  UserRound,
  Settings,
  Shapes,
} from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { LiveOrb } from '../Live/LiveOrb';

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

// Every part of Sergio, as icons only, each with its own colour (names on
// hover). The colour follows the section everywhere: icon, cards, accents.
export const TOOLBAR_ITEMS = [
  { path: '/chat', icon: MessageSquare, label: 'Chat', color: 'var(--sec-chat)' },
  { path: '/nodes', icon: NodesIcon, label: 'Nodes', color: 'var(--sec-nodes)' },
  { path: '/swarm', icon: SwarmIcon, label: 'Agent Swarm', color: 'var(--sec-swarm)' },
  { path: '/workspace', icon: NotebookPen, label: 'Workspace', color: 'var(--sec-workspace)' },
  { path: '/creator', icon: Shapes, label: 'Creator', color: 'var(--sec-creator)' },
  { path: '/cowork', icon: Briefcase, label: 'Cowork', color: 'var(--sec-cowork)' },
  { path: '/salud', icon: HeartPulse, label: 'Salud', color: 'var(--sec-health)' },
  { path: '/perfil', icon: UserRound, label: 'Perfil', color: 'var(--sec-profile)' },
] as const;

export function isActive(path: string, pathname: string): boolean {
  if (path === '/chat') return pathname === '/' || pathname === '/chat' || pathname.startsWith('/chat/');
  return pathname === path || pathname.startsWith(`${path}/`);
}

function RailButton({
  label,
  hint,
  active,
  onClick,
  children,
  pressed,
  color,
}: {
  label: string;
  hint?: string;
  active?: boolean;
  pressed?: boolean;
  color?: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className="rail-item"
      style={color ? ({ '--sec': color } as React.CSSProperties) : undefined}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      aria-pressed={pressed}
      onClick={onClick}
    >
      {children}
      <span className="rail-tip" aria-hidden="true">
        {label}
        {hint && <kbd>{hint}</kbd>}
      </span>
    </button>
  );
}

// The rail on the left: the mark, new chat, search and the history on top;
// the colour-coded sections in the middle; Sergio's living orb (the
// always-on conversation) and settings at the foot. On a phone it becomes a
// bar of icons at the bottom.
export function Toolbar({ historyOpen, onToggleHistory }: { historyOpen: boolean; onToggleHistory: () => void }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const createConversation = useAppStore((s) => s.createConversation);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const mac = typeof navigator !== 'undefined' && navigator.platform.includes('Mac');

  return (
    <nav className="rail" aria-label="Secciones">
      <div className="rail-group rail-top">
        <button type="button" className="rail-mark" aria-label="Sergio, inicio" onClick={() => navigate('/')}>
          S
        </button>
        <RailButton
          label="Nuevo chat"
          onClick={() => {
            createConversation(selectedModel);
            navigate('/chat');
          }}
        >
          <SquarePen size={19} strokeWidth={1.5} />
        </RailButton>
        <RailButton label="Buscar" hint={mac ? '⌘K' : 'Ctrl K'} onClick={() => setCommandPaletteOpen(true)}>
          <Search size={19} strokeWidth={1.5} />
        </RailButton>
        <RailButton label={historyOpen ? 'Cerrar historial' : 'Historial'} pressed={historyOpen} onClick={onToggleHistory}>
          <PanelLeft size={19} strokeWidth={1.5} />
        </RailButton>
      </div>
      <div className="rail-group rail-sections">
        {TOOLBAR_ITEMS.map((item) => (
          <RailButton
            key={item.path}
            label={item.label}
            color={item.color}
            active={isActive(item.path, pathname)}
            onClick={() => navigate(item.path)}
          >
            <item.icon size={20} strokeWidth={1.5} />
          </RailButton>
        ))}
      </div>
      <div className="rail-group rail-foot">
        <LiveOrb />
        <RailButton label="Ajustes" active={isActive('/settings', pathname)} onClick={() => navigate('/settings')}>
          <Settings size={19} strokeWidth={1.5} />
        </RailButton>
      </div>
    </nav>
  );
}
