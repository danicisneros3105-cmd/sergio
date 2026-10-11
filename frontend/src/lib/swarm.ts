// Agent Swarm: one huge task, many sub-agents at once, one report, gone.

import { apiFetch } from './api';

export type SwarmStatus = 'planning' | 'running' | 'synthesizing' | 'done' | 'failed' | 'cancelled';
export type AgentStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

export interface SwarmAgent {
  id: number;
  title: string;
  role: string;
  instruction: string;
  deliver: string;
  tools: string[];
  document: string;
  status: AgentStatus;
  result: string;
  tool_calls: number;
  sources: string[];
  started: number;
  ended: number;
}

export interface SwarmRun {
  id: string;
  task: string;
  parallel: number;
  title: string;
  status: SwarmStatus;
  roles: Array<{ nombre: string; especialidad: string }>;
  subtasks: SwarmAgent[];
  report: string;
  contradictions: string[];
  gaps: string[];
  documents: Array<{ name: string; path: string }>;
  error: string;
  created: number;
  ended: number;
  counts: Record<AgentStatus, number>;
  tool_calls: number;
  sources: string[];
  elapsed: number;
}

export const FINAL: SwarmStatus[] = ['done', 'failed', 'cancelled'];

export const STATUS_ES: Record<SwarmStatus, string> = {
  planning: 'El orquestador reparte el trabajo',
  running: 'Los agentes trabajan a la vez',
  synthesizing: 'El supervisor une y verifica',
  done: 'Terminado',
  failed: 'Falló',
  cancelled: 'Cancelado',
};

export const AGENT_ES: Record<AgentStatus, string> = {
  queued: 'En cola',
  running: 'Trabajando',
  done: 'Listo',
  failed: 'Falló',
  cancelled: 'Cancelado',
};

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(String((body as { detail?: string }).detail || `Error ${res.status}`));
  return body as T;
}

export const swarmApi = {
  start: (task: string, parallel: number, files: File[]) => {
    const form = new FormData();
    form.append('task', task);
    form.append('parallel', String(parallel));
    for (const f of files) form.append('files', f, f.name);
    return json<SwarmRun>('/v1/swarm', { method: 'POST', body: form });
  },
  list: () => json<{ runs: SwarmRun[] }>('/v1/swarm').then((r) => r.runs),
  get: (id: string) => json<SwarmRun>(`/v1/swarm/${id}`),
  cancel: (id: string) => json<{ ok: boolean }>(`/v1/swarm/${id}/cancel`, { method: 'POST' }),
};

// Progress 0..1: planning counts for a little, the agents for most, the
// supervisor for the last bit.
export function progress(run: Pick<SwarmRun, 'status' | 'counts' | 'subtasks'>): number {
  if (run.status === 'done') return 1;
  if (run.status === 'planning') return 0.04;
  const total = run.subtasks.length || 1;
  const finished = (run.counts.done || 0) + (run.counts.failed || 0) + (run.counts.cancelled || 0);
  const agents = finished / total;
  return Math.min(0.99, run.status === 'synthesizing' ? 0.92 : 0.06 + agents * 0.84);
}

export function elapsed(seconds: number): string {
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${String(s % 60).padStart(2, '0')} s`;
}

export function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}
