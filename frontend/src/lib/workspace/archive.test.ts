import { describe, expect, it } from 'vitest';
import { INBOX_TITLE, isDoneRow, stalePages, stampDone, tidyPage } from './archive';
import { block, emptyTable, newPage } from './model';

const DAY = 86_400_000;
const NOW = Date.UTC(2026, 9, 10);

describe('the automatic vault', () => {
  it('stamps rows when they become done and unstamps reopened ones', () => {
    const t = emptyTable();
    const status = t.columns[1].id;
    t.rows[0].cells[status] = 'Hecho';
    const stamped = stampDone(t, NOW);
    expect(isDoneRow(stamped, stamped.rows[0])).toBe(true);
    expect(stamped.rows[0].doneAt).toBe(NOW);
    stamped.rows[0].cells[status] = 'En curso';
    expect(stampDone(stamped, NOW + DAY).rows[0].doneAt).toBeUndefined();
  });

  it('moves old finished rows and ticked tasks to the vault, keeps recent ones', () => {
    const table = block('table');
    const status = table.table!.columns[1].id;
    table.table!.rows = [
      { id: 'old', cells: { [status]: 'Hecho' }, doneAt: NOW - 40 * DAY },
      { id: 'new', cells: { [status]: 'Done' }, doneAt: NOW - 3 * DAY },
      { id: 'open', cells: { [status]: 'Por hacer' } },
    ];
    const page = newPage('Proyecto', null, [
      table,
      block('todo', 'vieja', { checked: true, doneAt: NOW - 31 * DAY }),
      block('todo', 'reciente', { checked: true, doneAt: NOW - DAY }),
      block('todo', 'pendiente'),
    ]);
    const { page: tidy, rows, todos } = tidyPage(page, NOW);
    expect(rows).toBe(1);
    expect(todos).toBe(1);
    expect(tidy.blocks[0].table!.rows.filter((r) => r.archived).map((r) => r.id)).toEqual(['old']);
    expect(tidy.blocks.filter((b) => b.archived).map((b) => b.text)).toEqual(['vieja']);
    const again = tidyPage(tidy, NOW);
    expect(again.rows + again.todos).toBe(0);
  });

  it('archives forgotten pages but never favourites, the inbox or parents in use', () => {
    const old = { ...newPage('Viejo'), openedAt: NOW - 120 * DAY, updatedAt: NOW - 120 * DAY };
    const fav = { ...old, id: 'fav', favorite: true };
    const inbox = { ...old, id: 'inbox', title: INBOX_TITLE };
    const parent = { ...old, id: 'parent' };
    const child = { ...newPage('Hijo', 'parent'), openedAt: NOW - DAY, updatedAt: NOW - DAY };
    const fresh = { ...newPage('Nuevo'), openedAt: NOW - DAY, updatedAt: NOW - DAY };
    expect(stalePages([old, fav, inbox, parent, child, fresh], NOW)).toEqual([old.id]);
  });
});
