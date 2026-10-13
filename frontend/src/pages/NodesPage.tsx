import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowUp,
  Check,
  Dices,
  Download,
  ExternalLink,
  HardDrive,
  Hand,
  Lock,
  Mic,
  Octagon,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { NodeCritter } from '../components/Nodes/NodeCritter';
import { NodeGoals, ReviewedIntegrations } from '../components/Nodes/NodeGoals';
import { apiFetch } from '../lib/api';
import { listConnectors } from '../lib/connectors-api';
import { useTtsStore } from '../lib/tts';
import type { ConnectorInfo } from '../types/connectors';
import {
  ACCESSORY_ES,
  describeRoutine,
  EYES_ES,
  groupByDay,
  nodesApi,
  relative,
  RULE_ES,
  SHAPE_ES,
  STATUS_ES,
  statusLine,
  type ActivityItem,
  type Avatar,
  type Catalog,
  type NodeMessage,
  type RuleChoice,
  type SergioNode,
} from '../lib/nodes';

type Tab = 'chat' | 'activity' | 'goals' | 'computer' | 'memory' | 'routines' | 'rules' | 'apps' | 'connections' | 'settings';
const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'chat', label: 'Chat' },
  { key: 'activity', label: 'Actividad' },
  { key: 'goals', label: 'Objetivos' },
  { key: 'computer', label: 'Computadora' },
  { key: 'memory', label: 'Memoria' },
  { key: 'routines', label: 'Rutinas' },
  { key: 'rules', label: 'Reglas' },
  { key: 'apps', label: 'Apps' },
  { key: 'connections', label: 'Conexiones' },
  { key: 'settings', label: 'Ajustes' },
];
const DAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const ACTIVITY_ICON: Record<string, string> = {
  started: '▸',
  tool: '·',
  result: '↳',
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
  watch: '◌',
  trigger: '⚡',
  verify: '⚠',
  swarm: '✳',
  connection: '⌁',
};
const FALLBACK_AVATAR: Avatar = { shape: 'bean', color: '#9fd3ff', accessory: 'none', eyes: 'dots' };

function look(node?: Pick<SergioNode, 'avatar'> | null): Avatar {
  return node?.avatar || FALLBACK_AVATAR;
}

function useConnectors() {
  const [apps, setApps] = useState<ConnectorInfo[]>([]);
  useEffect(() => {
    listConnectors()
      .then(setApps)
      .catch(() => setApps([]));
  }, []);
  return apps;
}

function randomAvatar(c: Catalog | null): Avatar {
  const pick = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)];
  return {
    shape: pick(c?.shapes || ['bean', 'blob', 'drop', 'heart', 'frog', 'bear', 'star', 'ghost']),
    color: pick(c?.felt?.slice(0, 8) || ['#9fd3ff']),
    accessory: pick(c?.accessories || ['none']),
    eyes: pick(c?.eyes?.slice(0, 4) || ['dots']),
  };
}

// -- the character designer (Muse: name, face, way of talking) ----------------------

function AvatarDesigner({ value, onChange, catalog }: { value: Avatar; onChange: (a: Avatar) => void; catalog: Catalog | null }) {
  const set = (patch: Partial<Avatar>) => onChange({ ...value, ...patch });
  return (
    <div className="critter-designer">
      <div className="critter-stage">
        <NodeCritter look={value} size={132} status="idle" />
        <button type="button" className="mac-icon-btn" aria-label="Al azar" title="Al azar" onClick={() => onChange(randomAvatar(catalog))}>
          <Dices size={16} strokeWidth={1.6} />
        </button>
      </div>
      <div className="critter-options">
        <div className="critter-row" role="radiogroup" aria-label="Forma">
          {(catalog?.shapes || []).map((shape) => (
            <button key={shape} type="button" role="radio" aria-checked={value.shape === shape} title={SHAPE_ES[shape]} onClick={() => set({ shape })}>
              <NodeCritter look={{ ...value, shape, accessory: 'none' }} size={40} />
            </button>
          ))}
        </div>
        <div className="critter-row critter-colors" role="radiogroup" aria-label="Color">
          {(catalog?.felt || []).map((color) => (
            <button key={color} type="button" role="radio" aria-checked={value.color === color} aria-label={color} onClick={() => set({ color })}>
              <i style={{ background: color }} />
            </button>
          ))}
        </div>
        <div className="critter-chips">
          {(catalog?.accessories || []).map((a) => (
            <button key={a} type="button" className="mac-chip" aria-pressed={value.accessory === a} onClick={() => set({ accessory: a })}>
              {ACCESSORY_ES[a]}
            </button>
          ))}
        </div>
        <div className="critter-chips">
          {(catalog?.eyes || []).map((e) => (
            <button key={e} type="button" className="mac-chip" aria-pressed={value.eyes === e} onClick={() => set({ eyes: e })}>
              {EYES_ES[e]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ToneSelect({ value, onChange, catalog }: { value: string; onChange: (t: string) => void; catalog: Catalog | null }) {
  return (
    <div className="critter-chips" role="radiogroup" aria-label="Forma de hablar">
      {(catalog?.tones || []).map((t) => (
        <button key={t.key} type="button" role="radio" className="mac-chip" aria-checked={value === t.key} aria-pressed={value === t.key} title={t.label} onClick={() => onChange(t.key)}>
          {t.key[0].toUpperCase() + t.key.slice(1)}
        </button>
      ))}
    </div>
  );
}

// -- creating a Node (templates gallery, then the face) -----------------------------

function CreateNode({
  first,
  catalog,
  onCreated,
  onCancel,
}: {
  first: boolean;
  catalog: Catalog | null;
  onCreated: (n: SergioNode) => void;
  onCancel?: () => void;
}) {
  const apps = useConnectors();
  const [template, setTemplate] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [what, setWhat] = useState('');
  const [avatar, setAvatar] = useState<Avatar>(() => randomAvatar(catalog));
  const [tone, setTone] = useState('cercano');
  const [picked, setPicked] = useState<Record<string, 'read' | 'write'>>({});
  const [busy, setBusy] = useState(false);
  const connected = apps.filter((a) => a.connected);

  const choose = (id: string) => {
    const t = catalog?.templates.find((x) => x.id === id);
    setTemplate(id);
    if (t) {
      setName(t.name);
      setAvatar(t.avatar);
    }
  };

  const create = async () => {
    if (!name.trim()) {
      toast.error('Póngale un nombre.');
      return;
    }
    setBusy(true);
    try {
      onCreated(
        await nodesApi.create({
          name: name.trim(),
          instructions: what.trim(),
          apps: Object.keys(picked).length ? picked : undefined,
          template: template && template !== 'blank' ? template : undefined,
          avatar,
          tone,
        }),
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude crearlo.');
    } finally {
      setBusy(false);
    }
  };

  if (template === null) {
    return (
      <div className="node-gallery">
        <div className="node-gallery-cast" aria-hidden="true">
          {(catalog?.templates || []).slice(0, 5).map((t, i) => (
            <NodeCritter key={t.id} look={t.avatar} size={i === 2 ? 108 : 84} />
          ))}
        </div>
        <h1 className="node-create-title">{first ? 'Su primer Node' : 'Un Node nuevo'}</h1>
        <p className="node-create-sub">
          Cada Node tiene su memoria, reglas y espacio de trabajo. Trabajan mientras Sergio está activo. Elija por dónde empezar.
        </p>
        <div className="node-templates">
          {(catalog?.templates || []).map((t) => (
            <button
              key={t.id}
              type="button"
              className="node-template"
              style={{ '--node': t.avatar.color } as React.CSSProperties}
              onClick={() => choose(t.id)}
            >
              <span className="node-template-stage">
                <NodeCritter look={t.avatar} size={72} />
              </span>
              <span>
                <b>{t.title}</b>
                <em>{t.description}</em>
              </span>
            </button>
          ))}
          <button type="button" className="node-template node-template-blank" onClick={() => (setTemplate('blank'), setName(''))}>
            <Plus size={22} strokeWidth={1.4} />
            <span>
              <b>En blanco</b>
              <em>Usted le dice de qué se encarga.</em>
            </span>
          </button>
        </div>
        {onCancel && (
          <button type="button" className="paper-button" data-variant="quiet" onClick={onCancel}>
            Cancelar
          </button>
        )}
      </div>
    );
  }

  const spec = catalog?.templates.find((t) => t.id === template);
  return (
    <div className="node-create">
      <AvatarDesigner value={avatar} onChange={setAvatar} catalog={catalog} />
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
          placeholder={spec ? spec.description : 'Ej. Vigila mi correo y mi calendario y avísame si algo es urgente.'}
        />
      </label>
      <div className="node-field">
        <span className="paper-label">Forma de hablar</span>
        <ToneSelect value={tone} onChange={setTone} catalog={catalog} />
      </div>
      <div className="node-field">
        <span className="paper-label">Apps que puede leer</span>
        {connected.length ? (
          <div className="node-chips">
            {connected.map((a) => (
              <button
                key={a.connector_id}
                type="button"
                className="mac-chip"
                aria-pressed={!!picked[a.connector_id]}
                onClick={() => {
                  const next = { ...picked };
                  if (next[a.connector_id]) delete next[a.connector_id];
                  else next[a.connector_id] = 'read';
                  setPicked(next);
                }}
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
        <button type="button" className="paper-button" data-variant="quiet" onClick={() => setTemplate(null)}>
          Atrás
        </button>
        <button type="button" className="paper-button" onClick={create} disabled={busy}>
          {busy ? 'Preparando su computadora…' : 'Crear y que se presente'}
        </button>
      </div>
    </div>
  );
}

// -- the tabs -------------------------------------------------------------------

type SpeechRec = { lang: string; interimResults: boolean; onresult: (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void; onend: () => void; start: () => void; stop: () => void };

function useDictation(onText: (t: string) => void) {
  const [listening, setListening] = useState(false);
  const rec = useRef<SpeechRec | null>(null);
  const W = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
  const Ctor = W.SpeechRecognition || W.webkitSpeechRecognition;
  const toggle = () => {
    if (!Ctor) {
      toast('Su navegador no dicta; use el micrófono del notch.');
      return;
    }
    if (listening) {
      rec.current?.stop();
      return;
    }
    const r = new Ctor();
    r.lang = navigator.language || 'es-ES';
    r.interimResults = false;
    r.onresult = (e) => onText(Array.from(e.results).map((x) => x[0].transcript).join(' '));
    r.onend = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };
  return { listening, toggle, available: !!Ctor };
}

function ChatTab({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const [thread, setThread] = useState('main');
  const [messages, setMessages] = useState<NodeMessage[]>([]);
  const [text, setText] = useState('');
  const [aloud, setAloud] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const spoken = useRef<string | null>(null);
  const tts = useTtsStore();
  const dictation = useDictation((t) => setText((x) => (x ? `${x} ${t}` : t)));

  const load = useCallback(() => {
    nodesApi
      .messages(node.id, 0, thread)
      .then(setMessages)
      .catch(() => {});
  }, [node.id, thread]);

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
  // Read new replies aloud (Sergio's voice), the face talks meanwhile.
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!aloud || !last || last.role !== 'node' || spoken.current === last.id) return;
    spoken.current = last.id;
    void tts.speak(`node-${last.id}`, last.text.replace(/[*_`#>|]/g, ''));
  }, [messages, aloud]); // eslint-disable-line react-hooks/exhaustive-deps

  const send = async () => {
    const t = text.trim();
    if (!t) return;
    setText('');
    try {
      await nodesApi.say(node.id, t, thread);
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

  const talking = tts.state === 'speaking' && !!tts.speakingId?.startsWith('node-');
  return (
    <div className="node-chat">
      <div className="node-threads" role="tablist" aria-label="Hilos">
        {node.threads.map((t) => (
          <button key={t.id} type="button" role="tab" className="mac-chip" aria-pressed={thread === t.id} onClick={() => setThread(t.id)}>
            {t.title}
          </button>
        ))}
        <button
          type="button"
          className="mac-chip"
          onClick={async () => {
            const title = window.prompt('Nombre del hilo nuevo', '');
            if (title === null) return;
            const t = await nodesApi.newThread(node.id, title);
            onChanged();
            setThread(t.id);
          }}
        >
          <Plus size={13} /> Hilo
        </button>
        <span className="flex-1" />
        <button
          type="button"
          className="mac-icon-btn"
          aria-pressed={aloud}
          aria-label={aloud ? 'No leer en voz alta' : 'Leer sus respuestas en voz alta'}
          title={aloud ? 'No leer en voz alta' : 'Leer sus respuestas en voz alta'}
          onClick={() => (aloud && tts.stop(), setAloud(!aloud))}
        >
          {aloud ? <Volume2 size={16} /> : <VolumeX size={16} />}
        </button>
      </div>
      <div className="node-thread">
        {messages.map((m, i) => (
          <div key={m.id} className={m.role === 'user' ? 'node-msg mine' : 'node-msg'}>
            {m.role === 'node' && <NodeCritter look={look(node)} size={30} talking={talking && i === messages.length - 1} />}
            <div className="node-msg-body">
              {m.source && m.source !== 'Encargo del usuario' && <span className="node-msg-source">{m.source}</span>}
              <div className="prose prose-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
              </div>
            </div>
          </div>
        ))}
        {node.approvals
          .filter((a) => (a.thread || 'main') === thread)
          .map((a) => (
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
        {node.status === 'needs_you' && <TakeOver node={node} onChanged={onChanged} />}
        {(node.status === 'working' || node.busy) && (
          <div className="node-msg">
            <NodeCritter look={look(node)} size={30} status="working" />
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
        <button
          type="button"
          className="mac-icon-btn"
          aria-pressed={dictation.listening}
          aria-label={dictation.listening ? 'Dejar de dictar' : 'Dictar'}
          onClick={dictation.toggle}
        >
          <Mic size={17} strokeWidth={1.6} />
        </button>
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
          {(data?.recent || []).slice(-14).map((r) => (
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
      <p className="node-hint">
        Lo que {node.name} recuerda de usted y de su trabajo. Lo escribe solo; usted puede leerlo, corregirlo o borrarlo.
      </p>
      <textarea className="paper-input" rows={14} value={text} onChange={(e) => (setText(e.target.value), setDirty(true))} placeholder="Todavía no recuerda nada." />
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
  const [kind, setKind] = useState<'time' | 'web' | 'app'>('time');
  const [mode, setMode] = useState<'every' | 'at'>('at');
  const [every, setEvery] = useState(60);
  const [at, setAt] = useState('08:00');
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [url, setUrl] = useState('');
  const [app, setApp] = useState(Object.keys(node.apps)[0] || '');
  const [keywords, setKeywords] = useState('');
  const add = async () => {
    try {
      const body =
        kind === 'web'
          ? { task, kind, url, every_minutes: every }
          : kind === 'app'
            ? { task, kind, app, keywords: keywords.split(',').map((k) => k.trim()).filter(Boolean), every_minutes: every }
            : mode === 'every'
              ? { task, every_minutes: every }
              : { task, at, days };
      await nodesApi.addRoutine(node.id, body);
      setTask('');
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude.');
    }
  };
  const everySelect = (
    <select className="paper-input node-time" value={every} onChange={(e) => setEvery(Number(e.target.value))} aria-label="Cada">
      {[15, 30, 60, 120, 240, 720, 1440].map((m) => (
        <option key={m} value={m}>
          {describeRoutine({ every_minutes: m, at: '', days: [] })}
        </option>
      ))}
    </select>
  );
  return (
    <div className="node-routines">
      <p className="node-hint">
        Trabajo que {node.name} repite solo, aunque usted no esté. Las vigilancias las revisa el código: {node.name} solo
        despierta cuando algo cambió de verdad.
      </p>
      <ul>
        {node.routines.map((r) => (
          <li key={r.id}>
            <span className="node-routine-when">{describeRoutine(r)}</span>
            <span className="flex-1">{r.task}</span>
            <button type="button" className="mac-icon-btn" title={r.last_error || ''}
              aria-label={r.enabled ? 'Pausar rutina' : 'Reanudar rutina'}
              onClick={() => void nodesApi.setRoutineEnabled(node.id, r.id, !r.enabled)
                .then(onChanged).catch(() => toast('No pude cambiar la rutina.'))}>
              {r.enabled ? 'Pausar' : `Reanudar${r.failures ? ` (${r.failures} fallos)` : ''}`}
            </button>
            {(r.last_check || r.last_run) > 0 && <span className="node-hint">{relative(r.last_check || r.last_run)}</span>}
            {r.kind && r.kind !== 'time' && (
              <button
                type="button"
                className="mac-icon-btn"
                aria-label="Revisar ahora"
                title="Revisar ahora"
                onClick={async () => {
                  const out = await nodesApi.checkRoutine(node.id, r.id).catch(() => null);
                  toast(out?.error ? `No pude revisar: ${out.error}` : out?.woke ? 'Hubo cambios: se puso a trabajar.' : 'Sin cambios.');
                  onChanged();
                }}
              >
                <RefreshCw size={14} />
              </button>
            )}
            <button type="button" className="mac-icon-btn" aria-label="Quitar rutina" onClick={async () => (await nodesApi.removeRoutine(node.id, r.id), onChanged())}>
              <Trash2 size={14} />
            </button>
          </li>
        ))}
      </ul>
      <div className="node-routine-form">
        <div className="node-seg" role="radiogroup" aria-label="Tipo">
          {(
            [
              ['time', 'Por horario'],
              ['web', 'Vigilar una web'],
              ['app', 'Cuando llegue algo a una app'],
            ] as const
          ).map(([k, label]) => (
            <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}>
              {label}
            </button>
          ))}
        </div>
        <input
          className="paper-input"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder={kind === 'web' ? 'Ej. Si bajó el precio, dime cuánto' : kind === 'app' ? 'Ej. ¿Es urgente? Prepárame un borrador' : 'Ej. Resumen del correo y la agenda'}
        />
        <div className="node-routine-when-row">
          {kind === 'web' && (
            <>
              <input className="paper-input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" aria-label="Dirección" />
              {everySelect}
            </>
          )}
          {kind === 'app' && (
            <>
              <select className="paper-input node-time" value={app} onChange={(e) => setApp(e.target.value)} aria-label="App">
                {Object.keys(node.apps).length ? (
                  Object.keys(node.apps).map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))
                ) : (
                  <option value="">Dele acceso a una app primero</option>
                )}
              </select>
              <input className="paper-input" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="Palabras clave (opcional, con comas)" aria-label="Palabras clave" />
              {everySelect}
            </>
          )}
          {kind === 'time' && (
            <>
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
                everySelect
              )}
            </>
          )}
          <button type="button" className="paper-button" onClick={add} disabled={!task.trim()}>
            <Plus size={14} /> Añadir
          </button>
        </div>
      </div>
    </div>
  );
}

function RulesTab({ node, catalog, onChanged }: { node: SergioNode; catalog: Catalog | null; onChanged: () => void }) {
  const set = async (key: string, choice: RuleChoice) => {
    await nodesApi.update(node.id, { rules: { ...node.rules, [key]: choice } });
    onChanged();
  };
  return (
    <div className="node-rules">
      <p className="node-hint">
        Qué hace {node.name} solo, qué le pregunta antes y qué no hará nunca. Enviar mensajes o correos, borrar y pagar
        nunca son automáticos: le deja el borrador y usted decide. Usar su PC está apagado hasta que usted lo permita.
      </p>
      {(catalog?.rules || []).map((r) => (
        <div key={r.key} className="node-rule">
          <span>{r.label}</span>
          <div className="node-seg" role="radiogroup" aria-label={r.label}>
            {(['allow', 'ask', 'block'] as RuleChoice[]).map((c) => (
              <button key={c} type="button" role="radio" aria-checked={node.rules[r.key] === c} disabled={!r.choices.includes(c)} onClick={() => set(r.key, c)}>
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
  const set = async (id: string, level: 'none' | 'read' | 'write') => {
    const next = { ...node.apps };
    if (level === 'none') delete next[id];
    else next[id] = level;
    await nodesApi.update(node.id, { apps: next });
    onChanged();
  };
  return (
    <div className="node-apps">
      <p className="node-hint">
        A qué apps entra {node.name} y cómo: solo leer, o leer y preparar cambios (escritura). Escribir siempre pasa por su
        aprobación.
      </p>
      {apps.map((a) => {
        const level = node.apps[a.connector_id] || 'none';
        return (
          <div key={a.connector_id} className="node-rule">
            <span>
              {a.display_name}
              {!a.connected && <em className="node-hint"> · sin conectar</em>}
            </span>
            <div className="node-seg" role="radiogroup" aria-label={a.display_name}>
              {(
                [
                  ['none', 'Sin acceso'],
                  ['read', 'Leer'],
                  ['write', 'Leer y escribir'],
                ] as const
              ).map(([k, label]) => (
                <button key={k} type="button" role="radio" aria-checked={level === k} disabled={!a.connected && k !== 'none'} onClick={() => set(a.connector_id, k)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
      <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/data-sources')}>
        Conectar más apps
      </button>
    </div>
  );
}

function ConnectionsTab({ node, catalog, onChanged }: { node: SergioNode; catalog: Catalog | null; onChanged: () => void }) {
  const [cli, setCli] = useState({ name: '', command: '' });
  const [mcp, setMcp] = useState({ name: '', command: '', url: '' });
  const [api, setApi] = useState({ name: '', base_url: '', auth_header: 'Authorization', prefix: 'Bearer', secret: '' });
  const [tools, setTools] = useState<Record<string, string[]>>({});
  const add = async (kind: 'cli' | 'mcp' | 'api', body: Record<string, string>, reset: () => void) => {
    try {
      await nodesApi.addConnection(node.id, kind, body);
      reset();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude.');
    }
  };
  const remove = async (kind: string, id: string) => {
    await nodesApi.removeConnection(node.id, kind, id);
    onChanged();
  };
  return (
    <div className="node-connections">
      <section>
        <h3 className="paper-label">Comandos (CLI)</h3>
        <p className="node-hint">
          Programas que {node.name} puede ejecutar en su computadora, uno a la vez y sin tuberías. «git status» permite
          solo «git status…»; «git» permite cualquier orden de git. Nunca: shells, sudo, rm.
        </p>
        <ul>
          {node.connections.cli.map((c) => (
            <li key={c.id}>
              <b>{c.name}</b>
              <code>{c.command}</code>
              <button type="button" className="mac-icon-btn" aria-label={`Quitar ${c.name}`} onClick={() => remove('cli', c.id)}>
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
        <div className="node-conn-form">
          <input className="paper-input" placeholder="Nombre (p. ej. git)" value={cli.name} onChange={(e) => setCli({ ...cli, name: e.target.value })} />
          <input className="paper-input" placeholder="Programa permitido (p. ej. git status)" value={cli.command} onChange={(e) => setCli({ ...cli, command: e.target.value })} />
          <button type="button" className="paper-button" disabled={!cli.name || !cli.command} onClick={() => add('cli', cli, () => setCli({ name: '', command: '' }))}>
            <Plus size={14} /> Añadir
          </button>
        </div>
      </section>

      <section>
        <h3 className="paper-label">Servidores MCP</h3>
        <p className="node-hint">Por comando (stdio) o por URL. Pruébelo para ver sus herramientas.</p>
        <ul>
          {node.connections.mcp.map((c) => (
            <li key={c.id}>
              <b>{c.name}</b>
              <code>{c.url || c.command}</code>
              <button
                type="button"
                className="mac-chip"
                onClick={async () => {
                  try {
                    const list = await nodesApi.mcpTools(node.id, c.id);
                    setTools({ ...tools, [c.id]: list.map((t) => t.name) });
                  } catch (e) {
                    toast.error(e instanceof Error ? e.message : 'No respondió.');
                  }
                }}
              >
                Probar
              </button>
              <button type="button" className="mac-icon-btn" aria-label={`Quitar ${c.name}`} onClick={() => remove('mcp', c.id)}>
                <Trash2 size={14} />
              </button>
              {tools[c.id] && <span className="node-hint node-conn-tools">{tools[c.id].join(' · ') || 'Sin herramientas'}</span>}
            </li>
          ))}
        </ul>
        <div className="node-conn-form">
          <input className="paper-input" placeholder="Nombre" value={mcp.name} onChange={(e) => setMcp({ ...mcp, name: e.target.value })} />
          <input className="paper-input" placeholder="Comando (npx -y servidor) o https://…" value={mcp.url || mcp.command} onChange={(e) => (/^https?:/.test(e.target.value) ? setMcp({ ...mcp, url: e.target.value, command: '' }) : setMcp({ ...mcp, command: e.target.value, url: '' }))} />
          <button type="button" className="paper-button" disabled={!mcp.name || !(mcp.url || mcp.command)} onClick={() => add('mcp', mcp, () => setMcp({ name: '', command: '', url: '' }))}>
            <Plus size={14} /> Añadir
          </button>
        </div>
      </section>

      <section>
        <h3 className="paper-label">
          APIs propias {!catalog?.api_allowed && <Lock size={12} />}
        </h3>
        {catalog?.api_allowed ? (
          <>
            <p className="node-hint">
              Su clave se guarda solo en este equipo y {node.name} nunca la ve: el código la añade. Leer (GET) sigue la
              regla «APIs»; cambiar datos siempre le pregunta.
            </p>
            <ul>
              {node.connections.api.map((c) => (
                <li key={c.id}>
                  <b>{c.name}</b>
                  <code>{c.base_url}</code>
                  {c.has_secret && <span className="node-hint">con clave</span>}
                  <button type="button" className="mac-icon-btn" aria-label={`Quitar ${c.name}`} onClick={() => remove('api', c.id)}>
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
            <div className="node-conn-form">
              <input className="paper-input" placeholder="Nombre (p. ej. crm)" value={api.name} onChange={(e) => setApi({ ...api, name: e.target.value })} />
              <input className="paper-input" placeholder="https://api.suempresa.com/v1" value={api.base_url} onChange={(e) => setApi({ ...api, base_url: e.target.value })} />
              <input className="paper-input" placeholder="Cabecera (Authorization)" value={api.auth_header} onChange={(e) => setApi({ ...api, auth_header: e.target.value })} />
              <input className="paper-input" placeholder="Prefijo (Bearer)" value={api.prefix} onChange={(e) => setApi({ ...api, prefix: e.target.value })} />
              <input className="paper-input" type="password" placeholder="Clave" value={api.secret} onChange={(e) => setApi({ ...api, secret: e.target.value })} autoComplete="off" />
              <button
                type="button"
                className="paper-button"
                disabled={!api.name || !api.base_url}
                onClick={() => add('api', api, () => setApi({ name: '', base_url: '', auth_header: 'Authorization', prefix: 'Bearer', secret: '' }))}
              >
                <Plus size={14} /> Añadir
              </button>
            </div>
          </>
        ) : (
          <div className="node-locked">
            <Lock size={16} />
            <p>
              Conectar sus propias APIs a un Node es parte del <b>plan Dev</b>. Su plan ahora: {catalog?.plan || 'free'}. Véalo
              con <code>sergio planes</code>.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}

function SettingsTab({ node, catalog, onChanged, onDeleted }: { node: SergioNode; catalog: Catalog | null; onChanged: () => void; onDeleted: () => void }) {
  const [name, setName] = useState(node.name);
  const [what, setWhat] = useState(node.instructions);
  const [avatar, setAvatar] = useState<Avatar>(look(node));
  const [tone, setTone] = useState(node.tone);
  return (
    <div className="node-settings">
      <AvatarDesigner value={avatar} onChange={setAvatar} catalog={catalog} />
      <label className="node-field">
        <span className="paper-label">Nombre</span>
        <input className="paper-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} />
      </label>
      <label className="node-field">
        <span className="paper-label">De qué se encarga</span>
        <textarea className="paper-input" rows={5} value={what} onChange={(e) => setWhat(e.target.value)} />
      </label>
      <div className="node-field">
        <span className="paper-label">Forma de hablar</span>
        <ToneSelect value={tone} onChange={setTone} catalog={catalog} />
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
              await nodesApi.update(node.id, { name, instructions: what, avatar, tone });
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
  const [catalog, setCatalog] = useState<Catalog | null>(null);
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
      .catalog()
      .then(setCatalog)
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
          catalog={catalog}
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
          <button
            key={n.id}
            type="button"
            className="nodes-item"
            style={{ '--node': look(n).color } as React.CSSProperties}
            aria-current={node?.id === n.id ? 'true' : undefined}
            onClick={() => open(n)}
          >
            <NodeCritter look={look(n)} status={n.status} size={40} />
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
        <section className="node-page" aria-label={node.name} style={{ '--node': look(node).color } as React.CSSProperties}>
          <header className="node-head">
            <NodeCritter look={look(node)} status={node.status} size={64} label={`${node.name}: ${STATUS_ES[node.status]}`} />
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
            {tab === 'chat' && <ChatTab key={node.id} node={node} onChanged={refresh} />}
            {tab === 'activity' && <ActivityTab node={node} />}
            {tab === 'computer' && <ComputerTab node={node} />}
            {tab === 'memory' && <MemoryTab node={node} onChanged={refresh} />}
            {tab === 'routines' && <RoutinesTab key={node.id} node={node} onChanged={refresh} />}
            {tab === 'rules' && <RulesTab node={node} catalog={catalog} onChanged={refresh} />}
            {tab === 'apps' && <AppsTab node={node} onChanged={refresh} />}
            {tab === 'goals' && <NodeGoals nodeId={node.id} />}
            {tab === 'connections' && (
              <div className="node-connections">
                <ConnectionsTab node={node} catalog={catalog} onChanged={refresh} />
                <ReviewedIntegrations nodeId={node.id} />
              </div>
            )}
            {tab === 'settings' && (
              <SettingsTab
                key={node.id}
                node={node}
                catalog={catalog}
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
