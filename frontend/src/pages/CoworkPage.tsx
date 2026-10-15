import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Ban,
  Briefcase,
  CheckCircle2,
  CircleDashed,
  HelpCircle,
  Loader2,
  MinusCircle,
  ShieldCheck,
  ShieldAlert,
  Square,
  XCircle,
} from 'lucide-react';
import { apiFetch } from '../lib/api';
import { readSSE } from '../lib/sse';

// Shapes of /v1/cowork (see server/cowork_routes.py and cowork/session.py).
export interface CoworkStep {
  index: number;
  text: string;
  where: string;
  status: string;
  result: string;
  actions: number;
  verdict: { decision?: string; scores?: Record<string, number>; reasons?: string[] };
}

export interface CoworkRun {
  id: string;
  goal: string;
  title: string;
  status: string;
  autonomy: string;
  max_actions: number;
  actions_used: number;
  summary: string;
  steps: CoworkStep[];
  progress: number;
  waiting: number[];
}

interface AuditEntry {
  seq: number;
  event: string;
  ts: number;
  data: Record<string, unknown>;
}

export const STATUS_ES: Record<string, string> = {
  planning: 'Planificando',
  running: 'Trabajando',
  waiting_approval: 'Espera su visto bueno',
  done: 'Terminado',
  partial: 'Hecho en parte',
  failed: 'No se pudo',
  capped: 'Detenido en el tope de acciones',
  cancelled: 'Cancelado',
  interrupted: 'Interrumpido',
};

export const AXIS_ES: Record<string, string> = {
  privacy: 'datos personales',
  destructive: 'borra o sobrescribe',
  external_actor: 'otras personas',
  financial: 'dinero',
  credentials: 'contraseñas',
  system: 'sistema',
  network: 'sale a internet',
  irreversible: 'sin vuelta atrás',
  scope: 'fuera del objetivo',
  uncertainty: 'incierto',
};

const FINISHED = ['done', 'partial', 'failed', 'capped', 'cancelled', 'interrupted'];

// The risky axes of a step, highest first ("dinero 3", "sale a internet 1").
export function riskChips(step: CoworkStep): { axis: string; label: string; score: number }[] {
  const scores = step.verdict?.scores ?? {};
  return Object.entries(scores)
    .filter(([, score]) => score > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([axis, score]) => ({ axis, label: AXIS_ES[axis] ?? axis, score }));
}

export function isFinished(run: Pick<CoworkRun, 'status'>): boolean {
  return FINISHED.includes(run.status);
}

function StepIcon({ status }: { status: string }) {
  const size = 15;
  switch (status) {
    case 'done':
      return <CheckCircle2 size={size} style={{ color: 'var(--color-accent-text)' }} />;
    case 'failed':
      return <XCircle size={size} style={{ color: 'var(--color-error, #6a6a6a)' }} />;
    case 'blocked':
      return <Ban size={size} style={{ color: 'var(--color-error, #6a6a6a)' }} />;
    case 'skipped':
      return <MinusCircle size={size} style={{ color: 'var(--color-text-secondary)' }} />;
    case 'running':
      return <Loader2 size={size} className="animate-spin" style={{ color: 'var(--color-accent-text)' }} />;
    case 'waiting_approval':
      return <HelpCircle size={size} style={{ color: 'var(--color-warning)' }} />;
    default:
      return <CircleDashed size={size} style={{ color: 'var(--color-text-secondary)' }} />;
  }
}

const field = {
  borderColor: 'var(--color-border)',
  background: 'var(--color-surface)',
  color: 'var(--color-text)',
};

// Cowork: describe the outcome, step away, Sergio does the rest.
export function CoworkPage() {
  const [goal, setGoal] = useState('');
  const [autonomy, setAutonomy] = useState('normal');
  const [maxActions, setMaxActions] = useState(50);
  const [runs, setRuns] = useState<CoworkRun[]>([]);
  const [selected, setSelected] = useState<CoworkRun | null>(null);
  const [audit, setAudit] = useState<{ entries: AuditEntry[]; intact: boolean } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const streamRef = useRef<AbortController | null>(null);

  const refreshList = useCallback(async () => {
    try {
      const res = await apiFetch('/v1/cowork');
      if (!res.ok) throw new Error();
      setRuns(((await res.json()).runs ?? []) as CoworkRun[]);
    } catch {
      setError('No pude cargar sus tareas.');
    }
  }, []);

  const follow = useCallback(
    async (run: CoworkRun) => {
      streamRef.current?.abort();
      setSelected(run);
      setAudit(null);
      if (isFinished(run)) return;
      const controller = new AbortController();
      streamRef.current = controller;
      try {
        const res = await apiFetch(`/v1/cowork/${run.id}/events`, { signal: controller.signal });
        await readSSE<{ type: string; run?: CoworkRun }>(res, async (event) => {
          if (streamRef.current !== controller || controller.signal.aborted) return;
          if (event.type === 'snapshot' && event.run) {
            setSelected(event.run);
          } else {
            const fresh = await apiFetch(`/v1/cowork/${run.id}`);
            if (fresh.ok) {
              const snapshot = (await fresh.json()) as CoworkRun;
              if (streamRef.current === controller && !controller.signal.aborted) setSelected(snapshot);
            }
          }
        });
      } catch (err) {
        if ((err as Error).name !== 'AbortError') setError('Se perdió la conexión con Sergio.');
      } finally {
        void refreshList();
      }
    },
    [refreshList],
  );

  useEffect(() => {
    void refreshList();
    return () => streamRef.current?.abort();
  }, [refreshList]);

  const start = async () => {
    if (!goal.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch('/v1/cowork', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, autonomy, max_actions: maxActions }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(String(data.detail ?? `Error ${res.status}`));
        return;
      }
      setGoal('');
      void refreshList();
      void follow(data as CoworkRun);
    } catch {
      setError('No pude conectar con Sergio.');
    } finally {
      setBusy(false);
    }
  };

  const decide = async (step: number, approve: boolean) => {
    if (!selected) return;
    try {
      const res = await apiFetch(`/v1/cowork/${selected.id}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step: step + 1, approve }),
      });
      if (!res.ok) throw new Error();
    } catch { setError('No se guardó su decisión. Vuelva a intentarlo.'); }
  };

  const cancel = async () => {
    try {
      if (selected) {
        const res = await apiFetch(`/v1/cowork/${selected.id}/cancel`, { method: 'POST' });
        if (!res.ok) throw new Error();
      }
    } catch { setError('No pude detener la tarea. Compruebe su conexión.'); }
  };

  const loadAudit = async () => {
    if (!selected) return;
    try {
      const res = await apiFetch(`/v1/cowork/${selected.id}/audit`);
      if (!res.ok) throw new Error();
      setAudit(await res.json());
    } catch { setError('No pude cargar la auditoría.'); }
  };

  const usedPct = selected ? Math.min(100, Math.round((selected.actions_used / selected.max_actions) * 100)) : 0;

  return (
    <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 sm:py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <header className={`space-y-3 ${!selected ? 'text-center pt-12 pb-4' : ''}`}>
          <h1 className={`text-2xl font-medium flex items-center gap-2 ${!selected ? 'justify-center' : ''}`} style={{ color: 'var(--color-text)' }}>
            <Briefcase size={18} /> Cowork
          </h1>
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            ¿En qué trabajamos hoy? Describa el resultado: verá el plan, los avances y los archivos.
          </p>
        </header>

        <section className="space-y-3 rounded-3xl border p-4 shadow-sm" style={field}>
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            rows={3}
            placeholder="Ej.: compara los 3 mejores portátiles para diseño 3D y déjame una tabla en Documentos"
            className="w-full px-2 py-2 rounded-2xl text-base border-0 resize-y outline-none"
            aria-label="Resultado que quiere conseguir"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void start(); }
            }}
            style={field}
          />
          <div className="flex flex-wrap gap-3 items-center">
            <select
              value={autonomy}
              onChange={(e) => setAutonomy(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm border"
              style={field}
              aria-label="Autonomía"
            >
              <option value="cauteloso">Cauteloso: pregunta más</option>
              <option value="normal">Normal</option>
              <option value="autonomo">Autónomo: pregunta menos</option>
            </select>
            <label className="text-sm flex items-center gap-2" style={{ color: 'var(--color-text-secondary)' }}>
              Tope
              <input
                type="number"
                min={1}
                max={500}
                value={maxActions}
                onChange={(e) => setMaxActions(Math.max(1, Math.min(500, Number(e.target.value) || 50)))}
                className="w-20 px-2 py-2 rounded-lg text-sm border"
                style={field}
                aria-label="Tope de acciones"
              />
              acciones
            </label>
            <button
              onClick={start}
              disabled={!goal.trim() || busy}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-white disabled:opacity-50"
              style={{ background: 'var(--color-accent)' }}
            >
              <Briefcase size={16} /> Empezar
            </button>
          </div>
          {error && (
            <p className="text-sm" style={{ color: 'var(--color-warning)' }}>
              {error}
            </p>
          )}
        </section>

        {selected && (
          <section className="rounded-xl p-4 space-y-4" style={{ background: 'var(--color-bg-secondary)' }}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="font-medium" style={{ color: 'var(--color-text)' }}>
                  {selected.title || selected.goal}
                </h2>
                <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  {STATUS_ES[selected.status] ?? selected.status} · autonomía {selected.autonomy}
                </p>
              </div>
              {!isFinished(selected) && (
                <button
                  onClick={cancel}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border"
                  style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                >
                  <Square size={12} /> Detener
                </button>
              )}
            </div>

            <div className="space-y-1">
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-border)' }}>
                <div className="h-full rounded-full" style={{ width: `${usedPct}%`, background: 'var(--color-accent)' }} />
              </div>
              <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                {selected.actions_used} de {selected.max_actions} acciones
              </p>
            </div>

            <ol className="space-y-3">
              {selected.steps.map((step) => (
                <li key={step.index} className="space-y-1.5">
                  <div className="flex items-start gap-2 text-sm" style={{ color: 'var(--color-text)' }}>
                    <span className="mt-0.5 shrink-0">
                      <StepIcon status={step.status} />
                    </span>
                    <span>
                      {step.index + 1}. {step.text}
                    </span>
                  </div>
                  {riskChips(step).length > 0 && (
                    <div className="flex flex-wrap gap-1 pl-6">
                      {riskChips(step).map((chip) => (
                        <span
                          key={chip.axis}
                          className="text-[11px] px-1.5 py-0.5 rounded"
                          style={{
                            background: chip.score >= 2 ? 'rgba(106, 106, 106,0.12)' : 'var(--color-surface)',
                            color: 'var(--color-text-secondary)',
                          }}
                        >
                          {chip.label} {chip.score}
                        </span>
                      ))}
                    </div>
                  )}
                  {step.result && step.status !== 'pending' && (
                    <p className="text-xs pl-6" style={{ color: 'var(--color-text-secondary)' }}>
                      {step.result}
                    </p>
                  )}
                  {step.status === 'waiting_approval' && (
                    <div className="pl-6 space-y-2">
                      <p className="text-xs flex items-center gap-1" style={{ color: 'var(--color-warning)' }}>
                        <ShieldAlert size={12} /> {(step.verdict?.reasons ?? []).join(' ')}
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => decide(step.index, true)}
                          className="px-3 py-1.5 rounded-lg text-xs text-white"
                          style={{ background: 'var(--color-accent)' }}
                        >
                          Sí, hazlo
                        </button>
                        <button
                          onClick={() => decide(step.index, false)}
                          className="px-3 py-1.5 rounded-lg text-xs border"
                          style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                        >
                          No
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ol>

            {selected.summary && (
              <p className="text-sm" style={{ color: 'var(--color-text)' }}>
                {selected.summary}
              </p>
            )}

            <div className="space-y-2">
              <button onClick={loadAudit} className="text-xs underline" style={{ color: 'var(--color-text-secondary)' }}>
                Ver el registro de auditoría
              </button>
              {audit && (
                <div className="space-y-1">
                  <p
                    className="text-xs flex items-center gap-1"
                    style={{ color: audit.intact ? 'var(--color-accent)' : 'var(--color-error, #6a6a6a)' }}
                  >
                    {audit.intact ? <ShieldCheck size={12} /> : <ShieldAlert size={12} />}
                    {audit.intact ? 'Registro íntegro: nadie lo modificó.' : 'El registro fue alterado.'}
                  </p>
                  <ol className="text-[11px] font-mono space-y-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                    {audit.entries.map((entry) => (
                      <li key={entry.seq}>
                        {entry.seq}. {entry.event}{' '}
                        {String(entry.data?.text ?? entry.data?.result ?? entry.data?.decision ?? '').slice(0, 90)}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          </section>
        )}

        {runs.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
              Tareas recientes
            </h2>
            <ul className="space-y-1">
              {runs.map((run) => (
                <li key={run.id}>
                  <button
                    onClick={() => follow(run)}
                    className="w-full text-left px-3 py-2 rounded-lg text-sm flex justify-between gap-2"
                    style={{
                      background: selected?.id === run.id ? 'var(--color-bg-secondary)' : 'transparent',
                      color: 'var(--color-text)',
                    }}
                  >
                    <span className="truncate">{run.title || run.goal}</span>
                    <span className="shrink-0 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                      {STATUS_ES[run.status] ?? run.status}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
