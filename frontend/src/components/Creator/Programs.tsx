// The real programs of each Creator space: a slim shelf with the Windows ones
// (install / open), and the ones Sergio serves inside the web (OpenDesign,
// VSCodium) shown full size in a frame, started when the space opens.

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Download, ExternalLink, Loader2, MonitorUp, RotateCw } from 'lucide-react';
import { toast } from 'sonner';
import {
  embedUrl,
  installProgram,
  listPrograms,
  openProgram,
  programState,
  startProgram,
  type Program,
} from '../../lib/creatorPrograms';

/** All programs, refreshed every few seconds while something installs. */
export function usePrograms() {
  const [programs, setPrograms] = useState<Program[] | null>(null);
  const [error, setError] = useState('');
  const reload = useCallback(async () => {
    try {
      setPrograms(await listPrograms());
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  const busy = programs?.some((p) => p.installing || p.windows?.installing);
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => void reload(), 5000);
    return () => window.clearInterval(t);
  }, [busy, reload]);
  return { programs, error, reload };
}

const STATE_LABEL = {
  listo: 'Instalado',
  instalando: 'Instalando…',
  falta: 'Sin instalar',
  'sin-escritorio': 'Abra Sergio en Windows',
} as const;

function ProgramCard({ p, reload }: { p: Program; reload: () => void }) {
  const state = programState(p);
  const [working, setWorking] = useState(false);
  const act = async (fn: () => Promise<{ message?: string }>) => {
    setWorking(true);
    try {
      const out = await fn();
      if (out.message) toast.success(out.message);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setWorking(false);
    }
  };
  return (
    <article className="program-card" data-state={state} title={p.what}>
      <div>
        <b>{p.name}</b>
      </div>
      <em>{p.error && state === 'falta' ? `No se pudo: ${p.error.slice(0, 80)}` : STATE_LABEL[state]}</em>
      {state === 'listo' ? (
        <button type="button" className="paper-button" disabled={working} onClick={() => act(() => openProgram(p.id))}>
          <MonitorUp size={15} /> Abrir
        </button>
      ) : state === 'falta' ? (
        <button type="button" className="paper-button" data-variant="quiet" disabled={working} onClick={() => act(() => installProgram(p.id))}>
          <Download size={15} /> Instalar
        </button>
      ) : state === 'instalando' ? (
        <Loader2 className="program-spin" size={16} aria-label="Instalando" />
      ) : null}
    </article>
  );
}

/** The Windows programs of a space, as a slim shelf above the work area. */
export function ProgramShelf({ space, programs, reload }: { space: string; programs: Program[] | null; reload: () => void }) {
  const mine = (programs || []).filter((p) => p.space === space && p.where === 'windows');
  if (!mine.length) return null;
  return (
    <div className="program-shelf" aria-label="Programas de este espacio">
      {mine.map((p) => (
        <ProgramCard key={p.id} p={p} reload={reload} />
      ))}
    </div>
  );
}

/** A program Sergio serves inside the web, full size. Starts it on demand;
 * without it installed, offers to install it and shows *fallback* meanwhile. */
export function EmbeddedProgram({
  program,
  reload,
  path = '',
  fallback,
  toolbar,
}: {
  program: Program | undefined;
  reload: () => void;
  path?: string;
  fallback?: ReactNode;
  toolbar?: ReactNode;
}) {
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState('');
  const [frameKey, setFrameKey] = useState(0);
  const tried = useRef(false);

  useEffect(() => {
    if (!program?.installed || program.running || tried.current) return;
    tried.current = true;
    setStarting(true);
    startProgram(program.id)
      .then((out) => {
        if (!out.running) setProblem(out.outcome);
        reload();
      })
      .catch((e) => setProblem(e instanceof Error ? e.message : String(e)))
      .finally(() => setStarting(false));
  }, [program, reload]);

  if (!program) return <div className="creator-loading">Buscando los programas…</div>;

  if (!program.installed) {
    return (
      <div className="program-missing">
        <div className="program-missing-card">
          <b>{program.name}</b>
          <p className="studio-note">
            {program.installing
              ? 'Se está instalando en este equipo (un par de minutos).'
              : 'Sin instalar en este equipo: se instala con la próxima actualización.'}
          </p>
          {!program.installing && (
            <button
              type="button"
              className="paper-button"
              onClick={() =>
                installProgram(program.id)
                  .then(() => {
                    toast.success(`Instalando ${program.name}…`);
                    reload();
                  })
                  .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
              }
            >
              <Download size={15} /> Instalar {program.name}
            </button>
          )}
          {program.error && <p className="studio-error">{program.error}</p>}
        </div>
        {fallback && <div className="program-fallback">{fallback}</div>}
      </div>
    );
  }

  const url = embedUrl(program) + path.replace(/^\//, '');
  return (
    <div className="program-embed">
      <div className="program-embed-bar">
        <b>{program.name}</b>
        {toolbar}
        <span className="program-embed-spacer" />
        <button type="button" className="mac-icon-btn" title="Recargar" aria-label="Recargar" onClick={() => setFrameKey((k) => k + 1)}>
          <RotateCw size={15} />
        </button>
        <a className="mac-icon-btn" href={url} target="_blank" rel="noreferrer" title="Abrir en otra pestaña" aria-label="Abrir en otra pestaña">
          <ExternalLink size={15} />
        </a>
      </div>
      {program.running ? (
        <iframe key={`${frameKey}-${path}`} src={url} title={program.name} className="program-frame" allow="clipboard-read; clipboard-write" />
      ) : (
        <div className="creator-loading">
          {problem ? `No pude abrir ${program.name}: ${problem}` : starting ? `Abriendo ${program.name}…` : `Preparando ${program.name}…`}
        </div>
      )}
    </div>
  );
}
