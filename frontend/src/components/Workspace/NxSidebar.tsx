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
  LayoutTemplate,
  MoreHorizontal,
  Network,
  Plus,
  Scissors,
  Search,
  Settings2,
  ShieldCheck,
  Star,
  Trash2,
} from 'lucide-react';
import { useWorkspace } from '../../lib/workspace/store';
import { NxIcon } from './NxIcon';
import { childrenOf } from '../../lib/workspace/notion';
import type { Page } from '../../lib/workspace/model';

export type SidebarAction = 'search' | 'home' | 'inbox' | 'agenda' | 'templates' | 'graph' | 'clip' | 'shares' | 'vault' | 'layout' | 'export';

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
              <Archive size={15} /> Mover al baúl
            </button>
            <button
              type="button"
              role="menuitem"
              className="nx-danger"
              onClick={() => {
                setMenu(false);
                if (window.confirm(`¿Borrar «${page.title || 'Sin título'}»?`)) remove(page.id);
              }}
            >
              <Trash2 size={15} /> Borrar
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

export function NxSidebar({ onPick, onAction, onCollapse }: { onPick: (id: string) => void; onAction: (a: SidebarAction) => void; onCollapse: () => void }) {
  const pages = useWorkspace((s) => s.pages);
  const active = useWorkspace((s) => s.active);
  const create = useWorkspace((s) => s.create);
  const [showFav, setShowFav] = useState(true);
  const [showPriv, setShowPriv] = useState(true);
  const favorites = Object.values(pages).filter((p) => p.favorite && !p.archived);
  const top = childrenOf(pages, null);

  const item = (icon: React.ReactNode, label: string, action: SidebarAction, current = false) => (
    <button type="button" className="nx-row nx-item" data-active={current || undefined} onClick={() => onAction(action)}>
      <span className="nx-row-icon">{icon}</span>
      <span className="nx-row-label">{label}</span>
    </button>
  );

  return (
    <aside className="nx-sidebar" aria-label="Workspace">
      <div className="nx-switcher">
        <span className="nx-ws-avatar">S</span>
        <span className="nx-ws-name">Workspace de Sergio</span>
        <button type="button" className="nx-icon" aria-label="Ocultar la barra" title="Ocultar la barra" onClick={onCollapse}>
          <ChevronsLeft size={17} />
        </button>
        <button type="button" className="nx-icon" aria-label="Nueva página" title="Nueva página" onClick={() => onPick(create({ open: false }).id)}>
          <Plus size={17} />
        </button>
      </div>

      <nav className="nx-section">
        {item(<Search size={16} />, 'Buscar', 'search')}
        {item(<Home size={16} />, 'Inicio', 'home', !active)}
        {item(<Inbox size={16} />, 'Bandeja de entrada', 'inbox')}
        {item(<CalendarDays size={16} />, 'Calendario', 'agenda')}
      </nav>

      <div className="nx-scroll">
        {favorites.length > 0 && (
          <div className="nx-group">
            <button type="button" className="nx-group-head" onClick={() => setShowFav(!showFav)}>
              Favoritos
            </button>
            {showFav && favorites.map((p) => <TreeRow key={`f-${p.id}`} page={p} depth={0} onPick={onPick} />)}
          </div>
        )}
        <div className="nx-group">
          <div className="nx-group-head-row">
            <button type="button" className="nx-group-head" onClick={() => setShowPriv(!showPriv)}>
              Privado
            </button>
            <button type="button" className="nx-icon nx-group-add" aria-label="Añadir una página" onClick={() => onPick(create({ open: false }).id)}>
              <Plus size={14} />
            </button>
          </div>
          {showPriv && top.map((p) => <TreeRow key={p.id} page={p} depth={0} onPick={onPick} />)}
          {showPriv && (
            <button type="button" className="nx-row nx-item nx-muted" onClick={() => onPick(create({ open: false }).id)}>
              <span className="nx-row-icon">
                <Plus size={16} />
              </span>
              <span className="nx-row-label">Añadir una página</span>
            </button>
          )}
        </div>

        <nav className="nx-section nx-bottom">
          {item(<LayoutTemplate size={16} />, 'Plantillas', 'templates')}
          {item(<Network size={16} />, 'Grafo', 'graph')}
          {item(<Scissors size={16} />, 'Recortar web', 'clip')}
          {item(<ShieldCheck size={16} />, 'Permisos', 'shares')}
          {item(<Download size={16} />, 'Exportar todo', 'export')}
          {item(<Settings2 size={16} />, 'Diseño', 'layout')}
          {item(<Archive size={16} />, 'Baúl', 'vault')}
        </nav>
      </div>
    </aside>
  );
}
