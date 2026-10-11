import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router';
import {
  MessageSquare,
  Plus,
  Settings,
  Search,
  PanelLeftClose,
  PanelLeft,
  Network,
  HeartPulse,
  UserRound,
  Sun,
  Moon,
  Monitor,
  Loader2,
  ChevronsUpDown,
  Briefcase,
} from 'lucide-react';
import { ConversationList } from './ConversationList';
import { useAppStore } from '../../lib/store';

const STROKE = 1.75;
const IS_MAC = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform);
const THEME_LABEL = { light: 'claro', dark: 'oscuro', system: 'automático' } as const;

/** Sergio's mark: an ink ring inside a hairline circle (paper, not glass). */
export function SergioMark({ size = 22 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="inline-grid place-items-center rounded-full shrink-0"
      style={{
        width: size,
        height: size,
        border: '1px solid var(--color-ink)',
      }}
    >
      <span
        className="rounded-full"
        style={{
          width: size * 0.46,
          height: size * 0.46,
          border: `${Math.max(1.5, size / 12)}px solid var(--color-ink)`,
        }}
      />
    </span>
  );
}

// The same seven sections as the notch on the desktop. The
// other pages (data sources, logs, faces…) are reached from Configuración.
export const NAV_ITEMS = [
  { path: '/', icon: MessageSquare, label: 'Chat' },
  { path: '/cowork', icon: Briefcase, label: 'Cowork' },
  { path: '/agents', icon: Network, label: 'Agent Swarm' },
  { path: '/nodes', icon: UserRound, label: 'Nodes' },
  { path: '/salud', icon: HeartPulse, label: 'Salud' },
  { path: '/perfil', icon: UserRound, label: 'Perfil' },
  { path: '/settings', icon: Settings, label: 'Configuración' },
];

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState('');

  const sidebarOpen = useAppStore((s) => s.sidebarOpen);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const createConversation = useAppStore((s) => s.createConversation);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const serverInfo = useAppStore((s) => s.serverInfo);
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const modelLoading = useAppStore((s) => s.modelLoading);
  const deepResearch = useAppStore((s) => s.deepResearch);

  const settings = useAppStore((s) => s.settings);
  const updateSettings = useAppStore((s) => s.updateSettings);

  const ThemeIcon = settings.theme === 'light' ? Sun : settings.theme === 'dark' ? Moon : Monitor;
  const nextTheme = settings.theme === 'light' ? 'dark' : settings.theme === 'dark' ? 'system' : 'light';

  const messages = useAppStore((s) => s.messages);
  const handleNewChat = () => {
    // Don't create a new chat if the current one is empty
    if (messages.length === 0) {
      navigate('/');
      return;
    }
    createConversation(selectedModel);
    navigate('/');
  };

  return (
    <>
      {!sidebarOpen && (
        <button
          onClick={toggleSidebar}
          className="mac-icon-btn fixed top-3 left-3 z-30"
          title="Mostrar barra lateral"
          aria-label="Mostrar barra lateral"
        >
          <PanelLeft size={18} strokeWidth={STROKE} />
        </button>
      )}

      <aside
        className={`mac-sidebar flex flex-col h-full shrink-0 overflow-hidden fixed md:relative z-30
          transition-[width] duration-300 ${sidebarOpen ? 'w-[248px]' : 'w-0 border-r-0'}`}
        style={{ transitionTimingFunction: 'var(--ease-mac)' }}
        aria-label="Barra lateral"
      >
        <div className="flex flex-col h-full w-[248px]">
          {/* Title bar */}
          <div className="flex items-center gap-2.5 px-4 pt-4 pb-3">
            <SergioMark />
            <span
              className="text-[19px] flex-1"
              style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}
            >
              Sergio
            </span>
            <button
              onClick={toggleSidebar}
              className="mac-icon-btn"
              title="Ocultar barra lateral"
              aria-label="Ocultar barra lateral"
            >
              <PanelLeftClose size={17} strokeWidth={STROKE} />
            </button>
          </div>

          <div className="px-3 flex flex-col gap-2">
            <button
              onClick={handleNewChat}
              className="paper-button w-full justify-start"
            >
              <Plus size={16} strokeWidth={STROKE} />
              Nueva conversación
            </button>

            <label className="mac-field text-[13px]">
              <Search size={14} strokeWidth={STROKE} style={{ color: 'var(--color-text-tertiary)' }} />
              <input
                type="text"
                placeholder="Buscar"
                aria-label="Buscar conversaciones"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 bg-transparent outline-none min-w-0"
                style={{ color: 'var(--color-text)' }}
              />
            </label>
          </div>

          {/* Sections */}
          <nav className="px-2 pt-4 pb-2 flex flex-col gap-px" aria-label="Secciones">
            {NAV_ITEMS.map((item) => {
              const isActive =
                item.path === '/' ? location.pathname === '/' : location.pathname.startsWith(item.path);
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className="mac-row"
                  data-active={isActive}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <item.icon size={16} strokeWidth={1.5} />
                  {item.label}
                </button>
              );
            })}
          </nav>

          {/* Conversations */}
          <div className="px-4 pt-3 pb-1.5 paper-label" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
            Abiertas recientemente
          </div>
          <div className="flex-1 overflow-y-auto px-2">
            <ConversationList searchQuery={searchQuery} />
          </div>

          {/* Model + appearance */}
          <div className="flex items-center gap-1 px-2 pb-3 pt-1" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
            <button
              onClick={() => setCommandPaletteOpen(true)}
              className="mac-row flex-1 min-w-0"
              title={`Cambiar modelo (${IS_MAC ? '⌘' : 'Ctrl'}+K)`}
            >
              {modelLoading ? (
                <Loader2 size={15} strokeWidth={STROKE} className="animate-spin" style={{ color: 'var(--color-accent)' }} />
              ) : (
                <SergioMark size={15} />
              )}
              <span className="truncate flex-1 text-[12.5px]">
                {modelLoading
                  ? 'Cargando modelo…'
                  : deepResearch
                    ? 'Investigación a fondo'
                    : selectedModel || serverInfo?.model || 'Elegir modelo'}
              </span>
              <ChevronsUpDown size={13} strokeWidth={STROKE} style={{ color: 'var(--color-text-tertiary)' }} />
            </button>
            <button
              onClick={() => updateSettings({ theme: nextTheme })}
              className="mac-icon-btn shrink-0"
              title={`Apariencia: ${THEME_LABEL[settings.theme as keyof typeof THEME_LABEL] ?? settings.theme}`}
              aria-label="Cambiar apariencia"
            >
              <ThemeIcon size={15} strokeWidth={STROKE} />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
