// Spreadsheet formulas for Workspace tables: a cell that starts with «=» is
// computed. No eval: a small tokenizer and parser, safe on any input.
//
//   =A1 + B2            cells: column letter (A = first column) and row number
//   =SUM(C1:C9)         ranges; =SUM(C:C) is the whole column
//   ={Precio} * {Cantidad}   a column by name: this row's value
//   =SUMA({Cantidad})   inside SUM/AVG/MIN/MAX/COUNT a named column is the
//                       whole column (without the cell being computed, so a
//                       «total» row in the same column works)
//   =SI({Cantidad} > 10, "mucho", "poco")    Spanish and English names
//
// Cell values accept «1234.5», «1234,5» and «1.234,5»; inside a formula the
// decimal point is «.» and arguments are separated by «,» or «;». Errors: #ERROR,
// #REF (a missing cell or column), #DIV/0 and #CICLO (a loop).

import type { TableData } from './model';

type Value = number | string | boolean;
type Node =
  | { k: 'num'; v: number }
  | { k: 'str'; v: string }
  | { k: 'bool'; v: boolean }
  | { k: 'cell'; col: number; row: number }
  | { k: 'range'; c1: number; r1: number; c2: number; r2: number }
  | { k: 'colref'; name: string }
  | { k: 'un'; op: string; a: Node }
  | { k: 'bin'; op: string; a: Node; b: Node }
  | { k: 'call'; name: string; args: Node[] };

export class FormulaError extends Error {
  constructor(public code: string) {
    super(code);
  }
}

// -- numbers ---------------------------------------------------------------------
export function toNumber(raw: string | number | boolean | undefined | null): number | null {
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null;
  if (typeof raw === 'boolean') return raw ? 1 : 0;
  if (raw === undefined || raw === null) return null;
  let s = String(raw).trim().replace(/\s/g, '').replace(/[€$%]/g, '');
  if (!s) return null;
  if (s.includes('.') && s.includes(',')) s = s.replace(/\./g, '').replace(',', '.');
  else if (s.includes(',')) s = s.replace(',', '.');
  if (!/^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(s)) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function letterIndex(letters: string): number {
  let n = 0;
  for (const ch of letters.toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n - 1;
}

export function columnLetter(index: number): string {
  let s = '';
  let n = index + 1;
  while (n > 0) {
    const r = (n - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

// -- tokenizer -------------------------------------------------------------------
type Tok = { t: 'num' | 'str' | 'id' | 'op' | 'col' | 'cell' | 'range' | '(' | ')' | ',' | 'end'; v: string };

function tokenize(src: string): Tok[] {
  const out: Tok[] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (/\s/.test(c)) {
      i++;
      continue;
    }
    if (c === '"') {
      let j = i + 1;
      let s = '';
      while (j < src.length && src[j] !== '"') s += src[j++];
      if (j >= src.length) throw new FormulaError('#ERROR');
      out.push({ t: 'str', v: s });
      i = j + 1;
      continue;
    }
    if (c === '{') {
      const j = src.indexOf('}', i);
      if (j < 0) throw new FormulaError('#ERROR');
      out.push({ t: 'col', v: src.slice(i + 1, j).trim() });
      i = j + 1;
      continue;
    }
    const range = /^([A-Za-z]{1,2})(\d+)?:([A-Za-z]{1,2})(\d+)?/.exec(src.slice(i));
    if (range && (range[2] ? range[4] : !range[4])) {
      out.push({ t: 'range', v: range[0] });
      i += range[0].length;
      continue;
    }
    const cellRef = /^([A-Za-z]{1,2})(\d+)(?![\w(])/.exec(src.slice(i));
    if (cellRef) {
      out.push({ t: 'cell', v: cellRef[0] });
      i += cellRef[0].length;
      continue;
    }
    // Inside a formula «.» is the decimal point; «,» and «;» separate
    // arguments (cell values may still use «1234,5»).
    const num = /^(\d+(\.\d+)?|\.\d+)/.exec(src.slice(i));
    if (num) {
      out.push({ t: 'num', v: num[0] });
      i += num[0].length;
      continue;
    }
    const id = /^[A-Za-zÁÉÍÓÚÑáéíóúñ_][\wÁÉÍÓÚÑáéíóúñ.]*/.exec(src.slice(i));
    if (id) {
      out.push({ t: 'id', v: id[0] });
      i += id[0].length;
      continue;
    }
    const op = /^(<=|>=|<>|!=|==|[-+*/^%&=<>])/.exec(src.slice(i));
    if (op) {
      out.push({ t: 'op', v: op[0] });
      i += op[0].length;
      continue;
    }
    if (c === '(' || c === ')' || c === ',' || c === ';') {
      out.push({ t: c === ';' ? ',' : (c as '(' | ')' | ','), v: c });
      i++;
      continue;
    }
    throw new FormulaError('#ERROR');
  }
  out.push({ t: 'end', v: '' });
  return out;
}

// -- parser (precedence climbing) -----------------------------------------------
const BINARY: Record<string, number> = {
  '=': 1, '==': 1, '<>': 1, '!=': 1, '<': 1, '>': 1, '<=': 1, '>=': 1,
  '&': 2,
  '+': 3, '-': 3,
  '*': 4, '/': 4, '%': 4,
  '^': 5,
};

function parse(src: string): Node {
  const toks = tokenize(src);
  let p = 0;
  const peek = () => toks[p];
  const next = () => toks[p++];

  function primary(): Node {
    const tok = next();
    if (tok.t === 'num') return { k: 'num', v: Number(tok.v) };
    if (tok.t === 'str') return { k: 'str', v: tok.v };
    if (tok.t === 'col') return { k: 'colref', name: tok.v };
    if (tok.t === 'cell') {
      const m = /^([A-Za-z]{1,2})(\d+)$/.exec(tok.v)!;
      return { k: 'cell', col: letterIndex(m[1]), row: Number(m[2]) - 1 };
    }
    if (tok.t === 'range') {
      const m = /^([A-Za-z]{1,2})(\d+)?:([A-Za-z]{1,2})(\d+)?$/.exec(tok.v)!;
      return {
        k: 'range',
        c1: letterIndex(m[1]),
        r1: m[2] ? Number(m[2]) - 1 : 0,
        c2: letterIndex(m[3]),
        r2: m[4] ? Number(m[4]) - 1 : Number.MAX_SAFE_INTEGER,
      };
    }
    if (tok.t === 'op' && (tok.v === '-' || tok.v === '+')) return { k: 'un', op: tok.v, a: expr(5) };
    if (tok.t === '(') {
      const inner = expr(0);
      if (next().t !== ')') throw new FormulaError('#ERROR');
      return inner;
    }
    if (tok.t === 'id') {
      const name = tok.v.toUpperCase();
      if (name === 'TRUE' || name === 'VERDADERO') return { k: 'bool', v: true };
      if (name === 'FALSE' || name === 'FALSO') return { k: 'bool', v: false };
      if (peek().t !== '(') throw new FormulaError('#ERROR');
      next();
      const args: Node[] = [];
      if (peek().t !== ')') {
        for (;;) {
          args.push(expr(0));
          if (peek().t === ',') {
            next();
            continue;
          }
          break;
        }
      }
      if (next().t !== ')') throw new FormulaError('#ERROR');
      return { k: 'call', name, args };
    }
    throw new FormulaError('#ERROR');
  }

  function expr(min: number): Node {
    let left = primary();
    for (;;) {
      const tok = peek();
      if (tok.t !== 'op' || BINARY[tok.v] === undefined || BINARY[tok.v] < min) break;
      next();
      const prec = BINARY[tok.v];
      const right = expr(tok.v === '^' ? prec : prec + 1);
      left = { k: 'bin', op: tok.v, a: left, b: right };
    }
    return left;
  }

  const tree = expr(0);
  if (peek().t !== 'end') throw new FormulaError('#ERROR');
  return tree;
}

// -- evaluation ------------------------------------------------------------------
const ALIASES: Record<string, string> = {
  SUMA: 'SUM', PROMEDIO: 'AVG', AVERAGE: 'AVG', MEDIA: 'AVG', CONTAR: 'COUNT', MINIMO: 'MIN', MAXIMO: 'MAX',
  REDONDEAR: 'ROUND', SI: 'IF', LARGO: 'LEN', MAYUSC: 'UPPER', MINUSC: 'LOWER', HOY: 'TODAY', DIAS: 'DAYS',
  RAIZ: 'SQRT', CONCATENAR: 'CONCAT', Y: 'AND', O: 'OR', NO: 'NOT',
};
const AGGREGATES = new Set(['SUM', 'AVG', 'MIN', 'MAX', 'COUNT']);

interface Ctx {
  table: TableData;
  row: number;
  visiting: Set<string>;
  rows: TableData['rows'];
}

function visibleRows(table: TableData) {
  return table.rows.filter((r) => !r.archived);
}

function columnIndexByName(table: TableData, name: string): number {
  const want = name.trim().toLowerCase();
  return table.columns.findIndex((c) => c.name.trim().toLowerCase() === want);
}

function cellValue(ctx: Ctx, col: number, row: number): Value {
  const column = ctx.table.columns[col];
  const r = ctx.rows[row];
  if (!column || !r) throw new FormulaError('#REF');
  const raw = r.cells[column.id] ?? '';
  if (raw.startsWith('=')) {
    const key = `${col}:${row}`;
    if (ctx.visiting.has(key)) throw new FormulaError('#CICLO');
    ctx.visiting.add(key);
    try {
      return evaluate(parse(raw.slice(1)), { ...ctx, row });
    } finally {
      ctx.visiting.delete(key);
    }
  }
  if (column.type === 'checkbox') return raw === 'true';
  const n = toNumber(raw);
  return n === null ? raw : n;
}

function many(node: Node, ctx: Ctx): Value[] {
  if (node.k === 'range') {
    const out: Value[] = [];
    const whole = node.r2 === Number.MAX_SAFE_INTEGER;
    const r2 = Math.min(node.r2, ctx.rows.length - 1);
    for (let c = Math.min(node.c1, node.c2); c <= Math.max(node.c1, node.c2); c++) {
      for (let r = node.r1; r <= r2; r++) {
        // A whole column leaves out the cell being computed: a «total» row works.
        if (whole && ctx.visiting.has(`${c}:${r}`)) continue;
        out.push(cellValue(ctx, c, r));
      }
    }
    return out;
  }
  if (node.k === 'colref') {
    const col = columnIndexByName(ctx.table, node.name);
    if (col < 0) throw new FormulaError('#REF');
    return ctx.rows.flatMap((_, r) => (ctx.visiting.has(`${col}:${r}`) ? [] : [cellValue(ctx, col, r)]));
  }
  return [evaluate(node, ctx)];
}

function num(v: Value): number {
  if (typeof v === 'number') return v;
  if (typeof v === 'boolean') return v ? 1 : 0;
  const n = toNumber(v);
  if (n === null) {
    if (v === '') return 0;
    throw new FormulaError('#ERROR');
  }
  return n;
}

function text(v: Value): string {
  if (typeof v === 'number') return formatNumber(v);
  if (typeof v === 'boolean') return v ? 'VERDADERO' : 'FALSO';
  return v;
}

function truthy(v: Value): boolean {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'number') return v !== 0;
  return v !== '' && v.toUpperCase() !== 'FALSO' && v.toUpperCase() !== 'FALSE';
}

function dateMs(v: Value): number {
  if (typeof v === 'number') return v * 86_400_000;
  const t = Date.parse(String(v));
  if (Number.isNaN(t)) throw new FormulaError('#ERROR');
  return t;
}

function compare(a: Value, b: Value): number {
  const na = typeof a === 'number' ? a : toNumber(a as string);
  const nb = typeof b === 'number' ? b : toNumber(b as string);
  if (na !== null && nb !== null) return na - nb;
  return text(a).localeCompare(text(b), 'es', { sensitivity: 'base' });
}

function evaluate(node: Node, ctx: Ctx): Value {
  switch (node.k) {
    case 'num':
    case 'str':
    case 'bool':
      return node.v;
    case 'cell':
      return cellValue(ctx, node.col, node.row);
    case 'colref': {
      const col = columnIndexByName(ctx.table, node.name);
      if (col < 0) throw new FormulaError('#REF');
      return cellValue(ctx, col, ctx.row);
    }
    case 'range':
      throw new FormulaError('#ERROR'); // a range alone is not a value
    case 'un': {
      const v = num(evaluate(node.a, ctx));
      return node.op === '-' ? -v : v;
    }
    case 'bin': {
      const a = evaluate(node.a, ctx);
      const b = evaluate(node.b, ctx);
      switch (node.op) {
        case '+':
          return num(a) + num(b);
        case '-':
          return num(a) - num(b);
        case '*':
          return num(a) * num(b);
        case '/': {
          const d = num(b);
          if (d === 0) throw new FormulaError('#DIV/0');
          return num(a) / d;
        }
        case '%': {
          const d = num(b);
          if (d === 0) throw new FormulaError('#DIV/0');
          return num(a) % d;
        }
        case '^':
          return num(a) ** num(b);
        case '&':
          return text(a) + text(b);
        case '=':
        case '==':
          return compare(a, b) === 0;
        case '<>':
        case '!=':
          return compare(a, b) !== 0;
        case '<':
          return compare(a, b) < 0;
        case '>':
          return compare(a, b) > 0;
        case '<=':
          return compare(a, b) <= 0;
        case '>=':
          return compare(a, b) >= 0;
      }
      throw new FormulaError('#ERROR');
    }
    case 'call': {
      const name = ALIASES[node.name] || node.name;
      if (AGGREGATES.has(name)) {
        const values = node.args.flatMap((a) => many(a, ctx));
        const nums = values.map((v) => (typeof v === 'number' ? v : toNumber(text(v)))).filter((v): v is number => v !== null);
        if (name === 'COUNT') return values.filter((v) => text(v) !== '').length;
        if (name === 'SUM') return nums.reduce((s, x) => s + x, 0);
        if (!nums.length) return 0;
        if (name === 'AVG') return nums.reduce((s, x) => s + x, 0) / nums.length;
        if (name === 'MIN') return Math.min(...nums);
        return Math.max(...nums);
      }
      const args = () => node.args.map((a) => evaluate(a, ctx));
      switch (name) {
        case 'ROUND': {
          const [x, d = 0] = args();
          const f = 10 ** num(d);
          return Math.round(num(x) * f) / f;
        }
        case 'ABS':
          return Math.abs(num(args()[0]));
        case 'SQRT': {
          const x = num(args()[0]);
          if (x < 0) throw new FormulaError('#ERROR');
          return Math.sqrt(x);
        }
        case 'IF': {
          if (node.args.length < 2) throw new FormulaError('#ERROR');
          return truthy(evaluate(node.args[0], ctx))
            ? evaluate(node.args[1], ctx)
            : node.args[2]
              ? evaluate(node.args[2], ctx)
              : '';
        }
        case 'AND':
          return args().every(truthy);
        case 'OR':
          return args().some(truthy);
        case 'NOT':
          return !truthy(args()[0]);
        case 'CONCAT':
          return args().map(text).join('');
        case 'LEN':
          return text(args()[0]).length;
        case 'UPPER':
          return text(args()[0]).toUpperCase();
        case 'LOWER':
          return text(args()[0]).toLowerCase();
        case 'TODAY':
          return new Date().toISOString().slice(0, 10);
        case 'DAYS': {
          const [a, b] = args();
          return Math.round((dateMs(a) - dateMs(b)) / 86_400_000);
        }
      }
      throw new FormulaError('#ERROR');
    }
  }
}

export function formatNumber(n: number): string {
  if (Number.isInteger(n)) return String(n);
  return String(Math.round(n * 1e6) / 1e6);
}

export function isFormula(raw: string | undefined): boolean {
  return !!raw && raw.startsWith('=') && raw.length > 1;
}

// What a cell shows: its own text, or its formula's result.
export function computeCell(table: TableData, rowIndex: number, colIndex: number): string {
  const rows = visibleRows(table);
  const column = table.columns[colIndex];
  const row = rows[rowIndex];
  if (!column || !row) return '';
  const raw = row.cells[column.id] ?? '';
  if (!isFormula(raw)) return raw;
  try {
    const key = `${colIndex}:${rowIndex}`;
    const v = evaluate(parse(raw.slice(1)), { table, row: rowIndex, visiting: new Set([key]), rows });
    return text(v);
  } catch (err) {
    return err instanceof FormulaError ? err.code : '#ERROR';
  }
}

export function evaluateFormula(table: TableData, rowIndex: number, source: string): string {
  const rows = visibleRows(table);
  try {
    return text(evaluate(parse(source.replace(/^=/, '')), { table, row: rowIndex, visiting: new Set(), rows }));
  } catch (err) {
    return err instanceof FormulaError ? err.code : '#ERROR';
  }
}
