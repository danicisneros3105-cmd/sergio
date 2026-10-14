// Sergio's brain for the Workspace: the pure logic behind every improvement
// over Notion that does not need a model — so it is instant, works offline
// and is tested. The parts that do need a model (writing, planning, triage)
// live in ai.ts and use these to check what comes back.
//
//   memory      relatedPages, searchPages (semantic-ish, multimodal text)
//   databases   inferTable (types guessed from data), detectRelations
//   rollups     rollup (the right aggregation for each column type)
//   formulas    naturalFormula (Spanish/English sentences → formula)
//   projects    schedule (dependencies, critical path), projectRisk
//   wikis       staleness (what to verify and why)
//   automations evaluateRules / applyRules (AND/OR conditions, actions)
//   forms       visibleFields, submitForm (conditional logic, validation)
//   buttons     runButton (programmable actions)
//   templates   evolveTemplate (learns from how you use it)
//   history     blockDiff, wordDiff (visual Git for documents)
//   teams       merge3 (three-way merge instead of conflict copies)
//   dashboards  kpis
//   calendar    datedItems (every date in every page, one agenda)

import { computeCell, toNumber } from './formula';
import { newId, plainText, type Block, type Column, type ColumnType, type Page, type Row, type TableData } from './model';

// -- text ---------------------------------------------------------------------

const STOP = new Set(
  (
    'el la los las un una unos unas de del al a en y o u que se su sus por para con sin es son fue ser lo le les ' +
    'como mas más pero si no ya muy este esta estos estas ese esa eso aquí hay the of and to in is for on with it'
  ).split(' '),
);

export function fold(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
}

/** Words that carry meaning, folded and lightly stemmed (plural -s/-es). */
export function terms(text: string): string[] {
  return (fold(text).match(/[a-z0-9ñ]{2,}/g) || [])
    .filter((w) => !STOP.has(w))
    .map((w) => (w.length > 4 && w.endsWith('es') ? w.slice(0, -2) : w.length > 3 && w.endsWith('s') ? w.slice(0, -1) : w));
}

/** Everything searchable in a page: text, cells, image captions, transcripts. */
export function pageText(page: Page): string {
  const extra = page.blocks
    .map((b) => [b.media?.name, b.media?.caption, b.media?.transcript].filter(Boolean).join(' '))
    .join(' ');
  return `${page.title} ${(page.tags || []).join(' ')} ${plainText(page, 20000)} ${extra}`;
}

type Vec = Map<string, number>;

function vectors(docs: string[][]): Vec[] {
  const df = new Map<string, number>();
  for (const d of docs) for (const t of new Set(d)) df.set(t, (df.get(t) || 0) + 1);
  const n = docs.length;
  return docs.map((d) => {
    const tf = new Map<string, number>();
    for (const t of d) tf.set(t, (tf.get(t) || 0) + 1);
    const v: Vec = new Map();
    let norm = 0;
    for (const [t, c] of tf) {
      const w = (1 + Math.log(c)) * Math.log(1 + n / (df.get(t) || 1));
      v.set(t, w);
      norm += w * w;
    }
    norm = Math.sqrt(norm) || 1;
    for (const [t, w] of v) v.set(t, w / norm);
    return v;
  });
}

function cosine(a: Vec, b: Vec): number {
  let s = 0;
  const [small, big] = a.size < b.size ? [a, b] : [b, a];
  for (const [t, w] of small) s += w * (big.get(t) || 0);
  return s;
}

// A few synonyms so «reunión» finds «junta» and «gasto» finds «costo».
const SYNONYMS: string[][] = [
  ['reunion', 'junta', 'meeting', 'llamada'],
  ['gasto', 'costo', 'coste', 'presupuesto', 'pago', 'factura'],
  ['tarea', 'pendiente', 'todo', 'hacer'],
  ['cliente', 'comprador', 'customer'],
  ['proyecto', 'plan', 'iniciativa'],
  ['idea', 'propuesta', 'nota'],
  ['foto', 'imagen', 'captura', 'image'],
  ['audio', 'grabacion', 'voz', 'nota de voz'],
  ['fecha', 'dia', 'plazo', 'entrega', 'deadline'],
];

export function expandQuery(q: string): string[] {
  const base = terms(q);
  const out = new Set(base);
  for (const t of base) for (const group of SYNONYMS) if (group.some((g) => g.startsWith(t) || t.startsWith(g))) group.forEach((g) => terms(g).forEach((x) => out.add(x)));
  return [...out];
}

export interface Hit {
  page: Page;
  score: number;
  snippet: string;
}

/** Search by meaning (terms, synonyms, weights) over text, cells, image
 * captions and audio transcripts — not just exact words. */
export function searchPages(pages: Page[], query: string, limit = 20): Hit[] {
  const live = pages.filter((p) => !p.archived && !p.sealed);
  const q = expandQuery(query);
  if (!q.length) return [];
  const docs = live.map((p) => terms(pageText(p)));
  const vs = vectors([...docs, q]);
  const qv = vs[vs.length - 1];
  const raw = fold(query.trim());
  return live
    .map((page, i) => {
      let score = cosine(vs[i], qv);
      if (raw && fold(page.title).includes(raw)) score += 0.6;
      if (raw && fold(pageText(page)).includes(raw)) score += 0.25;
      return { page, score, snippet: snippet(pageText(page), q) };
    })
    .filter((h) => h.score > 0.02)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

function snippet(text: string, q: string[]): string {
  const folded = fold(text);
  let at = -1;
  for (const t of q) {
    at = folded.indexOf(t);
    if (at >= 0) break;
  }
  const start = Math.max(0, at - 50);
  return (start > 0 ? '…' : '') + text.slice(start, start + 140).replace(/\s+/g, ' ').trim();
}

/** The pages most related to this one (shared meaning, links, tags). */
export function relatedPages(pages: Page[], page: Page, limit = 5): Array<{ page: Page; score: number; why: string }> {
  const others = pages.filter((p) => p.id !== page.id && !p.archived && !p.sealed);
  if (!others.length) return [];
  const docs = [page, ...others].map((p) => terms(pageText(p)));
  const vs = vectors(docs);
  const links = new Set(page.blocks.filter((b) => b.pageId).map((b) => b.pageId));
  const mentionsTitle = (a: Page, b: Page) => !!b.title && fold(pageText(a)).includes(fold(b.title));
  return others
    .map((p, i) => {
      let score = cosine(vs[0], vs[i + 1]);
      let why = 'tema parecido';
      const sharedTags = (p.tags || []).filter((t) => (page.tags || []).includes(t));
      if (sharedTags.length) {
        score += 0.2 * sharedTags.length;
        why = `etiqueta ${sharedTags[0]}`;
      }
      if (links.has(p.id) || mentionsTitle(page, p) || mentionsTitle(p, page)) {
        score += 0.5;
        why = 'se mencionan';
      }
      return { page: p, score, why };
    })
    .filter((r) => r.score > 0.08)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

// -- databases ------------------------------------------------------------------

const DATE_RE = /^(\d{4}-\d{2}-\d{2})|(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})$/;

export function guessType(values: string[]): { type: ColumnType; options?: string[] } {
  const v = values.map((x) => x.trim()).filter(Boolean);
  if (!v.length) return { type: 'text' };
  const all = (re: RegExp) => v.every((x) => re.test(x));
  if (v.every((x) => /^(sí|si|no|true|false|x|✓|☑|☐|yes)$/i.test(x))) return { type: 'checkbox' };
  if (v.every((x) => toNumber(x.replace(/[$€%\s]/g, '')) !== null)) return { type: 'number' };
  if (all(DATE_RE)) return { type: 'date' };
  if (all(/^[^@\s]+@[^@\s]+\.[^@\s]+$/)) return { type: 'email' };
  if (all(/^(https?:\/\/|www\.)\S+$/i)) return { type: 'url' };
  if (all(/^[+\d][\d\s().-]{6,}$/)) return { type: 'phone' };
  const distinct = [...new Set(v)];
  if (v.some((x) => x.includes(',')) && v.every((x) => x.split(',').every((p) => p.trim().length < 24))) {
    const opts = [...new Set(v.flatMap((x) => x.split(',').map((p) => p.trim())))];
    if (opts.length <= 16) return { type: 'multi', options: opts };
  }
  if (distinct.length <= Math.max(2, Math.ceil(v.length / 2)) && distinct.length <= 12 && v.length >= 3)
    return { type: 'select', options: distinct };
  return { type: 'text' };
}

function normalizeCell(type: ColumnType, raw: string): string {
  const v = raw.trim();
  if (type === 'checkbox') return /^(sí|si|true|x|✓|☑|yes)$/i.test(v) ? 'true' : 'false';
  if (type === 'date') {
    const m = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$/.exec(v);
    if (m) {
      const y = m[3].length === 2 ? `20${m[3]}` : m[3];
      return `${y}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
    }
  }
  if (type === 'number') return v.replace(/[$€%\s]/g, '');
  return v;
}

/** A table built from rows of text (pasted CSV/TSV, or what the model
 * returned): the first row names the columns, each column's type is guessed
 * from its values. */
export function inferTable(rows: string[][]): TableData {
  const [head = [], ...body] = rows.filter((r) => r.some((c) => c.trim()));
  const width = Math.max(head.length, ...body.map((r) => r.length), 1);
  const columns: Column[] = Array.from({ length: width }, (_, i) => {
    const guess = guessType(body.map((r) => r[i] || ''));
    return { id: newId('c'), name: (head[i] || `Columna ${i + 1}`).trim(), type: i === 0 ? 'text' : guess.type, ...(guess.options && i ? { options: guess.options } : {}) };
  });
  const view = { id: newId('v'), name: 'Tabla', kind: 'table' as const };
  const views: TableData['views'] = [view];
  const status = columns.find((c) => c.type === 'select');
  if (status) views.push({ id: newId('v'), name: 'Tablero', kind: 'board', groupBy: status.id });
  if (columns.some((c) => c.type === 'date')) views.push({ id: newId('v'), name: 'Calendario', kind: 'calendar' });
  return {
    columns,
    rows: body.map((r) => ({ id: newId('r'), cells: Object.fromEntries(columns.map((c, i) => [c.id, normalizeCell(c.type, r[i] || '')])) })),
    views,
    view: view.id,
  };
}

/** Split pasted text (CSV, TSV, a Markdown table) into rows of cells. */
export function parseGrid(text: string): string[][] {
  const lines = text.replace(/\r/g, '').split('\n').filter((l) => l.trim() && !/^\s*\|?\s*:?-{2,}/.test(l));
  if (!lines.length) return [];
  if (lines[0].includes('|')) return lines.map((l) => l.replace(/^\s*\||\|\s*$/g, '').split('|').map((c) => c.trim()));
  const sep = lines[0].includes('\t') ? '\t' : lines[0].split(';').length > lines[0].split(',').length ? ';' : ',';
  return lines.map((l) => splitCsv(l, sep));
}

function splitCsv(line: string, sep: string): string[] {
  const out: string[] = [];
  let cur = '';
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else quoted = !quoted;
    } else if (ch === sep && !quoted) {
      out.push(cur.trim());
      cur = '';
    } else cur += ch;
  }
  out.push(cur.trim());
  return out;
}

export interface TableRef {
  pageId: string;
  blockId: string;
  title: string;
  table: TableData;
}

export function allTables(pages: Page[]): TableRef[] {
  return pages.flatMap((p) =>
    p.archived ? [] : p.blocks.filter((b) => b.table).map((b) => ({ pageId: p.id, blockId: b.id, title: b.text || p.title || 'Tabla', table: b.table! })),
  );
}

export interface RelationHint {
  pageId: string;
  blockId: string;
  column: Column;
  target: { kind: 'table'; ref: TableRef } | { kind: 'pages' };
  matches: number;
}

/** Columns whose values are, mostly, the names of rows of another table or
 * titles of pages: relations nobody had to configure. */
export function detectRelations(pages: Page[]): RelationHint[] {
  const tables = allTables(pages);
  const titles = new Set(pages.map((p) => fold(p.title)).filter(Boolean));
  const hints: RelationHint[] = [];
  for (const t of tables) {
    for (const col of t.table.columns.slice(1)) {
      if (!['text', 'select', 'multi'].includes(col.type) || col.relation) continue;
      const values = t.table.rows.flatMap((r) => (r.cells[col.id] || '').split(',')).map((v) => fold(v.trim())).filter(Boolean);
      if (values.length < 2) continue;
      let best: RelationHint | null = null;
      for (const other of tables) {
        // a column naming rows of its own table (dependencies) is a relation too
        const first = other.table.columns[0];
        const names = new Set(other.table.rows.map((r) => fold((r.cells[first.id] || '').trim())).filter(Boolean));
        const matches = values.filter((v) => names.has(v)).length;
        const ref = other.blockId === t.blockId ? { ...other, title: 'esta tabla' } : other;
        if (matches / values.length >= 0.6 && (!best || matches > best.matches)) best = { pageId: t.pageId, blockId: t.blockId, column: col, target: { kind: 'table', ref }, matches };
      }
      const pageMatches = values.filter((v) => titles.has(v)).length;
      if (!best && pageMatches / values.length >= 0.6) best = { pageId: t.pageId, blockId: t.blockId, column: col, target: { kind: 'pages' }, matches: pageMatches };
      if (best) hints.push(best);
    }
  }
  return hints;
}

// -- rollups -----------------------------------------------------------------------

/** The aggregation that makes sense for a column, already computed. */
export function rollup(table: TableData, columnId: string): string {
  const col = table.columns.find((c) => c.id === columnId);
  if (!col) return '';
  const rows = table.rows.filter((r) => !r.archived);
  const ci = table.columns.indexOf(col);
  const values = rows.map((_r, i) => computeCell(table, i, ci)).filter((v) => v !== '');
  if (!rows.length) return '';
  const fmt = (n: number) => n.toLocaleString('es', { maximumFractionDigits: 2 });
  switch (col.type) {
    case 'number': {
      const nums = values.map((v) => toNumber(v)).filter((n): n is number => n !== null);
      if (!nums.length) return '';
      const sum = nums.reduce((a, b) => a + b, 0);
      return `Σ ${fmt(sum)} · x̄ ${fmt(sum / nums.length)}`;
    }
    case 'checkbox': {
      const done = rows.filter((r) => r.cells[col.id] === 'true').length;
      return `${Math.round((done / rows.length) * 100)} % hecho`;
    }
    case 'select':
    case 'multi': {
      const counts = new Map<string, number>();
      for (const v of values) for (const part of v.split(',').map((x) => x.trim()).filter(Boolean)) counts.set(part, (counts.get(part) || 0) + 1);
      return [...counts].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, n]) => `${k} ${n}`).join(' · ');
    }
    case 'date': {
      const sorted = values.filter((v) => /^\d{4}-\d{2}-\d{2}/.test(v)).sort();
      if (!sorted.length) return '';
      return sorted.length === 1 ? sorted[0] : `${sorted[0]} → ${sorted[sorted.length - 1]}`;
    }
    default:
      return `${values.length}/${rows.length}`;
  }
}

// -- formulas from sentences --------------------------------------------------------

/** «suma de precio», «precio por cantidad», «si total > 100 entonces "caro" si no
 * "barato"» → a formula the parser understands. Returns '' when it cannot. */
export function naturalFormula(sentence: string, table: TableData): string {
  const s = fold(sentence).trim().replace(/[¿?.!]/g, '');
  const col = (name: string) => {
    const n = fold(name).trim();
    const c = table.columns.find((x) => fold(x.name) === n) || table.columns.find((x) => fold(x.name).startsWith(n) || n.startsWith(fold(x.name)));
    return c ? `{${c.name}}` : '';
  };
  const agg: Array<[RegExp, string]> = [
    [/^(la )?(suma|total|sumar)( de| del)? (.+)$/, 'SUMA'],
    [/^(el )?(promedio|media)( de| del)? (.+)$/, 'PROMEDIO'],
    [/^(el )?(maximo|mayor)( de| del)? (.+)$/, 'MAX'],
    [/^(el )?(minimo|menor)( de| del)? (.+)$/, 'MIN'],
    [/^(cuantos|cuantas|contar|numero de|cantidad de) (.+)$/, 'CONTAR'],
  ];
  for (const [re, fn] of agg) {
    const m = re.exec(s);
    if (m) {
      const c = col(m[m.length - 1]);
      if (c) return `=${fn}(${c})`;
    }
  }
  const cond = /^si (.+?) (mayor que|menor que|igual a|es|>|<|=) (.+?) entonces (.+?) si no (.+)$/.exec(s);
  if (cond) {
    const a = col(cond[1]);
    const op = { 'mayor que': '>', 'menor que': '<', 'igual a': '=', es: '=', '>': '>', '<': '<', '=': '=' }[cond[2]];
    const lit = (x: string) => (/^-?\d+([.,]\d+)?$/.test(x.trim()) ? x.trim().replace(',', '.') : col(x) || `"${x.replace(/"/g, '').trim()}"`);
    if (a && op) return `=SI(${a} ${op} ${lit(cond[3])}, ${lit(cond[4])}, ${lit(cond[5])})`;
  }
  const bin = /^(.+?) (por|multiplicado por|x|\*|mas|\+|menos|-|entre|dividido entre|dividido por|\/) (.+)$/.exec(s);
  if (bin) {
    const ops: Record<string, string> = { por: '*', 'multiplicado por': '*', x: '*', '*': '*', mas: '+', '+': '+', menos: '-', '-': '-', entre: '/', 'dividido entre': '/', 'dividido por': '/', '/': '/' };
    const a = col(bin[1]);
    const b = /^\d+([.,]\d+)?%?$/.test(bin[3]) ? bin[3].replace(',', '.').replace(/(\d+(\.\d+)?)%/, '($1/100)') : col(bin[3]);
    if (a && b) return `=${a} ${ops[bin[2]]} ${b}`;
  }
  const pct = /^(\d+([.,]\d+)?) ?% (de|del) (.+)$/.exec(s);
  if (pct) {
    const c = col(pct[4]);
    if (c) return `=${c} * ${pct[1].replace(',', '.')} / 100`;
  }
  return '';
}

// -- projects: dependencies, schedule, risk ---------------------------------------------

const DAY = 86_400_000;

export function findColumn(table: TableData, ...names: string[]): Column | undefined {
  const wanted = names.map(fold);
  return table.columns.find((c) => wanted.some((w) => fold(c.name).startsWith(w)));
}

export interface Planned {
  row: Row;
  name: string;
  start: number;
  end: number;
  days: number;
  deps: string[]; // row ids
  critical: boolean;
  slack: number; // days it can slip without moving the end
  done: boolean;
}

export interface Schedule {
  tasks: Planned[];
  end: number;
  cycle: string[]; // names in a dependency loop ([] when none)
}

function dayOf(v: string | undefined): number | null {
  if (!v || !/^\d{4}-\d{2}-\d{2}/.test(v)) return null;
  const t = Date.parse(`${v.slice(0, 10)}T00:00:00`);
  return Number.isFinite(t) ? t : null;
}

export function isDone(table: TableData, row: Row): boolean {
  const status = findColumn(table, 'estado', 'status');
  const check = table.columns.find((c) => c.type === 'checkbox');
  const s = status ? fold(row.cells[status.id] || '') : '';
  return /^(hecho|terminad|complet|listo|done)/.test(s) || (check ? row.cells[check.id] === 'true' : false);
}

/** Earliest start/finish from dependencies («Depende de»: names of other
 * rows) and durations («Duración», days), the critical path and the slack. */
export function schedule(table: TableData, now = Date.now()): Schedule {
  const first = table.columns[0];
  const depCol = findColumn(table, 'depende', 'dependencias', 'despues de', 'después de', 'bloqueado por');
  const durCol = findColumn(table, 'duracion', 'duración', 'dias', 'días', 'estimacion', 'estimación');
  const startCol = findColumn(table, 'inicio', 'empieza', 'start');
  const dueCol = findColumn(table, 'fecha', 'entrega', 'vence', 'fin', 'deadline', 'plazo');
  const rows = table.rows.filter((r) => !r.archived);
  const byName = new Map(rows.map((r) => [fold((r.cells[first.id] || '').trim()), r]));
  const deps = new Map<string, string[]>();
  for (const r of rows) {
    const names = depCol ? (r.cells[depCol.id] || '').split(',').map((x) => fold(x.trim())).filter(Boolean) : [];
    deps.set(r.id, names.map((n) => byName.get(n)?.id).filter((x): x is string => !!x && x !== r.id));
  }
  // topological order (Kahn); what is left is a loop
  const indeg = new Map(rows.map((r) => [r.id, deps.get(r.id)!.length]));
  const order: Row[] = [];
  const queue = rows.filter((r) => indeg.get(r.id) === 0);
  const next = new Map<string, string[]>();
  for (const r of rows) for (const d of deps.get(r.id)!) next.set(d, [...(next.get(d) || []), r.id]);
  while (queue.length) {
    const r = queue.shift()!;
    order.push(r);
    for (const n of next.get(r.id) || []) {
      indeg.set(n, indeg.get(n)! - 1);
      if (indeg.get(n) === 0) queue.push(rows.find((x) => x.id === n)!);
    }
  }
  const cycle = rows.filter((r) => !order.includes(r)).map((r) => r.cells[first.id] || '?');
  const today = Math.floor(now / DAY) * DAY;
  const plan = new Map<string, Planned>();
  for (const r of order) {
    const done = isDone(table, r);
    // finished work takes no more time; the rest starts as soon as it can
    const days = done ? 0 : Math.max(durCol ? toNumber(r.cells[durCol.id]) ?? 1 : 1, 0);
    const own = startCol ? dayOf(r.cells[startCol.id]) : null;
    const after = Math.max(today, ...deps.get(r.id)!.map((d) => plan.get(d)?.end ?? today));
    const start = Math.max(after, own ?? after);
    plan.set(r.id, { row: r, name: r.cells[first.id] || '', start, end: start + days * DAY, days, deps: deps.get(r.id)!, critical: false, slack: 0, done });
  }
  const end = Math.max(today, ...[...plan.values()].map((p) => p.end));
  // latest finish, backwards
  const late = new Map<string, number>();
  for (const r of [...order].reverse()) {
    const succ = next.get(r.id) || [];
    const lf = succ.length ? Math.min(...succ.map((s) => (late.get(s) ?? end) - (plan.get(s)?.days ?? 0) * DAY)) : end;
    late.set(r.id, lf);
    const p = plan.get(r.id)!;
    p.slack = Math.round((lf - p.end) / DAY);
    p.critical = p.slack <= 0;
  }
  return { tasks: order.map((r) => plan.get(r.id)!), end, cycle };
}

export interface Risk {
  name: string;
  level: 'alto' | 'medio' | 'bajo';
  reasons: string[];
}

export interface ProjectRisk {
  progress: number; // 0..1 of tasks done
  predictedEnd: number;
  dueEnd: number | null; // the latest due date set by hand
  delayDays: number; // predicted end minus the due end (≤0 is on time)
  budget: { planned: number; spent: number; forecast: number } | null;
  risks: Risk[];
  needs: string[]; // what the project will need soon (people, money, decisions)
}

/** Predict delays and budget, and say which tasks are at risk and why. */
export function projectRisk(table: TableData, now = Date.now()): ProjectRisk {
  const plan = schedule(table, now);
  const dueCol = findColumn(table, 'fecha', 'entrega', 'vence', 'fin', 'deadline', 'plazo');
  const ownerCol = findColumn(table, 'responsable', 'persona', 'asignado', 'quien', 'quién', 'owner');
  const budgetCol = findColumn(table, 'presupuesto', 'budget');
  const spentCol = findColumn(table, 'gastado', 'gasto', 'coste', 'costo', 'spent');
  const progressCol = findColumn(table, 'progreso', 'avance', '%');
  const rows = table.rows.filter((r) => !r.archived);
  const done = rows.filter((r) => isDone(table, r));
  const dues = rows.map((r) => (dueCol ? dayOf(r.cells[dueCol.id]) : null)).filter((d): d is number => d !== null);
  const dueEnd = dues.length ? Math.max(...dues) : null;
  const pending = plan.tasks.filter((t) => !t.done && t.name.trim());
  const predictedEnd = pending.length ? Math.max(...pending.map((t) => t.end)) : now;
  // the worst lateness of any open task against its own date
  const lateness = pending
    .map((t) => (dueCol ? dayOf(t.row.cells[dueCol.id]) : null) !== null ? Math.ceil((t.end - dayOf(t.row.cells[dueCol!.id])!) / DAY) : null)
    .filter((d): d is number => d !== null);
  const delayDays = lateness.length ? Math.max(...lateness) : 0;
  const risks: Risk[] = [];
  const loads = new Map<string, number>();
  for (const t of pending) {
    const reasons: string[] = [];
    const due = dueCol ? dayOf(t.row.cells[dueCol.id]) : null;
    if (due !== null && due < now) reasons.push('vencida');
    else if (due !== null && t.end > due + DAY) reasons.push(`terminaría ${Math.ceil((t.end - due) / DAY)} días tarde`);
    const late = t.deps.map((d) => plan.tasks.find((x) => x.row.id === d)).filter((d) => d && !d.done && dueCol && (dayOf(d.row.cells[dueCol.id]) ?? Infinity) < now);
    if (late.length) reasons.push(`espera a «${late[0]!.name}», que va tarde`);
    if (t.critical && t.days > 0) reasons.push('en la ruta crítica');
    if (progressCol && due !== null) {
      const p = (toNumber((t.row.cells[progressCol.id] || '').replace('%', '')) ?? 0) / 100;
      const window = Math.max(due - t.start, DAY);
      const expected = Math.min(Math.max((now - t.start) / window, 0), 1);
      if (expected - p > 0.25) reasons.push(`lleva ${Math.round(p * 100)} % y debería ir por ${Math.round(expected * 100)} %`);
    }
    if (ownerCol) {
      const who = (t.row.cells[ownerCol.id] || '').trim();
      if (!who) reasons.push('sin responsable');
      else loads.set(who, (loads.get(who) || 0) + 1);
    }
    if (reasons.length) {
      const high = reasons.some((r) => r === 'vencida' || r.startsWith('terminaría') || r.startsWith('espera'));
      risks.push({ name: t.name, level: high ? 'alto' : reasons.length > 1 ? 'medio' : 'bajo', reasons });
    }
  }
  let budget: ProjectRisk['budget'] = null;
  if (budgetCol || spentCol) {
    const sum = (c?: Column) => (c ? rows.reduce((a, r) => a + (toNumber(r.cells[c.id]) ?? 0), 0) : 0);
    const planned = sum(budgetCol);
    const spent = sum(spentCol);
    const progress = rows.length ? done.length / rows.length : 0;
    const forecast = progress > 0.05 ? spent / progress : spent;
    budget = { planned, spent, forecast };
  }
  const needs: string[] = [];
  const busiest = [...loads].sort((a, b) => b[1] - a[1])[0];
  if (busiest && busiest[1] >= 4) needs.push(`${busiest[0]} tiene ${busiest[1]} tareas abiertas: reparta o priorice`);
  if (budget && budget.planned && budget.forecast > budget.planned * 1.05)
    needs.push(`el presupuesto se pasaría en ${Math.round(budget.forecast - budget.planned).toLocaleString('es')}`);
  if (plan.cycle.length) needs.push(`dependencias en círculo: ${plan.cycle.slice(0, 3).join(', ')}`);
  if (delayDays > 0) needs.push(`mover la entrega ${delayDays} días o recortar alcance en la ruta crítica`);
  const order = { alto: 0, medio: 1, bajo: 2 };
  risks.sort((a, b) => order[a.level] - order[b.level]);
  return { progress: rows.length ? done.length / rows.length : 0, predictedEnd, dueEnd, delayDays, budget, risks, needs };
}

// -- wikis: what to verify ---------------------------------------------------------------

export interface Staleness {
  score: number; // 0 fresh … 1 surely outdated
  reasons: string[];
}

export function staleness(page: Page, pages: Page[], now = Date.now()): Staleness {
  const reasons: string[] = [];
  let score = 0;
  const verified = page.verifiedAt || page.updatedAt;
  const ageDays = (now - verified) / DAY;
  if (ageDays > 90) {
    score += Math.min(0.5, ageDays / 360);
    reasons.push(`sin revisar hace ${Math.round(ageDays)} días`);
  }
  const text = plainText(page, 20000);
  const years = (text.match(/\b(20\d{2})\b/g) || []).map(Number);
  const thisYear = new Date(now).getFullYear();
  if (years.length && Math.max(...years) < thisYear - 1) {
    score += 0.2;
    reasons.push(`habla de ${Math.max(...years)}`);
  }
  const titles = new Map(pages.map((p) => [fold(p.title), p]));
  const links = [...text.matchAll(/\[\[([^\]]+)\]\]/g)].map((m) => m[1]);
  const broken = links.filter((l) => !titles.has(fold(l)));
  if (broken.length) {
    score += 0.2;
    reasons.push(`enlace roto: ${broken[0]}`);
  }
  const newer = links.map((l) => titles.get(fold(l))).filter((p) => p && p.updatedAt > verified + DAY);
  if (newer.length) {
    score += 0.15;
    reasons.push(`«${newer[0]!.title}» cambió después`);
  }
  if (/\b(pr[oó]ximamente|esta semana|este mes|todav[ií]a no|por ahora|TODO|pendiente)\b/i.test(text) && ageDays > 30) {
    score += 0.15;
    reasons.push('dice «pronto» o «por ahora» y ya pasó tiempo');
  }
  return { score: Math.min(1, score), reasons };
}

// -- automations ---------------------------------------------------------------------------

export type CondOp = 'is' | 'not' | 'contains' | 'gt' | 'lt' | 'empty' | 'filled' | 'changed';

export interface Condition {
  column: string;
  op: CondOp;
  value?: string;
}

export type RuleAction =
  | { kind: 'set'; column: string; value: string }
  | { kind: 'todo'; text: string }
  | { kind: 'notify'; text: string }
  | { kind: 'archive' }
  | { kind: 'webhook'; url: string };

export interface Rule {
  id: string;
  name: string;
  on: boolean;
  any: boolean; // OR instead of AND
  when: Condition[];
  then: RuleAction[];
}

export function matches(table: TableData, cond: Condition, row: Row, before?: Row): boolean {
  const raw = row.cells[cond.column] ?? '';
  const v = fold(raw.trim());
  const want = fold((cond.value ?? '').trim());
  switch (cond.op) {
    case 'is':
      return v === want;
    case 'not':
      return v !== want;
    case 'contains':
      return v.includes(want);
    case 'gt':
    case 'lt': {
      const a = toNumber(raw);
      const b = toNumber(cond.value ?? '');
      if (a !== null && b !== null) return cond.op === 'gt' ? a > b : a < b;
      return cond.op === 'gt' ? v > want : v < want; // dates as text
    }
    case 'empty':
      return !v;
    case 'filled':
      return !!v;
    case 'changed':
      return !!before && (before.cells[cond.column] ?? '') !== raw;
  }
  void table;
  return false;
}

export function ruleFires(table: TableData, rule: Rule, row: Row, before?: Row): boolean {
  if (!rule.on || !rule.when.length) return false;
  const results = rule.when.map((c) => matches(table, c, row, before));
  const now = rule.any ? results.some(Boolean) : results.every(Boolean);
  if (!now || !before) return now;
  // fire on the change into the condition, not on every later edit
  const was = rule.when.map((c) => (c.op === 'changed' ? false : matches(table, c, before)));
  return !(rule.any ? was.some(Boolean) : was.every(Boolean));
}

export interface Effects {
  table: TableData;
  todos: string[];
  notes: string[];
  webhooks: Array<{ url: string; row: Record<string, string> }>;
}

/** Run the rules on a row that changed; returns the table after the actions. */
export function applyRules(table: TableData, rules: Rule[], rowId: string, before?: Row): Effects {
  let t = table;
  const out: Effects = { table, todos: [], notes: [], webhooks: [] };
  const fill = (text: string, row: Row) => text.replace(/\{([^}]+)\}/g, (_m, name) => {
    const c = t.columns.find((x) => fold(x.name) === fold(name));
    return c ? row.cells[c.id] || '' : '';
  });
  for (const rule of rules) {
    const row = t.rows.find((r) => r.id === rowId);
    if (!row || !ruleFires(t, rule, row, before)) continue;
    for (const a of rule.then) {
      if (a.kind === 'set') t = { ...t, rows: t.rows.map((r) => (r.id === rowId ? { ...r, cells: { ...r.cells, [a.column]: fill(a.value, r) } } : r)) };
      else if (a.kind === 'archive') t = { ...t, rows: t.rows.map((r) => (r.id === rowId ? { ...r, archived: true } : r)) };
      else if (a.kind === 'todo') out.todos.push(fill(a.text, row));
      else if (a.kind === 'notify') out.notes.push(fill(a.text, row));
      else if (a.kind === 'webhook' && /^https:\/\//.test(a.url))
        out.webhooks.push({ url: a.url, row: Object.fromEntries(t.columns.map((c) => [c.name, row.cells[c.id] || ''])) });
    }
  }
  out.table = t;
  return out;
}

// -- forms ------------------------------------------------------------------------------------

export interface FormField {
  column: string;
  label?: string;
  required?: boolean;
  showIf?: Condition | null;
}

export interface FormSpec {
  table: string; // block id of the table it fills
  title: string;
  fields: FormField[];
  thanks?: string;
}

export function visibleFields(spec: FormSpec, table: TableData, values: Record<string, string>): FormField[] {
  const row: Row = { id: 'draft', cells: values };
  return spec.fields.filter((f) => table.columns.some((c) => c.id === f.column) && (!f.showIf || matches(table, f.showIf, row)));
}

export function submitForm(spec: FormSpec, table: TableData, values: Record<string, string>): { table?: TableData; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const shown = visibleFields(spec, table, values);
  for (const f of shown) {
    const col = table.columns.find((c) => c.id === f.column)!;
    const v = (values[f.column] || '').trim();
    if (f.required && !v) errors[f.column] = 'Obligatorio';
    else if (v && col.type === 'number' && toNumber(v) === null) errors[f.column] = 'Un número';
    else if (v && col.type === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) errors[f.column] = 'Un correo válido';
    else if (v && col.type === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(v)) errors[f.column] = 'Una fecha';
  }
  if (Object.keys(errors).length) return { errors };
  const cells = Object.fromEntries(table.columns.map((c) => [c.id, shown.some((f) => f.column === c.id) ? (values[c.id] || '').trim() : '']));
  return { table: { ...table, rows: [...table.rows, { id: newId('r'), cells }] }, errors };
}

// -- buttons ----------------------------------------------------------------------------------

export type ButtonStep =
  | { kind: 'insert'; text: string; as?: Block['type'] }
  | { kind: 'row'; table: string; values: Record<string, string> }
  | { kind: 'check'; all: boolean }
  | { kind: 'ai'; prompt: string }
  | { kind: 'open'; page: string };

export interface ButtonSpec {
  label: string;
  steps: ButtonStep[];
}

/** The steps that need no model, applied to the page (ai and open steps are
 * returned for the caller to run, in order). */
export function runButton(page: Page, at: string, spec: ButtonSpec, now = new Date()): { page: Page; pending: ButtonStep[] } {
  let blocks = [...page.blocks];
  const pending: ButtonStep[] = [];
  const stamp = (s: string) => s.replace(/\{hoy\}/gi, now.toLocaleDateString('es')).replace(/\{hora\}/gi, now.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' }));
  for (const step of spec.steps) {
    if (step.kind === 'insert') {
      const i = blocks.findIndex((b) => b.id === at);
      const nb: Block = { id: newId('b'), type: step.as || 'text', text: stamp(step.text), ...(step.as === 'todo' ? { checked: false } : {}) };
      blocks = [...blocks.slice(0, i + 1), nb, ...blocks.slice(i + 1)];
    } else if (step.kind === 'row') {
      blocks = blocks.map((b) =>
        b.id === step.table && b.table ? { ...b, table: { ...b.table, rows: [...b.table.rows, { id: newId('r'), cells: Object.fromEntries(Object.entries(step.values).map(([k, v]) => [k, stamp(v)])) }] } } : b,
      );
    } else if (step.kind === 'check') {
      blocks = blocks.map((b) => (b.type === 'todo' ? { ...b, checked: step.all } : b));
    } else pending.push(step);
  }
  return { page: { ...page, blocks }, pending };
}

// -- templates that learn -------------------------------------------------------------------------

/** What people actually do with pages made from a template: headings added
 * in at least half of them join it; template headings deleted in at least
 * half leave it. */
export function evolveTemplate(base: Block[], uses: Page[]): { blocks: Block[]; added: string[]; removed: string[] } {
  if (uses.length < 2) return { blocks: base, added: [], removed: [] };
  const isHead = (b: Block) => b.type === 'h1' || b.type === 'h2' || b.type === 'h3';
  const baseHeads = base.filter(isHead).map((b) => fold(b.text));
  const counts = new Map<string, { n: number; block: Block }>();
  for (const p of uses) {
    for (const b of new Map(p.blocks.filter(isHead).map((b) => [fold(b.text), b])).values()) {
      const k = fold(b.text);
      if (!k || baseHeads.includes(k)) continue;
      counts.set(k, { n: (counts.get(k)?.n || 0) + 1, block: b });
    }
  }
  const half = uses.length / 2;
  const added = [...counts.values()].filter((c) => c.n >= half).map((c) => c.block.text);
  const removed = base
    .filter(isHead)
    .filter((h) => uses.filter((p) => !p.blocks.some((b) => isHead(b) && fold(b.text) === fold(h.text))).length >= half)
    .map((h) => h.text);
  const kept = base.filter((b, i) => {
    if (!isHead(b) || !removed.includes(b.text)) {
      // drop the empty block that followed a removed heading
      const prev = base[i - 1];
      return !(prev && isHead(prev) && removed.includes(prev.text) && !b.text);
    }
    return false;
  });
  const extra = added.flatMap((text) => [{ id: newId('b'), type: 'h2' as const, text }, { id: newId('b'), type: 'text' as const, text: '' }]);
  return { blocks: [...kept, ...extra], added, removed };
}

// -- history: visual Git for documents ----------------------------------------------------------

export type DiffOp = { kind: 'same' | 'added' | 'removed'; block: Block } | { kind: 'changed'; block: Block; before: Block; words: WordOp[] };
export type WordOp = { kind: 'same' | 'added' | 'removed'; text: string };

function lcs<T>(a: T[], b: T[], eq: (x: T, y: T) => boolean): Array<[number, number]> {
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = eq(a[i], b[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const pairs: Array<[number, number]> = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (eq(a[i], b[j])) {
      pairs.push([i, j]);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  return pairs;
}

export function wordDiff(before: string, after: string): WordOp[] {
  const a = before.split(/(\s+)/).filter(Boolean);
  const b = after.split(/(\s+)/).filter(Boolean);
  if (a.length * b.length > 250_000) return [{ kind: 'removed', text: before }, { kind: 'added', text: after }];
  const pairs = lcs(a, b, (x, y) => x === y);
  const out: WordOp[] = [];
  let i = 0;
  let j = 0;
  const push = (kind: WordOp['kind'], text: string) => {
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.text += text;
    else out.push({ kind, text });
  };
  for (const [pi, pj] of [...pairs, [a.length, b.length] as [number, number]]) {
    while (i < pi) push('removed', a[i++]);
    while (j < pj) push('added', b[j++]);
    if (pi < a.length) push('same', a[pi]);
    i = pi + 1;
    j = pj + 1;
  }
  return out;
}

function blockKey(b: Block): string {
  return `${b.type}|${b.text}|${b.checked ?? ''}|${JSON.stringify(b.table ?? b.chart ?? b.mind ?? b.media ?? '')}`;
}

/** Block by block: what was added, removed and changed (word by word). */
export function blockDiff(before: Block[], after: Block[]): DiffOp[] {
  const pairs = lcs(before, after, (x, y) => x.id === y.id);
  const out: DiffOp[] = [];
  let i = 0;
  let j = 0;
  for (const [pi, pj] of [...pairs, [before.length, after.length] as [number, number]]) {
    while (i < pi) out.push({ kind: 'removed', block: before[i++] });
    while (j < pj) out.push({ kind: 'added', block: after[j++] });
    if (pi < before.length) {
      const a = before[pi];
      const b = after[pj];
      out.push(blockKey(a) === blockKey(b) ? { kind: 'same', block: b } : { kind: 'changed', block: b, before: a, words: wordDiff(a.text, b.text) });
    }
    i = pi + 1;
    j = pj + 1;
  }
  return out;
}

// -- teams: three-way merge ------------------------------------------------------------------------

export interface Merged {
  blocks: Block[];
  conflicts: number; // blocks both sides changed differently (both kept)
}

/** Merge two edits of the same page made from a common base: changes to
 * different blocks both stay; the same block changed both ways keeps theirs
 * and adds ours right after it, marked, so nothing is lost. */
export function merge3(base: Block[], mine: Block[], theirs: Block[]): Merged {
  const B = new Map(base.map((b) => [b.id, b]));
  const M = new Map(mine.map((b) => [b.id, b]));
  const T = new Map(theirs.map((b) => [b.id, b]));
  const changed = (x?: Block, y?: Block) => !!x && !!y && blockKey(x) !== blockKey(y);
  let conflicts = 0;
  const out: Block[] = [];
  const placed = new Set<string>();
  // Their order is the backbone; our new blocks go after the block that
  // preceded them in our copy.
  const myAfter = new Map<string, Block[]>();
  let prev = '';
  for (const b of mine) {
    if (!B.has(b.id) && !T.has(b.id)) myAfter.set(prev, [...(myAfter.get(prev) || []), b]);
    prev = b.id;
  }
  const emit = (b: Block) => {
    if (placed.has(b.id)) return;
    placed.add(b.id);
    out.push(b);
    for (const n of myAfter.get(b.id) || []) emit(n);
  };
  for (const n of myAfter.get('') || []) emit(n);
  for (const t of theirs) {
    const b = B.get(t.id);
    const m = M.get(t.id);
    if (b && !m) {
      // we deleted it: keep it only if they changed it meanwhile
      if (changed(b, t)) emit(t);
      continue;
    }
    if (!b || !m) {
      emit(t);
      continue;
    }
    const iChanged = changed(b, m);
    const theyChanged = changed(b, t);
    if (iChanged && theyChanged && changed(m, t)) {
      conflicts++;
      emit(t);
      const copy = { ...m, id: newId('b'), conflict: true };
      placed.add(copy.id);
      out.push(copy);
      for (const n of myAfter.get(m.id) || []) emit(n);
    } else emit(iChanged ? m : t);
  }
  // our edits to blocks they deleted come back (they did not see them)
  for (const m of mine) if (!placed.has(m.id) && B.has(m.id) && !T.has(m.id) && changed(B.get(m.id), m)) emit(m);
  return { blocks: out, conflicts };
}

// -- dashboards ------------------------------------------------------------------------------------------

export interface Kpi {
  label: string;
  value: string;
  hint?: string;
}

export function kpis(table: TableData, now = Date.now()): Kpi[] {
  const rows = table.rows.filter((r) => !r.archived);
  const out: Kpi[] = [{ label: 'Filas', value: String(rows.length) }];
  const doneCount = rows.filter((r) => isDone(table, r)).length;
  if (findColumn(table, 'estado', 'status') || table.columns.some((c) => c.type === 'checkbox'))
    out.push({ label: 'Hecho', value: `${rows.length ? Math.round((doneCount / rows.length) * 100) : 0} %` });
  const due = findColumn(table, 'fecha', 'entrega', 'vence', 'plazo');
  if (due) {
    const late = rows.filter((r) => !isDone(table, r) && (dayOf(r.cells[due.id]) ?? Infinity) < now).length;
    out.push({ label: 'Vencidas', value: String(late) });
  }
  for (const c of table.columns.filter((c) => c.type === 'number').slice(0, 2)) {
    const sum = rows.reduce((a, r) => a + (toNumber(r.cells[c.id]) ?? 0), 0);
    out.push({ label: c.name, value: sum.toLocaleString('es', { maximumFractionDigits: 2 }) });
  }
  return out;
}

// -- one calendar for everything ---------------------------------------------------------------------------

export interface DatedItem {
  date: string; // YYYY-MM-DD
  title: string;
  pageId: string;
  where: string; // page title
  done: boolean;
}

const ISO_IN_TEXT = /\b(\d{4}-\d{2}-\d{2})\b/;

/** Every date in every page: table rows with a date column, and tasks or
 * lines that mention a date. */
export function datedItems(pages: Page[]): DatedItem[] {
  const out: DatedItem[] = [];
  for (const p of pages) {
    if (p.archived || p.sealed) continue;
    for (const b of p.blocks) {
      if (b.table) {
        const first = b.table.columns[0];
        for (const c of b.table.columns.filter((c) => c.type === 'date'))
          for (const r of b.table.rows.filter((r) => !r.archived && /^\d{4}-\d{2}-\d{2}/.test(r.cells[c.id] || '')))
            out.push({ date: r.cells[c.id].slice(0, 10), title: r.cells[first.id] || c.name, pageId: p.id, where: p.title, done: isDone(b.table, r) });
      } else if (b.text) {
        const m = ISO_IN_TEXT.exec(b.text);
        if (m) out.push({ date: m[1], title: b.text.replace(m[1], '').replace(/\s+/g, ' ').trim().slice(0, 80) || p.title, pageId: p.id, where: p.title, done: !!b.checked });
      }
    }
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}
