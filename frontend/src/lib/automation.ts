// Automations in three plain choices (owner, 2 Nov 2026: «aún se complican las
// automatizaciones complejas y simples»): WHEN (one tap), WHAT (one sentence,
// or several steps for a complex one) and WHO does it (one of the four
// Nodes). They become a Node routine (nodes/store.py: clean_routine), the one
// system that already runs work alone; nothing here sends, buys or deletes by
// itself: the Node still stops for the owner's yes on those.

export type When =
  | { kind: 'at'; at: string; days: number[] }
  | { kind: 'every'; minutes: number }
  | { kind: 'web'; url: string; minutes: number };

export interface Draft {
  when: When;
  steps: string[];
  node: string; // Node id
}

export const WEEKDAYS = [0, 1, 2, 3, 4];
export const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];
const DAY_NAMES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

export interface Quick {
  id: string;
  label: string;
  when: When;
}

/** The one-tap «when» choices. */
export const QUICK_WHEN: Quick[] = [
  { id: 'manana', label: 'Cada mañana', when: { kind: 'at', at: '08:00', days: ALL_DAYS } },
  { id: 'laborables', label: 'Días laborables', when: { kind: 'at', at: '09:00', days: WEEKDAYS } },
  { id: 'noche', label: 'Cada noche', when: { kind: 'at', at: '21:00', days: ALL_DAYS } },
  { id: 'hora', label: 'Cada hora', when: { kind: 'every', minutes: 60 } },
  { id: 'tres', label: 'Cada 3 horas', when: { kind: 'every', minutes: 180 } },
  { id: 'web', label: 'Cuando cambie una web', when: { kind: 'web', url: '', minutes: 60 } },
];

export interface Template {
  id: string;
  title: string;
  node: 'rhino' | 'dalmatian' | 'glove' | 'orb';
  when: When;
  steps: string[];
}

/** Ready-made automations: one tap fills the builder (nothing is created yet). */
export const TEMPLATES: Template[] = [
  {
    id: 'resumen',
    title: 'Resumen de la mañana',
    node: 'rhino',
    when: { kind: 'at', at: '08:00', days: ALL_DAYS },
    steps: ['Revisa mi agenda y mis correos sin leer', 'Dame un resumen de 5 líneas con lo urgente primero'],
  },
  {
    id: 'precio',
    title: 'Avisarme si baja un precio',
    node: 'rhino',
    when: { kind: 'web', url: '', minutes: 120 },
    steps: ['Si el precio bajó, avísame con el precio nuevo y el enlace'],
  },
  {
    id: 'noticias',
    title: 'Noticias de mi sector',
    node: 'dalmatian',
    when: { kind: 'at', at: '09:00', days: WEEKDAYS },
    steps: ['Busca las 5 noticias más importantes de mi sector de hoy', 'Resume cada una en una línea con su fuente'],
  },
  {
    id: 'clientes',
    title: 'Clientes nuevos cada día',
    node: 'dalmatian',
    when: { kind: 'at', at: '10:00', days: WEEKDAYS },
    steps: ['Busca 5 clientes o empleos que encajen con mi perfil', 'Escribe un borrador de mensaje para cada uno (no lo envíes)'],
  },
  {
    id: 'ideas',
    title: 'Ideas de video de la semana',
    node: 'glove',
    when: { kind: 'at', at: '09:00', days: [0] },
    steps: ['Mira las tendencias reales de esta semana', 'Propón 5 ideas de video con su gancho'],
  },
  {
    id: 'numeros',
    title: 'Mis números del viernes',
    node: 'orb',
    when: { kind: 'at', at: '17:00', days: [4] },
    steps: ['Revisa lo que gané y gasté esta semana', 'Dime con franqueza qué va bien, qué va mal y una decisión'],
  },
];

function daysText(days: number[]): string {
  const d = [...new Set(days)].sort();
  if (d.length === 0 || d.length === 7) return 'Cada día';
  if (d.join() === WEEKDAYS.join()) return 'De lunes a viernes';
  if (d.join() === '5,6') return 'Los fines de semana';
  if (d.length === 1) return `Cada ${DAY_NAMES[d[0]]}`;
  return `Los ${d.map((x) => DAY_NAMES[x]).join(', ').replace(/, ([^,]*)$/, ' y $1')}`;
}

function everyText(minutes: number): string {
  if (minutes % 1440 === 0) return minutes === 1440 ? 'cada día' : `cada ${minutes / 1440} días`;
  if (minutes % 60 === 0) return minutes === 60 ? 'cada hora' : `cada ${minutes / 60} horas`;
  return `cada ${minutes} minutos`;
}

export function host(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, '');
  } catch {
    return 'una página';
  }
}

/** «When» in words: «De lunes a viernes a las 09:00». */
export function whenText(w: When): string {
  if (w.kind === 'at') return `${daysText(w.days)} a las ${w.at}`;
  if (w.kind === 'every') return everyText(w.minutes).replace(/^c/, 'C');
  return `Cuando cambie ${w.url ? host(w.url) : 'la página'} (la miro ${everyText(w.minutes)})`;
}

export function cleanSteps(steps: string[]): string[] {
  return steps.map((s) => s.replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 8);
}

/** The whole automation in one sentence, before it is created. */
export function sentence(d: Draft, nodeName: string): string {
  const steps = cleanSteps(d.steps);
  const what = steps.length <= 1 ? steps[0] || '…' : steps.map((s, i) => `${i + 1}) ${s}`).join('; ');
  return `${whenText(d.when)}, ${nodeName}: ${what}`;
}

/** What is still missing, in plain words ('' when it can be created). */
export function problem(d: Draft): string {
  if (!d.node) return 'Elija quién lo hace.';
  if (cleanSteps(d.steps).length === 0) return 'Escriba qué debe hacer.';
  if (d.when.kind === 'at' && !/^([01]\d|2[0-3]):[0-5]\d$/.test(d.when.at)) return 'Elija la hora.';
  if (d.when.kind === 'web' && !/^https?:\/\/\S+\.\S+/.test(d.when.url)) return 'Escriba la dirección completa de la página (https://…).';
  return '';
}

/** The body for POST /v1/nodes/{id}/routines. Several steps become one
 * numbered task: the Node does them in order, in one go. */
export function toRoutine(d: Draft): {
  task: string;
  kind?: 'time' | 'web';
  every_minutes?: number;
  at?: string;
  days?: number[];
  url?: string;
} {
  const steps = cleanSteps(d.steps);
  const task =
    steps.length <= 1 ? steps[0] : `Hazlo en este orden y avísame al terminar:\n${steps.map((s, i) => `${i + 1}. ${s}`).join('\n')}`;
  if (d.when.kind === 'web') return { task, kind: 'web', url: d.when.url.trim(), every_minutes: Math.max(15, d.when.minutes) };
  if (d.when.kind === 'every') return { task, every_minutes: Math.max(15, d.when.minutes) };
  return { task, at: d.when.at, days: [...new Set(d.when.days)].sort() };
}
