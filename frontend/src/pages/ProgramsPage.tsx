import { useEffect, useMemo, useState } from 'react';
import { ArrowDownToLine, ArrowUpRight, Boxes, Check, ChevronRight, Code2, Cuboid, FileImage, LayoutTemplate, Search, TrendingUp } from 'lucide-react';
import { apiFetch } from '../lib/api';
import '../components/Studio/studio.css';

interface Program {
  id: string; name: string; group: string; description: string;
  source: string; license: string; detected: boolean; installable: boolean;
  download: string; adapter: string; note: string; opens_window: boolean;
}
interface Shelf { host: string; scope: string; programs: Program[] }
const GROUPS = ['Todo', 'Código', 'Arquitectura', 'Creatividad', 'Diseño', 'Mercados'];
const ICONS: Record<string, typeof Code2> = { Código: Code2, Arquitectura: Cuboid, Creatividad: FileImage, Diseño: LayoutTemplate, Mercados: TrendingUp };

async function read<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await apiFetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'No pude completar esta operación.');
  }
  return res.json();
}

export function ProgramsPage() {
  const [shelf, setShelf] = useState<Shelf | null>(null);
  const [group, setGroup] = useState('Todo');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState('');
  const [design, setDesign] = useState<{ ready: boolean; templates?: number; editor?: string; message?: string } | null>(null);
  const [canvasName, setCanvasName] = useState('Mi próximo proyecto');
  useEffect(() => {
    let active = true;
    read<Shelf>('/v1/programs').then(s => { if (active) setShelf(s); }).catch(e => { if (active) setMessage(e.message); });
    return () => { active = false; };
  }, []);
  const programs = useMemo(() => (shelf?.programs || []).filter(p =>
    (group === 'Todo' || p.group === group) && `${p.name} ${p.description}`.toLowerCase().includes(query.toLowerCase())), [shelf, group, query]);

  async function open(p: Program) {
    setBusy(p.id); setMessage('');
    try { const out = await read<{ result: string }>(`/v1/programs/${p.id}/open`, { method: 'POST' }); setMessage(out.result); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'No pude abrir la aplicación.'); }
    finally { setBusy(''); }
  }
  async function downloadInstaller() {
    setBusy('installer'); setMessage('');
    try {
      const res = await apiFetch('/v1/programs/installer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: selected }) });
      if (!res.ok) throw new Error('No pude preparar el instalador. Revise la selección.');
      const url = URL.createObjectURL(await res.blob());
      const link = document.createElement('a'); link.href = url; link.download = 'Sergio-Programas.ps1'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      setMessage('Instalador preparado. Ejecute el archivo descargado en PowerShell para instalar su selección.');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'No pude preparar el archivo.'); }
    finally { setBusy(''); }
  }
  async function connectDesign() {
    setBusy('opendesign'); setMessage('');
    try { const out = await read<typeof design>('/v1/programs/opendesign/status'); setDesign(out); if (!out?.ready) setMessage(out?.message || 'Servicio pendiente.'); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'No pude conectar.'); }
    finally { setBusy(''); }
  }
  async function createCanvas() {
    setBusy('canvas'); setMessage('');
    try {
      const out = await read<{ id: string; name: string }>('/v1/programs/opendesign/canvas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: canvasName, width: 1080, height: 1080 }) });
      setMessage(`Lienzo creado en OpenDesign: ${out.name} (${out.id}).`);
    } catch (e) { setMessage(e instanceof Error ? e.message : 'No pude crear el lienzo.'); }
    finally { setBusy(''); }
  }

  return <div className="studio-page">
    <div className="studio-content">
      <header className="studio-heading"><span className="studio-kicker">ESTUDIO</span><h1>Herramientas para hacer.</h1>
        <p>Del primer boceto al último commit. Sus aplicaciones completas, en una misma mesa de trabajo.</p>
      </header>
      <section className="studio-feature" aria-label="Editor de diseño conectado">
        <div className="studio-feature-symbol"><LayoutTemplate size={38} strokeWidth={1.1} /><span>OD</span></div>
        <div className="studio-feature-copy"><span className="studio-kicker">LIENZOS Y MARCAS</span><h2>Un espacio para sus ideas.</h2>
          <p>OpenDesign conserva su editor, plantillas, páginas, fuentes y exportación. Sergio puede crear lienzos y rellenar sus campos.</p>
          <div className="studio-inline-actions"><button className="studio-button" disabled={!!busy} onClick={connectDesign}>{design?.ready ? <Check size={15} /> : <Boxes size={15} />}{design?.ready ? `${design.templates} plantillas disponibles` : 'Comprobar conexión'}</button>
            {design?.ready && <a className="studio-button studio-button-quiet" href={design.editor} target="_blank" rel="noopener noreferrer">Abrir editor completo <ArrowUpRight size={15} /></a>}</div>
          {design?.ready && <form className="studio-canvas-form" onSubmit={e => { e.preventDefault(); createCanvas(); }}><input aria-label="Nombre del lienzo" value={canvasName} maxLength={100} onChange={e => setCanvasName(e.target.value)} /><button className="studio-button studio-button-quiet" disabled={!!busy || !canvasName.trim()}>Crear lienzo <ChevronRight size={15} /></button></form>}
        </div>
      </section>
      <div className="studio-shelf-bar"><div className="studio-tabs" role="group" aria-label="Categoría de herramientas">{GROUPS.map(g => <button key={g} aria-pressed={group === g} onClick={() => setGroup(g)}>{g}</button>)}</div>
        <label className="studio-search"><Search size={15} /><input aria-label="Buscar herramientas" placeholder="Buscar herramienta" value={query} onChange={e => setQuery(e.target.value)} /></label></div>
      <div className="studio-status-row"><span>{shelf ? `${shelf.programs.length} herramientas · detección en ${shelf.host} del servidor` : 'Cargando herramientas…'}</span><span>Instalación a su elección</span></div>
      {message && <p className="studio-message" role="status">{message}</p>}
      <div className="studio-programs" aria-busy={!shelf}>
        {programs.map(p => { const Icon = ICONS[p.group] || Code2; return <article key={p.id} className="studio-program">
          <div className="studio-program-top"><span className="studio-app-mark"><Icon size={22} strokeWidth={1.3} /></span><span className="studio-program-kind">{p.group}</span>
            {p.installable && <label className="studio-select"><input type="checkbox" aria-label={`Incluir ${p.name} en el instalador`} checked={selected.includes(p.id)} onChange={e => setSelected(s => e.target.checked ? [...s, p.id] : s.filter(x => x !== p.id))} /></label>}</div>
          <h2>{p.name}</h2><p>{p.description}</p>
          {p.note && <details><summary>Sobre esta integración</summary><p>{p.note}</p></details>}
          <div className="studio-program-foot"><span className="studio-detection" data-found={p.detected || undefined}>{p.detected ? 'En PATH del servidor' : p.adapter === 'reference' ? 'Licencia por verificar' : 'Sin detectar en PATH'}</span>
            {p.opens_window && <button disabled={!!busy} onClick={() => open(p)} aria-label={`Abrir ${p.name} en Windows`}>{busy === p.id ? 'Abriendo…' : 'Abrir'} <ArrowUpRight size={14} /></button>}</div>
          <div className="studio-program-source"><a href={p.source} target="_blank" rel="noopener noreferrer">GitHub ↗</a><span>{p.license}</span>{!p.installable && <a href={p.download} target="_blank" rel="noopener noreferrer">Releases ↗</a>}</div>
        </article> })}
      </div>
      {shelf && !programs.length && <p className="studio-message">No hay herramientas que coincidan con su búsqueda.</p>}
      <footer className="studio-install-bar"><div><strong>{selected.length ? `${selected.length} ${selected.length === 1 ? 'aplicación seleccionada' : 'aplicaciones seleccionadas'}` : 'Prepare su equipo a su medida.'}</strong><p>El archivo instala únicamente lo que usted elige mediante WinGet en Windows.</p></div><button className="studio-button" disabled={!selected.length || !!busy} onClick={downloadInstaller}><ArrowDownToLine size={16} /> Preparar instalador</button></footer>
      <details className="studio-setup"><summary>Preparar OpenDesign y Kronos</summary><p>En Ubuntu, dentro del repositorio de Sergio:</p><code>bash scripts/preparar-integraciones.sh opendesign</code><p>Luego: <code>bash scripts/preparar-integraciones.sh iniciar-opendesign</code>. Abra el editor en el puerto 5178.</p><p>Para el entorno de Kronos: <code>bash scripts/preparar-integraciones.sh kronos</code>. Sus pesos se preparan por separado; el modelo nunca opera en bolsa.</p></details>
    </div>
  </div>;
}
