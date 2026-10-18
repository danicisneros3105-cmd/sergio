// Shortcuts wired like the fruit fly brain (see src/openjarvis/connectome on the server).
// Lateral horn: the innate shortcuts below, matched in the browser with no wait.
// Mushroom body: what the owner chose before, learned on the server.
// Central complex: rank() mixes both and falls back to asking Sergio in the chat.
// Giant fiber: escape() stops whatever Sergio is doing.

import { apiFetch } from './api';

export type ShortcutRun =
  | { kind: 'go'; to: string }
  | { kind: 'event'; name: string }
  | { kind: 'chat'; text: string };

export interface Shortcut {
  id: string;
  title: string;
  words: string[];
  /** "g s" means: press g, then s. */
  keys?: string;
  group: 'Ir a' | 'Hacer' | 'Salud';
  run: ShortcutRun;
}

export const SHORTCUTS: Shortcut[] = [
  { id: 'chat', title: 'Chat', words: ['chat', 'hablar', 'conversar', 'preguntar'], keys: 'g c', group: 'Ir a', run: { kind: 'go', to: '/chat' } },
  { id: 'nodes', title: 'Nodes', words: ['nodes', 'equipo', 'rihno', 'manchas', 'hous', 'tennessee', 'empleados'], keys: 'g n', group: 'Ir a', run: { kind: 'go', to: '/nodes' } },
  { id: 'swarm', title: 'Agent Swarm', words: ['enjambre', 'swarm', 'agentes', 'investigacion masiva'], keys: 'g e', group: 'Ir a', run: { kind: 'go', to: '/swarm' } },
  { id: 'workspace', title: 'Workspace', words: ['workspace', 'paginas', 'notas', 'documentos', 'notion'], keys: 'g w', group: 'Ir a', run: { kind: 'go', to: '/workspace' } },
  { id: 'cowork', title: 'Cowork', words: ['cowork', 'tarea larga', 'encargo', 'trabajo'], keys: 'g k', group: 'Ir a', run: { kind: 'go', to: '/cowork' } },
  { id: 'extensiones', title: 'Extensiones', words: ['extensiones', 'plugins', 'conectores', 'skills', 'mcp'], keys: 'g x', group: 'Ir a', run: { kind: 'go', to: '/extensiones' } },
  { id: 'rostros', title: 'Rostros', words: ['rostros', 'caras', 'face id', 'reconocimiento facial'], keys: 'g r', group: 'Ir a', run: { kind: 'go', to: '/faces' } },
  { id: 'perfil', title: 'Perfil', words: ['perfil', 'yo', 'mis datos', 'quien soy'], keys: 'g p', group: 'Ir a', run: { kind: 'go', to: '/perfil' } },
  { id: 'ajustes', title: 'Configuración', words: ['configuracion', 'ajustes', 'opciones', 'preferencias', 'settings'], keys: 'g a', group: 'Ir a', run: { kind: 'go', to: '/settings' } },
  { id: 'pensar', title: 'Pensar a fondo', words: ['pensar', 'razonar', 'analizar a fondo', 'decidir'], group: 'Ir a', run: { kind: 'go', to: '/pensar' } },
  { id: 'atajos', title: 'Cómo funcionan los atajos', words: ['atajos', 'conectoma', 'mosca', 'cerebro', 'teclas', 'ayuda'], keys: '?', group: 'Ir a', run: { kind: 'go', to: '/atajos' } },
  { id: 'salud', title: 'Salud', words: ['salud', 'health', 'resumen', 'pasos', 'sueno', 'pulso', 'peso'], keys: 'g s', group: 'Salud', run: { kind: 'go', to: '/salud' } },
  { id: 'salud:mente', title: 'Salud mental', words: ['salud mental', 'mente', 'animo', 'ansiedad', 'autoestima', 'estres', 'encuesta', 'gimnasio mental'], keys: 'g m', group: 'Salud', run: { kind: 'go', to: '/salud?tab=mente' } },
  { id: 'salud:explorar', title: 'Explorar mis medidas', words: ['medidas', 'presion', 'tension', 'glucosa', 'frecuencia', 'variabilidad', 'explorar'], group: 'Salud', run: { kind: 'go', to: '/salud?tab=explorar' } },
  { id: 'salud:dispositivos', title: 'Conectar reloj o anillo', words: ['reloj', 'anillo', 'bascula', 'dispositivos', 'sincronizar', 'importar'], group: 'Salud', run: { kind: 'go', to: '/salud?tab=dispositivos' } },
  { id: 'nuevo-chat', title: 'Nueva conversación', words: ['nuevo chat', 'nueva conversacion', 'empezar de cero'], group: 'Hacer', run: { kind: 'event', name: 'sergio:new-chat' } },
  { id: 'post-it', title: 'Nuevo Post-it', words: ['post-it', 'postit', 'nota rapida', 'apuntar', 'recordar'], group: 'Hacer', run: { kind: 'event', name: 'sergio:sticky-notes-new' } },
  { id: 'modelo', title: 'Cambiar de modelo', words: ['modelo', 'cambiar modelo', 'ia', 'motor'], group: 'Hacer', run: { kind: 'event', name: 'sergio:model-picker' } },
  { id: 'escape', title: 'Detener todo lo que está haciendo Sergio', words: ['detener', 'parar', 'stop', 'cancelar todo', 'escape', 'panico'], keys: 'Esc Esc Esc', group: 'Hacer', run: { kind: 'event', name: 'sergio:escape' } },
];

export const BY_ID: Record<string, Shortcut> = Object.fromEntries(SHORTCUTS.map((s) => [s.id, s]));

export function fold(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .trim();
}

/** Lateral horn: how well the typed words fit a shortcut, 0 to 1, no network. */
export function innate(query: string, s: Shortcut): number {
  const q = fold(query);
  if (!q) return 0;
  const title = fold(s.title);
  if (title === q) return 1;
  if (title.startsWith(q)) return 0.92;
  let best = 0;
  for (const w of s.words) {
    if (w === q) best = Math.max(best, 0.95);
    else if (w.startsWith(q)) best = Math.max(best, 0.85);
    else if (q.includes(w) && w.length >= 4) best = Math.max(best, 0.75);
    else if (w.includes(q) && q.length >= 3) best = Math.max(best, 0.6);
  }
  if (!best && title.includes(q) && q.length >= 2) best = 0.55;
  // Every word typed appears somewhere: a weaker but real match.
  if (!best) {
    const hay = `${title} ${s.words.join(' ')}`;
    const parts = q.split(/\s+/).filter((p) => p.length >= 3);
    if (parts.length && parts.every((p) => hay.includes(p))) best = 0.45;
  }
  return best;
}

export interface Ranked {
  shortcut: Shortcut;
  score: number;
  why: 'reflejo' | 'aprendido' | 'ambos';
}

/** Central complex: innate and learned together, best first. */
export function rank(query: string, learned: Array<{ action: string; score: number }> = []): Ranked[] {
  const learnedBy = new Map(learned.map((l) => [l.action, Math.min(1, l.score)]));
  const out: Ranked[] = [];
  for (const s of SHORTCUTS) {
    const a = query.trim() ? innate(query, s) : 0.3;
    const b = learnedBy.get(s.id) ?? 0;
    if (a <= 0 && b <= 0) continue;
    out.push({ shortcut: s, score: Math.max(a, b) + 0.25 * Math.min(a, b), why: a && b ? 'ambos' : b > a ? 'aprendido' : 'reflejo' });
  }
  return out.sort((x, y) => y.score - x.score || SHORTCUTS.indexOf(x.shortcut) - SHORTCUTS.indexOf(y.shortcut));
}

export async function learnedFor(query: string, signal?: AbortSignal): Promise<Array<{ action: string; score: number }>> {
  if (!query.trim()) return [];
  const res = await apiFetch(`/v1/connectome/learned?q=${encodeURIComponent(query)}`, { signal });
  if (!res.ok) return [];
  return ((await res.json()) as { learned: Array<{ action: string; score: number }> }).learned;
}

/** Dopamine: +1 when the owner chose a destination for these words. */
export function reinforce(query: string, action: string, reward = 1): void {
  if (!query.trim()) return;
  void apiFetch('/v1/connectome/learn', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, action, reward }),
  }).catch(() => {});
}

/** Giant fiber: stop Nodes, Agent Swarm and Cowork runs, and the voice. */
export async function escape(): Promise<{ nodes: number; swarm: number; cowork: number } | null> {
  try {
    window.speechSynthesis?.cancel();
  } catch {
    /* no speech in this browser */
  }
  window.dispatchEvent(new CustomEvent('sergio:escaped'));
  try {
    const res = await apiFetch('/v1/connectome/escape', { method: 'POST' });
    return res.ok ? ((await res.json()) as { stopped: { nodes: number; swarm: number; cowork: number } }).stopped : null;
  } catch {
    return null;
  }
}

export interface BrainMap {
  facts: { neurons: string; synapses: string; cell_types: string; sources: Array<{ cite: string; url: string }> };
  regions: Array<{ key: string; fly: string; job: string; sergio: string; where: string }>;
  memory: { kenyon_cells?: number; active_cells?: number; synapses?: number; top?: Array<[string, number]> };
  learning?: string;
  /** The mind's zones and what they learned (connectome/brain.py). */
  mind?: { engrams?: number; synapses?: number; associations?: number; fast_path?: number; corrections?: number };
}

export async function brainMap(): Promise<BrainMap> {
  const res = await apiFetch('/v1/connectome/map');
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return (await res.json()) as BrainMap;
}

export async function forgetLearned(): Promise<void> {
  await apiFetch('/v1/connectome/memory', { method: 'DELETE' });
}
