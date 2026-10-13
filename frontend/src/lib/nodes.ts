// Nodes: persistent digital employees (like OpenAI's Dots). Each one has its
// own computer, memory, rules and routines on the Sergio server.

import { apiFetch } from './api';

export type NodeStatus = 'idle' | 'working' | 'waiting_approval' | 'needs_you' | 'paused';
export type RuleChoice = 'allow' | 'ask' | 'block';

export interface Routine {
  id: string;
  task: string;
  every_minutes: number;
  at: string;
  days: number[];
  last_run: number;
  enabled: boolean;
  failures?: number;
  last_error?: string;
  kind?: 'time' | 'web' | 'app';
  url?: string;
  app?: string;
  keywords?: string[];
  last_check?: number;
}

export interface Avatar {
  shape: 'bean' | 'blob' | 'drop' | 'heart' | 'frog' | 'bear' | 'star' | 'ghost' | 'mushroom' | 'cactus' | 'planet';
  color: string;
  accessory: 'none' | 'headphones' | 'beret' | 'glasses' | 'sunglasses' | 'bow' | 'cap' | 'beanie' | 'crown' | 'scarf';
  eyes: 'dots' | 'happy' | 'big' | 'sleepy' | 'googly';
}

export interface Connection {
  id: string;
  name: string;
  command?: string;
  url?: string;
  base_url?: string;
  auth_header?: string;
  prefix?: string;
  has_secret?: boolean;
}

export interface Thread {
  id: string;
  title: string;
  created: number;
}

export interface Template {
  id: string;
  name: string;
  title: string;
  description: string;
  avatar: Avatar;
}

export interface Catalog {
  rules: RuleSpec[];
  colors: string[];
  shapes: Avatar['shape'][];
  felt: string[];
  accessories: Avatar['accessory'][];
  eyes: Avatar['eyes'][];
  tones: Array<{ key: string; label: string }>;
  templates: Template[];
  plan: string;
  api_allowed: boolean;
}

export interface Approval {
  id: string;
  at: number;
  category: string;
  what: string;
  status: 'pending' | 'approved' | 'denied';
  thread?: string;
}

export interface OwnRule {
  id: string;
  text: string;
  effect: 'ask' | 'block';
  families: string[];
  words: string[];
  categories: string[];
  explain: string; // how Sergio understood it, in one line
}

export interface SergioNode {
  id: string;
  name: string;
  instructions: string;
  color: string;
  apps: Record<string, 'read' | 'write'>;
  rules: Record<string, RuleChoice>;
  own_rules?: OwnRule[];
  routines: Routine[];
  status: NodeStatus;
  doing: string;
  waiting: string;
  primary: boolean;
  created: number;
  updated: number;
  busy: boolean;
  memory: string;
  approvals: Approval[];
  unread: number;
  computer: string;
  avatar: Avatar;
  tone: string;
  template: string;
  threads: Thread[];
  connections: { cli: Connection[]; mcp: Connection[]; api: Connection[] };
}

export interface NodeMessage {
  id: string;
  at: number;
  role: 'user' | 'node';
  text: string;
  tool_calls?: number;
  source?: string;
  thread?: string;
  suggestions?: string[]; // next steps the Node proposes (click to ask)
}

export interface ActivityItem {
  id: string;
  at: number;
  kind: string;
  text: string;
  tool?: string;
  approval?: string;
}

export interface RuleSpec {
  key: string;
  label: string;
  default: RuleChoice;
  choices: RuleChoice[];
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(String((body as { detail?: string }).detail || `Error ${res.status}`));
  return body as T;
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const nodesApi = {
  list: () => json<{ nodes: SergioNode[] }>('/v1/nodes').then((r) => r.nodes),
  rules: () => json<{ rules: RuleSpec[]; colors: string[] }>('/v1/nodes/rules'),
  catalog: () => json<Catalog>('/v1/nodes/catalog'),
  get: (id: string) => json<SergioNode>(`/v1/nodes/${id}`),
  create: (body: {
    name: string;
    instructions?: string;
    apps?: Record<string, 'read' | 'write'>;
    color?: string;
    template?: string;
    avatar?: Avatar;
    tone?: string;
  }) => json<SergioNode>('/v1/nodes', send('POST', body)),
  update: (id: string, body: Partial<Pick<SergioNode, 'name' | 'instructions' | 'color' | 'apps' | 'rules' | 'avatar' | 'tone'>>) =>
    json<SergioNode>(`/v1/nodes/${id}`, send('PATCH', body)),
  addOwnRule: (id: string, text: string) =>
    json<SergioNode & { rule: OwnRule }>(`/v1/nodes/${id}/own-rules`, send('POST', { text })),
  removeOwnRule: (id: string, ruleId: string) => json<SergioNode>(`/v1/nodes/${id}/own-rules/${ruleId}`, send('DELETE')),
  newThread: (id: string, title = '') => json<{ thread: Thread }>(`/v1/nodes/${id}/threads`, send('POST', { title })).then((r) => r.thread),
  remove: (id: string) => json<{ deleted: boolean }>(`/v1/nodes/${id}`, send('DELETE')),
  seen: (id: string) => json<{ ok: boolean }>(`/v1/nodes/${id}/seen`, send('POST', {})),
  messages: (id: string, after = 0, thread = 'main') =>
    json<{ messages: NodeMessage[] }>(`/v1/nodes/${id}/messages?after=${after}&thread=${encodeURIComponent(thread)}`).then((r) => r.messages),
  say: (id: string, text: string, thread = 'main') =>
    json<{ message: NodeMessage }>(`/v1/nodes/${id}/messages`, send('POST', { text, thread })),
  activity: (id: string, after = 0) =>
    json<{ activity: ActivityItem[]; status: NodeStatus; doing: string; waiting: string; busy: boolean }>(
      `/v1/nodes/${id}/activity?after=${after}`,
    ),
  setMemory: (id: string, text: string) => json<{ text: string }>(`/v1/nodes/${id}/memory`, send('PUT', { text })),
  addRoutine: (
    id: string,
    body: { task: string; kind?: 'time' | 'web' | 'app'; every_minutes?: number; at?: string; days?: number[]; url?: string; app?: string; keywords?: string[] },
  ) => json<SergioNode>(`/v1/nodes/${id}/routines`, send('POST', body)),
  checkRoutine: (id: string, rid: string) => json<{ woke: boolean; error: string }>(`/v1/nodes/${id}/routines/${rid}/check`, send('POST', {})),
  setRoutineEnabled: (id: string, rid: string, enabled: boolean) => json<Node>(`/v1/nodes/${id}/routines/${rid}`, send('PATCH', { enabled })),
  addConnection: (id: string, kind: 'cli' | 'mcp' | 'api', body: Record<string, string>) =>
    json<SergioNode>(`/v1/nodes/${id}/connections/${kind}`, send('POST', body)),
  removeConnection: (id: string, kind: string, cid: string) => json<SergioNode>(`/v1/nodes/${id}/connections/${kind}/${cid}`, send('DELETE')),
  mcpTools: (id: string, cid: string) =>
    json<{ tools: Array<{ name: string; description: string }> }>(`/v1/nodes/${id}/connections/mcp/${cid}/tools`, send('POST', {})).then((r) => r.tools),
  removeRoutine: (id: string, rid: string) => json<SergioNode>(`/v1/nodes/${id}/routines/${rid}`, send('DELETE')),
  decide: (id: string, aid: string, approve: boolean) =>
    json<SergioNode>(`/v1/nodes/${id}/approvals/${aid}`, send('POST', { approve })),
  handBack: (id: string, note = '') => json<SergioNode>(`/v1/nodes/${id}/hand-back`, send('POST', { note })),
  stop: (id: string) => json<SergioNode>(`/v1/nodes/${id}/stop`, send('POST', {})),
  resume: (id: string) => json<SergioNode>(`/v1/nodes/${id}/resume`, send('POST', {})),
  computer: (id: string) =>
    json<{ files: Array<{ path: string; size: number; modified: number }>; path: string; doing: string; recent: ActivityItem[] }>(
      `/v1/nodes/${id}/computer`,
    ),
  fileUrl: (id: string, path: string) => `/v1/nodes/${id}/computer/file?path=${encodeURIComponent(path)}`,
};

// -- words for the screen ----------------------------------------------------

export const STATUS_ES: Record<NodeStatus, string> = {
  idle: 'Disponible',
  working: 'Trabajando',
  waiting_approval: 'Espera su aprobación',
  needs_you: 'Le necesita',
  paused: 'Detenido',
};

export function statusLine(node: Pick<SergioNode, 'status' | 'doing' | 'waiting'>): string {
  if (node.status === 'working' && node.doing) return node.doing;
  if (node.status === 'needs_you' && node.waiting) return node.waiting;
  return STATUS_ES[node.status] || node.status;
}

const DAYS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export const SHAPE_ES: Record<Avatar['shape'], string> = {
  bean: 'Guijarro',
  blob: 'Mochi',
  drop: 'Gotita',
  heart: 'Corazón',
  frog: 'Ranita',
  bear: 'Osito',
  star: 'Estrella',
  ghost: 'Fantasmita',
  mushroom: 'Setita',
  cactus: 'Cactus',
  planet: 'Planeta',
};
export const ACCESSORY_ES: Record<Avatar['accessory'], string> = {
  none: 'Nada',
  headphones: 'Cascos',
  beret: 'Boina',
  glasses: 'Gafas',
  sunglasses: 'Gafas de sol',
  bow: 'Lazo',
  cap: 'Gorra',
  beanie: 'Gorro',
  crown: 'Corona',
  scarf: 'Bufanda',
};
export const EYES_ES: Record<Avatar['eyes'], string> = {
  dots: 'Puntitos',
  happy: 'Felices',
  big: 'Grandes',
  sleepy: 'Dormilones',
  googly: 'Saltones',
};

export function describeRoutine(r: Pick<Routine, 'every_minutes' | 'at' | 'days'> & Partial<Pick<Routine, 'kind' | 'url' | 'app'>>): string {
  if (r.kind === 'web') return `Vigila ${host(r.url || '')} · ${describeRoutine({ every_minutes: r.every_minutes, at: '', days: [] }).toLowerCase()}`;
  if (r.kind === 'app') return `Novedades en ${r.app} · ${describeRoutine({ every_minutes: r.every_minutes, at: '', days: [] }).toLowerCase()}`;
  if (r.every_minutes) {
    const m = r.every_minutes;
    if (m % 1440 === 0) return m === 1440 ? 'Cada día' : `Cada ${m / 1440} días`;
    if (m % 60 === 0) return m === 60 ? 'Cada hora' : `Cada ${m / 60} horas`;
    return `Cada ${m} min`;
  }
  const days = r.days.length === 0 || r.days.length === 7 ? 'Todos los días' : r.days.map((d) => DAYS[d]).join(', ');
  return `${days} a las ${r.at}`;
}

export function relative(ts: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ts * 1000) / 1000));
  if (s < 45) return 'ahora';
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  const d = Math.round(s / 86400);
  return d === 1 ? 'ayer' : `hace ${d} días`;
}

export function dayLabel(ts: number, now = new Date()): string {
  const day = new Date(ts * 1000);
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((start(now) - start(day)) / 86400000);
  if (diff === 0) return 'Hoy';
  if (diff === 1) return 'Ayer';
  return day.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' });
}

export function groupByDay(items: ActivityItem[], now = new Date()): Array<{ day: string; items: ActivityItem[] }> {
  const out: Array<{ day: string; items: ActivityItem[] }> = [];
  for (const item of [...items].sort((a, b) => b.at - a.at)) {
    const day = dayLabel(item.at, now);
    const last = out[out.length - 1];
    if (last && last.day === day) last.items.push(item);
    else out.push({ day, items: [item] });
  }
  return out;
}

export const RULE_ES: Record<RuleChoice, string> = { allow: 'Solo', ask: 'Preguntar', block: 'Nunca' };
