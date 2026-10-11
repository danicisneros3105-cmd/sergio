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
}

export interface Approval {
  id: string;
  at: number;
  category: string;
  what: string;
  status: 'pending' | 'approved' | 'denied';
}

export interface SergioNode {
  id: string;
  name: string;
  instructions: string;
  color: string;
  apps: string[];
  rules: Record<string, RuleChoice>;
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
}

export interface NodeMessage {
  id: string;
  at: number;
  role: 'user' | 'node';
  text: string;
  tool_calls?: number;
  source?: string;
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
  get: (id: string) => json<SergioNode>(`/v1/nodes/${id}`),
  create: (body: { name: string; instructions?: string; apps?: string[]; color?: string }) =>
    json<SergioNode>('/v1/nodes', send('POST', body)),
  update: (id: string, body: Partial<Pick<SergioNode, 'name' | 'instructions' | 'color' | 'apps' | 'rules'>>) =>
    json<SergioNode>(`/v1/nodes/${id}`, send('PATCH', body)),
  remove: (id: string) => json<{ deleted: boolean }>(`/v1/nodes/${id}`, send('DELETE')),
  seen: (id: string) => json<{ ok: boolean }>(`/v1/nodes/${id}/seen`, send('POST', {})),
  messages: (id: string, after = 0) =>
    json<{ messages: NodeMessage[] }>(`/v1/nodes/${id}/messages?after=${after}`).then((r) => r.messages),
  say: (id: string, text: string) => json<{ message: NodeMessage }>(`/v1/nodes/${id}/messages`, send('POST', { text })),
  activity: (id: string, after = 0) =>
    json<{ activity: ActivityItem[]; status: NodeStatus; doing: string; waiting: string; busy: boolean }>(
      `/v1/nodes/${id}/activity?after=${after}`,
    ),
  setMemory: (id: string, text: string) => json<{ text: string }>(`/v1/nodes/${id}/memory`, send('PUT', { text })),
  addRoutine: (id: string, body: { task: string; every_minutes?: number; at?: string; days?: number[] }) =>
    json<SergioNode>(`/v1/nodes/${id}/routines`, send('POST', body)),
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

export function describeRoutine(r: Pick<Routine, 'every_minutes' | 'at' | 'days'>): string {
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
