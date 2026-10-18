import { useState } from 'react';
import {
  Archive,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  ChevronsLeft,
  Copy,
  Download,
  Home,
  Inbox,
  Library,
  LayoutTemplate,
  MoreHorizontal,
  Network,
  Plus,
  Scissors,
  Search,
  Settings,
  Settings2,
  SquarePen,
  ShieldCheck,
  Star,
  Trash2,
} from 'lucide-react';
import { useWorkspace, type SidebarSection } from '../../lib/workspace/store';
import { useSharedPages } from './NxLibrary';
import { NxIcon } from './NxIcon';
import { childrenOf } from '../../lib/workspace/notion';
import type { Page } from '../../lib/workspace/model';

export type SidebarAction =
  | 'search'
  | 'home'
  | 'inbox'
  | 'agenda'
  | 'templates'
  | 'graph'
  | 'clip'
  | 'shares'
  | 'vault'
  | 'trash'
  | 'library'
  | 'layout'
  | 'export';

// Sergio's own tools, gathered under «Configuración» as Notion keeps them in Settings.
const SETTINGS: [typeof Network, string, SidebarAction][] = [
  [Settings2, 'Diseño de la barra', 'layout'],
  [ShieldCheck, 'Permisos', 'shares'],
  [Archive, 'Baúl cifrado', 'vault'],
  [Network, 'Grafo', 'graph'],
  [Scissors, 'Recortar web', 'clip'],
  [Download, 'Exportar todo', 'export'],
];
export const SETTINGS_ACTIONS: SidebarAction[] = SETTINGS.map(([, , a]) => a);

function PageIcon({ page }: { page: Page }) {
  return <NxIcon icon={page.icon} size={16} />;
}

function TreeRow({ page, depth, onPick }: { page: Page; depth: number; onPick: (id: string) => void }) {
  const pages = useWorkspace((s) => s.pages);
  const active = useWorkspace((s) => s.active);
  const create = useWorkspace((s) => s.create);
  const update = useWorkspace((s) => s.update);
  const archive = useWorkspace((s) => s.archive);
  const remove = useWorkspace((s) => s.remove);
  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const kids = childrenOf(pages, page.id);
  return (
    <>
      <div className="nx-row nx-tree-row" data-active={active === page.id || undefined} style={{ paddingLeft: 8 + depth * 12 }}>
        <button type="button" className="nx-toggle" aria-label={open ? 'Plegar' : 'Desplegar'} aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </button>
        <button type="button" className="nx-row-main" onClick={() => onPick(page.id)}>
          <span className="nx-row-icon">
            <PageIcon page={page} />
          </span>
          <span className="nx-row-label">{page.title || 'Sin título'}</span>
        </button>
        <span className="nx-row-actions">
          <button type="button" aria-label="Más" onClick={() => setMenu(!menu)}>
            <MoreHorizontal size={14} />
          </button>
          <button
            type="button"
            aria-label="Añadir una página dentro"
            onClick={() => {
              setOpen(true);
              onPick(create({ parent: page.id, open: false }).id);
            }}
          >
            <Plus size={14} />
          </button>
        </span>
        {menu && (
          <div className="nx-menu" role="menu" style={{ left: 'auto', right: 4, top: 28 }} onMouseLeave={() => setMenu(false)}>
            <button type="button" role="menuitem" onClick={() => (setMenu(false), update(page.id, (p) => ({ ...p, favorite: !p.favorite })))}>
              <Star size={15} /> {page.favorite ? 'Quitar de favoritos' : 'Añadir a favoritos'}
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenu(false);
                const copy = create({ parent: page.parent, title: `${page.title || 'Sin título'} (copia)`, open: false });
                update(copy.id, (p) => ({ ...p, icon: page.icon, cover: page.cover, blocks: structuredClone(page.blocks) }));
                onPick(copy.id);
              }}
            >
              <Copy size={15} /> Duplicar
            </button>
            <button type="button" role="menuitem" onClick={() => (setMenu(false), void archive(page.id))}>
              <Archive size={15} /> Archivar
            </button>
            <button
              type="button"
              role="menuitem"
              className="nx-danger"
              onClick={() => {
                setMenu(false);
                remove(page.id);
              }}
            >
              <Trash2 size={15} /> Mover a la papelera
            </button>
          </div>
        )}
      </div>
      {open &&
        (kids.length ? (
          kids.map((k) => <TreeRow key={k.id} page={k} depth={depth + 1} onPick={onPick} />)
        ) : (
          <div className="nx-row nx-empty-row" style={{ paddingLeft: 30 + depth * 12 }}>
            Sin páginas dentro
          </div>
        ))}
    </>
  );
}

// A section header like Notion's: click folds it, «•••» hides it from the bar.
function Section({
  name,
  section,
  children,
  onAdd,
}: {
  name: string;
  section: SidebarSection;
  children: React.ReactNode;
  onAdd?: () => void;
}) {
  const toggleSection = useWorkspace((s) => s.toggleSection);
  const [open, setOpen] = useState(true);
  const [menu, setMenu] = useState(false);
  return (
    <div className="nx-group">
      <div className="nx-group-head-row">
        <button type="button" className="nx-group-head" aria-expanded={open} onClick={() => setOpen(!open)}>
          {name}
        </button>
        <button type="button" className="nx-icon nx-group-add" aria-label={`Opciones de ${name}`} onClick={() => setMenu(!menu)}>
          <MoreHorizontal size={14} />
        </button>
        {onAdd && (
          <button type="button" className="nx-icon nx-group-add" aria-label="Añadir una página" onClick={onAdd}>
            <Plus size={14} />
          </button>
        )}
        {menu && (
          <div className="nx-menu" role="menu" style={{ left: 'auto', right: 4, top: 26 }} onMouseLeave={() => setMenu(false)}>
            <button type="button" role="menuitem" onClick={() => (setMenu(false), toggleSection(section, false))}>
              Ocultar la sección
            </button>
          </div>
        )}
      </div>
      {open && children}
    </div>
  );
}

export function NxSidebar({
  onPick,
  onAction,
  onCollapse,
  current,
}: {
  onPick: (id: string) => void;
  onAction: (a: SidebarAction) => void;
  onCollapse: () => void;
  current?: SidebarAction | null;
}) {
  const pages = useWorkspace((s) => s.pages);
  const active = useWorkspace((s) => s.active);
  const create = useWorkspace((s) => s.create);
  const hidden = useWorkspace((s) => s.layout.hidden) || [];
  const shared = useSharedPages();
  const shows = (key: SidebarSection) => !hidden.includes(key);
  const live = Object.values(pages).filter((p) => !p.archived);
  const favorites = live.filter((p) => p.favorite);
  const recents = [...live].sort((a, b) => (b.openedAt || 0) - (a.openedAt || 0)).slice(0, 5);
  const sharedPages = live.filter((p) => shared.has(p.id));
  const top = childrenOf(pages, null);
  const newPage = () => onPick(create({ open: false }).id);
  const [settings, setSettings] = useState(false);

  const item = (icon: React.ReactNode, label: string, action: SidebarAction, on = false) => (
    <button type="button" className="nx-row nx-item" data-active={on || current === action || undefined} onClick={() => onAction(action)}>
      <span className="nx-row-icon">{icon}</span>
      <span className="nx-row-label">{label}</span>
    </button>
  );
  const flat = (list: typeof live, prefix: string) => list.map((p) => <TreeRow key={`${prefix}-${p.id}`} page={p} depth={0} onPick={onPick} />);

  return (
    <aside className="nx-sidebar" aria-label="Workspace">
      <div className="nx-switcher">
        <span className="nx-ws-avatar">S</span>
        <span className="nx-ws-name">Workspace de Sergio</span>
        <button type="button" className="nx-icon nx-hover-only" aria-label="Ocultar la barra" title="Ocultar la barra" onClick={onCollapse}>
          <ChevronsLeft size={17} />
        </button>
        <button type="button" className="nx-icon" aria-label="Nueva página" title="Nueva página" onClick={newPage}>
          <SquarePen size={16} />
        </button>
      </div>

      <nav className="nx-section">
        {item(<Search size={16} />, 'Buscar', 'search')}
        {item(<Home size={16} />, 'Inicio', 'home', !active && !current)}
        {item(<Inbox size={16} />, 'Bandeja de entrada', 'inbox')}
        {item(<CalendarDays size={16} />, 'Calendario', 'agenda')}
      </nav>

      <div className="nx-scroll">
        {shows('recents') && recents.length > 0 && (
          <Section name="Recientes" section="recents">
            {flat(recents, 'r')}
          </Section>
        )}
        {shows('favorites') && favorites.length > 0 && (
          <Section name="Favoritos" section="favorites">
            {flat(favorites, 'f')}
          </Section>
        )}
        {shows('shared') && sharedPages.length > 0 && (
          <Section name="Compartido" section="shared">
            {flat(sharedPages, 's')}
          </Section>
        )}
        {shows('private') && (
          <Section name="Privado" section="private" onAdd={newPage}>
            {top.map((p) => (
              <TreeRow key={p.id} page={p} depth={0} onPick={onPick} />
            ))}
            <button type="button" className="nx-row nx-item nx-muted" onClick={newPage}>
              <span className="nx-row-icon">
                <Plus size={16} />
              </span>
              <span className="nx-row-label">Añadir una página</span>
            </button>
          </Section>
        )}
        {shows('library') && <nav className="nx-section nx-library-link">{item(<Library size={16} />, 'Biblioteca', 'library')}</nav>}

        {/* Like Notion's foot of the bar: Configuración, Plantillas, Papelera.
            The rest of Sergio's tools live inside Configuración. */}
        <nav className="nx-section nx-bottom">
          <div className="nx-settings-wrap">
            <button
              type="button"
              className="nx-row nx-item"
              aria-haspopup="menu"
              aria-expanded={settings}
              data-active={settings || (current && SETTINGS_ACTIONS.includes(current)) || undefined}
              onClick={() => setSettings(!settings)}
            >
              <span className="nx-row-icon"><Settings size={16} /></span>
              <span className="nx-row-label">Configuración</span>
            </button>
            {settings && (
              <div className="nx-menu nx-settings-menu" role="menu" onMouseLeave={() => setSettings(false)}>
                {SETTINGS.map(([Icon, label, action]) => (
                  <button key={action} type="button" role="menuitem" onClick={() => (setSettings(false), onAction(action))}>
                    <Icon size={15} /> {label}
                  </button>
                ))}
              </div>
            )}
          </div>
          {item(<LayoutTemplate size={16} />, 'Plantillas', 'templates')}
          {item(<Trash2 size={16} />, 'Papelera', 'trash')}
        </nav>
      </div>
    </aside>
  );
}

