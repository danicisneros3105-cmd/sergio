// Cowork, laid out like the work mode of the best-known assistant: one
// composer, the task as a conversation, and a side panel with the plan,
// the files and the record. Pure helpers here (tested); the screen is
// pages/CoworkPage.tsx.

export type Autonomy = 'cauteloso' | 'normal' | 'autonomo';

export interface ComposerOptions {
  autonomy: Autonomy;
  maxActions: number;
  planFirst: boolean;
}

export const AUTONOMY_ES: Record<Autonomy, string> = {
  cauteloso: 'Cauteloso',
  normal: 'Normal',
  autonomo: 'Autónomo',
};

export interface SlashCommand {
  cmd: string;
  label: string;
  apply: (o: ComposerOptions, arg: string) => ComposerOptions;
}

export const SLASH: SlashCommand[] = [
  { cmd: '/plan', label: 'Modo plan: ver el plan antes de empezar', apply: (o) => ({ ...o, planFirst: !o.planFirst }) },
  { cmd: '/cauteloso', label: 'Preguntar más', apply: (o) => ({ ...o, autonomy: 'cauteloso' }) },
  { cmd: '/normal', label: 'Autonomía normal', apply: (o) => ({ ...o, autonomy: 'normal' }) },
  { cmd: '/autonomo', label: 'Preguntar menos', apply: (o) => ({ ...o, autonomy: 'autonomo' }) },
  {
    cmd: '/tope',
    label: 'Tope de acciones, p. ej. /tope 100',
    apply: (o, arg) => ({ ...o, maxActions: clampActions(Number(arg) || o.maxActions) }),
  },
];

export function clampActions(n: number): number {
  return Math.max(1, Math.min(500, Math.round(n)));
}

/** The commands that match what is typed after «/» (the menu above the box). */
export function slashMatches(text: string): SlashCommand[] {
  const m = text.match(/^\/(\S*)$/);
  if (!m) return [];
  return SLASH.filter((c) => c.cmd.slice(1).startsWith(m[1].toLowerCase()));
}

/** A whole «/command arg» line applied to the options; null when it is not one. */
export function applySlash(text: string, options: ComposerOptions): ComposerOptions | null {
  const m = text.trim().match(/^(\/\S+)\s*(.*)$/);
  if (!m) return null;
  const command = SLASH.find((c) => c.cmd === m[1].toLowerCase());
  return command ? command.apply(options, m[2]) : null;
}

export interface FoundFile {
  name: string;
  path: string;
}

const FILE_RE =
  /(?:[A-Za-z]:\\[^\s"'«»<>|]+|~?\/[^\s"'«»<>|]+|(?:[\w\-.]+[\\/])+[\w\-.]*\w|[\w\-.]*\w)\.(?:md|txt|csv|json|html|pdf|xlsx|xls|docx|doc|pptx|png|jpg|jpeg|svg|zip|py|ts|js)\b/gi;

/** The files a run says it produced (from step results and the summary). */
export function filesIn(texts: string[]): FoundFile[] {
  const seen = new Map<string, FoundFile>();
  for (const text of texts) {
    for (const raw of text.replace(/https?:\/\/\S+/gi, ' ').match(FILE_RE) ?? []) {
      const path = raw.trim().replace(/^[\s,;:(]+/, '');
      if (!path) continue;
      const name = path.split(/[\\/]/).pop() || path;
      if (!seen.has(name.toLowerCase())) seen.set(name.toLowerCase(), { name, path });
    }
  }
  return [...seen.values()];
}

/** «ahora», «hace 5 min», «hace 3 h», «ayer», «hace 4 días». */
export function timeAgo(seconds: number, now = Date.now() / 1000): string {
  const d = Math.max(0, now - seconds);
  if (d < 60) return 'ahora';
  if (d < 3600) return `hace ${Math.floor(d / 60)} min`;
  if (d < 86400) return `hace ${Math.floor(d / 3600)} h`;
  if (d < 172800) return 'ayer';
  return `hace ${Math.floor(d / 86400)} días`;
}

/** «Trabajó 4 min», for the folded activity of a finished run. */
export function workedFor(from: number, to: number): string {
  const d = Math.max(0, to - from);
  if (d < 60) return `Trabajó ${Math.max(1, Math.round(d))} s`;
  if (d < 3600) return `Trabajó ${Math.round(d / 60)} min`;
  return `Trabajó ${(d / 3600).toFixed(1).replace('.0', '')} h`;
}

export const SUGGESTIONS = [
  'Compara los 3 mejores portátiles para diseño 3D y déjame una tabla',
  'Ordena mi carpeta de Descargas por tipo y fecha',
  'Prepara un informe de una página sobre mis gastos del mes',
  'Busca vuelos a Madrid en diciembre y resume las mejores opciones',
];
