// Creator → Anatomía: the anatomy skill (isometric machine figures) with a
// gallery, a viewer and "Crear lámina". Figures are built by Node on this
// computer; the page is shown in a sandboxed frame (scripts only: no access
// to Sergio's pages, storage or keys).

import { useCallback, useEffect, useState } from 'react';
import { Download, Hammer, Moon, Sparkles, Sun } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { elapsedNote, useElapsed } from './useElapsed';

// The frame is sandboxed without same-origin (it cannot touch Sergio's
// storage or keys), so a figure that remembers its settings gets a storage
// that lives in memory instead of an error.
const MEMORY_STORAGE = `<script>(function(){try{window.localStorage.length}catch(e){var m={};var s={getItem:function(k){return Object.prototype.hasOwnProperty.call(m,k)?m[k]:null},setItem:function(k,v){m[k]=String(v)},removeItem:function(k){delete m[k]},clear:function(){m={}},key:function(i){return Object.keys(m)[i]||null},get length(){return Object.keys(m).length}};['localStorage','sessionStorage'].forEach(function(n){try{Object.defineProperty(window,n,{value:s,configurable:true})}catch(_){}})}})();</script>`;

export function withMemoryStorage(html: string): string {
  const head = /<head[^>]*>/i.exec(html);
  if (head) return html.slice(0, head.index + head[0].length) + MEMORY_STORAGE + html.slice(head.index + head[0].length);
  const doctype = /<!doctype[^>]*>/i.exec(html);
  if (doctype) return html.slice(0, doctype.index + doctype[0].length) + MEMORY_STORAGE + html.slice(doctype.index + doctype[0].length);
  return MEMORY_STORAGE + html;
}

interface Figure {
  name: string;
  title: string;
  description: string;
  built: boolean;
  kind: 'ejemplo' | 'suya';
}

export function AnatomyStudio() {
  const [figures, setFigures] = useState<Figure[]>([]);
  const [current, setCurrent] = useState<string>('');
  const [light, setLight] = useState(false);
  const [html, setHtml] = useState('');
  const [busy, setBusy] = useState('');
  const elapsed = useElapsed(busy);
  const building = busy.startsWith('Construyendo');
  const [prompt, setPrompt] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const res = await apiFetch('/v1/creator/anatomy');
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || 'No pude leer las láminas.');
    setFigures(body.figures as Figure[]);
    return body.figures as Figure[];
  }, []);

  useEffect(() => {
    load()
      .then((list) => {
        if (list.length && !current) setCurrent(list[0].name);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Show a figure: build it if needed (examples), then fetch its page.
  const show = useCallback(
    async (name: string, isLight: boolean) => {
      const fig = figures.find((f) => f.name === name);
      if (!fig) return;
      setError('');
      setHtml('');
      try {
        if (fig.kind === 'ejemplo') {
          setBusy('Construyendo la lámina con Node…');
          const res = await apiFetch('/v1/creator/anatomy/build', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, light: isLight }),
          });
          const body = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(body.detail || 'No pude construir la lámina.');
        }
        const page = await apiFetch(`/v1/creator/anatomy/view/${encodeURIComponent(name)}${isLight ? '?light=1' : ''}`);
        if (!page.ok) throw new Error((await page.json().catch(() => ({}))).detail || 'La lámina no está construida.');
        setHtml(withMemoryStorage(await page.text()));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy('');
      }
    },
    [figures],
  );

  useEffect(() => {
    if (current) void show(current, light);
  }, [current, light, show]);

  const create = async () => {
    const request = prompt.trim();
    if (!request) return;
    setBusy('Sergio está inventando la máquina y escribiendo su lámina (puede tardar un minuto)…');
    setError('');
    setHtml('');
    try {
      const res = await apiFetch('/v1/creator/anatomy/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'No pude crear la lámina.');
      setPrompt('');
      await load();
      setLight(false);
      setCurrent(body.name);
      toast.success(`Lámina creada${body.attempts > 1 ? ` (Node pidió ${body.attempts - 1} corrección${body.attempts > 2 ? 'es' : ''})` : ''}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy('');
    }
  };

  const fig = figures.find((f) => f.name === current);

  return (
    <div className="studio-anatomy">
      <aside className="studio-side studio-gallery" aria-label="Láminas">
        <section className="studio-panel">
          <h3>Láminas</h3>
          <ul className="anatomy-list">
            {figures.map((f) => (
              <li key={f.name}>
                <button type="button" aria-pressed={f.name === current} onClick={() => setCurrent(f.name)} disabled={!!busy}>
                  <b>{f.title}</b>
                  <span>{f.kind === 'suya' ? 'Suya' : f.description}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section className="studio-panel">
          <h3>Qué es</h3>
          <p className="studio-note">
            Una idea técnica explicada como una máquina real en isométrico: piezas sólidas, sombreado de cuatro tonos y
            movimiento. Pídale una a Sergio abajo («explica cómo funciona una caché»).
          </p>
        </section>
      </aside>

      <div className="studio-view">
        <div className="anatomy-bar">
          <h2>{fig?.title ?? 'Anatomía'}</h2>
          <div className="studio-chips">
            <button type="button" aria-pressed={!light} onClick={() => setLight(false)} disabled={!!busy || fig?.kind === 'suya'} title="Tema oscuro">
              <Moon size={14} /> Oscuro
            </button>
            <button type="button" aria-pressed={light} onClick={() => setLight(true)} disabled={!!busy || fig?.kind === 'suya'} title="Tema claro">
              <Sun size={14} /> Claro
            </button>
            <button
              type="button"
              disabled={!html}
              onClick={() => {
                const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
                const a = document.createElement('a');
                a.href = url;
                a.download = `${current}.html`;
                a.click();
                setTimeout(() => URL.revokeObjectURL(url), 2000);
              }}
            >
              <Download size={14} /> HTML
            </button>
          </div>
        </div>
        <div className="anatomy-frame">
          {html ? (
            <iframe title={fig?.title ?? 'Lámina'} sandbox="allow-scripts" srcDoc={html} data-testid="anatomy-frame" />
          ) : (
            <div className="studio-drop">
              {busy ? <Hammer size={26} className="spin-slow" /> : <Sparkles size={26} />}
              <b role={error && !busy ? 'alert' : undefined}>{busy ? busy + elapsedNote(elapsed, building ? 'las láminas grandes tardan unos minutos la primera vez; luego abren al instante' : undefined) : error || 'Elija una lámina'}</b>
            </div>
          )}
        </div>
        <form
          className="studio-ask"
          onSubmit={(e) => {
            e.preventDefault();
            void create();
          }}
        >
          <input
            className="paper-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={!!busy}
            aria-label="Pedir una lámina a Sergio"
            placeholder="Qué quiere explicar: «cómo funciona una caché», «un embrague», «el ciclo de una bomba de agua»"
          />
          <button type="submit" className="paper-button" disabled={!!busy || prompt.trim().length < 4}>
            <Sparkles size={15} /> Crear lámina
          </button>
        </form>
      </div>
    </div>
  );
}

export default AnatomyStudio;
