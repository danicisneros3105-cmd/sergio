// What the person reads, never the machinery: Sergio, the Nodes and the
// swarm talk to the code with tags (<aprobacion>, <cli>, <siguiente>…) and
// the brain adds its own blocks (<mente>, <cerebro_memoria>…). If one of
// them leaks into an answer — a model forgot to close it, or wrote it in the
// wrong place — it must not reach the screen as raw text. Approvals become a
// simple question («Sergio quiere usar tu PC: desinstalar Noticias, El
// Tiempo y Disney») with the exact commands folded under «Ver detalles».

export interface PlainApproval {
  category: string;
  /** One plain sentence anyone can read. */
  summary: string;
  /** The exact commands or text, for whoever wants to look. */
  details: string;
}

import { pointMarks, type PointRequest } from './pointer';

export interface PlainReply {
  text: string;
  approvals: PlainApproval[];
  /** Where Sergio moves his pointer («[[señalar: …]]», never shown). */
  points: PointRequest[];
}

const CATEGORY_LABEL: Record<string, string> = {
  cli: 'Usar tu computadora',
  computer: 'Guardar archivos en tu computadora',
  code: 'Ejecutar código',
  web: 'Buscar en internet',
  apps: 'Leer tus apps conectadas',
  workspace: 'Escribir en tu Workspace',
  memory: 'Recordar algo de ti',
  mcp: 'Usar un conector',
  api: 'Llamar a un servicio',
  messages: 'Enviar un mensaje',
  purchases: 'Hacer una compra',
  deletions: 'Borrar algo',
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABEL[category] ?? 'Hacer algo que necesita tu permiso';
}

// Tags that are only for the code: removed with what they hold.
const HIDDEN_BLOCKS = [
  'recordar',
  'videos_reales',
  'cli',
  'mcp',
  'api',
  'enjambre',
  'equipo',
  'mente',
  'biblioteca_de_prompts',
  'cerebro_[a-z_]+',
  'think',
  'thinking',
];
// Tags whose words are for the person: the tag goes, the words stay.
const UNWRAPPED = ['usuario', 'siguiente'];

const APPROVAL = /<aprobaci[oó]n(?:\s+categor[ií]a\s*=\s*["']?([\w-]+)["']?)?\s*>([\s\S]*?)(?:<\/aprobaci[oó]n>|$)/gi;
const CODE_FENCE = /```[\w-]*\n?([\s\S]*?)(?:```|$)/g;

/** One plain sentence from what a model wrote to ask for permission. */
export function summarize(raw: string): { summary: string; details: string } {
  const fences: string[] = [];
  const prose = raw.replace(CODE_FENCE, (_m, code: string) => {
    if (code.trim()) fences.push(code.trim());
    return ' ';
  });
  const flat = prose
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
  const first = (flat.match(/^[^.?!]*[.?!]?/)?.[0] ?? flat).trim();
  let summary = (first || flat)
    .replace(/^¿?\s*(desea|quiere|quieres|puedo|me permite[s]?)\s+(que\s+)?/i, '')
    .replace(/^(ejecut\w*|correr|run)\s+(los\s+|el\s+|estos\s+)?(siguientes\s+)?comandos?(\s+en\s+[\w ]+?)?\s+(para\s+)?/i, '')
    .replace(/[?¿]/g, '')
    .trim();
  const details = fences.length ? fences.join('\n') : flat.length > summary.length + 2 ? flat : '';
  // What the commands touch, in words: *MicrosoftNews* → News.
  const named = [...new Set([...details.matchAll(/\*([A-Za-z][\w.]+)\*/g)].map((m) => readable(m[1])))].filter(Boolean);
  if (named.length && named.length <= 6) summary = `${summary}: ${named.join(', ')}`;
  return { summary: summary ? summary[0].toUpperCase() + summary.slice(1) : 'Necesita tu permiso', details };
}

function readable(id: string): string {
  return id
    .replace(/^(Microsoft|Bing|Windows)(?=[A-Z])/, '')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/[._]/g, ' ')
    .trim();
}

export function plainReply(text: string): PlainReply {
  const approvals: PlainApproval[] = [];
  let out = (text ?? '').replace(APPROVAL, (_m, category: string | undefined, body: string) => {
    const { summary, details } = summarize(body ?? '');
    approvals.push({ category: (category ?? 'messages').toLowerCase(), summary, details });
    return '';
  });
  for (const tag of HIDDEN_BLOCKS) {
    out = out.replace(new RegExp(`<(${tag})(\\s[^>]*)?>[\\s\\S]*?(?:</\\1>|$)`, 'gi'), '');
  }
  for (const tag of UNWRAPPED) {
    out = out.replace(new RegExp(`</?${tag}(\\s[^>]*)?>`, 'gi'), '');
  }
  // A stray closing tag left by any of the above.
  out = out.replace(/<\/(aprobaci[oó]n|recordar|cli|mcp|api|enjambre|equipo|mente|usuario|siguiente)>/gi, '');
  const { clean, points } = pointMarks(out);
  return { text: clean.replace(/\n{3,}/g, '\n\n').trim(), approvals, points };
}
