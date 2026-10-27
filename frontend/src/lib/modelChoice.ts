// Choosing Sergio's model and how hard it thinks, simply: the chat models of
// every company Sergio can use (`/v1/personal/modelos`: Google, OpenAI,
// Anthropic, DeepSeek and, through OpenRouter, any other) and four levels of effort.
// «Automático» leaves both to Sergio's brain (cortex.py picks the effort).

import { apiFetch } from './api';

export type Effort = 'auto' | 'low' | 'medium' | 'high';

export interface ModelOption {
  id: string;
  nombre: string;
  para: string;
  disponible: boolean;
  empresa?: string;
  cuenta?: number;
}

export interface Company {
  id: string;
  nombre: string;
  clave: string;
  donde: string;
  conectada: boolean;
}

export const EFFORTS: { id: Effort; nombre: string; para: string }[] = [
  { id: 'auto', nombre: 'Automático', para: 'Sergio decide cuánto pensar.' },
  { id: 'low', nombre: 'Rápido', para: 'Responde enseguida.' },
  { id: 'medium', nombre: 'Normal', para: 'Piensa un poco.' },
  { id: 'high', nombre: 'A fondo', para: 'Piensa mucho; tarda más.' },
];

/** «gemini-3.6-flash» + «high» → «gemini-3.6-flash@high»; automatic adds nothing. */
export function withEffort(model: string, effort: Effort | undefined): string {
  // Only Gemini understands «@effort»; other companies get the bare id.
  if (!model || !effort || effort === 'auto' || model.includes('@') || !model.startsWith('gemini')) return model;
  return `${model}@${effort}`;
}

/** A model id as people read it: «gemini-3.6-flash» → «Gemini 3.6 Flash». */
export function modelName(id: string, known: ModelOption[] = []): string {
  const hit = known.find((m) => m.id === id);
  if (hit) return hit.nombre;
  return id
    .replace(/@.*$/, '')
    .split(/[-_]/)
    .map((w) => (/^\d/.test(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ');
}

export async function fetchModelOptions(): Promise<{ modelos: ModelOption[]; empresas?: Company[]; actual: string }> {
  const res = await apiFetch('/v1/personal/modelos');
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return res.json();
}
