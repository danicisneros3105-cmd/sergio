import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  Archive,
  Columns2,
  Download,
  FileText,
  ListTree,
  Network,
  Plus,
  Search,
  SlidersHorizontal,
  Star,
  X,
  Users,
  KanbanSquare,
  BookOpen,
  Timer,
} from 'lucide-react';
import { PaperHead } from '../components/Paper/PaperPage';
import { PageEditor } from '../components/Workspace/PageEditor';
import { Graph3D } from '../components/Workspace/Graph3D';
import { useWorkspace } from '../lib/workspace/store';
import { TEMPLATES, previewLines, type Page } from '../lib/workspace/model';
import { apiFetch } from '../lib/api';
import { relativeDay } from '../lib/paper';

const TEMPLATE_ICONS: Record<string, typeof FileText> = { file: FileText, users: Users, kanban: KanbanSquare, book: BookOpen, timer: Timer };

function SyncNote() {
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

function Tree({ onPick, onClose }: { onPick: (id: string) => void; onClose: () => void }) {
  const pages = useWorkspace((s) => s.pages);
  const create = useWorkspace((s) => s.create);
  const [q, setQ] = useState('');
  const all = Object.values(pages);
  const match = (p: Page) => !q || `${p.title} ${previewLines(p, 20).join(' ')}`.toLowerCase().includes(q.toLowerCase());
  const children = (parent: string | null) =>
    all.filter((p) => p.parent === parent && (parent !== null || !p.parent || !pages[p.parent])).sort((a, b) => a.title.localeCompare(b.title, 'es'));
  const render = (parent: string | null, depth: number): React.ReactNode =>
    children(parent).map((p) => (
      <div key={p.id}>
        {match(p) && (
          <button type="button" className="mac-row" style={{ paddingLeft: 10 + depth * 14 }} onClick={() => onPick(p.id)}>
            {p.favorite ? <Star size={12} fill="currentColor" /> : <FileText size={13} strokeWidth={1.5} />}
            <span className="truncate">{p.title || 'Sin título'}</span>
          </button>
        )}
        {render(p.id, depth + 1)}
      </div>
    ));
  return (
    <aside className="ws-drawer" aria-label="Páginas">
      <div className="flex items-center gap-2 mb-3">
        <span className="paper-label flex-1">Páginas</span>
        <button type="button" className="mac-icon-btn" aria-label="Nueva página" onClick={() => onPick(create({ open: false }).id)}>
          <Plus size={15} />
        </button>
        <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={onClose}>
          <X size={15} />
        </button>
      </div>
      <label className="mac-field text-[13px] mb-3">
        <Search size={13} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar en páginas" className="flex-1 bg-transparent outline-none" aria-label="Buscar en páginas" />
      </label>
      {all.filter((p) => p.favorite).length > 0 && !q && (
        <>
          <div className="paper-label mb-1">Favoritas</div>
          {all
            .filter((p) => p.favorite)
            .map((p) => (
              <button key={p.id} type="button" className="mac-row" onClick={() => onPick(p.id)}>
                <Star size={12} fill="currentColor" />
                <span className="truncate">{p.title || 'Sin título'}</span>
              </button>
            ))}
          <div className="paper-label mt-3 mb-1">Todas</div>
        </>
      )}
      <nav>{render(null, 0)}</nav>
    </aside>
  );
}

function LayoutPanel({ onClose }: { onClose: () => void }) {
  const layout = useWorkspace((s) => s.layout);
  const setLayout = useWorkspace((s) => s.setLayout);
  return (
    <div className="ws-pop" style={{ right: 0, top: 40, width: 260 }} role="dialog" aria-label="Diseño">
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
      <button type="button" className="paper-button w-full mt-2" data-variant="quiet" onClick={onClose}>
        Listo
      </button>
    </div>
  );
}

function Vault({ onClose }: { onClose: () => void }) {
  const vault = useWorkspace((s) => s.vault);
  const loadVault = useWorkspace((s) => s.loadVault);
  const restore = useWorkspace((s) => s.restore);
  const autoArchive = useWorkspace((s) => s.autoArchive);
  const [note, setNote] = useState('');
  useEffect(() => {
    void loadVault();
  }, [loadVault]);
  return (
    <div className="ws-modal" role="dialog" aria-modal="true" aria-label="Baúl">
      <div className="ws-modal-sheet" style={{ maxWidth: 560 }}>
        <h3 className="paper-title" style={{ fontSize: 16 }}>Baúl</h3>
        <p className="text-[13.5px] mt-3">
          Lo que no se abre en 90 días, y las tareas terminadas hace más de 30, viene aquí solo: fuera de las listas y de la
          búsqueda, para que todo vaya rápido. Nada se borra.
        </p>
        <div className="mt-3 max-h-[45vh] overflow-y-auto">
          {(vault || []).length === 0 && <p className="text-[13px]" style={{ color: 'var(--color-text-tertiary)' }}>El baúl está vacío.</p>}
          {(vault || []).map((p) => (
            <div key={p.id} className="flex items-center gap-2 py-1.5" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
              <span className="flex-1 truncate">{p.title || 'Sin título'}</span>
              <span className="text-[11.5px]" style={{ color: 'var(--color-text-tertiary)' }}>{relativeDay(p.updatedAt)}</span>
              <button type="button" className="paper-tab text-[12px]" onClick={() => void restore(p.id)}>
                Devolver
              </button>
            </div>
          ))}
        </div>
        {note && <p className="mt-2 text-[13px]">{note}</p>}
        <div className="flex gap-2 justify-end mt-4">
          <button
            type="button"
            className="paper-button"
            data-variant="quiet"
            onClick={async () => {
              const r = await autoArchive();
              setNote(`Ordenado: ${r.pages} páginas, ${r.rows} filas y ${r.todos} tareas al baúl.`);
              void loadVault();
            }}
          >
            Ordenar ahora
          </button>
          <button type="button" className="paper-button" onClick={onClose}>
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
}

function Start() {
  const create = useWorkspace((s) => s.create);
  return (
    <div className="ws-start">
      <p className="text-center text-[14px] mb-8" style={{ color: 'var(--color-text-secondary)' }}>
        Empiece con una de estas. Todo se guarda en su equipo al instante, también sin internet.
      </p>
      <div className="paper-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
        {TEMPLATES.map((t) => {
          const Icon = TEMPLATE_ICONS[t.icon] || FileText;
          return (
            <button key={t.key} type="button" className="paper-card" onClick={() => create({ template: t.key })}>
              <span className="paper-thumb">
                <Icon size={28} strokeWidth={1.1} />
              </span>
              <span>
                <span className="paper-name block">{t.name}</span>
                <span className="paper-meta block">{t.description}</span>
              </span>
            </button>
          );
        })}
      </div>
      <p className="text-center text-[12.5px] mt-8" style={{ color: 'var(--color-text-tertiary)' }}>
        En una página: «/» inserta tablas, gráficos, un pomodoro, audio o un mapa conceptual · [[Título]] enlaza páginas ·
        Alt+↑/↓ mueve bloques.
      </p>
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
  const layout = useWorkspace((s) => s.layout);
  const open = useWorkspace((s) => s.open);
  const close = useWorkspace((s) => s.close);
  const setActive = useWorkspace((s) => s.setActive);
  const setRatio = useWorkspace((s) => s.setRatio);
  const create = useWorkspace((s) => s.create);
  const syncNow = useWorkspace((s) => s.syncNow);
  const [panel, setPanel] = useState<null | 'tree' | 'graph' | 'vault' | 'layout'>(null);
  const body = useRef<HTMLDivElement>(null);

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
      setPanel(null);
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
  const maxWidth = layout.width === 'narrow' ? 720 : layout.width === 'wide' ? 1040 : 'none';

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

  return (
    <div className="paper-page" style={{ paddingBottom: 0 }}>
      <div className="paper-page-inner" style={{ maxWidth }}>
        <PaperHead
          title="Workspace"
          left={
            <>
              <button type="button" className="mac-icon-btn" aria-label="Páginas" title="Páginas" onClick={() => setPanel(panel === 'tree' ? null : 'tree')}>
                <ListTree size={17} strokeWidth={1.4} />
              </button>
              <SyncNote />
            </>
          }
          right={
            <span className="relative flex gap-1">
              <button type="button" className="mac-icon-btn" aria-label="Grafo de conocimiento" title="Grafo 3D" aria-pressed={panel === 'graph'} onClick={() => setPanel(panel === 'graph' ? null : 'graph')}>
                <Network size={17} strokeWidth={1.4} />
              </button>
              <button type="button" className="mac-icon-btn" aria-label="Baúl" title="Baúl" onClick={() => setPanel('vault')}>
                <Archive size={17} strokeWidth={1.4} />
              </button>
              <button type="button" className="mac-icon-btn" aria-label="Diseño" title="Diseño" onClick={() => setPanel(panel === 'layout' ? null : 'layout')}>
                <SlidersHorizontal size={17} strokeWidth={1.4} />
              </button>
              <button type="button" className="mac-icon-btn" aria-label="Exportar todo" title="Exportar todo (Markdown + JSON)" onClick={() => void exportAll()}>
                <Download size={17} strokeWidth={1.4} />
              </button>
              <button type="button" className="mac-icon-btn" aria-label="Nueva página" title="Nueva página" onClick={() => create()}>
                <Plus size={17} strokeWidth={1.4} />
              </button>
              {panel === 'layout' && <LayoutPanel onClose={() => setPanel(null)} />}
            </span>
          }
        />

        {tabs.length > 0 && (
          <div className="ws-tabs" role="tablist" aria-label="Páginas abiertas">
            {tabs.map((t) => (
              <span key={t} className="ws-tab" data-active={t === active || undefined} data-split={t === split || undefined}>
                <button type="button" role="tab" aria-selected={t === active} onClick={() => setActive(t)}>
                  {pages[t]?.title || 'Sin título'}
                </button>
                <button type="button" className="ws-tab-x" aria-label={`Cerrar ${pages[t]?.title || 'pestaña'}`} onClick={() => close(t)}>
                  <X size={11} />
                </button>
              </span>
            ))}
            {active && (
              <button
                type="button"
                className="mac-icon-btn ml-auto"
                aria-label="Pantalla dividida"
                title="Abrir otra página al lado"
                aria-pressed={!!split}
                onClick={() => {
                  if (split) return useWorkspace.setState({ split: null });
                  const other = tabs.find((t) => t !== active) || list.find((p) => p.id !== active)?.id;
                  if (other) open(other, 'split');
                }}
              >
                <Columns2 size={15} strokeWidth={1.4} />
              </button>
            )}
          </div>
        )}
      </div>

      {panel === 'graph' ? (
        <div className="paper-page-inner" style={{ maxWidth: 1040 }}>
          <Graph3D pages={list} onOpen={pick} />
        </div>
      ) : !ready ? null : !active || !pages[active] ? (
        <div className="paper-page-inner">
          <Start />
        </div>
      ) : (
        <div ref={body} className="ws-panes" style={{ maxWidth: split ? 'none' : maxWidth }}>
          <div className="ws-pane" style={{ flexBasis: split ? `${ratio * 100}%` : '100%' }}>
            <PageEditor key={active} pageId={active} />
          </div>
          {split && pages[split] && (
            <>
              <div className="ws-divider" role="separator" aria-orientation="vertical" aria-label="Ajustar división" onPointerDown={drag} onDoubleClick={() => setRatio(0.5)} />
              <div className="ws-pane" style={{ flexBasis: `${(1 - ratio) * 100}%` }}>
                <PageEditor key={split} pageId={split} />
              </div>
            </>
          )}
        </div>
      )}

      {panel === 'tree' && <Tree onPick={pick} onClose={() => setPanel(null)} />}
      {panel === 'vault' && <Vault onClose={() => setPanel(null)} />}
    </div>
  );
}

export default WorkspacePage;
