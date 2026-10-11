import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ArrowLeft, ArrowUp, Copy, Paperclip, Square, X } from 'lucide-react';
import { toast } from 'sonner';
import {
  AGENT_ES,
  elapsed,
  FINAL,
  host,
  progress,
  STATUS_ES,
  swarmApi,
  type SwarmAgent,
  type SwarmRun,
} from '../lib/swarm';

const EXAMPLES = [
  'Analiza estos contratos: partes, plazos, penalizaciones y riesgos, en una tabla',
  'Compara precio, garantía y opiniones de los 20 portátiles más vendidos para Blender',
  'Investiga a 15 competidores de mi negocio: precios, puntos fuertes y débiles',
  'Audita este código: errores, seguridad y rendimiento, archivo por archivo',
];
const PARALLEL = [4, 8, 16, 32];

function Stage({ label, state }: { label: string; state: 'wait' | 'now' | 'done' }) {
  return (
    <div className="swarm-stage" data-state={state}>
      <i />
      <span>{label}</span>
    </div>
  );
}

function AgentCard({ agent, open, onToggle }: { agent: SwarmAgent; open: boolean; onToggle: () => void }) {
  return (
    <button type="button" className="swarm-agent" data-status={agent.status} aria-expanded={open} onClick={onToggle}>
      <span className="swarm-agent-top">
        <span className="swarm-agent-n">{String(agent.id).padStart(2, '0')}</span>
        <span className="swarm-agent-role">{agent.role}</span>
        <span className="swarm-agent-dot" aria-label={AGENT_ES[agent.status]} />
      </span>
      <span className="swarm-agent-title">{agent.title}</span>
      <span className="swarm-agent-meta">
        {AGENT_ES[agent.status]}
        {agent.tool_calls > 0 && ` · ${agent.tool_calls} herramientas`}
        {agent.sources.length > 0 && ` · ${agent.sources.length} fuentes`}
      </span>
      {open && agent.result && (
        <span className="swarm-agent-result">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{agent.result}</ReactMarkdown>
        </span>
      )}
    </button>
  );
}

function RunView({ id }: { id: string }) {
  const navigate = useNavigate();
  const [run, setRun] = useState<SwarmRun | null>(null);
  const [openAgent, setOpenAgent] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    let timer = 0;
    const load = async () => {
      try {
        const r = await swarmApi.get(id);
        if (!alive) return;
        setRun(r);
        if (!FINAL.includes(r.status)) timer = window.setTimeout(load, 1000);
      } catch {
        if (alive) timer = window.setTimeout(load, 3000);
      }
    };
    void load();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [id]);

  if (!run) return <div className="paper-page" aria-busy="true" />;
  const p = progress(run);
  const stage = (s: 'plan' | 'agents' | 'sup') => {
    const order = { planning: 0, running: 1, synthesizing: 2, done: 3, failed: 3, cancelled: 3 }[run.status];
    const mine = { plan: 0, agents: 1, sup: 2 }[s];
    return order > mine ? 'done' : order === mine ? 'now' : 'wait';
  };
  const final = FINAL.includes(run.status);

  return (
    <div className="swarm-run">
      <header className="swarm-run-head">
        <button type="button" className="mac-icon-btn" aria-label="Volver" onClick={() => navigate('/swarm')}>
          <ArrowLeft size={18} strokeWidth={1.5} />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="swarm-title">{run.title || run.task}</h1>
          <p className="swarm-status" data-status={run.status}>
            {STATUS_ES[run.status]}
            {final && run.status === 'done' && ' · el enjambre se disolvió'}
          </p>
        </div>
        {!final && (
          <button type="button" className="paper-button" data-variant="quiet" onClick={() => swarmApi.cancel(run.id)}>
            <Square size={12} fill="currentColor" strokeWidth={0} /> Cancelar
          </button>
        )}
      </header>

      <div className="swarm-progress" role="progressbar" aria-valuenow={Math.round(p * 100)} aria-valuemin={0} aria-valuemax={100}>
        <i style={{ width: `${p * 100}%` }} />
      </div>

      <div className="swarm-stages">
        <Stage label="Orquestador" state={stage('plan')} />
        <Stage label={`${run.subtasks.length || '…'} subagentes en paralelo`} state={stage('agents')} />
        <Stage label="Supervisor" state={stage('sup')} />
      </div>

      <dl className="swarm-stats">
        <div>
          <dt>Listos</dt>
          <dd>
            {run.counts.done}/{run.subtasks.length}
          </dd>
        </div>
        <div>
          <dt>Trabajando</dt>
          <dd>{run.counts.running}</dd>
        </div>
        <div>
          <dt>En cola</dt>
          <dd>{run.counts.queued}</dd>
        </div>
        <div>
          <dt>Herramientas</dt>
          <dd>{run.tool_calls}</dd>
        </div>
        <div>
          <dt>Fuentes</dt>
          <dd>{run.sources.length}</dd>
        </div>
        <div>
          <dt>Tiempo</dt>
          <dd>{elapsed(run.elapsed)}</dd>
        </div>
      </dl>

      {run.roles.length > 0 && (
        <div className="swarm-roles" aria-label="Especialistas">
          {run.roles.map((r) => (
            <span key={r.nombre} className="swarm-role" title={r.especialidad}>
              {r.nombre}
            </span>
          ))}
        </div>
      )}

      {run.report && (
        <article className="swarm-report">
          <div className="swarm-report-head">
            <span className="paper-label">Informe del supervisor</span>
            <button
              type="button"
              className="mac-icon-btn"
              aria-label="Copiar el informe"
              onClick={() => navigator.clipboard.writeText(run.report).then(() => toast.success('Copiado.'))}
            >
              <Copy size={15} />
            </button>
          </div>
          <div className="prose max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{run.report}</ReactMarkdown>
          </div>
          {run.contradictions.length > 0 && (
            <div className="swarm-notes">
              <span className="paper-label">Contradicciones entre agentes</span>
              <ul>{run.contradictions.map((c) => <li key={c}>{c}</li>)}</ul>
            </div>
          )}
          {run.gaps.length > 0 && (
            <div className="swarm-notes">
              <span className="paper-label">Lo que faltó</span>
              <ul>{run.gaps.map((c) => <li key={c}>{c}</li>)}</ul>
            </div>
          )}
        </article>
      )}
      {run.error && <p className="swarm-error">{run.error}</p>}

      <section aria-label="Subagentes">
        <h2 className="paper-label swarm-section">Subagentes</h2>
        <div className="swarm-grid">
          {run.subtasks.map((a) => (
            <AgentCard key={a.id} agent={a} open={openAgent === a.id} onToggle={() => setOpenAgent(openAgent === a.id ? null : a.id)} />
          ))}
          {run.status === 'planning' &&
            Array.from({ length: 8 }, (_, i) => <span key={i} className="swarm-agent swarm-ghost" aria-hidden="true" />)}
        </div>
      </section>

      {run.sources.length > 0 && (
        <section aria-label="Fuentes">
          <h2 className="paper-label swarm-section">Fuentes visitadas</h2>
          <div className="swarm-sources">
            {run.sources.slice(0, 60).map((u) => (
              <a key={u} href={u} target="_blank" rel="noreferrer">
                {host(u)}
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Launcher() {
  const navigate = useNavigate();
  const [task, setTask] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [parallel, setParallel] = useState(8);
  const [busy, setBusy] = useState(false);
  const [runs, setRuns] = useState<SwarmRun[]>([]);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    swarmApi
      .list()
      .then(setRuns)
      .catch(() => setRuns([]));
  }, []);

  const launch = async () => {
    if (!task.trim()) return;
    setBusy(true);
    try {
      const run = await swarmApi.start(task.trim(), parallel, files);
      navigate(`/swarm/${run.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude lanzarlo.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="swarm-home">
      <p className="wordmark wordmark-lg">Agent Swarm</p>
      <h1 className="chat-hello">Una tarea enorme, resuelta a la vez.</h1>
      <p className="swarm-sub">
        Un orquestador reparte el trabajo entre muchos agentes especialistas que trabajan en paralelo; un supervisor une y
        verifica todo y le entrega un informe. Después, el enjambre se disuelve.
      </p>

      <div className="mac-composer swarm-composer">
        <textarea
          rows={3}
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Describa la tarea masiva…"
          aria-label="Tarea para el enjambre"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void launch();
          }}
        />
        {files.length > 0 && (
          <div className="swarm-files">
            {files.map((f, i) => (
              <span key={`${f.name}-${i}`} className="swarm-file">
                {f.name}
                <button type="button" aria-label={`Quitar ${f.name}`} onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="swarm-composer-foot">
          <input
            ref={input}
            type="file"
            multiple
            hidden
            accept=".pdf,.txt,.md,.csv,.json,.html,.xml,.docx,.log,.py,.js,.ts"
            onChange={(e) => {
              setFiles([...files, ...Array.from(e.target.files || [])].slice(0, 100));
              e.target.value = '';
            }}
          />
          <button type="button" className="mac-chip" onClick={() => input.current?.click()}>
            <Paperclip size={14} /> Documentos {files.length ? `(${files.length})` : ''}
          </button>
          <label className="swarm-parallel">
            <span>Agentes a la vez</span>
            <select value={parallel} onChange={(e) => setParallel(Number(e.target.value))} aria-label="Agentes a la vez">
              {PARALLEL.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <span className="flex-1" />
          <button type="button" className="mac-send" onClick={launch} disabled={busy || !task.trim()} aria-label="Lanzar el enjambre">
            <ArrowUp size={17} strokeWidth={2.25} />
          </button>
        </div>
      </div>
      <p className="swarm-hint">Cada documento tiene su propio agente lector. Nunca envía mensajes, compra ni borra nada.</p>

      <div className="swarm-examples">
        {EXAMPLES.map((e) => (
          <button key={e} type="button" className="mac-chip" onClick={() => setTask(e)}>
            {e}
          </button>
        ))}
      </div>

      {runs.length > 0 && (
        <section className="swarm-history" aria-label="Enjambres anteriores">
          <h2 className="paper-label">Anteriores</h2>
          <ul>
            {runs.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => navigate(`/swarm/${r.id}`)}>
                  <span className="truncate">{r.title || r.task}</span>
                  <span className="swarm-status" data-status={r.status}>
                    {r.subtasks.length} agentes · {STATUS_ES[r.status]} · {elapsed(r.elapsed)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function SwarmPage() {
  const { id } = useParams();
  return <div className="paper-page">{id ? <RunView id={id} /> : <Launcher />}</div>;
}

export default SwarmPage;
