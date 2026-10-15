import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowUp,
  Ban,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  Copy,
  FileText,
  HelpCircle,
  ListChecks,
  Loader2,
  MinusCircle,
  PanelRight,
  Paperclip,
  Plus,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Square,
  X,
  XCircle,
} from 'lucide-react';
import { apiFetch } from '../lib/api';
import {
  AUTONOMY_ES,
  SUGGESTIONS,
  applySlash,
  clampActions,
  filesIn,
  slashMatches,
  timeAgo,
  workedFor,
  type Autonomy,
  type ComposerOptions,
} from '../lib/cowork';
import '../components/Cowork/cowork.css';

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
  created?: number;
  updated?: number;
  notes?: Array<{ text: string; at: number }>;
  follows?: string;
  context?: string;
  plan_first?: boolean;
}

interface AuditEntry {
  seq: number;
  event: string;
  ts: number;
  data: Record<string, unknown>;
}

export const STATUS_ES: Record<string, string> = {
  planning: 'Planificando',
  waiting_plan: 'Espera que apruebe el plan',
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
const ATTACH = ' [Adjunto: ';

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

/** The words of the request and the names of the files attached to it. */
function splitGoal(goal: string): { text: string; files: string[] } {
  const [text, ...rest] = goal.split(ATTACH);
  return { text: text.trim(), files: rest.map((r) => r.slice(0, r.indexOf(']')).trim()).filter(Boolean) };
}

function StepIcon({ status }: { status: string }) {
  const size = 16;
  switch (status) {
    case 'done':
      return <CheckCircle2 size={size} />;
    case 'failed':
      return <XCircle size={size} />;
    case 'blocked':
      return <Ban size={size} />;
    case 'skipped':
      return <MinusCircle size={size} className="cw-dim" />;
    case 'running':
      return <Loader2 size={size} className="animate-spin" />;
    case 'waiting_approval':
      return <HelpCircle size={size} />;
    default:
      return <Circle size={size} className="cw-dim" />;
  }
}

const DEFAULTS: ComposerOptions = { autonomy: 'normal', maxActions: 50, planFirst: false };

// ── the composer (home and task) ────────────────────────────────────────────
function Composer({
  value,
  onChange,
  onSubmit,
  placeholder,
  options,
  setOptions,
  withOptions,
  attachments,
  setAttachments,
  busy,
  onStop,
  big,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  placeholder: string;
  options?: ComposerOptions;
  setOptions?: (o: ComposerOptions) => void;
  withOptions?: boolean;
  attachments?: Array<{ name: string; text: string }>;
  setAttachments?: (a: Array<{ name: string; text: string }>) => void;
  busy?: boolean;
  onStop?: () => void;
  big?: boolean;
}) {
  const [menu, setMenu] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const matches = withOptions ? slashMatches(value) : [];

  useEffect(() => {
    if (!menu) return;
    const close = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(false);
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [menu]);

  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [value]);

  const submit = () => {
    if (withOptions && options && setOptions) {
      const next = applySlash(value, options);
      if (next) {
        setOptions(next);
        onChange('');
        return;
      }
    }
    if (value.trim() && !busy) onSubmit();
  };

  const attach = async (list: FileList | null) => {
    if (!list || !setAttachments) return;
    const read = await Promise.all(
      [...list].slice(0, 5).map(async (f) => ({ name: f.name, text: (await f.text().catch(() => '')).slice(0, 3000) })),
    );
    setAttachments([...(attachments ?? []), ...read]);
    setMenu(false);
  };

  const chips: Array<{ key: string; label: string; clear: () => void }> = [];
  if (options && setOptions) {
    if (options.planFirst) chips.push({ key: 'plan', label: 'Plan', clear: () => setOptions({ ...options, planFirst: false }) });
    if (options.autonomy !== 'normal')
      chips.push({ key: 'aut', label: AUTONOMY_ES[options.autonomy], clear: () => setOptions({ ...options, autonomy: 'normal' }) });
    if (options.maxActions !== DEFAULTS.maxActions)
      chips.push({ key: 'tope', label: `Tope ${options.maxActions}`, clear: () => setOptions({ ...options, maxActions: DEFAULTS.maxActions }) });
  }

  return (
    <div className={`cw-composer${big ? ' cw-composer-big' : ''}`}>
      {matches.length > 0 && (
        <ul className="cw-slash" role="listbox" aria-label="Comandos">
          {matches.map((c) => (
            <li key={c.cmd}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  if (c.cmd === '/tope') onChange('/tope ');
                  else if (options && setOptions) {
                    setOptions(c.apply(options, ''));
                    onChange('');
                  }
                }}
              >
                <b>{c.cmd}</b>
                <span>{c.label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {attachments && attachments.length > 0 && (
        <div className="cw-attachments">
          {attachments.map((a, i) => (
            <span key={`${a.name}${i}`} className="cw-file-chip">
              <FileText size={14} />
              {a.name}
              <button type="button" aria-label={`Quitar ${a.name}`} onClick={() => setAttachments?.(attachments.filter((_, j) => j !== i))}>
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
      <textarea
        ref={area}
        value={value}
        rows={big ? 2 : 1}
        placeholder={placeholder}
        aria-label={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className="cw-composer-bar">
        {withOptions && (
          <div className="cw-plus-wrap">
            <button type="button" className="cw-round" aria-label="Más opciones" aria-expanded={menu} onClick={() => setMenu(!menu)}>
              <Plus size={18} />
            </button>
            {menu && options && setOptions && (
              <>
                <div className="cw-backdrop" onClick={() => setMenu(false)} />
                <div className="cw-menu" role="menu">
                  <button type="button" role="menuitem" onClick={() => fileInput.current?.click()}>
                    <Paperclip size={16} /> Adjuntar archivos
                  </button>
                  <button
                    type="button"
                    role="menuitemcheckbox"
                    aria-checked={options.planFirst}
                    onClick={() => setOptions({ ...options, planFirst: !options.planFirst })}
                  >
                    <ListChecks size={16} /> Modo plan
                    {options.planFirst && <Check size={15} className="cw-menu-check" />}
                  </button>
                  <div className="cw-menu-sep" />
                  <div className="cw-menu-label">
                    <SlidersHorizontal size={14} /> Autonomía
                  </div>
                  {(['cauteloso', 'normal', 'autonomo'] as Autonomy[]).map((a) => (
                    <button
                      key={a}
                      type="button"
                      role="menuitemradio"
                      aria-checked={options.autonomy === a}
                      className="cw-menu-sub"
                      onClick={() => setOptions({ ...options, autonomy: a })}
                    >
                      {AUTONOMY_ES[a]}
                      <span className="cw-dim">{a === 'cauteloso' ? 'pregunta más' : a === 'autonomo' ? 'pregunta menos' : ''}</span>
                      {options.autonomy === a && <Check size={15} className="cw-menu-check" />}
                    </button>
                  ))}
                  <div className="cw-menu-sep" />
                  <label className="cw-menu-row">
                    Tope de acciones
                    <input
                      type="number"
                      min={1}
                      max={500}
                      value={options.maxActions}
                      onChange={(e) => setOptions({ ...options, maxActions: clampActions(Number(e.target.value) || 1) })}
                    />
                  </label>
                </div>
              </>
            )}
            <input ref={fileInput} type="file" multiple hidden onChange={(e) => void attach(e.target.files)} />
          </div>
        )}
        {chips.map((c) => (
          <span key={c.key} className="cw-chip">
            {c.label}
            <button type="button" aria-label={`Quitar ${c.label}`} onClick={c.clear}>
              <X size={12} />
            </button>
          </span>
        ))}
        <span className="cw-spacer" />
        {onStop && !value.trim() ? (
          <button type="button" className="cw-send" aria-label="Detener" onClick={onStop}>
            <Square size={13} fill="currentColor" />
          </button>
        ) : (
          <button type="button" className="cw-send" aria-label="Enviar" disabled={!value.trim() || busy} onClick={submit}>
            <ArrowUp size={18} />
          </button>
        )}
      </div>
    </div>
  );
}

// ── the page ────────────────────────────────────────────────────────────────
export function CoworkPage() {
  const [runs, setRuns] = useState<CoworkRun[]>([]);
  const [run, setRun] = useState<CoworkRun | null>(null);
  const [text, setText] = useState('');
  const [reply, setReply] = useState('');
  const [options, setOptions] = useState<ComposerOptions>(DEFAULTS);
  const [attachments, setAttachments] = useState<Array<{ name: string; text: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [panel, setPanel] = useState(() => typeof window !== 'undefined' && window.innerWidth >= 1100);
  const [tab, setTab] = useState<'plan' | 'archivos' | 'registro'>('plan');
  const [audit, setAudit] = useState<{ entries: AuditEntry[]; intact: boolean } | null>(null);
  const [activity, setActivity] = useState<boolean | null>(null);
  const watching = useRef<string | null>(null);
  const thread = useRef<HTMLDivElement>(null);

  const refreshList = useCallback(async () => {
    try {
      const res = await apiFetch('/v1/cowork');
      if (!res.ok) throw new Error();
      setRuns(((await res.json()).runs ?? []) as CoworkRun[]);
    } catch {
      setError('No pude cargar sus tareas.');
    }
  }, []);

  useEffect(() => {
    void refreshList();
    return () => {
      watching.current = null;
    };
  }, [refreshList]);

  // Follow a run until it ends (a light poll: works through any proxy).
  const open = useCallback(
    async (id: string, first?: CoworkRun) => {
      watching.current = id;
      setAudit(null);
      setActivity(null);
      setReply('');
      setError('');
      if (first) setRun(first);
      for (;;) {
        if (watching.current !== id) return;
        try {
          const res = await apiFetch(`/v1/cowork/${id}`);
          if (res.ok) {
            const fresh = (await res.json()) as CoworkRun;
            if (watching.current !== id) return;
            setRun(fresh);
            if (isFinished(fresh)) {
              void refreshList();
              return;
            }
          }
        } catch {
          /* try again on the next beat */
        }
        await new Promise((r) => setTimeout(r, 1200));
      }
    },
    [refreshList],
  );

  const back = () => {
    watching.current = null;
    setRun(null);
    void refreshList();
  };

  const start = async (goal: string, follows?: string) => {
    if (!goal.trim() || busy) return;
    setBusy(true);
    setError('');
    const full = goal.trim() + attachments.map((a) => `${ATTACH}${a.name}] ${a.text}`).join('');
    try {
      const res = await apiFetch('/v1/cowork', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: full,
          autonomy: options.autonomy,
          max_actions: options.maxActions,
          plan_first: options.planFirst,
          follows,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(String(data.detail ?? `Error ${res.status}`));
        return;
      }
      setText('');
      setReply('');
      setAttachments([]);
      void refreshList();
      void open(data.id, data as CoworkRun);
    } catch {
      setError('No pude conectar con Sergio.');
    } finally {
      setBusy(false);
    }
  };

  const post = async (path: string, body?: unknown, failure = 'No se pudo. Vuelva a intentarlo.') => {
    try {
      const res = await apiFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!res.ok) throw new Error();
      return true;
    } catch {
      setError(failure);
      return false;
    }
  };

  const decide = (step: number, approve: boolean) =>
    run && post(`/v1/cowork/${run.id}/decision`, { step, approve }, 'No se guardó su decisión. Vuelva a intentarlo.');
  const stop = () => run && post(`/v1/cowork/${run.id}/cancel`, undefined, 'No pude detener la tarea.');

  const sendReply = async () => {
    if (!run || !reply.trim()) return;
    if (isFinished(run)) {
      await start(reply, run.id);
      return;
    }
    const words = reply.trim();
    setReply('');
    if (await post(`/v1/cowork/${run.id}/note`, { text: words }, 'No llegó su indicación.')) {
      setRun({ ...run, notes: [...(run.notes ?? []), { text: words, at: Date.now() / 1000 }] });
    }
  };

  const loadAudit = useCallback(async () => {
    if (!run) return;
    try {
      const res = await apiFetch(`/v1/cowork/${run.id}/audit`);
      if (!res.ok) throw new Error();
      setAudit(await res.json());
    } catch {
      setError('No pude cargar el registro.');
    }
  }, [run]);

  useEffect(() => {
    if (tab === 'registro' && panel && run && !audit) void loadAudit();
  }, [tab, panel, run, audit, loadAudit]);

  useEffect(() => {
    const el = thread.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
  }, [run]);

  const files = useMemo(
    () => (run ? filesIn([...run.steps.map((s) => s.result), run.summary]) : []),
    [run],
  );

  // ── home ──────────────────────────────────────────────────────────────────
  if (!run) {
    return (
      <div className="cw cw-home">
        <div className="cw-home-inner">
          <h1 className="cw-hero">¿En qué trabajamos?</h1>
          <Composer
            big
            value={text}
            onChange={setText}
            onSubmit={() => void start(text)}
            placeholder="Describa el resultado que quiere"
            options={options}
            setOptions={setOptions}
            withOptions
            attachments={attachments}
            setAttachments={setAttachments}
            busy={busy}
          />
          {error && <p className="cw-error">{error}</p>}
          {!text && (
            <ul className="cw-suggest">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button type="button" onClick={() => setText(s)}>
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {runs.length > 0 && (
            <section className="cw-tasks" aria-label="Tareas">
              <h2>Tareas</h2>
              <ul>
                {runs.map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => void open(r.id, r)}>
                      <span className="cw-task-icon">
                        {isFinished(r) ? <StepIcon status={r.status === 'done' ? 'done' : r.status === 'cancelled' ? 'skipped' : 'failed'} /> : <Loader2 size={16} className="animate-spin" />}
                      </span>
                      <span className="cw-task-title">{r.title || splitGoal(r.goal).text}</span>
                      <span className="cw-task-meta">
                        {STATUS_ES[r.status] ?? r.status}
                        {r.created ? ` · ${timeAgo(r.created)}` : ''}
                      </span>
                      <ChevronRight size={16} className="cw-dim" />
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

  // ── a task ────────────────────────────────────────────────────────────────
  const finished = isFinished(run);
  const goal = splitGoal(run.goal);
  const current = run.steps.find((s) => s.status === 'running');
  const done = run.steps.filter((s) => s.status === 'done').length;
  const showActivity = activity ?? !finished;
  const parent = run.follows ? runs.find((r) => r.id === run.follows) : undefined;
  const headline = finished
    ? `${run.created && run.updated ? workedFor(run.created, run.updated) : 'Trabajó'} · ${run.steps.length} ${run.steps.length === 1 ? 'paso' : 'pasos'}`
    : run.status === 'planning'
      ? 'Preparando el plan'
      : run.status === 'waiting_plan'
        ? 'El plan espera su visto bueno'
        : run.status === 'waiting_approval'
          ? 'Espera su visto bueno'
          : current
            ? current.text
            : 'Trabajando';

  return (
    <div className="cw cw-task" data-panel={panel ? 'open' : 'closed'}>
      <div className="cw-main">
        <header className="cw-top">
          <button type="button" className="cw-ghost" onClick={back}>
            <ChevronLeft size={18} /> Tareas
          </button>
          <div className="cw-top-title">
            <span>{run.title || goal.text}</span>
            <small>{STATUS_ES[run.status] ?? run.status}</small>
          </div>
          <button type="button" className="cw-icon" aria-label="Panel lateral" aria-pressed={panel} onClick={() => setPanel(!panel)}>
            <PanelRight size={18} />
          </button>
        </header>

        <div className="cw-thread" ref={thread}>
          <div className="cw-col">
            {run.follows && (
              <button type="button" className="cw-follows" onClick={() => parent && void open(parent.id, parent)}>
                Sigue a «{parent?.title || 'la tarea anterior'}»
              </button>
            )}
            <div className="cw-user">
              <p>{goal.text}</p>
              {goal.files.length > 0 && (
                <div className="cw-attachments">
                  {goal.files.map((f) => (
                    <span key={f} className="cw-file-chip">
                      <FileText size={14} /> {f}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="cw-sergio">
              <button
                type="button"
                className={`cw-activity${finished ? '' : ' cw-working'}`}
                aria-expanded={showActivity}
                onClick={() => setActivity(!showActivity)}
              >
                {!finished && <Loader2 size={15} className="animate-spin" />}
                <span>{headline}</span>
                {run.steps.length > 0 && (showActivity ? <ChevronDown size={15} /> : <ChevronRight size={15} />)}
              </button>

              {showActivity && run.steps.length > 0 && run.status !== 'waiting_plan' && (
                <ol className="cw-steps">
                  {run.steps.map((step) => (
                    <li key={step.index} data-status={step.status}>
                      <span className="cw-step-icon">
                        <StepIcon status={step.status} />
                      </span>
                      <div>
                        <p>{step.text}</p>
                        {step.result && step.status !== 'pending' && <small>{step.result}</small>}
                      </div>
                    </li>
                  ))}
                </ol>
              )}

              {run.status === 'waiting_plan' && (
                <div className="cw-card">
                  <h3>Este es el plan</h3>
                  <ol className="cw-plan">
                    {run.steps.map((s) => (
                      <li key={s.index}>{s.text}</li>
                    ))}
                  </ol>
                  <div className="cw-card-actions">
                    <button type="button" className="cw-primary" onClick={() => void decide(0, true)}>
                      Empezar
                    </button>
                    <button type="button" className="cw-secondary" onClick={() => void decide(0, false)}>
                      Cancelar
                    </button>
                  </div>
                </div>
              )}

              {run.steps
                .filter((s) => s.status === 'waiting_approval')
                .map((step) => (
                  <div key={step.index} className="cw-card">
                    <h3>
                      <ShieldAlert size={16} /> ¿Hago esto?
                    </h3>
                    <p>{step.text}</p>
                    {(step.verdict?.reasons ?? []).length > 0 && <small>{(step.verdict.reasons ?? []).join(' ')}</small>}
                    {riskChips(step).length > 0 && (
                      <div className="cw-risks">
                        {riskChips(step).map((c) => (
                          <span key={c.axis} data-high={c.score >= 2}>
                            {c.label}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="cw-card-actions">
                      <button type="button" className="cw-primary" onClick={() => void decide(step.index + 1, true)}>
                        Sí, hazlo
                      </button>
                      <button type="button" className="cw-secondary" onClick={() => void decide(step.index + 1, false)}>
                        No
                      </button>
                    </div>
                  </div>
                ))}

              {(run.notes ?? []).map((n) => (
                <div key={n.at} className="cw-user cw-note">
                  <p>{n.text}</p>
                </div>
              ))}
              {!finished && (run.notes ?? []).length > 0 && <p className="cw-ack">Lo tengo en cuenta en los siguientes pasos.</p>}

              {finished && run.summary && <div className="cw-answer">{run.summary}</div>}

              {finished && files.length > 0 && (
                <div className="cw-files">
                  {files.map((f) => (
                    <button
                      key={f.path}
                      type="button"
                      className="cw-file"
                      title={f.path}
                      onClick={() => void navigator.clipboard?.writeText(f.path)}
                    >
                      <FileText size={18} />
                      <span>
                        <b>{f.name}</b>
                        <small>{f.path === f.name ? 'Copiar nombre' : f.path}</small>
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {finished && run.summary && (
                <div className="cw-tools">
                  <button type="button" className="cw-icon" aria-label="Copiar" onClick={() => void navigator.clipboard?.writeText(run.summary)}>
                    <Copy size={15} />
                  </button>
                </div>
              )}
            </div>

            {error && <p className="cw-error">{error}</p>}
          </div>
        </div>

        <div className="cw-bottom">
          <Composer
            value={reply}
            onChange={setReply}
            onSubmit={() => void sendReply()}
            placeholder={finished ? 'Pida un cambio o el siguiente paso' : 'Añada una indicación'}
            busy={busy}
            onStop={finished ? undefined : () => void stop()}
          />
        </div>
      </div>

      {panel && (
        <aside className="cw-panel" aria-label="Panel de la tarea">
          <header>
            <div className="cw-tabs" role="tablist">
              {(
                [
                  ['plan', 'Plan'],
                  ['archivos', 'Archivos'],
                  ['registro', 'Registro'],
                ] as const
              ).map(([key, label]) => (
                <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
                  {label}
                </button>
              ))}
            </div>
            <button type="button" className="cw-icon" aria-label="Cerrar panel" onClick={() => setPanel(false)}>
              <X size={16} />
            </button>
          </header>
          <div className="cw-panel-body">
            {tab === 'plan' && (
              <>
                <div className="cw-meter">
                  <div>
                    <span>
                      {done} de {run.steps.length} pasos
                    </span>
                    <span>
                      {run.actions_used} / {run.max_actions} acciones
                    </span>
                  </div>
                  <i>
                    <b style={{ width: `${run.steps.length ? Math.round((done / run.steps.length) * 100) : 0}%` }} />
                  </i>
                </div>
                {run.steps.length === 0 ? (
                  <p className="cw-dim">Preparando el plan…</p>
                ) : (
                  <ol className="cw-checklist">
                    {run.steps.map((s) => (
                      <li key={s.index} data-status={s.status}>
                        <StepIcon status={s.status} />
                        <span>{s.text}</span>
                      </li>
                    ))}
                  </ol>
                )}
                <dl className="cw-facts">
                  <div>
                    <dt>Autonomía</dt>
                    <dd>{AUTONOMY_ES[(run.autonomy as Autonomy) ?? 'normal'] ?? run.autonomy}</dd>
                  </div>
                  {run.plan_first && (
                    <div>
                      <dt>Modo plan</dt>
                      <dd>Sí</dd>
                    </div>
                  )}
                  {run.created && (
                    <div>
                      <dt>Empezó</dt>
                      <dd>{timeAgo(run.created)}</dd>
                    </div>
                  )}
                </dl>
              </>
            )}
            {tab === 'archivos' &&
              (files.length === 0 ? (
                <p className="cw-dim">Aún no hay archivos.</p>
              ) : (
                <div className="cw-files cw-files-col">
                  {files.map((f) => (
                    <button key={f.path} type="button" className="cw-file" title="Copiar la ruta" onClick={() => void navigator.clipboard?.writeText(f.path)}>
                      <FileText size={18} />
                      <span>
                        <b>{f.name}</b>
                        <small>{f.path}</small>
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            {tab === 'registro' && (
              <>
                {!audit ? (
                  <p className="cw-dim">Cargando…</p>
                ) : (
                  <>
                    <p className="cw-integrity">
                      {audit.intact ? <ShieldCheck size={15} /> : <ShieldAlert size={15} />}
                      {audit.intact ? 'Registro íntegro: nadie lo modificó.' : 'El registro fue alterado.'}
                    </p>
                    <ol className="cw-log">
                      {audit.entries.map((e) => (
                        <li key={e.seq}>
                          <b>{e.event}</b>
                          <span>{String(e.data?.text ?? e.data?.result ?? e.data?.decision ?? e.data?.summary ?? '').slice(0, 140)}</span>
                        </li>
                      ))}
                    </ol>
                    <button type="button" className="cw-secondary" onClick={() => void loadAudit()}>
                      Actualizar
                    </button>
                  </>
                )}
              </>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
