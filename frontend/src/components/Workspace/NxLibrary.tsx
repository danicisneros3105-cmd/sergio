import { useEffect, useMemo, useState } from 'react';
import { RotateCcw, Search, Trash2 } from 'lucide-react';
import { NxIcon } from './NxIcon';
import { apiFetch } from '../../lib/api';
import { relativeDay } from '../../lib/paper';
import { SIDEBAR_SECTIONS, TRASH_DAYS, useWorkspace, type SidebarSection } from '../../lib/workspace/store';
import type { Page } from '../../lib/workspace/model';

export type LibraryTab = 'recents' | 'favorites' | 'private' | 'shared' | 'archived' | 'trash';

const TABS: Array<{ key: LibraryTab; name: string }> = [
  { key: 'recents', name: 'Recientes' },
  { key: 'favorites', name: 'Favoritos' },
  { key: 'private', name: 'Privado' },
  { key: 'shared', name: 'Compartido' },
  { key: 'archived', name: 'Archivado' },
  { key: 'trash', name: 'Papelera' },
];

// Pages with a live share link (asked to the server once per minute at most).
let sharedCache: { at: number; ids: Set<string> } = { at: 0, ids: new Set() };
export function useSharedPages(): Set<string> {
  const [ids, setIds] = useState(sharedCache.ids);
  useEffect(() => {
    if (Date.now() - sharedCache.at < 60_000) return;
    sharedCache = { ...sharedCache, at: Date.now() };
    apiFetch('/v1/workspace/shares')
      .then((r) => (r.ok ? r.json() : { shares: [] }))
      .then((d: { shares?: Array<{ page: string }> }) => {
        sharedCache = { at: Date.now(), ids: new Set((d.shares || []).map((s) => s.page)) };
        setIds(sharedCache.ids);
      })
      .catch(() => undefined);
  }, []);
  return ids;
}

function daysLeft(p: Page, now = Date.now()): number {
  return Math.max(0, TRASH_DAYS - Math.floor((now - (p.trashedAt || now)) / 86_400_000));
}

// The Library, like Notion's: every page by where it lives, on one full page.
export function NxLibrary({ tab, onTab, onPick }: { tab: LibraryTab; onTab: (t: LibraryTab) => void; onPick: (id: string) => void }) {
  const pages = useWorkspace((s) => s.pages);
  const vault = useWorkspace((s) => s.vault);
  const trash = useWorkspace((s) => s.trash);
  const loadVault = useWorkspace((s) => s.loadVault);
  const loadTrash = useWorkspace((s) => s.loadTrash);
  const restore = useWorkspace((s) => s.restore);
  const restoreTrash = useWorkspace((s) => s.restoreTrash);
  const purge = useWorkspace((s) => s.purge);
  const autoArchive = useWorkspace((s) => s.autoArchive);
  const hidden = useWorkspace((s) => s.layout.hidden) || [];
  const toggleSection = useWorkspace((s) => s.toggleSection);
  const shared = useSharedPages();
  const [q, setQ] = useState('');
  const [note, setNote] = useState('');

  useEffect(() => {
    if (tab === 'archived') void loadVault();
    if (tab === 'trash') void loadTrash();
    setNote('');
  }, [tab, loadVault, loadTrash]);

  const rows = useMemo(() => {
    const live = Object.values(pages).filter((p) => !p.archived);
    let list: Page[];
    if (tab === 'recents') list = [...live].sort((a, b) => (b.openedAt || 0) - (a.openedAt || 0)).slice(0, 50);
    else if (tab === 'favorites') list = live.filter((p) => p.favorite);
    else if (tab === 'shared') list = live.filter((p) => shared.has(p.id));
    else if (tab === 'archived') list = vault || [];
    else if (tab === 'trash') list = trash || [];
    else list = [...live].sort((a, b) => (a.title || '').localeCompare(b.title || '', 'es'));
    const needle = q.trim().toLowerCase();
    return needle ? list.filter((p) => (p.title || 'sin título').toLowerCase().includes(needle)) : list;
  }, [pages, vault, trash, shared, tab, q]);

  const where = (p: Page) => (p.parent && pages[p.parent] ? pages[p.parent].title || 'Sin título' : 'Privado');
  const section = SIDEBAR_SECTIONS.find((s) => s.key === (tab as SidebarSection));
  const empty: Record<LibraryTab, string> = {
    recents: 'Aún no ha abierto ninguna página.',
    favorites: 'Marque una página con la estrella para verla aquí.',
    private: 'No hay páginas.',
    shared: 'Ninguna página tiene un enlace para compartir.',
    archived: 'No hay nada archivado.',
    trash: `La papelera está vacía. Lo que borre se guarda aquí ${TRASH_DAYS} días.`,
  };

  return (
    <div className="nx-library">
      <h1 className="nx-library-title">Biblioteca</h1>
      <div className="nx-library-bar">
        <div className="nx-library-tabs" role="tablist" aria-label="Biblioteca">
          {TABS.map((t) => (
            <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className="nx-library-tab" onClick={() => onTab(t.key)}>
              {t.name}
            </button>
          ))}
        </div>
        <label className="nx-library-search">
          <Search size={14} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filtrar por título" aria-label="Filtrar por título" />
        </label>
      </div>

      <div className="nx-library-tools">
        {section && (
          <label className="nx-library-check">
            <input type="checkbox" checked={!hidden.includes(section.key)} onChange={(e) => toggleSection(section.key, e.target.checked)} />
            Mostrar en la barra lateral
          </label>
        )}
        {tab === 'archived' && (
          <button
            type="button"
            className="nx-pill"
            onClick={async () => {
              const r = await autoArchive();
              setNote(`Ordenado: ${r.pages} páginas, ${r.rows} filas y ${r.todos} tareas archivadas.`);
              void loadVault();
            }}
          >
            Ordenar ahora
          </button>
        )}
        {tab === 'trash' && (trash || []).length > 0 && (
          <button
            type="button"
            className="nx-pill"
            onClick={async () => {
              if (!window.confirm('¿Vaciar la papelera? No se puede deshacer.')) return;
              for (const p of trash || []) await purge(p.id);
            }}
          >
            Vaciar la papelera
          </button>
        )}
        {note && <span className="nx-library-note">{note}</span>}
      </div>

      <div className="nx-library-list" role="list">
        <div className="nx-library-row nx-library-head" aria-hidden="true">
          <span>Nombre</span>
          <span>{tab === 'trash' ? 'Se borra en' : 'Ubicación'}</span>
          <span>{tab === 'trash' ? 'Borrada' : 'Editada'}</span>
          <span />
        </div>
        {rows.length === 0 && <p className="nx-library-empty">{empty[tab]}</p>}
        {rows.map((p) => {
          const gone = tab === 'archived' || tab === 'trash';
          return (
            <div key={p.id} className="nx-library-row" role="listitem">
              <button type="button" className="nx-library-name" disabled={gone} onClick={() => onPick(p.id)}>
                <NxIcon icon={p.icon} size={16} />
                <span>{p.title || 'Sin título'}</span>
              </button>
              <span className="nx-library-meta">{tab === 'trash' ? `${daysLeft(p)} días` : where(p)}</span>
              <span className="nx-library-meta">{relativeDay(tab === 'trash' ? p.trashedAt || p.updatedAt : p.updatedAt)}</span>
              <span className="nx-library-actions">
                {tab === 'archived' && (
                  <button type="button" className="nx-icon" aria-label={`Devolver ${p.title || 'Sin título'}`} title="Devolver" onClick={() => void restore(p.id)}>
                    <RotateCcw size={15} />
                  </button>
                )}
                {tab === 'trash' && (
                  <>
                    <button type="button" className="nx-icon" aria-label={`Restaurar ${p.title || 'Sin título'}`} title="Restaurar" onClick={() => void restoreTrash(p.id)}>
                      <RotateCcw size={15} />
                    </button>
                    <button
                      type="button"
                      className="nx-icon"
                      aria-label={`Borrar para siempre ${p.title || 'Sin título'}`}
                      title="Borrar para siempre"
                      onClick={() => window.confirm(`¿Borrar «${p.title || 'Sin título'}» para siempre?`) && void purge(p.id)}
                    >
                      <Trash2 size={15} />
                    </button>
                  </>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
