import { useLocation, useNavigate } from 'react-router';
import {
  Library,
  MessageSquare,
  NotebookPen,
  Briefcase,
  Network,
  HeartPulse,
  UserRound,
  Search,
  Settings,
} from 'lucide-react';
import { useAppStore } from '../../lib/store';

// The bottom toolbar of the e-paper home: a hairline bar, then thin icons.
// Only icons: hovering one lifts it and shows its name above it.
// Inicio is the library; then the sections, the workspace, search and
// Configuración. The notch on the desktop has the same six sections.
export const TOOLBAR_ITEMS = [
  { path: '/', icon: Library, label: 'Inicio' },
  { path: '/chat', icon: MessageSquare, label: 'Chat' },
  { path: '/workspace', icon: NotebookPen, label: 'Workspace' },
  { path: '/cowork', icon: Briefcase, label: 'Cowork' },
  { path: '/agents', icon: Network, label: 'Agent Swarm' },
  { path: '/salud', icon: HeartPulse, label: 'Salud' },
  { path: '/perfil', icon: UserRound, label: 'Perfil' },
] as const;

export function isActive(path: string, pathname: string): boolean {
  return path === '/' ? pathname === '/' : pathname === path || pathname.startsWith(`${path}/`);
}

export function Toolbar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const stroke = 1.25;

  return (
    <footer className="paper-toolbar">
      <nav aria-label="Secciones">
        {TOOLBAR_ITEMS.map((item) => {
          const active = isActive(item.path, pathname);
          return (
            <button
              key={item.path}
              type="button"
              className="paper-tool"
              aria-label={item.label}
              aria-current={active ? 'page' : undefined}
              onClick={() => navigate(item.path)}
            >
              <item.icon size={20} strokeWidth={stroke} />
              <span className="paper-tip" aria-hidden="true">{item.label}</span>
            </button>
          );
        })}
        <span aria-hidden="true" style={{ width: 1, height: 18, background: 'var(--color-border)', margin: '0 4px' }} />
        <button
          type="button"
          className="paper-tool"
          aria-label="Buscar (Ctrl+K)"
          onClick={() => setCommandPaletteOpen(true)}
        >
          <Search size={20} strokeWidth={stroke} />
          <span className="paper-tip" aria-hidden="true">Buscar · Ctrl K</span>
        </button>
        <button
          type="button"
          className="paper-tool"
          aria-label="Configuración"
          aria-current={isActive('/settings', pathname) ? 'page' : undefined}
          onClick={() => navigate('/settings')}
        >
          <Settings size={20} strokeWidth={stroke} />
          <span className="paper-tip" aria-hidden="true">Ajustes</span>
        </button>
      </nav>
    </footer>
  );
}
