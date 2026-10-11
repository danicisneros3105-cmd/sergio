// Sergio inside a page: summarise it, pull out the tasks, continue the text,
// polish the wording. One request to your own server's chat endpoint.

import { apiFetch } from '../api';
import { plainText, type Page } from './model';

export type PageAction = 'summary' | 'tasks' | 'continue' | 'polish';

export const PAGE_ACTIONS: Array<{ key: PageAction; label: string }> = [
  { key: 'summary', label: 'Resumir' },
  { key: 'tasks', label: 'Sacar las tareas' },
  { key: 'continue', label: 'Seguir escribiendo' },
  { key: 'polish', label: 'Mejorar la redacción' },
];

const PROMPTS: Record<PageAction, string> = {
  summary: 'Resume esta página en 3 a 5 viñetas cortas, en español. Solo las viñetas, cada una empezando por «- ».',
  tasks:
    'Extrae de esta página las tareas concretas que hay que hacer, una por línea, empezando cada una por «- [ ] ». ' +
    'Si no hay ninguna, responde exactamente «(ninguna)».',
  continue: 'Continúa este texto con uno o dos párrafos más, con el mismo tono y en el mismo idioma. Solo el texto nuevo.',
  polish: 'Mejora la redacción de este texto sin cambiar su significado ni su idioma. Devuelve solo el texto mejorado.',
};

export function buildMessages(page: Page, action: PageAction) {
  return [
    { role: 'system', content: 'Eres Sergio, un asistente preciso. Respondes solo con lo que se pide, sin preámbulos.' },
    { role: 'user', content: `${PROMPTS[action]}\n\nTítulo: ${page.title || 'Sin título'}\n\n${plainText(page, 12000)}` },
  ];
}

export function parseLines(text: string): Array<{ kind: 'todo' | 'bullet' | 'text'; text: string }> {
  if (text.trim() === '(ninguna)') return [];
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const todo = /^[-*]\s*\[[ xX]?\]\s*(.+)$/.exec(line);
      if (todo) return { kind: 'todo' as const, text: todo[1] };
      const bullet = /^[-*•]\s+(.+)$/.exec(line);
      if (bullet) return { kind: 'bullet' as const, text: bullet[1] };
      return { kind: 'text' as const, text: line };
    });
}

export async function askAboutPage(page: Page, action: PageAction, model: string): Promise<string> {
  const r = await apiFetch('/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages: buildMessages(page, action), stream: false, temperature: 0.3 }),
  });
  if (!r.ok) throw new Error(`Sergio no respondió (HTTP ${r.status}).`);
  const data = await r.json();
  return String(data?.choices?.[0]?.message?.content || '').trim();
}
