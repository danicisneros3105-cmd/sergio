// More ways to see a table, like Notion's database views: a list, a gallery
// of cards and a month calendar (on the first date column). They show the
// same rows as the table, with the same filter and order, and edits made in
// any view are the same edit.

import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, ExternalLink, Plus } from 'lucide-react';
import { computeCell, toNumber } from '../../lib/workspace/formula';
import type { Column, Row, TableData } from '../../lib/workspace/model';

/** What a cell shows (formulas computed, multi-select as a list). */
export function shownValue(table: TableData, row: Row, column: Column): string {
  const all = table.rows.filter((r) => !r.archived);
  const ci = table.columns.findIndex((c) => c.id === column.id);
  return computeCell(table, all.indexOf(row), ci);
}

export function multiValues(raw: string): string[] {
  return raw
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}

/** A link for url / email / phone cells ('' when it is not one). */
export function cellHref(column: Column, raw: string): string {
  const v = raw.trim();
  if (!v) return '';
  if (column.type === 'url') return /^https?:\/\//i.test(v) ? v : `https://${v}`;
  if (column.type === 'email') return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v) ? `mailto:${v}` : '';
  if (column.type === 'phone') return /^[+\d][\d\s().-]{5,}$/.test(v) ? `tel:${v.replace(/[^\d+]/g, '')}` : '';
  return '';
}

function Value({ table, row, column }: { table: TableData; row: Row; column: Column }) {
  const raw = row.cells[column.id] ?? '';
  if (column.type === 'checkbox') return <span>{raw === 'true' ? '☑' : '☐'}</span>;
  if (column.type === 'multi' || column.type === 'select') {
    const values = column.type === 'multi' ? multiValues(raw) : raw ? [raw] : [];
    return (
      <span className="ws-chips">
        {values.map((v) => (
          <i key={v}>{v}</i>
        ))}
      </span>
    );
  }
  const href = cellHref(column, raw);
  if (href)
    return (
      <a href={href} target="_blank" rel="noreferrer" className="ws-link">
        {raw} <ExternalLink size={11} />
      </a>
    );
  return <span>{shownValue(table, row, column)}</span>;
}

export function ListView({ table, rows, onOpen }: { table: TableData; rows: Row[]; onOpen?: (r: Row) => void }) {
  const [title, ...rest] = table.columns;
  return (
    <ul className="ws-list-view">
      {rows.map((r) => (
        <li key={r.id} onClick={() => onOpen?.(r)}>
          <b>{r.cells[title.id] || 'Sin nombre'}</b>
          <span>
            {rest
              .filter((c) => (r.cells[c.id] ?? '') !== '')
              .slice(0, 4)
              .map((c) => (
                <span key={c.id} className="ws-prop" title={c.name}>
                  <Value table={table} row={r} column={c} />
                </span>
              ))}
          </span>
        </li>
      ))}
      {rows.length === 0 && <li className="ws-empty">Sin filas en esta vista.</li>}
    </ul>
  );
}

export function GalleryView({ table, rows }: { table: TableData; rows: Row[] }) {
  const [title, ...rest] = table.columns;
  return (
    <div className="ws-gallery">
      {rows.map((r) => (
        <article key={r.id} className="ws-gallery-card">
          <h4>{r.cells[title.id] || 'Sin nombre'}</h4>
          <dl>
            {rest.slice(0, 5).map((c) => (
              <div key={c.id}>
                <dt>{c.name}</dt>
                <dd>
                  <Value table={table} row={r} column={c} />
                </dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
      {rows.length === 0 && <p className="ws-empty">Sin filas en esta vista.</p>}
    </div>
  );
}

const WEEKDAYS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];

/** The days of a month grid (Monday first), with leading/trailing days. */
export function monthGrid(year: number, month: number): Array<{ iso: string; day: number; inMonth: boolean }> {
  const first = new Date(Date.UTC(year, month, 1));
  const lead = (first.getUTCDay() + 6) % 7;
  const start = new Date(Date.UTC(year, month, 1 - lead));
  const out = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getTime() + i * 86400000);
    out.push({ iso: d.toISOString().slice(0, 10), day: d.getUTCDate(), inMonth: d.getUTCMonth() === month });
  }
  // drop a sixth week made only of the next month
  return out.slice(35).every((d) => !d.inMonth) ? out.slice(0, 35) : out;
}

export function CalendarView({
  table,
  rows,
  dateColumn,
  onAdd,
  onMove,
  onRename,
}: {
  table: TableData;
  rows: Row[];
  dateColumn: Column | undefined;
  onAdd: (cells: Record<string, string>) => void;
  onMove: (rowId: string, iso: string) => void;
  onRename: (rowId: string, title: string) => void;
}) {
  const today = new Date();
  const [editing, setEditing] = useState<string | null>(null);
  const [cursor, setCursor] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const days = useMemo(() => monthGrid(cursor.y, cursor.m), [cursor]);
  const title = table.columns[0];
  if (!dateColumn)
    return <p className="ws-empty">Para ver el calendario, cambie una columna al tipo «Fecha» (menú ⋯ de la columna).</p>;
  const raw = new Date(cursor.y, cursor.m, 1).toLocaleDateString('es', { month: 'long', year: 'numeric' });
  const label = raw.charAt(0).toUpperCase() + raw.slice(1);
  const todayIso = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())).toISOString().slice(0, 10);
  const step = (n: number) => setCursor(({ y, m }) => ({ y: y + Math.floor((m + n) / 12), m: (((m + n) % 12) + 12) % 12 }));
  return (
    <div className="ws-calendar">
      <div className="ws-calendar-bar">
        <button type="button" className="mac-icon-btn" onClick={() => step(-1)} aria-label="Mes anterior">
          <ChevronLeft size={15} />
        </button>
        <b>{label}</b>
        <button type="button" className="mac-icon-btn" onClick={() => step(1)} aria-label="Mes siguiente">
          <ChevronRight size={15} />
        </button>
        <button type="button" className="paper-tab" onClick={() => setCursor({ y: today.getFullYear(), m: today.getMonth() })}>
          Hoy
        </button>
      </div>
      <div className="ws-calendar-grid" role="grid" aria-label={`Calendario de ${label}`}>
        {WEEKDAYS.map((d) => (
          <span key={d} className="ws-calendar-wd">
            {d}
          </span>
        ))}
        {days.map((d) => {
          const items = rows.filter((r) => (r.cells[dateColumn.id] || '').slice(0, 10) === d.iso);
          return (
            <div
              key={d.iso}
              className="ws-calendar-day"
              data-out={!d.inMonth || undefined}
              data-today={d.iso === todayIso || undefined}
              role="gridcell"
              aria-label={d.iso}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                const id = e.dataTransfer.getData('text/row');
                if (id) onMove(id, d.iso);
              }}
            >
              <span className="ws-calendar-n">{d.day}</span>
              {items.map((r) =>
                editing === r.id ? (
                  <input
                    key={r.id}
                    className="ws-calendar-item"
                    autoFocus
                    defaultValue={r.cells[title.id] || ''}
                    placeholder="Nombre"
                    aria-label={title.name}
                    onBlur={(e) => {
                      onRename(r.id, e.target.value);
                      setEditing(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                      if (e.key === 'Escape') setEditing(null);
                    }}
                  />
                ) : (
                  <button
                    type="button"
                    key={r.id}
                    className="ws-calendar-item"
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData('text/row', r.id)}
                    onClick={() => setEditing(r.id)}
                    title={`${r.cells[title.id] || 'Sin nombre'} · clic para renombrar, arrastre para cambiar de día`}
                  >
                    {r.cells[title.id] || 'Sin nombre'}
                  </button>
                ),
              )}
              <button
                type="button"
                className="ws-calendar-add"
                aria-label={`Añadir el ${d.iso}`}
                onClick={() => onAdd({ [dateColumn.id]: d.iso, [title.id]: '' })}
              >
                <Plus size={11} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// -- dashboard view: the table as widgets (Notion's «Panel» view) -------------------
// Number cards first, then one bar widget per select column; the view's
// filter applies to every widget, as in Notion. Up to four per row.
export function DashboardView({ table, rows }: { table: TableData; rows: Row[] }) {
  const widgets = useMemo(() => {
    const cards: Array<{ label: string; value: string }> = [{ label: 'Filas', value: rows.length.toLocaleString('es') }];
    for (const c of table.columns.filter((c) => c.type === 'number')) {
      const values = rows.map((r) => toNumber(shownValue(table, r, c))).filter((n): n is number => n !== null && Number.isFinite(n));
      if (!values.length) continue;
      const sum = values.reduce((a, b) => a + b, 0);
      cards.push({ label: `${c.name} · suma`, value: sum.toLocaleString('es', { maximumFractionDigits: 2 }) });
      cards.push({ label: `${c.name} · promedio`, value: (sum / values.length).toLocaleString('es', { maximumFractionDigits: 2 }) });
    }
    for (const c of table.columns.filter((c) => c.type === 'checkbox')) {
      const done = rows.filter((r) => r.cells[c.id] === 'true' || r.cells[c.id] === '1').length;
      cards.push({ label: c.name, value: `${rows.length ? Math.round((done / rows.length) * 100) : 0} %` });
    }
    const bars = table.columns
      .filter((c) => c.type === 'select' || c.type === 'multi')
      .map((c) => {
        const counts = new Map<string, number>();
        for (const r of rows) {
          const values = c.type === 'multi' ? multiValues(r.cells[c.id] || '') : [r.cells[c.id] || ''];
          for (const v of values.length ? values : ['']) counts.set(v || 'Vacío', (counts.get(v || 'Vacío') || 0) + 1);
        }
        const order = [...(c.options || []), 'Vacío'];
        const items = [...counts.entries()].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]) || b[1] - a[1]);
        return { name: c.name, items, max: Math.max(1, ...items.map((i) => i[1])) };
      });
    return { cards, bars };
  }, [table, rows]);

  return (
    <div className="ws-dashview">
      <div className="ws-dashview-grid">
        {widgets.cards.map((k) => (
          <section key={k.label} className="ws-dashview-card">
            <small>{k.label}</small>
            <strong>{k.value}</strong>
          </section>
        ))}
      </div>
      {widgets.bars.length > 0 && (
        <div className="ws-dashview-grid">
          {widgets.bars.map((b) => (
            <section key={b.name} className="ws-dashview-card ws-dashview-wide">
              <small>{b.name}</small>
              {b.items.map(([label, n]) => (
                <div key={label} className="ws-dashview-bar">
                  <span className="ws-dashview-label">{label}</span>
                  <span className="ws-dashview-track">
                    <span style={{ width: `${(n / b.max) * 100}%` }} />
                  </span>
                  <span className="ws-dashview-n">{n}</span>
                </div>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
