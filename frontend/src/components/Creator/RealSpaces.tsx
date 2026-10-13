// Creator spaces built on the real programs: Diseño is OpenDesign (and
// Sergio can lay a design out inside it), Código is VSCodium. While a
// program is not installed yet, the quick editor that ships with Sergio
// stays available underneath.

import { lazy, Suspense, useState } from 'react';
import { MonitorUp, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { installProgram, openProgram, type Program } from '../../lib/creatorPrograms';
import { EmbeddedProgram } from './Programs';
import { elapsedNote, useElapsed } from './useElapsed';

const DesignStudio = lazy(() => import('./DesignStudio'));
const CodeStudio = lazy(() => import('./CodeStudio'));

const Quick = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<div className="creator-loading">Abriendo el editor rápido…</div>}>{children}</Suspense>
);

export function DesignSpace({ programs, reload }: { programs: Program[] | null; reload: () => void }) {
  const program = programs?.find((p) => p.id === 'opendesign');
  const [path, setPath] = useState('');
  const [request, setRequest] = useState('');
  const [busy, setBusy] = useState('');
  const elapsed = useElapsed(busy);

  const ask = async () => {
    const text = request.trim();
    if (!text) return;
    setBusy('Sergio está diseñando…');
    try {
      const res = await apiFetch('/v1/creator/opendesign/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: text, width: 1080, height: 1080 }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'No pude crear el diseño.');
      setPath(`design/${body.id}`);
      setRequest('');
      toast.success('Diseño creado: ya puede editarlo.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy('');
    }
  };

  return (
    <EmbeddedProgram
      program={program}
      reload={reload}
      path={path}
      fallback={
        <Quick>
          <DesignStudio mode="diseno" />
        </Quick>
      }
      toolbar={
        program?.running && (
          <form
            className="program-ask"
            onSubmit={(e) => {
              e.preventDefault();
              void ask();
            }}
          >
            <Sparkles size={15} />
            <input
              value={request}
              onChange={(e) => setRequest(e.target.value)}
              placeholder={busy ? `${busy}${elapsedNote(elapsed)}` : 'Pídale un diseño a Sergio: «post para la apertura de mi tienda»'}
              aria-label="Pídale un diseño a Sergio"
              disabled={!!busy}
            />
            <button type="submit" className="paper-button" disabled={!!busy || !request.trim()}>
              Crear
            </button>
          </form>
        )
      }
    />
  );
}

export function CodeSpace({ programs, reload }: { programs: Program[] | null; reload: () => void }) {
  const program = programs?.find((p) => p.id === 'vscodium');
  const desktop = program?.windows;
  const openDesktop = async () => {
    try {
      const out = desktop?.installed ? await openProgram('vscodium') : await installProgram('vscodium', 'windows');
      toast.success(out.message || 'Hecho.');
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <EmbeddedProgram
      program={program}
      reload={reload}
      fallback={
        <Quick>
          <CodeStudio />
        </Quick>
      }
      toolbar={
        desktop?.reachable && (
          <button type="button" className="paper-button" data-variant="quiet" onClick={() => void openDesktop()}>
            <MonitorUp size={15} /> {desktop.installed ? 'Abrir en Windows' : 'Instalar en Windows'}
          </button>
        )
      }
    />
  );
}
