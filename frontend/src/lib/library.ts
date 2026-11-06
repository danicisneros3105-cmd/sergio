import { scopedDataKey } from './browserAccount';
// The Home library (the e-paper home screen): everything Sergio keeps for
// you as documents on a shelf — conversations, workspace pages and the
// sections — sorted, filtered, marked and paged. Pure helpers, no store.

import type { Conversation } from '../types';
import type { Page } from './workspace/model';
import { previewLines } from './workspace/model';
import { stripThinkTags } from './message-text';
import { relativeDay } from './paper';

export type LibraryKind = 'conversation' | 'page' | 'section';

export interface LibraryItem {
  id: string;
  kind: LibraryKind;
  title: string;
  meta: string;
  updatedAt: number;
  createdAt: number;
  path: string;
  // A few lines to print, tiny, on the page thumbnail.
  lines: string[];
  // Sections draw a thin icon instead of text.
  icon?: string;
}

export type SortKey = 'recent' | 'name' | 'created';
export type FilterKey = 'all' | 'conversation' | 'page' | 'section';

export const SORTS: Array<{ key: SortKey; label: string }> = [
  { key: 'recent', label: 'Abiertos recientemente' },
  { key: 'name', label: 'Por nombre' },
  { key: 'created', label: 'Creados recientemente' },
];

export const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: 'all', label: 'Todo' },
  { key: 'conversation', label: 'Conversaciones' },
  { key: 'page', label: 'Páginas' },
];

// The sections. The shelf no longer shows them: they live only as icons in
// the toolbar (kept here for the notch and older saved marks).
export const SECTION_ITEMS: LibraryItem[] = [
  { id: 'section:cowork', kind: 'section', title: 'Cowork', meta: 'Trabajos largos, paso a paso', path: '/cowork', icon: 'briefcase' },
  { id: 'section:agents', kind: 'section', title: 'Agent Swarm', meta: 'Varios agentes a la vez', path: '/swarm', icon: 'network' },
  { id: 'section:salud', kind: 'section', title: 'Salud', meta: 'Cuerpo, sueño y mente', path: '/salud', icon: 'heart' },
  { id: 'section:perfil', kind: 'section', title: 'Perfil', meta: 'Quién es usted para Sergio', path: '/perfil', icon: 'user' },
].map((s) => ({ ...s, kind: 'section' as const, updatedAt: 0, createdAt: 0, lines: [] }));

export const DEFAULT_MARKS = SECTION_ITEMS.map((s) => s.id);

export function conversationItems(conversations: Conversation[], now = Date.now()): LibraryItem[] {
  return conversations
    .filter((c) => c.messages.length > 0)
    .map((c) => ({
      id: `conversation:${c.id}`,
      kind: 'conversation' as const,
      title: c.title || 'Conversación',
      meta: `${c.messages.length} ${c.messages.length === 1 ? 'mensaje' : 'mensajes'} · ${relativeDay(c.updatedAt, now)}`,
      updatedAt: c.updatedAt,
      createdAt: c.createdAt,
      path: '/chat',
      lines: c.messages
        .slice(0, 5)
        .map((m) => stripThinkTags(m.content).replace(/\s+/g, ' ').slice(0, 120))
        .filter(Boolean),
    }));
}

export function pageItems(pages: Page[], now = Date.now()): LibraryItem[] {
  return pages
    .filter((p) => !p.archived)
    .map((p) => {
      const tasks = p.blocks.filter((b) => b.type === 'todo' && !b.archived);
      const done = tasks.filter((b) => b.checked).length;
      return {
        id: `page:${p.id}`,
        kind: 'page' as const,
        title: p.title || 'Sin título',
        meta: !tasks.length
          ? relativeDay(p.updatedAt, now)
          : done
            ? `${Math.round((done / tasks.length) * 100)} % · ${relativeDay(p.updatedAt, now)}`
            : `${tasks.length} ${tasks.length === 1 ? 'tarea' : 'tareas'} · ${relativeDay(p.updatedAt, now)}`,
        updatedAt: Math.max(p.updatedAt, p.openedAt || 0),
        createdAt: p.createdAt,
        path: `/workspace/${p.id}`,
        lines: previewLines(p),
        icon: p.sealed ? 'lock' : undefined,
      };
    });
}

export function sortItems(items: LibraryItem[], sort: SortKey): LibraryItem[] {
  const out = [...items];
  if (sort === 'name') out.sort((a, b) => a.title.localeCompare(b.title, 'es', { sensitivity: 'base' }));
  else if (sort === 'created') out.sort((a, b) => b.createdAt - a.createdAt);
  else out.sort((a, b) => b.updatedAt - a.updatedAt);
  return out;
}

export function filterItems(items: LibraryItem[], filter: FilterKey): LibraryItem[] {
  return filter === 'all' ? items : items.filter((i) => i.kind === filter);
}

export function paginate<T>(items: T[], page: number, perPage: number): { items: T[]; page: number; pages: number } {
  const pages = Math.max(1, Math.ceil(items.length / perPage));
  const current = Math.min(Math.max(1, page), pages);
  return { items: items.slice((current - 1) * perPage, current * perPage), page: current, pages };
}

// Marks live in this browser only (a per-viewer convenience).
const MARKS_KEY = scopedDataKey('sergio-marks');

export function loadMarks(): string[] {
  try {
    const raw = localStorage.getItem(MARKS_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : DEFAULT_MARKS;
  } catch {
    return DEFAULT_MARKS;
  }
}

export function saveMarks(marks: string[]): void {
  try {
    localStorage.setItem(MARKS_KEY, JSON.stringify(marks));
  } catch {
    // storage blocked: marks last for this visit
  }
}

export function toggleMark(marks: string[], id: string): string[] {
  return marks.includes(id) ? marks.filter((m) => m !== id) : [...marks, id];
}
