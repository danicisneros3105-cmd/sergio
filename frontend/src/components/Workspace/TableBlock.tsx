import { useMemo, useState } from 'react';
import { Plus, Trash2, Share2, Columns3, LayoutGrid, Filter, ArrowUpDown, List, GalleryVerticalEnd, CalendarDays, ExternalLink, GanttChart, LayoutDashboard, Zap } from 'lucide-react';
import { applyRules, rollup } from '../../lib/workspace/brain';
import { AiTable, FormulaWords, RulesEditor, TimelineView } from './TableSmarts';
import { columnLetter, computeCell, isFormula, toNumber } from '../../lib/workspace/formula';
import { stampDone } from '../../lib/workspace/archive';
import { newId, type Column, type ColumnType, type Row, type TableData, type TableView } from '../../lib/workspace/model';
import { CalendarView, DashboardView, GalleryView, ListView, cellHref, multiValues } from './TableViews';
import { tagColor } from '../../lib/workspace/notion';
import { AtSign, Calendar, CheckSquare, ChevronDown as ChevronDownIcon, Hash, Link2, ListChecks, Phone, Text as TextIcon, Type } from 'lucide-react';

const TYPE_ICON: Record<ColumnType, typeof Hash> = {
  text: TextIcon,
  number: Hash,
  select: ChevronDownIcon,
  multi: ListChecks,
  date: Calendar,
  checkbox: CheckSquare,
  url: Link2,
  email: AtSign,
  phone: Phone,
};

const TYPES: Array<{ key: ColumnType; label: string }> = [
  { key: 'text', label: 'Texto' },
  { key: 'number', label: 'Número' },
  { key: 'select', label: 'Opciones' },
  { key: 'multi', label: 'Varias opciones' },
  { key: 'date', label: 'Fecha' },
  { key: 'checkbox', label: 'Casilla' },
  { key: 'url', label: 'Enlace' },
  { key: 'email', label: 'Correo' },
  { key: 'phone', label: 'Teléfono' },
];

const VIEW_KINDS: Array<{ key: TableView['kind']; label: string }> = [
  { key: 'table', label: 'Tabla' },
  { key: 'board', label: 'Tablero' },
  { key: 'list', label: 'Lista' },
  { key: 'gallery', label: 'Galería' },
  { key: 'calendar', label: 'Calendario' },
  { key: 'timeline', label: 'Cronograma' },
  { key: 'dashboard', label: 'Panel' },
];

const VIEW_ICON = { table: Columns3, board: LayoutGrid, list: List, gallery: GalleryVerticalEnd, calendar: CalendarDays, timeline: GanttChart, dashboard: LayoutDashboard };

export function visibleRows(table: TableData, view: TableView): Row[] {
  let rows = table.rows.filter((r) => !r.archived);
  const f = view.filter;
  if (f && f.column) {
    const col = table.columns.findIndex((c) => c.id === f.column);
    rows = rows.filter((r) => {
      const all = table.rows.filter((x) => !x.archived);
      const shown = computeCell(table, all.indexOf(r), col);
      const v = f.value.toLowerCase();
      const cell = shown.toLowerCase();
      if (f.op === 'is') return cell === v;
      if (f.op === 'not') return cell !== v;
      if (f.op === 'contains') return cell.includes(v);
      const a = toNumber(shown);
      const b = toNumber(f.value);
      if (a === null || b === null) return false;
      return f.op === 'gt' ? a > b : a < b;
    });
  }
  const s = view.sort;
  if (s && s.column) {
    const col = table.columns.findIndex((c) => c.id === s.column);
    const all = table.rows.filter((x) => !x.archived);
    rows = [...rows].sort((a, b) => {
      const va = computeCell(table, all.indexOf(a), col);
      const vb = computeCell(table, all.indexOf(b), col);
      const na = toNumber(va);
      const nb = toNumber(vb);
      const cmp = na !== null && nb !== null ? na - nb : va.localeCompare(vb, 'es', { sensitivity: 'base' });
      return s.dir === 'asc' ? cmp : -cmp;
    });
  }
  return rows;
}

function Cell({
  table,
  row,
  rowIndex,
  colIndex,
  column,
  onSet,
}: {
  table: TableData;
  row: Row;
  rowIndex: number;
  colIndex: number;
  column: Column;
  onSet: (value: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const raw = row.cells[column.id] ?? '';
  if (column.type === 'checkbox') {
    return (
      <input
        type="checkbox"
        checked={raw === 'true'}
        onChange={(e) => onSet(e.target.checked ? 'true' : 'false')}
        aria-label={column.name}
      />
    );
  }
  if (column.type === 'select') {
    return (
      <span className="nx-tag-wrap">
        {raw && (
          <span className="nx-tag" data-tag={tagColor(raw)}>
            {raw}
          </span>
        )}
        <select value={raw} onChange={(e) => onSet(e.target.value)} aria-label={column.name}>
          <option value="" />
          {(column.options || []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </span>
    );
  }
  if (column.type === 'date') {
    return <input type="date" className="ws-cell" value={raw} onChange={(e) => onSet(e.target.value)} aria-label={column.name} />;
  }
  if (column.type === 'multi') {
    const chosen = multiValues(raw);
    const toggle = (o: string) => onSet((chosen.includes(o) ? chosen.filter((x) => x !== o) : [...chosen, o]).join(', '));
    return (
      <span className="ws-multi" role="group" aria-label={column.name}>
        {(column.options || []).map((o) => (
          <button key={o} type="button" aria-pressed={chosen.includes(o)} onClick={() => toggle(o)}>
            {o}
          </button>
        ))}
      </span>
    );
  }
  if (column.type === 'url' || column.type === 'email' || column.type === 'phone') {
    const href = cellHref(column, raw);
    return (
      <span className="ws-linkcell">
        <input
          className="ws-cell"
          type={column.type === 'email' ? 'email' : column.type === 'phone' ? 'tel' : 'url'}
          value={raw}
          onChange={(e) => onSet(e.target.value)}
          aria-label={column.name}
          data-invalid={raw && !href ? 'true' : undefined}
        />
        {href && (
          <a href={href} target="_blank" rel="noreferrer" aria-label={`Abrir ${raw}`}>
            <ExternalLink size={12} />
          </a>
        )}
      </span>
    );
  }
  const shown = editing || !isFormula(raw) ? raw : computeCell(table, rowIndex, colIndex);
  return (
    <input
      className="ws-cell"
      data-number={column.type === 'number' || isFormula(raw) ? 'true' : undefined}
      data-formula={isFormula(raw) && !editing ? 'true' : undefined}
      value={shown}
      title={isFormula(raw) ? raw : undefined}
      onFocus={() => setEditing(true)}
      onBlur={() => setEditing(false)}
      onChange={(e) => onSet(e.target.value)}
      aria-label={`${column.name} ${columnLetter(colIndex)}${rowIndex + 1}`}
    />
  );
}

export function TableBlock({
  table,
  onChange,
  onShareRows,
  onShareView,
  onEffects,
}: {
  table: TableData;
  onChange: (t: TableData) => void;
  onShareRows?: (rowIds: string[]) => void;
  onShareView?: (viewId: string) => void;
  onEffects?: (fx: { todos: string[]; notes: string[] }) => void;
}) {
  const view = table.views.find((v) => v.id === table.view) || table.views[0];
  const [picked, setPicked] = useState<string[]>([]);
  const [tools, setTools] = useState(false);
  const [adding, setAdding] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const all = table.rows.filter((r) => !r.archived);
  const rows = useMemo(() => visibleRows(table, view), [table, view]);
  // Every change runs the table's automations on the rows it touched.
  const set = (t: TableData) => {
    let next = stampDone(t);
    if (next.rules?.some((x) => x.on)) {
      const before = new Map(table.rows.map((row) => [row.id, row]));
      const todos: string[] = [];
      const notes: string[] = [];
      for (const row of next.rows) {
        const old = before.get(row.id);
        if (old && JSON.stringify(old.cells) === JSON.stringify(row.cells)) continue;
        const fx = applyRules(next, next.rules || [], row.id, old);
        next = fx.table;
        todos.push(...fx.todos);
        notes.push(...fx.notes);
        for (const hook of fx.webhooks) void fetch(hook.url, { method: 'POST', mode: 'no-cors', body: JSON.stringify(hook.row) }).catch(() => undefined);
      }
      if (todos.length || notes.length) onEffects?.({ todos, notes });
    }
    onChange(next);
  };
  const blank = table.rows.length <= 1 && table.rows.every((row) => Object.values(row.cells).every((v) => !v || v === 'Por hacer'));
  const setView = (patch: Partial<TableView>) =>
    set({ ...table, views: table.views.map((v) => (v.id === view.id ? { ...v, ...patch } : v)) });
  const setCell = (rowId: string, colId: string, value: string) =>
    set({ ...table, rows: table.rows.map((r) => (r.id === rowId ? { ...r, cells: { ...r.cells, [colId]: value } } : r)) });
  const addRow = (cells: Record<string, string> = {}) =>
    set({ ...table, rows: [...table.rows, { id: newId('r'), cells }] });
  const addColumn = () => {
    const col: Column = { id: newId('c'), name: `Columna ${table.columns.length + 1}`, type: 'text' };
    set({ ...table, columns: [...table.columns, col] });
  };
  const setColumn = (id: string, patch: Partial<Column>) =>
    set({ ...table, columns: table.columns.map((c) => (c.id === id ? { ...c, ...patch } : c)) });
  const dropColumn = (id: string) =>
    set({ ...table, columns: table.columns.filter((c) => c.id !== id), rows: table.rows.map((r) => {
      const { [id]: _gone, ...cells } = r.cells;
      return { ...r, cells };
    }) });
  const selects = table.columns.filter((c) => c.type === 'select');
  const numbers = table.columns.map((c, i) => ({ c, i })).filter(({ c }) => c.type === 'number');

  return (
    <div className="ws-table">
      <div className="ws-table-bar">
        <div className="paper-tabs" role="tablist" aria-label="Vistas">
          {table.views.map((v) => (
            <button
              key={v.id}
              type="button"
              role="tab"
              className="paper-tab"
              aria-selected={v.id === view.id}
              onClick={() => set({ ...table, view: v.id })}
            >
              {(() => {
                const Icon = VIEW_ICON[v.kind] ?? Columns3;
                return <Icon size={12} className="inline mr-1" />;
              })()}
              {v.name}
            </button>
          ))}
          <span className="relative">
            <button type="button" className="paper-tab" onClick={() => setAdding(!adding)} aria-label="Nueva vista" aria-expanded={adding}>
              +
            </button>
            {adding && (
              <div className="nx-menu" role="menu" style={{ top: 30, minWidth: 180 }} onMouseLeave={() => setAdding(false)}>
                {VIEW_KINDS.map((k) => {
                  const Icon = VIEW_ICON[k.key];
                  return (
                    <button
                      key={k.key}
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setAdding(false);
                        const v: TableView = { id: newId('v'), name: k.label, kind: k.key, ...(k.key === 'board' ? { groupBy: selects[0]?.id } : {}) };
                        set({ ...table, views: [...table.views, v], view: v.id });
                      }}
                    >
                      <Icon size={15} /> {k.label}
                    </button>
                  );
                })}
              </div>
            )}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button type="button" className="mac-icon-btn" onClick={() => setRulesOpen(!rulesOpen)} aria-label="Automatizaciones" title="Automatizaciones" aria-pressed={rulesOpen}>
            <Zap size={14} strokeWidth={1.5} fill={table.rules?.some((x) => x.on) ? 'currentColor' : 'none'} />
          </button>
          <button type="button" className="mac-icon-btn" onClick={() => setTools(!tools)} aria-label="Filtrar y ordenar" aria-pressed={tools}>
            <Filter size={14} strokeWidth={1.5} />
          </button>
          {onShareView && (
            <button type="button" className="mac-icon-btn" onClick={() => onShareView(view.id)} aria-label="Compartir esta vista" title="Compartir esta vista">
              <Share2 size={14} strokeWidth={1.5} />
            </button>
          )}
          <button type="button" className="nx-new-btn" onClick={() => addRow()}>
            Nuevo
          </button>
        </div>
      </div>

      {tools && (
        <div className="ws-table-tools">
          <label>
            Vista
            <input className="ws-mini-input" style={{ width: 110 }} value={view.name} onChange={(e) => setView({ name: e.target.value })} />
          </label>
          <label>
            Tipo
            <select
              className="ws-mini-input"
              value={view.kind}
              onChange={(e) => {
                const kind = e.target.value as TableView['kind'];
                // A view still called by its kind («Tabla», «Vista 2») takes the new kind's name.
                const generic = VIEW_KINDS.some((k) => k.label === view.name) || /^Vista \d+$/.test(view.name);
                setView({
                  kind,
                  groupBy: view.groupBy || selects[0]?.id,
                  ...(generic ? { name: VIEW_KINDS.find((k) => k.key === kind)?.label ?? view.name } : {}),
                });
              }}
            >
              {VIEW_KINDS.map((k) => (
                <option key={k.key} value={k.key}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <Filter size={12} /> Si
            <select className="ws-mini-input" value={view.filter?.column || ''} onChange={(e) => setView({ filter: e.target.value ? { column: e.target.value, op: view.filter?.op || 'is', value: view.filter?.value || '' } : null })}>
              <option value="">(sin filtro)</option>
              {table.columns.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            {view.filter && (
              <>
                <select className="ws-mini-input" value={view.filter.op} onChange={(e) => setView({ filter: { ...view.filter!, op: e.target.value as 'is' } })}>
                  <option value="is">es</option>
                  <option value="not">no es</option>
                  <option value="contains">contiene</option>
                  <option value="gt">mayor que</option>
                  <option value="lt">menor que</option>
                </select>
                <input className="ws-mini-input" style={{ width: 96 }} value={view.filter.value} onChange={(e) => setView({ filter: { ...view.filter!, value: e.target.value } })} aria-label="Valor del filtro" />
              </>
            )}
          </label>
          <label>
            <ArrowUpDown size={12} /> Orden
            <select className="ws-mini-input" value={view.sort?.column || ''} onChange={(e) => setView({ sort: e.target.value ? { column: e.target.value, dir: view.sort?.dir || 'asc' } : null })}>
              <option value="">(como están)</option>
              {table.columns.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            {view.sort && (
              <select className="ws-mini-input" value={view.sort.dir} onChange={(e) => setView({ sort: { ...view.sort!, dir: e.target.value as 'asc' } })}>
                <option value="asc">↑</option>
                <option value="desc">↓</option>
              </select>
            )}
          </label>
          {view.kind === 'board' && (
            <label>
              Agrupar por
              <select className="ws-mini-input" value={view.groupBy || ''} onChange={(e) => setView({ groupBy: e.target.value })}>
                {selects.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      {rulesOpen && <RulesEditor table={table} onChange={set} onClose={() => setRulesOpen(false)} />}
      {blank && <AiTable onTable={(t) => set(t)} />}
      {view.kind === 'dashboard' ? (
        <DashboardView table={table} rows={rows} />
      ) : view.kind === 'timeline' ? (
        <TimelineView table={table} />
      ) : view.kind === 'list' ? (
        <ListView table={table} rows={rows} />
      ) : view.kind === 'gallery' ? (
        <GalleryView table={table} rows={rows} />
      ) : view.kind === 'calendar' ? (
        <CalendarView
          table={table}
          rows={rows}
          dateColumn={table.columns.find((c) => c.type === 'date')}
          onAdd={addRow}
          onMove={(rowId, iso) => {
            const date = table.columns.find((c) => c.type === 'date');
            if (date) setCell(rowId, date.id, iso);
          }}
          onRename={(rowId, title) => setCell(rowId, table.columns[0].id, title)}
        />
      ) : view.kind === 'board' && view.groupBy && table.columns.find((c) => c.id === view.groupBy) ? (
        <Board table={table} rows={rows} groupBy={table.columns.find((c) => c.id === view.groupBy)!} onSet={setCell} onAdd={addRow} />
      ) : (
        <div className="ws-grid-scroll">
          <table className="ws-grid">
            <thead>
              <tr>
                <th className="ws-rownum" />
                {table.columns.map((c, i) => (
                  <th key={c.id}>
                    <span className="ws-letter">{columnLetter(i)}</span>
                    <ColumnHead column={c} first={i === 0} onChange={(patch) => setColumn(c.id, patch)} onDrop={() => dropColumn(c.id)} />
                  </th>
                ))}
                <th className="ws-add">
                  <button type="button" className="mac-icon-btn" onClick={addColumn} aria-label="Añadir columna">
                    <Plus size={14} strokeWidth={1.5} />
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const index = all.indexOf(r);
                return (
                  <tr key={r.id} data-picked={picked.includes(r.id) || undefined}>
                    <td className="ws-rownum">
                      <label className="ws-pick" title="Elegir fila">
                        <input
                          type="checkbox"
                          checked={picked.includes(r.id)}
                          onChange={(e) => setPicked(e.target.checked ? [...picked, r.id] : picked.filter((x) => x !== r.id))}
                          aria-label={`Elegir fila ${index + 1}`}
                        />
                        <span>{index + 1}</span>
                      </label>
                    </td>
                    {table.columns.map((c, ci) => (
                      <td key={c.id}>
                        <Cell table={table} row={r} rowIndex={index} colIndex={ci} column={c} onSet={(v) => setCell(r.id, c.id, v)} />
                      </td>
                    ))}
                    <td className="ws-add">
                      <button
                        type="button"
                        className="mac-icon-btn ws-row-delete"
                        onClick={() => set({ ...table, rows: table.rows.filter((x) => x.id !== r.id) })}
                        aria-label={`Borrar fila ${index + 1}`}
                      >
                        <Trash2 size={13} strokeWidth={1.5} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            {rows.length > 1 && (
              <tfoot>
                <tr>
                  <td className="ws-rownum" />
                  {table.columns.map((c, ci) => (
                    <td key={c.id} className="ws-sum">
                      {ci === 0 ? '' : rollup(table, c.id)}
                    </td>
                  ))}
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
      <div className="ws-table-foot">
        <button type="button" className="paper-tab" onClick={() => addRow()}>
          + Nuevo
        </button>
        {picked.length > 0 && onShareRows && (
          <button type="button" className="paper-tab" onClick={() => onShareRows(picked)}>
            Compartir {picked.length} {picked.length === 1 ? 'fila' : 'filas'}
          </button>
        )}
        <FormulaWords table={table} onChange={set} />
      </div>
    </div>
  );
}

function ColumnHead({ column, first, onChange, onDrop }: { column: Column; first?: boolean; onChange: (p: Partial<Column>) => void; onDrop: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="ws-col-head">
      <span className="nx-col-type" aria-hidden="true">
        {first ? <Type size={14} /> : (() => {
          const Icon = TYPE_ICON[column.type] ?? TextIcon;
          return <Icon size={14} />;
        })()}
      </span>
      <input value={column.name} onChange={(e) => onChange({ name: e.target.value })} aria-label="Nombre de la columna" />
      <button type="button" className="ws-col-menu" onClick={() => setOpen(!open)} aria-label={`Opciones de ${column.name}`}>
        ⋯
      </button>
      {open && (
        <span className="ws-pop" role="menu">
          <span className="paper-label">Tipo</span>
          {TYPES.map((t) => (
            <button
              key={t.key}
              type="button"
              role="menuitemradio"
              aria-checked={column.type === t.key}
              onClick={() =>
                onChange({
                  type: t.key,
                  options: t.key === 'select' || t.key === 'multi' ? column.options || ['Por hacer', 'En curso', 'Hecho'] : column.options,
                })
              }
            >
              {column.type === t.key ? '● ' : ''}
              {t.label}
            </button>
          ))}
          {(column.type === 'select' || column.type === 'multi') && (
            <label className="block mt-2">
              <span className="paper-label">Opciones (separadas por comas)</span>
              <input
                className="ws-mini-input w-full"
                value={(column.options || []).join(', ')}
                onChange={(e) => onChange({ options: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })}
              />
            </label>
          )}
          <button type="button" role="menuitem" onClick={onDrop} style={{ color: 'var(--color-error)' }}>
            Borrar columna
          </button>
          <button type="button" role="menuitem" onClick={() => setOpen(false)}>
            Cerrar
          </button>
        </span>
      )}
    </span>
  );
}

function Board({
  table,
  rows,
  groupBy,
  onSet,
  onAdd,
}: {
  table: TableData;
  rows: Row[];
  groupBy: Column;
  onSet: (rowId: string, colId: string, value: string) => void;
  onAdd: (cells: Record<string, string>) => void;
}) {
  const title = table.columns[0];
  const lanes = [...(groupBy.options || []), ''];
  return (
    <div className="ws-board">
      {lanes.map((lane) => {
        const items = rows.filter((r) => (r.cells[groupBy.id] || '') === lane);
        if (!lane && !items.length) return null;
        return (
          <div key={lane || '_'} className="ws-lane">
            <div className="flex items-center gap-2 mb-2 text-[14px]">
              <span className="nx-tag" data-tag={lane ? tagColor(lane) : 'gray'}>
                {lane || 'Sin estado'}
              </span>
              <span style={{ color: 'var(--nx-text-3, inherit)' }}>{items.length}</span>
            </div>
            {items.map((r) => (
              <div key={r.id} className="ws-board-card">
                <input
                  className="ws-cell"
                  value={r.cells[title.id] || ''}
                  placeholder="Sin nombre"
                  onChange={(e) => onSet(r.id, title.id, e.target.value)}
                  aria-label={title.name}
                />
                <select className="ws-cell text-[11.5px]" value={lane} onChange={(e) => onSet(r.id, groupBy.id, e.target.value)} aria-label={groupBy.name}>
                  {lanes.map((l) => (
                    <option key={l || '_'} value={l}>
                      {l || 'Sin estado'}
                    </option>
                  ))}
                </select>
              </div>
            ))}
            <button type="button" className="paper-tab text-[14px]" onClick={() => onAdd({ [groupBy.id]: lane })}>
              + Nueva
            </button>
          </div>
        );
      })}
    </div>
  );
}
