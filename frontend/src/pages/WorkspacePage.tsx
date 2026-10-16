import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { Columns2, Menu, X } from 'lucide-react';
import { HubPanels, type HubPanel } from '../components/Workspace/HubPanels';
import { NxSidebar, type SidebarAction } from '../components/Workspace/NxSidebar';
import { NxHome } from '../components/Workspace/NxHome';
import { NxLibrary, type LibraryTab } from '../components/Workspace/NxLibrary';
import { NxIcon } from '../components/Workspace/NxIcon';
import '../components/Workspace/notion.css';
import { PageEditor } from '../components/Workspace/PageEditor';
import { Graph3D } from '../components/Workspace/Graph3D';
import { SIDEBAR_SECTIONS, useWorkspace } from '../lib/workspace/store';
import { apiFetch } from '../lib/api';

export function SyncNote() {
  const sync = useWorkspace((s) => s.sync);
  const dirty = useWorkspace((s) => s.dirty.length);
  const text =
    sync === 'syncing'
      ? 'Sincronizando…'
      : sync === 'offline'
        ? 'Sin conexión · guardado en este equipo'
        : sync === 'error'
          ? 'Guardado en este equipo · el servidor no responde'
          : dirty
            ? 'Guardado en este equipo'
            : 'Guardado y sincronizado';
  return (
    <span className="text-[11.5px]" style={{ color: 'var(--color-text-tertiary)' }} role="status">
      {text}
    </span>
  );
}

function LayoutPanel({ onClose }: { onClose: () => void }) {
  const layout = useWorkspace((s) => s.layout);
  const setLayout = useWorkspace((s) => s.setLayout);
  const toggleSection = useWorkspace((s) => s.toggleSection);
  return (
    <div role="dialog" aria-label="Diseño">
      <div className="paper-label mb-2">Diseño de las páginas</div>
      <label className="ws-setting">
        Densidad
        <select className="ws-mini-input" value={layout.density} onChange={(e) => setLayout({ density: e.target.value as 'compact' })}>
          <option value="comfortable">Cómoda</option>
          <option value="compact">Compacta</option>
        </select>
      </label>
      <label className="ws-setting">
        Letra · {layout.fontSize}px
        <input type="range" min={13} max={19} value={layout.fontSize} onChange={(e) => setLayout({ fontSize: Number(e.target.value) })} />
      </label>
      <label className="ws-setting">
        Ancho
        <select className="ws-mini-input" value={layout.width} onChange={(e) => setLayout({ width: e.target.value as 'wide' })}>
          <option value="narrow">Estrecho (lectura)</option>
          <option value="wide">Amplio</option>
          <option value="full">Toda la pantalla</option>
        </select>
      </label>
      <label className="ws-setting">
        Márgenes · {layout.margin}px
        <input type="range" min={0} max={96} step={8} value={layout.margin} onChange={(e) => setLayout({ margin: Number(e.target.value) })} />
      </label>
      <div className="paper-label mt-3 mb-1">Barra lateral</div>
      {SIDEBAR_SECTIONS.map((sec) => (
        <label key={sec.key} className="ws-setting" style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          {sec.name}
          <input type="checkbox" checked={!(layout.hidden || []).includes(sec.key)} onChange={(e) => toggleSection(sec.key, e.target.checked)} />
        </label>
      ))}
      <button type="button" className="paper-button w-full mt-2" data-variant="quiet" onClick={onClose}>
        Listo
      </button>
    </div>
  );
}

export function WorkspacePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const ready = useWorkspace((s) => s.ready);
  const load = useWorkspace((s) => s.load);
  const pages = useWorkspace((s) => s.pages);
  const tabs = useWorkspace((s) => s.tabs);
  const active = useWorkspace((s) => s.active);
  const split = useWorkspace((s) => s.split);
  const ratio = useWorkspace((s) => s.ratio);
  const open = useWorkspace((s) => s.open);
  const close = useWorkspace((s) => s.close);
  const setActive = useWorkspace((s) => s.setActive);
  const setRatio = useWorkspace((s) => s.setRatio);
  const syncNow = useWorkspace((s) => s.syncNow);
  const [view, setView] = useState<'page' | 'home' | 'templates' | 'graph' | 'library'>('page');
  const [libraryTab, setLibraryTab] = useState<LibraryTab>('recents');
  const [panel, setPanel] = useState<null | 'layout'>(null);
  const [hub, setHub] = useState<HubPanel | null>(null);
  const narrow = typeof window !== 'undefined' && window.matchMedia?.('(max-width: 1099px)').matches;
  const [sidebar, setSidebar] = useState(() => {
    try {
      const saved = localStorage.getItem('sergio-ws-sidebar');
      return saved === null ? !narrow : saved === '1';
    } catch {
      return !narrow;
    }
  });
  const body = useRef<HTMLDivElement>(null);

  const showSidebar = (on: boolean) => {
    setSidebar(on);
    try {
      localStorage.setItem('sergio-ws-sidebar', on ? '1' : '0');
    } catch {
      /* storage blocked */
    }
  };

  useEffect(() => {
    if (!ready) void load();
  }, [ready, load]);

  // Remote changes (another device, Sergio) every 30 s while visible.
  useEffect(() => {
    const t = window.setInterval(() => {
      if (document.visibilityState === 'visible') void syncNow();
    }, 30_000);
    return () => window.clearInterval(t);
  }, [syncNow]);

  useEffect(() => {
    if (ready && id && pages[id] && active !== id) open(id);
  }, [ready, id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (ready && active && id !== active) navigate(`/workspace/${active}`, { replace: true });
  }, [ready, active]); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = useCallback(
    (pid: string) => {
      open(pid);
      setView('page');
      if (window.matchMedia?.('(max-width: 1099px)').matches) setSidebar(false);
    },
    [open],
  );

  const drag = (e: React.PointerEvent) => {
    const el = body.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const target = e.currentTarget as HTMLElement;
    target.setPointerCapture(e.pointerId);
    const moveTo = (ev: PointerEvent) => setRatio((ev.clientX - rect.left) / rect.width);
    const stop = () => {
      target.removeEventListener('pointermove', moveTo);
      target.removeEventListener('pointerup', stop);
    };
    target.addEventListener('pointermove', moveTo);
    target.addEventListener('pointerup', stop);
  };

  const list = useMemo(() => Object.values(pages), [pages]);

  const exportAll = async () => {
    const r = await apiFetch('/v1/workspace/export').catch(() => null);
    if (!r || !r.ok) {
      window.alert('Para exportar todo, su servidor de Sergio debe estar encendido. Cada página también se puede descargar en Markdown desde su menú.');
      return;
    }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await r.blob());
    a.download = 'sergio-workspace.zip';
    a.click();
  };

  const act = (a: SidebarAction) => {
    if (a === 'search') setHub('search');
    else if (a === 'inbox') setHub('mail');
    else if (a === 'agenda') setHub('agenda');
    else if (a === 'clip') setHub('clip');
    else if (a === 'shares') setHub('shares');
    else if (a === 'home') {
      useWorkspace.setState({ active: null, split: null });
      setView('home');
      navigate('/workspace', { replace: true });
    } else if (a === 'templates') setView('templates');
    else if (a === 'graph') setView('graph');
    else if (a === 'library' || a === 'vault' || a === 'trash') {
      setLibraryTab(a === 'vault' ? 'archived' : a === 'trash' ? 'trash' : libraryTab);
      setView('library');
    }
    else if (a === 'layout') setPanel('layout');
    else if (a === 'export') void exportAll();
  };

  const showPage = view === 'page' && ready && active && pages[active];
  const toggle = { sidebarOpen: sidebar, onToggleSidebar: () => showSidebar(!sidebar) };

  return (
    <div className="nx" data-sidebar={sidebar || undefined}>
      {sidebar && (
        <NxSidebar
          onPick={pick}
          onAction={act}
          onCollapse={() => showSidebar(false)}
          current={view === 'library' ? 'library' : view === 'graph' ? 'graph' : view === 'templates' ? 'templates' : null}
        />
      )}
      {sidebar && narrow && <button type="button" className="nx-scrim" aria-label="Cerrar la barra" onClick={() => showSidebar(false)} />}
      <main className="nx-main">
        {tabs.length > 1 && showPage && (
          <div className="nx-tabs" role="tablist" aria-label="Páginas abiertas">
            {tabs.map((t) => (
              <span key={t} className="nx-tab" data-active={t === active || undefined} data-split={t === split || undefined}>
                <button type="button" role="tab" aria-selected={t === active} onClick={() => setActive(t)}>
                  <span className="nx-tab-icon"><NxIcon icon={pages[t]?.icon} size={13} /></span>
                  {pages[t]?.title || 'Sin título'}
                </button>
                <button type="button" className="nx-tab-x" aria-label={`Cerrar ${pages[t]?.title || 'pestaña'}`} onClick={() => close(t)}>
                  <X size={12} />
                </button>
              </span>
            ))}
            <button
              type="button"
              className="nx-icon nx-tab-split"
              aria-label="Pantalla dividida"
              title="Abrir otra página al lado"
              aria-pressed={!!split}
              onClick={() => {
                if (split) return useWorkspace.setState({ split: null });
                const other = tabs.find((t) => t !== active) || list.find((p) => p.id !== active)?.id;
                if (other) open(other, 'split');
              }}
            >
              <Columns2 size={15} strokeWidth={1.6} />
            </button>
          </div>
        )}

        {view === 'graph' ? (
          <div className="nx-plain">
            <NxBar {...toggle} title="Grafo" />
            <div className="nx-plain-body">
              <Graph3D pages={list} onOpen={pick} />
            </div>
          </div>
        ) : view === 'library' ? (
          <div className="nx-plain">
            <NxBar {...toggle} title="Biblioteca" />
            <NxLibrary tab={libraryTab} onTab={setLibraryTab} onPick={pick} />
          </div>
        ) : !ready ? null : view === 'templates' || !showPage ? (
          <div className="nx-plain">
            <NxBar {...toggle} title={view === 'templates' ? 'Plantillas' : 'Inicio'} />
            <NxHome onPick={pick} templatesOnly={view === 'templates'} />
          </div>
        ) : (
          <div ref={body} className="nx-panes">
            <div className="nx-pane" style={{ flexBasis: split ? `${ratio * 100}%` : '100%' }}>
              <PageEditor key={active} pageId={active!} onOpen={pick} {...toggle} />
            </div>
            {split && pages[split] && (
              <>
                <div className="ws-divider" role="separator" aria-orientation="vertical" aria-label="Ajustar división" onPointerDown={drag} onDoubleClick={() => setRatio(0.5)} />
                <div className="nx-pane" style={{ flexBasis: `${(1 - ratio) * 100}%` }}>
                  <PageEditor key={split} pageId={split} onOpen={pick} />
                </div>
              </>
            )}
          </div>
        )}
      </main>

      {panel === 'layout' && (
        <div className="ws-modal" role="dialog" aria-modal="true" aria-label="Diseño" onClick={(e) => e.target === e.currentTarget && setPanel(null)}>
          <div className="ws-modal-sheet" style={{ maxWidth: 320, position: 'relative' }}>
            <LayoutPanel onClose={() => setPanel(null)} />
          </div>
        </div>
      )}
      {hub && <HubPanels panel={hub} onClose={() => setHub(null)} />}
    </div>
  );
}

function NxBar({ title, sidebarOpen, onToggleSidebar }: { title: string; sidebarOpen: boolean; onToggleSidebar: () => void }) {
  return (
    <header className="nx-topbar">
      {!sidebarOpen && (
        <button type="button" className="nx-icon" aria-label="Mostrar la barra" title="Mostrar la barra" onClick={onToggleSidebar}>
          <Menu size={17} />
        </button>
      )}
      <span className="nx-crumb">{title}</span>
      <span className="ml-auto">
        <SyncNote />
      </span>
    </header>
  );
}

export default WorkspacePage;
