// Sergio inside a page: summarise it, pull out the tasks, continue the text,
// polish the wording. One request to your own server's chat endpoint.

import { apiFetch } from '../api';
import { plainText, type Page } from './model';
import { inferTable, naturalFormula, parseGrid } from './brain';
import { computeCell } from './formula';
import type { TableData } from './model';

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

// -- beyond Notion: the parts that need a model ---------------------------------
// Each answer is checked with brain.ts before it touches a page.


export async function ask(system: string, user: string, model: string, temperature = 0.3): Promise<string> {
  const r = await apiFetch('/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, stream: false, temperature, messages: [{ role: 'system', content: system }, { role: 'user', content: user }] }),
  });
  if (!r.ok) throw new Error(`Sergio no respondió (HTTP ${r.status}).`);
  const data = await r.json();
  return String(data?.choices?.[0]?.message?.content || '').trim();
}

const PRECISE = 'Eres Sergio, un asistente preciso. Respondes solo con lo que se pide, sin preámbulos ni explicaciones.';

/** A whole database from a sentence: «clientes con teléfono, ciudad y último pedido». */
export async function aiTable(description: string, model: string): Promise<TableData> {
  const text = await ask(
    PRECISE,
    `Diseña una tabla para: ${description}\nResponde SOLO con CSV (coma como separador): la primera fila son los nombres de las columnas ` +
      '(la primera columna es el nombre de cada fila; usa columnas como Estado, Fecha (AAAA-MM-DD), Responsable, Cantidad cuando tengan sentido) ' +
      'y luego 3 a 6 filas de ejemplo realistas.',
    model,
  );
  const grid = parseGrid(text.replace(/^```\w*\n?|```$/g, ''));
  if (grid.length < 2) throw new Error('Sergio no devolvió una tabla.');
  return inferTable(grid);
}

/** A formula from words; the rules first, the model only when they fail —
 * and only a formula that computes without error is accepted. */
export async function aiFormula(sentence: string, table: TableData, model: string): Promise<string> {
  const local = naturalFormula(sentence, table);
  if (local) return local;
  const cols = table.columns.map((c) => `{${c.name}} (${c.type})`).join(', ');
  const out = (
    await ask(
      PRECISE,
      `Columnas: ${cols}.\nEscribe UNA fórmula de hoja de cálculo para: «${sentence}». Usa {Nombre de columna} para el valor de la fila, ` +
        'funciones SUMA, PROMEDIO, MIN, MAX, CONTAR, SI, REDONDEAR, ABS, y operadores + - * / > < =. Responde solo la fórmula, empezando por =.',
      model,
      0,
    )
  )
    .split('\n')[0]
    .replace(/^`+|`+$/g, '')
    .trim();
  if (!out.startsWith('=')) throw new Error('No entendí esa fórmula.');
  const probe: TableData = { ...table, columns: [...table.columns, { id: '__f', name: '__f', type: 'text' }], rows: table.rows.slice(0, 1).map((r) => ({ ...r, cells: { ...r.cells, __f: out } })) };
  const value = probe.rows.length ? computeCell(probe, 0, probe.columns.length - 1) : '';
  if (value.startsWith('#')) throw new Error(`La fórmula da ${value}.`);
  return out;
}

export interface PlanStep {
  title: string;
  kind: 'investigar' | 'escribir' | 'tabla' | 'tareas';
  approve: boolean; // asks before running
  status?: 'pendiente' | 'hecho' | 'error';
  result?: string;
}

/** An autonomous plan for a goal: steps Sergio can run, each one shown
 * first; nothing is sent or bought — results only land in the page. */
export async function aiPlan(goal: string, context: string, model: string): Promise<PlanStep[]> {
  const text = await ask(
    PRECISE,
    `Objetivo: ${goal}\nContexto de la página:\n${context.slice(0, 6000)}\n\nDivide el objetivo en 3 a 7 pasos que un asistente pueda ejecutar ` +
      'escribiendo en un documento (investigar, escribir, crear una tabla, sacar tareas). Responde SOLO JSON: ' +
      '[{"title":"…","kind":"investigar|escribir|tabla|tareas"}]',
    model,
  );
  const json = text.slice(text.indexOf('['), text.lastIndexOf(']') + 1);
  let raw: Array<{ title?: string; kind?: string }> = [];
  try {
    raw = JSON.parse(json);
  } catch {
    throw new Error('Sergio no devolvió un plan.');
  }
  const kinds = ['investigar', 'escribir', 'tabla', 'tareas'] as const;
  return raw
    .filter((s) => s && typeof s.title === 'string')
    .slice(0, 8)
    .map((s) => {
      const kind = (kinds as readonly string[]).includes(String(s.kind)) ? (s.kind as PlanStep['kind']) : 'escribir';
      return { title: s.title!.slice(0, 160), kind, approve: kind === 'investigar', status: 'pendiente' as const };
    });
}

export async function aiStep(step: PlanStep, goal: string, done: PlanStep[], model: string): Promise<string> {
  const before = done.filter((d) => d.result).map((d) => `## ${d.title}\n${d.result}`).join('\n\n').slice(-6000);
  const how: Record<PlanStep['kind'], string> = {
    investigar: 'Investiga y resume lo esencial en viñetas que empiecen por «- ». Distingue hechos de suposiciones.',
    escribir: 'Escribe el contenido pedido en párrafos cortos.',
    tabla: 'Responde SOLO con CSV (coma como separador) con encabezados.',
    tareas: 'Responde SOLO con tareas, una por línea, empezando por «- [ ] ».',
  };
  return ask(PRECISE, `Objetivo general: ${goal}\nPaso: ${step.title}\n${how[step.kind]}\n\nLo hecho hasta ahora:\n${before}`, model);
}

/** Which claims of a wiki page might be outdated or wrong, and why. */
export async function aiVerify(text: string, model: string): Promise<string[]> {
  const out = await ask(
    PRECISE,
    `Revisa este documento interno y lista las afirmaciones que podrían estar desactualizadas, ser contradictorias o necesitar ` +
      `una fuente. Una por línea, empezando por «- ». Si todo parece bien, responde «(nada)».\n\n${text.slice(0, 12000)}`,
    model,
  );
  return out.trim() === '(nada)' ? [] : parseLines(out).map((l) => l.text);
}

export interface Triage {
  summary: string;
  tasks: string[];
  reply: string;
}

/** One message: what it says, what to do, and a reply draft (never sent). */
export async function aiTriage(message: { from: string; subject: string; preview: string }, model: string): Promise<Triage> {
  const text = await ask(
    PRECISE,
    `Correo de ${message.from} — «${message.subject}»:\n${message.preview}\n\nResponde SOLO JSON: ` +
      '{"summary":"una frase","tasks":["tareas concretas"],"reply":"borrador de respuesta breve y cordial en el idioma del correo"}',
    model,
  );
  try {
    const j = JSON.parse(text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1));
    return { summary: String(j.summary || ''), tasks: Array.isArray(j.tasks) ? j.tasks.map(String).slice(0, 8) : [], reply: String(j.reply || '') };
  } catch {
    return { summary: text.slice(0, 200), tasks: [], reply: '' };
  }
}
