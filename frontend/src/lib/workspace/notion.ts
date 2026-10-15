// What makes the Workspace look and behave like the well-known notes app:
// covers, icons, block colours, the grouped «/» menu, inline formatting and
// page paths. Pure functions and data only (no React), so they are tested.

import type { BlockType, Page } from './model';

// -- covers: the gallery's colours and gradients, or an uploaded image --------
export const COVERS: Array<{ key: string; name: string; css: string }> = [
  { key: 'g1', name: 'Amanecer', css: 'linear-gradient(120deg, #f6d365 0%, #fda085 100%)' },
  { key: 'g2', name: 'Lago', css: 'linear-gradient(120deg, #89f7fe 0%, #66a6ff 100%)' },
  { key: 'g3', name: 'Lavanda', css: 'linear-gradient(120deg, #e0c3fc 0%, #8ec5fc 100%)' },
  { key: 'g4', name: 'Menta', css: 'linear-gradient(120deg, #d4fc79 0%, #96e6a1 100%)' },
  { key: 'g5', name: 'Rosa', css: 'linear-gradient(120deg, #fbc2eb 0%, #a6c1ee 100%)' },
  { key: 'g6', name: 'Noche', css: 'linear-gradient(120deg, #30cfd0 0%, #330867 100%)' },
  { key: 'c1', name: 'Rojo', css: '#e16259' },
  { key: 'c2', name: 'Amarillo', css: '#dfab01' },
  { key: 'c3', name: 'Azul', css: '#0b6e99' },
  { key: 'c4', name: 'Verde', css: '#0f7b6c' },
  { key: 'c5', name: 'Morado', css: '#6940a5' },
  { key: 'c6', name: 'Gris', css: '#9b9a97' },
];

/** The CSS background of a cover ('' when the page has none). Uploaded
 * images are resolved by the caller (they need the file's address). */
export function coverCss(cover: string | null | undefined): string {
  if (!cover) return '';
  return COVERS.find((c) => c.key === cover)?.css ?? '';
}

export const EMOJI = [
  '📄', '📝', '📌', '📎', '📚', '📖', '🗂️', '🗃️', '📅', '🗓️', '✅', '☑️', '🎯', '🚀', '💡', '🧠',
  '⭐', '🔥', '⚡', '🌱', '🌿', '🌳', '🌊', '☀️', '🌙', '❤️', '💼', '🏠', '🏢', '🛒', '💰', '📈',
  '📊', '🧾', '✈️', '🗺️', '🍽️', '☕', '🏋️', '🧘', '🎨', '🎬', '🎵', '📷', '💻', '🛠️', '🔧', '🧪',
  '🔬', '🩺', '💊', '🎓', '✏️', '🗣️', '👥', '🤝', '🎁', '🎉', '🔒', '🔑', '🐶', '🦏', '🧤', '🔮',
];

export function randomEmoji(rng: () => number = Math.random): string {
  return EMOJI[Math.floor(rng() * EMOJI.length) % EMOJI.length];
}

// -- block colours: text or background, the same ten as the original ----------
export const COLORS: Array<{ key: string; name: string }> = [
  { key: 'gray', name: 'Gris' },
  { key: 'brown', name: 'Marrón' },
  { key: 'orange', name: 'Naranja' },
  { key: 'yellow', name: 'Amarillo' },
  { key: 'green', name: 'Verde' },
  { key: 'blue', name: 'Azul' },
  { key: 'purple', name: 'Morado' },
  { key: 'pink', name: 'Rosa' },
  { key: 'red', name: 'Rojo' },
];

/** 'red' = red text, 'red_bg' = red background, '' = default. */
export function colorParts(color: string | undefined): { text: string; bg: string } {
  if (!color) return { text: '', bg: '' };
  if (color.endsWith('_bg')) return { text: '', bg: color.slice(0, -3) };
  return { text: color, bg: '' };
}

// Select options get a stable colour from their name, like tags do.
const TAG_COLORS = ['gray', 'brown', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'red'];
export function tagColor(option: string): string {
  let h = 0;
  for (const ch of option) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return TAG_COLORS[h % TAG_COLORS.length];
}

// -- the «/» menu, grouped ----------------------------------------------------
export const SLASH_GROUPS: Array<{ name: string; types: BlockType[] }> = [
  { name: 'Bloques básicos', types: ['text', 'page', 'todo', 'h1', 'h2', 'h3', 'table', 'bullet', 'number', 'toggle', 'quote', 'divider', 'callout'] },
  { name: 'Multimedia', types: ['image', 'video', 'audio', 'bookmark', 'code'] },
  { name: 'Avanzados', types: ['toc', 'equation', 'button', 'form', 'chart', 'dashboard', 'mindmap', 'pomodoro'] },
];

export function groupOf(type: BlockType): string {
  return SLASH_GROUPS.find((g) => g.types.includes(type))?.name ?? 'Avanzados';
}

// -- inline formatting -----------------------------------------------------------
// Stored as light Markdown inside a block's text, shown formatted when the
// block is not being edited: **negrita**, *cursiva*, __subrayado__,
// ~~tachado~~, `código`, [texto](https://…) and [[Página]].
export type Inline =
  | { kind: 'text'; text: string }
  | { kind: 'bold' | 'italic' | 'underline' | 'strike' | 'code'; text: string }
  | { kind: 'link'; text: string; href: string }
  | { kind: 'page'; text: string };

const INLINE = /(\*\*([^*\n]+)\*\*|__([^_\n]+)__|~~([^~\n]+)~~|`([^`\n]+)`|\[\[([^\]\n]{1,120})\]\]|\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)|\*([^*\n]+)\*)/g;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ kind: 'text', text: text.slice(last, at) });
    if (m[2] !== undefined) out.push({ kind: 'bold', text: m[2] });
    else if (m[3] !== undefined) out.push({ kind: 'underline', text: m[3] });
    else if (m[4] !== undefined) out.push({ kind: 'strike', text: m[4] });
    else if (m[5] !== undefined) out.push({ kind: 'code', text: m[5] });
    else if (m[6] !== undefined) out.push({ kind: 'page', text: m[6].trim() });
    else if (m[7] !== undefined) out.push({ kind: 'link', text: m[7], href: m[8] });
    else if (m[9] !== undefined) out.push({ kind: 'italic', text: m[9] });
    last = at + m[0].length;
  }
  if (last < text.length) out.push({ kind: 'text', text: text.slice(last) });
  return out;
}

export function hasInline(text: string): boolean {
  return parseInline(text).some((p) => p.kind !== 'text');
}

export const MARKS = { bold: '**', italic: '*', underline: '__', strike: '~~', code: '`' } as const;

/** Wrap (or unwrap, if already wrapped) the selection [start, end). */
export function toggleMark(text: string, start: number, end: number, mark: keyof typeof MARKS): { text: string; start: number; end: number } {
  const m = MARKS[mark];
  const inner = text.slice(start, end);
  if (text.slice(start - m.length, start) === m && text.slice(end, end + m.length) === m) {
    return { text: text.slice(0, start - m.length) + inner + text.slice(end + m.length), start: start - m.length, end: end - m.length };
  }
  return { text: text.slice(0, start) + m + inner + m + text.slice(end), start: start + m.length, end: end + m.length };
}

export function linkSelection(text: string, start: number, end: number, href: string): string {
  const label = text.slice(start, end) || href;
  return `${text.slice(0, start)}[${label}](${href})${text.slice(end)}`;
}

// -- «@» mentions: the query being typed right before the caret ------------------
export function mentionQuery(text: string, caret: number): string | null {
  const m = text.slice(0, caret).match(/(?:^|\s)@([^\s@[\]]{0,30})$/);
  return m ? m[1] : null;
}

export function insertMention(text: string, caret: number, title: string): { text: string; caret: number } {
  const before = text.slice(0, caret).replace(/@([^\s@[\]]{0,30})$/, `[[${title}]]`);
  return { text: before + text.slice(caret), caret: before.length };
}

// -- pages ---------------------------------------------------------------------
/** The path from the top page down to (and including) this one. */
export function ancestors(pages: Record<string, Page>, id: string): Page[] {
  const path: Page[] = [];
  const seen = new Set<string>();
  let p: Page | undefined = pages[id];
  while (p && !seen.has(p.id)) {
    path.unshift(p);
    seen.add(p.id);
    p = p.parent ? pages[p.parent] : undefined;
  }
  return path;
}

export function childrenOf(pages: Record<string, Page>, parent: string | null): Page[] {
  return Object.values(pages)
    .filter((p) => !p.archived && (parent === null ? !p.parent || !pages[p.parent] : p.parent === parent))
    .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
}

export function editedAgo(ms: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 60) return 'Editado ahora';
  const m = Math.round(s / 60);
  if (m < 60) return `Editado hace ${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `Editado hace ${h} h`;
  const d = Math.round(h / 24);
  if (d === 1) return 'Editado ayer';
  if (d < 30) return `Editado hace ${d} días`;
  return `Editado el ${new Date(ms).toLocaleDateString('es', { day: 'numeric', month: 'short', year: 'numeric' })}`;
}

export function greeting(now = new Date()): string {
  const h = now.getHours();
  if (h < 6) return 'Buenas noches, señor';
  if (h < 13) return 'Buenos días, señor';
  if (h < 20) return 'Buenas tardes, señor';
  return 'Buenas noches, señor';
}

/** Every «/» entry belongs to exactly one group (the menu shows them all). */
export function slashTypesAreGrouped(types: BlockType[]): boolean {
  return types.every((t) => SLASH_GROUPS.filter((g) => g.types.includes(t)).length === 1);
}
