// The Workspace's data: pages made of blocks, in plain JSON (lossless) with
// a Markdown mirror for portability. Pure functions, no store, no DOM.

export type BlockType =
  | 'text'
  | 'h1'
  | 'h2'
  | 'h3'
  | 'todo'
  | 'bullet'
  | 'number'
  | 'quote'
  | 'callout'
  | 'code'
  | 'divider'
  | 'toggle'
  | 'table'
  | 'chart'
  | 'pomodoro'
  | 'audio'
  | 'image'
  | 'mindmap'
  | 'equation'
  | 'toc'
  | 'bookmark'
  | 'page';

export type ColumnType = 'text' | 'number' | 'select' | 'multi' | 'date' | 'checkbox' | 'url' | 'email' | 'phone';

export interface Column {
  id: string;
  name: string;
  type: ColumnType;
  options?: string[]; // for select / multi
}

export interface Row {
  id: string;
  cells: Record<string, string>;
  archived?: boolean;
  doneAt?: number; // when a status/checkbox column marked it done
}

export interface TableView {
  id: string;
  name: string;
  kind: 'table' | 'board' | 'list' | 'gallery' | 'calendar';
  filter?: { column: string; op: 'is' | 'not' | 'contains' | 'gt' | 'lt'; value: string } | null;
  sort?: { column: string; dir: 'asc' | 'desc' } | null;
  groupBy?: string; // board: a select column
}

export interface TableData {
  columns: Column[];
  rows: Row[];
  views: TableView[];
  view: string;
}

export interface ChartData {
  table: string; // block id of a table on the same page
  kind: 'bar' | 'line' | 'pie';
  x: string; // column id
  y: string; // column id ('' = count)
  agg: 'sum' | 'avg' | 'count';
}

export interface MindNode {
  id: string;
  text: string;
  parent: string | null;
}

export interface Block {
  id: string;
  type: BlockType;
  text: string;
  checked?: boolean;
  open?: boolean; // toggle
  lang?: string; // code
  table?: TableData;
  chart?: ChartData;
  pomodoro?: { work: number; rest: number };
  media?: { file: string; name: string; mime: string }; // audio / image, stored apart
  mind?: MindNode[];
  pageId?: string; // a link to another page
  doneAt?: number; // when a task was ticked
  archived?: boolean; // moved to the page's vault (old finished tasks)
}

export interface Sealed {
  v: 1;
  salt: string; // base64
  iv: string; // base64
  data: string; // base64 AES-GCM ciphertext of the blocks
}

export interface Page {
  id: string;
  title: string;
  icon: string;
  parent: string | null;
  blocks: Block[];
  createdAt: number;
  updatedAt: number;
  openedAt: number;
  rev: number; // the server's revision this copy is based on
  favorite?: boolean;
  archived?: boolean; // in the vault («baúl»): out of lists and search
  tags?: string[];
  sealed?: Sealed | null; // end-to-end encrypted: blocks are empty until unlocked
}

export function newId(prefix = ''): string {
  const bytes = new Uint8Array(9);
  globalThis.crypto.getRandomValues(bytes);
  const raw = Array.from(bytes, (b) => b.toString(36).padStart(2, '0')).join('').slice(0, 14);
  return prefix ? `${prefix}_${raw}` : raw;
}

export function block(type: BlockType, text = '', extra: Partial<Block> = {}): Block {
  const b: Block = { id: newId('b'), type, text, ...extra };
  if (type === 'todo' && b.checked === undefined) b.checked = false;
  if (type === 'toggle' && b.open === undefined) b.open = true;
  if (type === 'table' && !b.table) b.table = emptyTable();
  if (type === 'pomodoro' && !b.pomodoro) b.pomodoro = { work: 25, rest: 5 };
  if (type === 'mindmap' && !b.mind) b.mind = [{ id: newId('n'), text: text || 'Idea central', parent: null }];
  return b;
}

export function emptyTable(): TableData {
  const name: Column = { id: newId('c'), name: 'Nombre', type: 'text' };
  const status: Column = { id: newId('c'), name: 'Estado', type: 'select', options: ['Por hacer', 'En curso', 'Hecho'] };
  const amount: Column = { id: newId('c'), name: 'Cantidad', type: 'number' };
  const view: TableView = { id: newId('v'), name: 'Tabla', kind: 'table' };
  const board: TableView = { id: newId('v'), name: 'Tablero', kind: 'board', groupBy: status.id };
  return {
    columns: [name, status, amount],
    rows: [
      { id: newId('r'), cells: { [name.id]: '', [status.id]: 'Por hacer', [amount.id]: '' } },
    ],
    views: [view, board],
    view: view.id,
  };
}

export function newPage(title = '', parent: string | null = null, blocks?: Block[], now = Date.now()): Page {
  return {
    id: newId('p'),
    title,
    icon: '',
    parent,
    blocks: blocks && blocks.length ? blocks : [block('text')],
    createdAt: now,
    updatedAt: now,
    openedAt: now,
    rev: 0,
    tags: [],
    sealed: null,
  };
}

// -- templates: a good first page instead of a blank one ----------------------
export interface Template {
  key: string;
  name: string;
  description: string;
  icon: string;
  make: () => { title: string; blocks: Block[] };
}

export const TEMPLATES: Template[] = [
  {
    key: 'blank',
    name: 'Página en blanco',
    description: 'Escriba; «/» para insertar bloques.',
    icon: 'file',
    make: () => ({ title: '', blocks: [block('text')] }),
  },
  {
    key: 'meeting',
    name: 'Notas de reunión',
    description: 'Asistentes, puntos, decisiones y tareas.',
    icon: 'users',
    make: () => ({
      title: `Reunión — ${new Date().toLocaleDateString('es')}`,
      blocks: [
        block('callout', 'Recuerde avisar a los asistentes de que está tomando notas.'),
        block('h2', 'Asistentes'),
        block('bullet', ''),
        block('h2', 'Puntos'),
        block('bullet', ''),
        block('h2', 'Decisiones'),
        block('bullet', ''),
        block('h2', 'Tareas'),
        block('todo', ''),
      ],
    }),
  },
  {
    key: 'project',
    name: 'Proyecto',
    description: 'Objetivo, tareas en tabla y tablero, y un gráfico.',
    icon: 'kanban',
    make: () => {
      const table = block('table');
      const chart = block('chart', '', {
        chart: { table: table.id, kind: 'bar', x: table.table!.columns[1].id, y: '', agg: 'count' },
      });
      return {
        title: 'Proyecto nuevo',
        blocks: [block('h2', 'Objetivo'), block('text', ''), block('h2', 'Tareas'), table, chart],
      };
    },
  },
  {
    key: 'journal',
    name: 'Diario',
    description: 'Tres preguntas cortas para cada día.',
    icon: 'book',
    make: () => ({
      title: new Date().toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' }),
      blocks: [
        block('h3', '¿Qué salió bien hoy?'),
        block('text', ''),
        block('h3', '¿Qué aprendí?'),
        block('text', ''),
        block('h3', '¿Qué haré mañana primero?'),
        block('todo', ''),
      ],
    }),
  },
  {
    key: 'focus',
    name: 'Sesión de enfoque',
    description: 'Un pomodoro y la lista de lo que va a hacer.',
    icon: 'timer',
    make: () => ({
      title: 'Enfoque',
      blocks: [block('pomodoro'), block('h3', 'En esta sesión'), block('todo', '')],
    }),
  },
];

// -- text helpers -----------------------------------------------------------------
export function plainText(page: Pick<Page, 'blocks'>, limit = 4000): string {
  const parts: string[] = [];
  for (const b of page.blocks) {
    if (b.text) parts.push(b.text);
    if (b.table) for (const r of b.table.rows) parts.push(Object.values(r.cells).join(' '));
    if (b.mind) parts.push(b.mind.map((n) => n.text).join(' '));
    if (parts.join(' ').length > limit) break;
  }
  return parts.join('\n').slice(0, limit);
}

export function previewLines(page: Page, count = 6): string[] {
  if (page.sealed) return ['Página cifrada'];
  return page.blocks
    .filter((b) => !b.archived)
    .flatMap((b) => {
      if (b.type === 'table') return [`▦ ${b.table?.rows.filter((r) => !r.archived).length ?? 0} filas`];
      if (b.type === 'mindmap') return (b.mind || []).map((n) => n.text);
      if (b.type === 'pomodoro') return [`◷ ${b.pomodoro?.work ?? 25} / ${b.pomodoro?.rest ?? 5} min`];
      if (b.type === 'chart') return ['▥ gráfico'];
      if (b.type === 'divider') return [];
      return [b.text];
    })
    .filter(Boolean)
    .slice(0, count)
    .map((t) => t.slice(0, 120));
}

// [[Título]] mentions in a page's text.
export function mentions(page: Pick<Page, 'blocks'>): string[] {
  const found = new Set<string>();
  for (const b of page.blocks) {
    for (const m of (b.text || '').matchAll(/\[\[([^\]\n]{1,120})\]\]/g)) found.add(m[1].trim());
  }
  return [...found];
}

// -- Markdown: the portable copy ----------------------------------------------------
function cell(value: string): string {
  return (value || '').replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

export function tableMarkdown(t: TableData): string {
  const head = `| ${t.columns.map((c) => cell(c.name)).join(' | ')} |`;
  const rule = `| ${t.columns.map(() => '---').join(' | ')} |`;
  const rows = t.rows.filter((r) => !r.archived).map((r) => `| ${t.columns.map((c) => cell(r.cells[c.id] ?? '')).join(' | ')} |`);
  return [head, rule, ...rows].join('\n');
}

export function toMarkdown(page: Page, titleOf: (id: string) => string = () => ''): string {
  const out: string[] = [`# ${page.title || 'Sin título'}`, ''];
  let n = 0;
  for (const b of page.blocks) {
    if (b.type !== 'number') n = 0;
    switch (b.type) {
      case 'h1':
        out.push(`## ${b.text}`);
        break;
      case 'h2':
        out.push(`### ${b.text}`);
        break;
      case 'h3':
        out.push(`#### ${b.text}`);
        break;
      case 'todo':
        out.push(`- [${b.checked ? 'x' : ' '}] ${b.text}`);
        break;
      case 'bullet':
        out.push(`- ${b.text}`);
        break;
      case 'number':
        n += 1;
        out.push(`${n}. ${b.text}`);
        break;
      case 'quote':
        out.push(`> ${b.text}`);
        break;
      case 'callout':
        out.push(`> **Nota:** ${b.text}`);
        break;
      case 'code':
        out.push(`\`\`\`${b.lang || ''}`, b.text, '```');
        break;
      case 'divider':
        out.push('---');
        break;
      case 'toggle':
        out.push(`<details><summary>${b.text}</summary></details>`);
        break;
      case 'table':
        if (b.table) out.push(tableMarkdown(b.table));
        break;
      case 'chart':
        out.push(`\`\`\`sergio-chart\n${JSON.stringify(b.chart)}\n\`\`\``);
        break;
      case 'pomodoro':
        out.push(`\`\`\`sergio-pomodoro\n${JSON.stringify(b.pomodoro)}\n\`\`\``);
        break;
      case 'mindmap':
        out.push(...mindOutline(b.mind || []));
        break;
      case 'audio':
      case 'image':
        if (b.media) out.push(`[${b.media.name}](files/${b.media.file})`);
        break;
      case 'page':
        out.push(`[[${titleOf(b.pageId || '') || b.text}]]`);
        break;
      case 'equation':
        out.push('$$', b.text, '$$');
        break;
      case 'bookmark':
        if (b.text.trim()) out.push(`<${b.text.trim()}>`);
        break;
      case 'toc':
        out.push(
          ...page.blocks
            .filter((x) => (x.type === 'h1' || x.type === 'h2' || x.type === 'h3') && x.text.trim())
            .map((x) => `${'  '.repeat(Number(x.type[1]) - 1)}- ${x.text}`),
        );
        break;
      default:
        out.push(b.text);
    }
    out.push('');
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd() + '\n';
}

export function mindOutline(nodes: MindNode[]): string[] {
  const lines: string[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const n of nodes.filter((x) => x.parent === parent)) {
      lines.push(`${'  '.repeat(depth)}- ${n.text}`);
      walk(n.id, depth + 1);
    }
  };
  walk(null, 0);
  return lines;
}

// Markdown shortcuts typed at the start of a block: «# », «- », «[] »…
export function shortcut(text: string): { type: BlockType; text: string; checked?: boolean } | null {
  const rules: Array<[RegExp, BlockType, boolean?]> = [
    [/^### /, 'h3'],
    [/^## /, 'h2'],
    [/^# /, 'h1'],
    [/^\[x\] /i, 'todo', true],
    [/^\[ ?\] /, 'todo', false],
    [/^[-*] /, 'bullet'],
    [/^1[.)] /, 'number'],
    [/^> /, 'quote'],
    [/^!> /, 'callout'],
  ];
  for (const [re, type, checked] of rules) {
    if (re.test(text)) return { type, text: text.replace(re, ''), ...(checked !== undefined ? { checked } : {}) };
  }
  if (text === '---') return { type: 'divider', text: '' };
  if (text === '```') return { type: 'code', text: '' };
  return null;
}

// The «/» menu.
export const SLASH: Array<{ type: BlockType; label: string; hint: string; keywords: string }> = [
  { type: 'text', label: 'Texto', hint: 'Un párrafo', keywords: 'texto parrafo text' },
  { type: 'h1', label: 'Título 1', hint: 'Sección grande', keywords: 'titulo encabezado h1 heading' },
  { type: 'h2', label: 'Título 2', hint: 'Sección media', keywords: 'titulo encabezado h2' },
  { type: 'h3', label: 'Título 3', hint: 'Sección pequeña', keywords: 'titulo encabezado h3' },
  { type: 'todo', label: 'Tarea', hint: 'Casilla para marcar', keywords: 'tarea todo casilla check' },
  { type: 'bullet', label: 'Lista', hint: 'Viñetas', keywords: 'lista viñeta bullet' },
  { type: 'number', label: 'Lista numerada', hint: '1, 2, 3', keywords: 'numerada lista number' },
  { type: 'toggle', label: 'Desplegable', hint: 'Se abre y se cierra', keywords: 'desplegable toggle' },
  { type: 'quote', label: 'Cita', hint: 'Texto citado', keywords: 'cita quote' },
  { type: 'callout', label: 'Nota destacada', hint: 'Un aviso', keywords: 'nota aviso callout' },
  { type: 'code', label: 'Código', hint: 'Bloque de código', keywords: 'codigo code' },
  { type: 'divider', label: 'Separador', hint: 'Una línea', keywords: 'separador linea divider' },
  { type: 'table', label: 'Tabla', hint: 'Hoja de cálculo y base de datos', keywords: 'tabla base datos hoja calculo database' },
  { type: 'chart', label: 'Gráfico', hint: 'Barras, líneas o pastel de una tabla', keywords: 'grafico chart barras lineas pastel' },
  { type: 'pomodoro', label: 'Pomodoro', hint: 'Temporizador de enfoque', keywords: 'pomodoro temporizador timer foco' },
  { type: 'audio', label: 'Audio', hint: 'Nota de voz o archivo', keywords: 'audio voz grabar musica' },
  { type: 'image', label: 'Imagen', hint: 'Foto o captura', keywords: 'imagen foto picture' },
  { type: 'mindmap', label: 'Mapa conceptual', hint: 'Ideas enlazadas', keywords: 'mapa mental conceptual mindmap' },
  { type: 'equation', label: 'Ecuación', hint: 'Fórmula matemática (LaTeX)', keywords: 'ecuacion formula matematica latex math' },
  { type: 'toc', label: 'Índice', hint: 'Los títulos de esta página', keywords: 'indice contenido toc tabla de contenidos' },
  { type: 'bookmark', label: 'Marcador web', hint: 'Una tarjeta con un enlace', keywords: 'marcador enlace link web bookmark url' },
  { type: 'page', label: 'Subpágina', hint: 'Una página dentro de esta', keywords: 'pagina subpagina page' },
];

export function slashMatches(query: string) {
  const q = query
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
  if (!q) return SLASH;
  return SLASH.filter((s) => s.keywords.includes(q) || s.label.toLowerCase().includes(q));
}
