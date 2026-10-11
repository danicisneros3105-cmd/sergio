// Agents you make yourself, like a custom GPT: a name, a short description,
// instructions, conversation starters, knowledge and capabilities. Sergio
// himself is not personalised; agents are.
//
// The draft lives in the agent's config under `builder`; the runtime reads
// `system_prompt`, `tools` and `model` from the same config.

import type { ManagedAgent } from './api';

export type Capability = 'web' | 'code' | 'images' | 'workspace' | 'memory';

export interface KnowledgeFile {
  name: string;
  text: string;
}

export interface AgentDraft {
  name: string;
  description: string;
  instructions: string;
  starters: string[];
  capabilities: Capability[];
  knowledge: KnowledgeFile[];
  icon: string; // one emoji or letter
  color: string;
  model: string;
}

export const CAPABILITIES: Array<{ key: Capability; label: string; hint: string; tools: string[] }> = [
  { key: 'web', label: 'Búsqueda web', hint: 'Busca y lee páginas', tools: ['web_search', 'browser_navigate', 'browser_extract'] },
  { key: 'code', label: 'Código y datos', hint: 'Ejecuta Python y calcula', tools: ['code_interpreter', 'calculator'] },
  { key: 'images', label: 'Imágenes', hint: 'Genera imágenes', tools: ['image_generate'] },
  { key: 'workspace', label: 'Workspace', hint: 'Lee y escribe sus páginas', tools: ['workspace'] },
  { key: 'memory', label: 'Memoria', hint: 'Recuerda entre conversaciones', tools: ['memory_search', 'memory_store'] },
];

export const COLORS = ['#1d1d1b', '#6b6a64', '#8a6a4f', '#4f6b5a', '#4c5d78', '#7a4f5d'];

export const MAX_STARTERS = 4;
export const MAX_KNOWLEDGE_CHARS = 60_000;
export const KNOWLEDGE_TYPES = ['.txt', '.md', '.markdown', '.csv', '.json', '.html', '.xml', '.yaml', '.yml', '.log'];

export function emptyDraft(model = ''): AgentDraft {
  return {
    name: '',
    description: '',
    instructions: '',
    starters: [],
    capabilities: ['web'],
    knowledge: [],
    icon: '',
    color: COLORS[0],
    model,
  };
}

export function knowledgeChars(draft: AgentDraft): number {
  return draft.knowledge.reduce((n, k) => n + k.text.length, 0);
}

// The system prompt the agent runs with: its instructions, then what it
// knows (clipped so the whole stays within MAX_KNOWLEDGE_CHARS).
export function systemPrompt(draft: AgentDraft): string {
  const parts = [`Eres «${draft.name.trim() || 'un agente'}», un agente creado por el usuario dentro de Sergio.`];
  if (draft.description.trim()) parts.push(`Tu propósito: ${draft.description.trim()}`);
  if (draft.instructions.trim()) parts.push(`Instrucciones:\n${draft.instructions.trim()}`);
  let room = MAX_KNOWLEDGE_CHARS;
  const known: string[] = [];
  for (const file of draft.knowledge) {
    if (room <= 0) break;
    const text = file.text.slice(0, room);
    room -= text.length;
    known.push(`### ${file.name}\n${text}`);
  }
  if (known.length) {
    parts.push(
      'Conocimiento (archivos del usuario). Úsalo como fuente principal y dilo cuando algo no esté en él:\n\n' +
        known.join('\n\n'),
    );
  }
  parts.push('Responde en el idioma del usuario. No inventes datos; si no sabes algo, dilo.');
  return parts.join('\n\n');
}

export function toolsFor(capabilities: Capability[]): string[] {
  const out: string[] = [];
  for (const cap of CAPABILITIES) {
    if (capabilities.includes(cap.key)) for (const t of cap.tools) if (!out.includes(t)) out.push(t);
  }
  return out;
}

export function toConfig(draft: AgentDraft): Record<string, unknown> {
  return {
    system_prompt: systemPrompt(draft),
    tools: toolsFor(draft.capabilities),
    ...(draft.model ? { model: draft.model } : {}),
    builder: { ...draft, starters: cleanStarters(draft.starters) },
  };
}

export function cleanStarters(starters: string[]): string[] {
  return starters.map((s) => s.trim()).filter(Boolean).slice(0, MAX_STARTERS);
}

function isCapability(x: unknown): x is Capability {
  return CAPABILITIES.some((c) => c.key === x);
}

// Back from a stored agent. Agents made elsewhere (no `builder`) still open:
// their prompt becomes the instructions.
export function fromAgent(agent: ManagedAgent): AgentDraft {
  const cfg = (agent.config || {}) as Record<string, unknown>;
  const b = (cfg.builder || {}) as Partial<AgentDraft>;
  const base = emptyDraft(typeof cfg.model === 'string' ? cfg.model : '');
  return {
    ...base,
    name: typeof b.name === 'string' ? b.name : agent.name,
    description: typeof b.description === 'string' ? b.description : '',
    instructions:
      typeof b.instructions === 'string'
        ? b.instructions
        : typeof cfg.system_prompt === 'string'
          ? cfg.system_prompt
          : '',
    starters: Array.isArray(b.starters) ? b.starters.filter((s): s is string => typeof s === 'string') : [],
    capabilities: Array.isArray(b.capabilities) ? b.capabilities.filter(isCapability) : base.capabilities,
    knowledge: Array.isArray(b.knowledge)
      ? b.knowledge.filter((k): k is KnowledgeFile => !!k && typeof k.name === 'string' && typeof k.text === 'string')
      : [],
    icon: typeof b.icon === 'string' ? b.icon : '',
    color: typeof b.color === 'string' ? b.color : base.color,
    model: typeof b.model === 'string' && b.model ? b.model : base.model,
  };
}

export function problems(draft: AgentDraft): string[] {
  const out: string[] = [];
  if (!draft.name.trim()) out.push('Póngale un nombre.');
  if (!draft.instructions.trim()) out.push('Escriba qué debe hacer (instrucciones).');
  if (knowledgeChars(draft) > MAX_KNOWLEDGE_CHARS) out.push('El conocimiento es demasiado largo: se usará solo el principio.');
  return out;
}

export function initial(draft: AgentDraft): string {
  if (draft.icon.trim()) return [...draft.icon.trim()][0];
  const letter = draft.name.trim()[0];
  return letter ? letter.toUpperCase() : '·';
}

// -- «Crear»: describe the agent in a conversation ---------------------------

export interface BuilderTurn {
  role: 'user' | 'assistant';
  content: string;
}

const BUILDER_SYSTEM = `Ayudas a crear un agente personalizado (como un GPT personalizado) dentro de Sergio.
Conversa en español, breve y cálido. Con lo que el usuario cuente, propón o mejora la configuración.
Haz como mucho UNA pregunta corta por turno, solo si falta algo importante.
Termina SIEMPRE tu respuesta con un bloque JSON entre <config> y </config> con los campos que cambien:
{"name": "...", "description": "una línea", "instructions": "instrucciones completas en segunda persona",
 "starters": ["hasta 4 frases de inicio"], "capabilities": ["web"|"code"|"images"|"workspace"|"memory"], "icon": "un emoji"}
Nunca incluyas en las instrucciones enviar mensajes, llamar ni publicar por el usuario sin su aprobación.`;

export function builderMessages(history: BuilderTurn[], draft: AgentDraft) {
  const current = { ...draft, knowledge: draft.knowledge.map((k) => k.name) };
  return [
    { role: 'system', content: `${BUILDER_SYSTEM}\n\nConfiguración actual:\n${JSON.stringify(current)}` },
    ...history.map((t) => ({ role: t.role, content: t.content })),
  ];
}

// Split the builder's answer into what it says and the fields it changes.
export function parseBuilderReply(text: string): { say: string; patch: Partial<AgentDraft> } {
  const m = /<config>([\s\S]*?)<\/config>/i.exec(text);
  const say = text.replace(/<config>[\s\S]*?(<\/config>|$)/i, '').trim();
  if (!m) return { say, patch: {} };
  let raw: unknown;
  try {
    const body = m[1].trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
    raw = JSON.parse(body);
  } catch {
    return { say, patch: {} };
  }
  if (!raw || typeof raw !== 'object') return { say, patch: {} };
  const r = raw as Record<string, unknown>;
  const patch: Partial<AgentDraft> = {};
  for (const key of ['name', 'description', 'instructions', 'icon'] as const) {
    if (typeof r[key] === 'string' && (r[key] as string).trim()) patch[key] = (r[key] as string).trim();
  }
  if (patch.icon) patch.icon = [...patch.icon][0];
  if (Array.isArray(r.starters)) patch.starters = cleanStarters(r.starters.filter((s): s is string => typeof s === 'string'));
  if (Array.isArray(r.capabilities)) patch.capabilities = r.capabilities.filter(isCapability);
  return { say, patch };
}
