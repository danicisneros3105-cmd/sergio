import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router';
import {
  MessageSquare,
  Plus,
  BarChart3,
  Settings,
  Search,
  PanelLeftClose,
  PanelLeft,
  Rocket,
  Bot,
  Sun,
  Moon,
  Monitor,
  Loader2,
  ScrollText,
  Database,
  Globe,
  MousePointerClick,
  ScanFace,
  ChevronsUpDown,
  Brain,
  Briefcase,
} from 'lucide-react';
import { ConversationList } from './ConversationList';
import { useAppStore } from '../../lib/store';

const STROKE = 1.75;
const IS_MAC = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform);
const THEME_LABEL = { light: 'claro', dark: 'oscuro', system: 'automático' } as const;

/** Sergio's mark: a single geometric ring, the same as the Windows tray icon. */
export function SergioMark({ size = 22 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="inline-grid place-items-center rounded-full shrink-0"
      style={{
        width: size,
        height: size,
        background: 'var(--color-accent)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.25)',
      }}
    >
      <span
        className="rounded-full"
        style={{
          width: size * 0.42,
          height: size * 0.42,
          border: `${Math.max(2, size / 11)}px solid rgba(255,255,255,0.95)`,
        }}
      />
    </span>
  );
}

const NAV_ITEMS = [
  { path: '/', icon: MessageSquare, label: 'Chat' },
  { path: '/pensar', icon: Brain, label: 'Pensar a fondo' },
  { path: '/cowork', icon: Briefcase, label: 'Cowork' },
  { path: '/globe', icon: Globe, label: 'Globo' },
  { path: '/clacky', icon: MousePointerClick, label: 'Clacky' },
  { path: '/faces', icon: ScanFace, label: 'Rostros' },
  { path: '/agents', icon: Bot, label: 'Agentes' },
  { path: '/data-sources', icon: Database, label: 'Fuentes de datos' },
  { path: '/dashboard', icon: BarChart3, label: 'Panel' },
  { path: '/logs', icon: ScrollText, label: 'Registro' },
  { path: '/get-started', icon: Rocket, label: 'Primeros pasos' },
  { path: '/settings', icon: Settings, label: 'Ajustes' },
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
          transition-[width] duration-300 ${sidebarOpen ? 'w-[264px]' : 'w-0 border-r-0'}`}
        style={{ transitionTimingFunction: 'var(--ease-mac)' }}
        aria-label="Barra lateral"
      >
        <div className="flex flex-col h-full w-[264px]">
          {/* Title bar */}
          <div className="flex items-center gap-2.5 px-4 pt-4 pb-3">
            <SergioMark />
            <span
              className="text-[15px] font-semibold flex-1"
              style={{ fontFamily: 'var(--font-display)', letterSpacing: '-0.02em', color: 'var(--color-text)' }}
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
              className="flex items-center gap-2 w-full px-3 py-2 rounded-[10px] text-[13.5px] font-medium cursor-pointer transition-[transform,box-shadow] duration-150 active:scale-[0.98]"
              style={{
                background: 'var(--color-surface)',
                color: 'var(--color-text)',
                border: '1px solid var(--color-border)',
                boxShadow: 'var(--shadow-sm)',
              }}
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

          {/* Conversations */}
          <div className="px-4 pt-4 pb-1 text-[12px] font-medium" style={{ color: 'var(--color-text-tertiary)' }}>
            Recientes
          </div>
          <div className="flex-1 overflow-y-auto px-2">
            <ConversationList searchQuery={searchQuery} />
          </div>

          {/* Sections */}
          <nav className="px-2 pt-2 pb-1 flex flex-col gap-px" aria-label="Secciones">
            {NAV_ITEMS.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className="mac-row"
                  data-active={isActive}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <item.icon size={16} strokeWidth={STROKE} />
                  {item.label}
                </button>
              );
            })}
          </nav>

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
