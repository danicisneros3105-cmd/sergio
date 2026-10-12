// Agent Swarm: one huge task, many sub-agents at once, one report, gone.

import { apiFetch } from './api';

export type SwarmStatus = 'scouting' | 'planning' | 'running' | 'synthesizing' | 'checking' | 'done' | 'failed' | 'cancelled';
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
  attempts?: number;
  current?: string; // the tool it is using right now
}

export interface SwarmChecks {
  links: number;
  links_unverified: string[];
  figures: number;
  figures_unbacked: string[];
  documents: number;
  documents_unread: string[];
  documents_unmentioned: string[];
  ok: boolean;
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
  budget?: number;
  explore?: boolean;
  scout?: string;
  scout_calls?: number;
  checks?: SwarmChecks | Record<string, never>;
  revised?: boolean;
  activity?: SwarmLine[]; // what is happening, in words, as it happens
}

export interface SwarmLine {
  t: number; // seconds since the swarm started
  who: string; // Explorador · Orquestador · #3 Rol · Supervisor · Comprobación
  text: string;
}

/** The colour family of a feed line's speaker. */
export function speaker(who: string): 'scout' | 'plan' | 'agent' | 'sup' | 'check' {
  if (who.startsWith('#')) return 'agent';
  if (who === 'Explorador') return 'scout';
  if (who === 'Orquestador') return 'plan';
  if (who === 'Supervisor') return 'sup';
  return 'check';
}

export const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

export const MAX_AGENTS = 300;
export const RUN_BUDGET = 4000;

export const FINAL: SwarmStatus[] = ['done', 'failed', 'cancelled'];

export const STATUS_ES: Record<SwarmStatus, string> = {
  scouting: 'Un explorador mira el terreno',
  planning: 'El orquestador reparte el trabajo',
  running: 'Los agentes trabajan a la vez',
  synthesizing: 'El supervisor une los resultados',
  checking: 'El código comprueba enlaces y cifras',
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
  start: (task: string, parallel: number, files: File[], scout?: boolean) => {
    const form = new FormData();
    form.append('task', task);
    form.append('parallel', String(parallel));
    if (scout !== undefined) form.append('scout', String(scout));
    for (const f of files) form.append('files', f, f.name);
    return json<SwarmRun>('/v1/swarm', { method: 'POST', body: form });
  },
  list: () => json<{ runs: SwarmRun[] }>('/v1/swarm').then((r) => r.runs),
  get: (id: string) => json<SwarmRun>(`/v1/swarm/${id}`),
  cancel: (id: string) => json<{ ok: boolean }>(`/v1/swarm/${id}/cancel`, { method: 'POST' }),
  /** Download the report (auth headers included, so a plain link would not do). */
  download: async (id: string, format: 'md' | 'csv' | 'json') => {
    const res = await apiFetch(`/v1/swarm/${id}/export?format=${format}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(String((body as { detail?: string }).detail || `Error ${res.status}`));
    }
    const cd = res.headers.get('content-disposition') || '';
    const name = decodeURIComponent(cd.match(/filename\*=UTF-8''([^;]+)/)?.[1] || `agent-swarm.${format}`);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  },
  toWorkspace: (id: string) => json<{ page: string; title: string }>(`/v1/swarm/${id}/workspace`, { method: 'POST' }),
};

/** Markdown tables in the report (the CSV export is only offered when there are some). */
export function hasTables(markdown: string): boolean {
  return /^\s*\|.*\|\s*\n\s*\|?\s*:?-{2,}/m.test(markdown || '');
}

/** Problems the code check found (0 = all checked out). */
export function checkIssues(checks: SwarmRun['checks']): number {
  if (!checks || !('ok' in checks)) return 0;
  return (
    checks.links_unverified.length +
    checks.figures_unbacked.length +
    checks.documents_unread.length +
    checks.documents_unmentioned.length
  );
}

// Progress 0..1: planning counts for a little, the agents for most, the
// supervisor for the last bit.
export function progress(run: Pick<SwarmRun, 'status' | 'counts' | 'subtasks'>): number {
  if (run.status === 'done') return 1;
  if (run.status === 'scouting') return 0.02;
  if (run.status === 'planning') return 0.05;
  const total = run.subtasks.length || 1;
  const finished = (run.counts.done || 0) + (run.counts.failed || 0) + (run.counts.cancelled || 0);
  const agents = finished / total;
  if (run.status === 'checking') return 0.97;
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
