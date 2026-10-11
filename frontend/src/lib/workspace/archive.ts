// The automatic vault («baúl»): what is finished or forgotten moves out of
// sight, so lists stay short and the app stays fast. Nothing is deleted:
// archived pages live in their own local store and come back with one click.
//
// * A finished task (a ticked to-do, or a table row whose status says
//   «Hecho»/«Done»…) goes to the vault 30 days after it was finished.
// * A page nobody opened or edited in 90 days goes to the vault, unless it
//   is a favourite, the inbox, or the parent of a page still in use.

import type { Page, Row, TableData } from './model';

export interface ArchiveRules {
  staleDays: number;
  doneDays: number;
}

export const DEFAULT_RULES: ArchiveRules = { staleDays: 90, doneDays: 30 };
const DAY = 86_400_000;
const DONE = new Set(['hecho', 'hecha', 'done', 'completado', 'completada', 'terminado', 'terminada', 'listo', 'lista', 'cerrado', 'cerrada']);

function plain(text: string): string {
  return text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
}

export function isDoneRow(table: TableData, row: Row): boolean {
  return table.columns.some((c) => {
    const v = row.cells[c.id] ?? '';
    if (c.type === 'checkbox') return v === 'true' && /hech|done|list|complet/.test(plain(c.name));
    if (c.type === 'select') return DONE.has(plain(v));
    return false;
  });
}

// Stamp when rows became done (and unstamp the ones reopened).
export function stampDone(table: TableData, now = Date.now()): TableData {
  let changed = false;
  const rows = table.rows.map((r) => {
    const done = isDoneRow(table, r);
    if (done && !r.doneAt) {
      changed = true;
      return { ...r, doneAt: now };
    }
    if (!done && r.doneAt) {
      changed = true;
      const { doneAt: _gone, ...rest } = r;
      return rest;
    }
    return r;
  });
  return changed ? { ...table, rows } : table;
}

// Inside one page: old finished rows and tasks go to the vault.
export function tidyPage(page: Page, now = Date.now(), rules = DEFAULT_RULES): { page: Page; rows: number; todos: number } {
  let rows = 0;
  let todos = 0;
  const limit = now - rules.doneDays * DAY;
  const blocks = page.blocks.map((b) => {
    if (b.type === 'todo' && b.checked && !b.archived && b.doneAt && b.doneAt < limit) {
      todos += 1;
      return { ...b, archived: true };
    }
    if (b.type === 'table' && b.table) {
      const table = stampDone(b.table, now);
      let moved = 0;
      const tableRows = table.rows.map((r) => {
        if (!r.archived && r.doneAt && r.doneAt < limit) {
          moved += 1;
          return { ...r, archived: true };
        }
        return r;
      });
      rows += moved;
      if (moved || table !== b.table) return { ...b, table: { ...table, rows: tableRows } };
    }
    return b;
  });
  return rows || todos ? { page: { ...page, blocks }, rows, todos } : { page, rows, todos };
}

export const INBOX_TITLE = 'Bandeja de entrada';

// Pages to move to the vault: untouched for a long time and not needed.
export function stalePages(pages: Page[], now = Date.now(), rules = DEFAULT_RULES): string[] {
  const limit = now - rules.staleDays * DAY;
  const parents = new Set(pages.filter((p) => !p.archived && Math.max(p.openedAt, p.updatedAt) >= limit).map((p) => p.parent));
  return pages
    .filter(
      (p) =>
        !p.archived &&
        !p.favorite &&
        p.title !== INBOX_TITLE &&
        Math.max(p.openedAt || 0, p.updatedAt || 0) < limit &&
        !parents.has(p.id),
    )
    .map((p) => p.id);
}
