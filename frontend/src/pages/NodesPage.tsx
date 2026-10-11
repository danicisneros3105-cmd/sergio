import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowUp,
  Check,
  Download,
  ExternalLink,
  HardDrive,
  Hand,
  Octagon,
  Play,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { NodeDot } from '../components/Nodes/NodeDot';
import { apiFetch } from '../lib/api';
import { listConnectors } from '../lib/connectors-api';
import type { ConnectorInfo } from '../types/connectors';
import {
  describeRoutine,
  groupByDay,
  nodesApi,
  relative,
  RULE_ES,
  STATUS_ES,
  statusLine,
  type ActivityItem,
  type NodeMessage,
  type RuleChoice,
  type RuleSpec,
  type SergioNode,
} from '../lib/nodes';

type Tab = 'chat' | 'activity' | 'computer' | 'memory' | 'routines' | 'rules' | 'apps' | 'settings';
const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'chat', label: 'Chat' },
  { key: 'activity', label: 'Actividad' },
  { key: 'computer', label: 'Computadora' },
  { key: 'memory', label: 'Memoria' },
  { key: 'routines', label: 'Rutinas' },
  { key: 'rules', label: 'Reglas' },
  { key: 'apps', label: 'Apps' },
  { key: 'settings', label: 'Ajustes' },
];
const DAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const ACTIVITY_ICON: Record<string, string> = {
  started: '▸',
  tool: '·',
  done: '✓',
  approval: '?',
  approved: '✓',
  denied: '×',
  needs_you: '!',
  memory: '◦',
  failed: '×',
  stopped: '■',
  resumed: '▸',
  routine: '↻',
  created: '●',
  handed_back: '▸',
  blocked: '×',
  discarded: '×',
};

function useConnectors() {
  const [apps, setApps] = useState<ConnectorInfo[]>([]);
  useEffect(() => {
    listConnectors()
      .then(setApps)
      .catch(() => setApps([]));
  }, []);
  return apps;
}

// -- creating a Node ------------------------------------------------------------

function CreateNode({ first, onCreated, onCancel }: { first: boolean; onCreated: (n: SergioNode) => void; onCancel?: () => void }) {
  const apps = useConnectors();
  const [name, setName] = useState('');
  const [what, setWhat] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const connected = apps.filter((a) => a.connected);

  const create = async () => {
    if (!name.trim()) {
      toast.error('Póngale un nombre.');
      return;
    }
    setBusy(true);
    try {
      onCreated(await nodesApi.create({ name: name.trim(), instructions: what.trim(), apps: picked }));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude crearlo.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="node-create">
      <NodeDot color="#9fd3ff" size={88} status={busy ? 'working' : 'idle'} />
      <h1 className="node-create-title">{first ? 'Su primer Node' : 'Un Node nuevo'}</h1>
      <p className="node-create-sub">
        Un empleado digital que trabaja 24/7: tiene su propia computadora, un navegador y memoria a largo plazo. Sigue
        trabajando aunque usted cierre esto, y le pide permiso antes de lo delicado.
      </p>
      <label className="node-field">
        <span className="paper-label">Nombre</span>
        <input className="paper-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ej. Ana" maxLength={40} autoFocus />
      </label>
      <label className="node-field">
        <span className="paper-label">¿De qué se encarga?</span>
        <textarea
          className="paper-input"
          rows={3}
          value={what}
          onChange={(e) => setWhat(e.target.value)}
          placeholder="Ej. Vigila mi correo y mi calendario, prepara un resumen cada mañana y avísame si algo es urgente."
        />
      </label>
      <div className="node-field">
        <span className="paper-label">Conectar apps</span>
        {connected.length ? (
          <div className="node-chips">
            {connected.map((a) => (
              <button
                key={a.connector_id}
                type="button"
                className="mac-chip"
                aria-pressed={picked.includes(a.connector_id)}
                onClick={() =>
                  setPicked(picked.includes(a.connector_id) ? picked.filter((x) => x !== a.connector_id) : [...picked, a.connector_id])
                }
              >
                {a.display_name}
              </button>
            ))}
          </div>
        ) : (
          <p className="node-hint">Aún no hay apps conectadas. Puede conectarlas luego en «Apps».</p>
        )}
      </div>
      <div className="node-create-actions">
        {onCancel && (
          <button type="button" className="paper-button" data-variant="quiet" onClick={onCancel}>
            Cancelar
          </button>
        )}
        <button type="button" className="paper-button" onClick={create} disabled={busy}>
          {busy ? 'Preparando su computadora…' : 'Crear y que se presente'}
        </button>
      </div>
    </div>
  );
}

// -- the tabs -------------------------------------------------------------------

function ChatTab({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const [messages, setMessages] = useState<NodeMessage[]>([]);
  const [text, setText] = useState('');
  const end = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    nodesApi
      .messages(node.id)
      .then(setMessages)
      .catch(() => {});
  }, [node.id]);

  useEffect(() => {
    load();
    const t = window.setInterval(load, 2000);
    return () => window.clearInterval(t);
  }, [load]);
  // Scroll only the Node's own pane (scrollIntoView would also move the shell).
  useEffect(() => {
    const pane = end.current?.closest('.node-body');
    if (pane) pane.scrollTop = pane.scrollHeight;
  }, [messages.length, node.status]);

  const send = async () => {
    const t = text.trim();
    if (!t) return;
    setText('');
    try {
      await nodesApi.say(node.id, t);
      load();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No se envió.');
    }
  };

  const decide = async (aid: string, approve: boolean) => {
    try {
      await nodesApi.decide(node.id, aid, approve);
      onChanged();
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude.');
    }
  };

  return (
    <div className="node-chat">
      <div className="node-thread">
        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'node-msg mine' : 'node-msg'}>
            {m.role === 'node' && <NodeDot color={node.color} size={24} />}
            <div className="node-msg-body">
              {m.source && m.source !== 'Encargo del usuario' && <span className="node-msg-source">{m.source}</span>}
              <div className="prose prose-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
              </div>
            </div>
          </div>
        ))}
        {node.approvals.map((a) => (
          <div key={a.id} className="node-approval" role="group" aria-label="Aprobación pendiente">
            <span className="paper-label">Necesita su aprobación</span>
            <p>{a.what}</p>
            <div className="node-approval-actions">
              <button type="button" className="paper-button" data-variant="quiet" onClick={() => decide(a.id, false)}>
                <X size={14} /> No
              </button>
              <button type="button" className="paper-button" onClick={() => decide(a.id, true)}>
                <Check size={14} /> Aprobar
              </button>
            </div>
          </div>
        ))}
        {node.status === 'needs_you' && (
          <TakeOver node={node} onChanged={onChanged} />
        )}
        {(node.status === 'working' || node.busy) && (
          <div className="node-msg">
            <NodeDot color={node.color} size={24} status="working" />
            <div className="node-working">{node.doing || 'Trabajando…'}</div>
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="node-composer">
        <textarea
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={`Encárguele algo a ${node.name}…`}
          aria-label={`Mensaje para ${node.name}`}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button type="button" className="mac-send" onClick={send} disabled={!text.trim()} aria-label="Enviar">
          <ArrowUp size={17} strokeWidth={2.25} />
        </button>
      </div>
    </div>
  );
}

function TakeOver({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const url = node.waiting.match(/https?:\/\/\S+/)?.[0];
  return (
    <div className="node-approval node-takeover" role="group" aria-label="Tomar el control">
      <span className="paper-label">Le necesita a usted</span>
      <p>{node.waiting}</p>
      <div className="node-approval-actions">
        {url && (
          <a className="paper-button" data-variant="quiet" href={url} target="_blank" rel="noreferrer">
            <ExternalLink size={14} /> Tomar el control
          </a>
        )}
        <button
          type="button"
          className="paper-button"
          onClick={async () => {
            await nodesApi.handBack(node.id).catch(() => toast.error('No pude devolverle el control.'));
            onChanged();
          }}
        >
          <Play size={14} /> Listo, continúe
        </button>
      </div>
    </div>
  );
}

function ActivityTab({ node }: { node: SergioNode }) {
  const [items, setItems] = useState<ActivityItem[]>([]);
  useEffect(() => {
    let alive = true;
    const load = () =>
      nodesApi
        .activity(node.id)
        .then((r) => alive && setItems(r.activity))
        .catch(() => {});
    load();
    const t = window.setInterval(load, 2000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [node.id]);
  const days = useMemo(() => groupByDay(items), [items]);
  if (!items.length) return <p className="node-empty">Aquí verá todo lo que hace, en vivo.</p>;
  return (
    <div className="node-activity">
      {days.map((d) => (
        <section key={d.day}>
          <h3 className="paper-label">{d.day}</h3>
          <ol>
            {d.items.map((a) => (
              <li key={a.id} data-kind={a.kind}>
                <span className="node-act-icon" aria-hidden="true">
                  {ACTIVITY_ICON[a.kind] || '·'}
                </span>
                <span className="node-act-text">{a.text}</span>
                <time>{new Date(a.at * 1000).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })}</time>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

async function download(nodeId: string, path: string) {
  const res = await apiFetch(nodesApi.fileUrl(nodeId, path));
  if (!res.ok) {
    toast.error('No pude bajar ese archivo.');
    return;
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = path.split('/').pop() || 'archivo';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function ComputerTab({ node }: { node: SergioNode }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof nodesApi.computer>> | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      nodesApi
        .computer(node.id)
        .then((d) => alive && setData(d))
        .catch(() => {});
    load();
    const t = window.setInterval(load, 3000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [node.id]);
  return (
    <div className="node-computer">
      <div className="node-screen" aria-label="Su computadora ahora">
        <div className="node-screen-bar">
          <span />
          <span />
          <span />
          <em>{node.name} · computadora</em>
        </div>
        <div className="node-screen-body">
          {(data?.recent || []).slice(-12).map((r) => (
            <p key={r.id}>
              <span>{new Date(r.at * 1000).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span> {r.text}
            </p>
          ))}
          <p className="node-screen-now">
            {node.status === 'working' ? `▸ ${node.doing || 'trabajando…'}` : `${STATUS_ES[node.status]}.`}
            <i className="node-caret" />
          </p>
        </div>
      </div>
      <div className="node-files">
        <h3 className="paper-label">
          <HardDrive size={13} /> Archivos
        </h3>
        {data?.files.length ? (
          <ul>
            {data.files.map((f) => (
              <li key={f.path}>
                <span className="truncate">{f.path}</span>
                <span className="node-hint">{(f.size / 1024).toFixed(f.size < 10240 ? 1 : 0)} KB</span>
                <button type="button" className="mac-icon-btn" aria-label={`Bajar ${f.path}`} onClick={() => download(node.id, f.path)}>
                  <Download size={14} />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="node-hint">Lo que produzca (informes, tablas, notas) aparecerá aquí.</p>
        )}
        <p className="node-hint node-path">{data?.path}</p>
      </div>
    </div>
  );
}

function MemoryTab({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const [text, setText] = useState(node.memory);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (!dirty) setText(node.memory);
  }, [node.memory, dirty]);
  return (
    <div className="node-memory">
      <p className="node-hint">Lo que {node.name} recuerda de usted y de su trabajo. Lo escribe solo; usted puede corregirlo o borrarlo.</p>
      <textarea
        className="paper-input"
        rows={14}
        value={text}
        onChange={(e) => (setText(e.target.value), setDirty(true))}
        placeholder="Todavía no recuerda nada."
      />
      <div className="node-row-end">
        <button
          type="button"
          className="paper-button"
          disabled={!dirty}
          onClick={async () => {
            await nodesApi.setMemory(node.id, text);
            setDirty(false);
            toast.success('Memoria guardada.');
            onChanged();
          }}
        >
          Guardar
        </button>
      </div>
    </div>
  );
}

function RoutinesTab({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const [task, setTask] = useState('');
  const [mode, setMode] = useState<'every' | 'at'>('at');
  const [every, setEvery] = useState(60);
  const [at, setAt] = useState('08:00');
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const add = async () => {
    try {
      await nodesApi.addRoutine(node.id, mode === 'every' ? { task, every_minutes: every } : { task, at, days });
      setTask('');
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude.');
    }
  };
  return (
    <div className="node-routines">
      <p className="node-hint">Trabajo que {node.name} repite solo, aunque usted no esté. Como mucho, cada 15 minutos.</p>
      <ul>
        {node.routines.map((r) => (
          <li key={r.id}>
            <span className="node-routine-when">{describeRoutine(r)}</span>
            <span className="flex-1">{r.task}</span>
            {r.last_run > 0 && <span className="node-hint">{relative(r.last_run)}</span>}
            <button
              type="button"
              className="mac-icon-btn"
              aria-label="Quitar rutina"
              onClick={async () => (await nodesApi.removeRoutine(node.id, r.id), onChanged())}
            >
              <Trash2 size={14} />
            </button>
          </li>
        ))}
      </ul>
      <div className="node-routine-form">
        <input className="paper-input" value={task} onChange={(e) => setTask(e.target.value)} placeholder="Ej. Revisa pisos nuevos en Cuenca y avísame si hay alguno bueno" />
        <div className="node-routine-when-row">
          <div className="node-seg" role="radiogroup" aria-label="Cuándo">
            <button type="button" role="radio" aria-checked={mode === 'at'} onClick={() => setMode('at')}>
              A una hora
            </button>
            <button type="button" role="radio" aria-checked={mode === 'every'} onClick={() => setMode('every')}>
              Cada cierto tiempo
            </button>
          </div>
          {mode === 'at' ? (
            <>
              <input className="paper-input node-time" type="time" value={at} onChange={(e) => setAt(e.target.value)} aria-label="Hora" />
              <div className="node-days">
                {DAYS.map((d, i) => (
                  <button
                    key={i}
                    type="button"
                    aria-pressed={days.includes(i)}
                    aria-label={['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][i]}
                    onClick={() => setDays(days.includes(i) ? days.filter((x) => x !== i) : [...days, i].sort())}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <select className="paper-input node-time" value={every} onChange={(e) => setEvery(Number(e.target.value))} aria-label="Cada">
              {[15, 30, 60, 120, 240, 720, 1440].map((m) => (
                <option key={m} value={m}>
                  {describeRoutine({ every_minutes: m, at: '', days: [] })}
                </option>
              ))}
            </select>
          )}
          <button type="button" className="paper-button" onClick={add} disabled={!task.trim()}>
            <Plus size={14} /> Añadir
          </button>
        </div>
      </div>
    </div>
  );
}

function RulesTab({ node, specs, onChanged }: { node: SergioNode; specs: RuleSpec[]; onChanged: () => void }) {
  const set = async (key: string, choice: RuleChoice) => {
    await nodesApi.update(node.id, { rules: { ...node.rules, [key]: choice } });
    onChanged();
  };
  return (
    <div className="node-rules">
      <p className="node-hint">
        Qué hace {node.name} solo, qué le pregunta antes y qué no hará nunca. Enviar mensajes o correos, borrar y pagar
        nunca son automáticos: le deja el borrador y usted decide.
      </p>
      {specs.map((r) => (
        <div key={r.key} className="node-rule">
          <span>{r.label}</span>
          <div className="node-seg" role="radiogroup" aria-label={r.label}>
            {(['allow', 'ask', 'block'] as RuleChoice[]).map((c) => (
              <button
                key={c}
                type="button"
                role="radio"
                aria-checked={node.rules[r.key] === c}
                disabled={!r.choices.includes(c)}
                onClick={() => set(r.key, c)}
              >
                {RULE_ES[c]}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function AppsTab({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const apps = useConnectors();
  const navigate = useNavigate();
  const toggle = async (id: string) => {
    const next = node.apps.includes(id) ? node.apps.filter((a) => a !== id) : [...node.apps, id];
    await nodesApi.update(node.id, { apps: next });
    onChanged();
  };
  return (
    <div className="node-apps">
      <p className="node-hint">Las apps que {node.name} puede leer. Solo ve las que usted marque.</p>
      <div className="node-app-grid">
        {apps.map((a) => (
          <button
            key={a.connector_id}
            type="button"
            className="node-app"
            aria-pressed={node.apps.includes(a.connector_id)}
            disabled={!a.connected}
            onClick={() => toggle(a.connector_id)}
            title={a.connected ? undefined : 'Conéctela primero'}
          >
            <span>{a.display_name}</span>
            <span className="node-hint">{!a.connected ? 'Sin conectar' : node.apps.includes(a.connector_id) ? 'Con acceso' : 'Sin acceso'}</span>
          </button>
        ))}
      </div>
      <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/data-sources')}>
        Conectar más apps
      </button>
    </div>
  );
}

function SettingsTab({ node, colors, onChanged, onDeleted }: { node: SergioNode; colors: string[]; onChanged: () => void; onDeleted: () => void }) {
  const [name, setName] = useState(node.name);
  const [what, setWhat] = useState(node.instructions);
  return (
    <div className="node-settings">
      <label className="node-field">
        <span className="paper-label">Nombre</span>
        <input className="paper-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} />
      </label>
      <label className="node-field">
        <span className="paper-label">De qué se encarga</span>
        <textarea className="paper-input" rows={5} value={what} onChange={(e) => setWhat(e.target.value)} />
      </label>
      <div className="node-field">
        <span className="paper-label">Color</span>
        <div className="node-colors" role="radiogroup" aria-label="Color">
          {colors.map((c) => (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={node.color === c}
              aria-label={c}
              onClick={async () => (await nodesApi.update(node.id, { color: c }), onChanged())}
            >
              <NodeDot color={c} size={30} />
            </button>
          ))}
        </div>
      </div>
      <div className="node-row-end">
        <button
          type="button"
          className="paper-button"
          data-variant="quiet"
          onClick={async () => {
            if (!window.confirm(`¿Borrar a ${node.name}, su computadora y su memoria?`)) return;
            await nodesApi.remove(node.id);
            onDeleted();
          }}
        >
          <Trash2 size={14} /> Borrar
        </button>
        <button
          type="button"
          className="paper-button"
          onClick={async () => {
            try {
              await nodesApi.update(node.id, { name, instructions: what });
              toast.success('Guardado.');
              onChanged();
            } catch (e) {
              toast.error(e instanceof Error ? e.message : 'No pude guardar.');
            }
          }}
        >
          Guardar
        </button>
      </div>
    </div>
  );
}

// -- the page ---------------------------------------------------------------------

export function NodesPage() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [nodes, setNodes] = useState<SergioNode[] | null>(null);
  const [specs, setSpecs] = useState<RuleSpec[]>([]);
  const [colors, setColors] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>('chat');
  const creating = params.get('nuevo') === '1';

  const refresh = useCallback(() => {
    nodesApi
      .list()
      .then(setNodes)
      .catch(() => setNodes((n) => n ?? []));
  }, []);

  useEffect(() => {
    refresh();
    nodesApi
      .rules()
      .then((r) => (setSpecs(r.rules), setColors(r.colors)))
      .catch(() => {});
    const t = window.setInterval(refresh, 2500);
    return () => window.clearInterval(t);
  }, [refresh]);

  const node = nodes?.find((n) => n.id === id) || (!id && nodes?.[0]) || undefined;
  useEffect(() => {
    if (node && node.unread) nodesApi.seen(node.id).catch(() => {});
  }, [node?.id, node?.unread]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = (n: SergioNode) => {
    setTab('chat');
    navigate(`/nodes/${n.id}`);
  };

  if (nodes === null) return <div className="paper-page" aria-busy="true" />;

  if (!nodes.length || creating) {
    return (
      <div className="paper-page">
        <CreateNode
          first={!nodes.length}
          onCreated={(n) => {
            setParams({});
            refresh();
            open(n);
          }}
          onCancel={nodes.length ? () => setParams({}) : undefined}
        />
      </div>
    );
  }

  return (
    <div className="nodes">
      <aside className="nodes-list" aria-label="Sus Nodes">
        <div className="nodes-list-head">
          <span className="wordmark">Nodes</span>
          <button type="button" className="mac-icon-btn" aria-label="Nuevo Node" onClick={() => setParams({ nuevo: '1' })}>
            <Plus size={17} strokeWidth={1.5} />
          </button>
        </div>
        {nodes.map((n) => (
          <button key={n.id} type="button" className="nodes-item" aria-current={node?.id === n.id ? 'true' : undefined} onClick={() => open(n)}>
            <NodeDot color={n.color} status={n.status} size={34} />
            <span className="min-w-0 flex-1 text-left">
              <span className="nodes-item-name">{n.name}</span>
              <span className="nodes-item-status">{statusLine(n)}</span>
            </span>
            {n.approvals.length > 0 || n.status === 'needs_you' ? (
              <span className="nodes-badge" aria-label="Le necesita">
                !
              </span>
            ) : n.unread > 0 && node?.id !== n.id ? (
              <span className="nodes-badge nodes-badge-quiet">{n.unread}</span>
            ) : null}
          </button>
        ))}
      </aside>

      {node && (
        <section className="node-page" aria-label={node.name}>
          <header className="node-head">
            <NodeDot color={node.color} status={node.status} size={48} label={`${node.name}: ${STATUS_ES[node.status]}`} />
            <div className="min-w-0 flex-1">
              <h1 className="node-name">{node.name}</h1>
              <p className="node-status" data-status={node.status}>
                <i />
                {statusLine(node)}
              </p>
            </div>
            {node.status === 'paused' ? (
              <button type="button" className="paper-button" onClick={async () => (await nodesApi.resume(node.id), refresh())}>
                <Play size={14} /> Reanudar
              </button>
            ) : (
              <button
                type="button"
                className="paper-button node-stop"
                data-variant="danger"
                title="Parada de emergencia: deja todo y espera"
                onClick={async () => (await nodesApi.stop(node.id), refresh(), toast('Detenido.'))}
              >
                <Octagon size={14} /> Detener
              </button>
            )}
          </header>
          <nav className="node-tabs paper-tabs" role="tablist">
            {TABS.map((t) => (
              <button key={t.key} type="button" role="tab" className="paper-tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}>
                {t.label}
                {t.key === 'chat' && node.approvals.length > 0 && <span className="node-tab-dot" />}
              </button>
            ))}
          </nav>
          <div className="node-body">
            {tab === 'chat' && <ChatTab node={node} onChanged={refresh} />}
            {tab === 'activity' && <ActivityTab node={node} />}
            {tab === 'computer' && <ComputerTab node={node} />}
            {tab === 'memory' && <MemoryTab node={node} onChanged={refresh} />}
            {tab === 'routines' && <RoutinesTab node={node} onChanged={refresh} />}
            {tab === 'rules' && <RulesTab node={node} specs={specs} onChanged={refresh} />}
            {tab === 'apps' && <AppsTab node={node} onChanged={refresh} />}
            {tab === 'settings' && (
              <SettingsTab
                key={node.id}
                node={node}
                colors={colors}
                onChanged={refresh}
                onDeleted={() => {
                  refresh();
                  navigate('/nodes');
                }}
              />
            )}
          </div>
          {node.status === 'needs_you' && tab !== 'chat' && (
            <button type="button" className="node-floating" onClick={() => setTab('chat')}>
              <Hand size={14} /> {node.name} le necesita
            </button>
          )}
        </section>
      )}
    </div>
  );
}

export default NodesPage;
