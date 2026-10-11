import { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { computeCell, toNumber } from '../../lib/workspace/formula';
import type { Block, ChartData, TableData } from '../../lib/workspace/model';

// A chart drawn from a table on the same page, in ink and greys (paper has
// no colour to spare): bars, a line, or a pie. Count, sum or average by a
// column, in two clicks.
export function chartRows(table: TableData, chart: ChartData): Array<{ name: string; value: number }> {
  const rows = table.rows.filter((r) => !r.archived);
  const xi = table.columns.findIndex((c) => c.id === chart.x);
  const yi = table.columns.findIndex((c) => c.id === chart.y);
  if (xi < 0) return [];
  const groups = new Map<string, number[]>();
  rows.forEach((_, i) => {
    const key = computeCell(table, i, xi) || '(vacío)';
    const value = yi >= 0 ? toNumber(computeCell(table, i, yi)) ?? 0 : 1;
    groups.set(key, [...(groups.get(key) || []), value]);
  });
  return [...groups].map(([name, values]) => ({
    name,
    value:
      chart.agg === 'count' || yi < 0
        ? values.length
        : chart.agg === 'avg'
          ? Math.round((values.reduce((s, v) => s + v, 0) / values.length) * 100) / 100
          : Math.round(values.reduce((s, v) => s + v, 0) * 100) / 100,
  }));
}

const INKS = ['var(--color-ink)', '#6b6c69', '#9a9b98', '#bfc0bd', '#4a4b48', '#80817e'];

export function ChartBlock({ block, tables, onChange }: { block: Block; tables: Block[]; onChange: (c: ChartData) => void }) {
  const chart = block.chart || { table: tables[0]?.id || '', kind: 'bar', x: '', y: '', agg: 'count' };
  const source = tables.find((t) => t.id === chart.table) || tables[0];
  const table = source?.table;
  const data = useMemo(() => (table ? chartRows(table, { ...chart, table: source!.id }) : []), [table, chart, source]);
  if (!table) {
    return <div className="ws-card text-[13px]">Añada primero una tabla a esta página: el gráfico se dibuja con sus datos.</div>;
  }
  const set = (patch: Partial<ChartData>) => onChange({ ...chart, table: source!.id, ...patch });
  const axis = { stroke: 'var(--color-text-tertiary)', fontSize: 11, tickLine: false };
  return (
    <div className="ws-card">
      <div className="ws-table-tools" style={{ marginBottom: 8 }}>
        <select className="ws-mini-input" value={chart.kind} onChange={(e) => set({ kind: e.target.value as ChartData['kind'] })} aria-label="Tipo de gráfico">
          <option value="bar">Barras</option>
          <option value="line">Líneas</option>
          <option value="pie">Pastel</option>
        </select>
        {tables.length > 1 && (
          <select className="ws-mini-input" value={source!.id} onChange={(e) => set({ table: e.target.value })} aria-label="Tabla">
            {tables.map((t, i) => (
              <option key={t.id} value={t.id}>
                Tabla {i + 1}
              </option>
            ))}
          </select>
        )}
        <label>
          por
          <select className="ws-mini-input" value={chart.x} onChange={(e) => set({ x: e.target.value })} aria-label="Agrupar por">
            <option value="">—</option>
            {table.columns.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <select className="ws-mini-input" value={chart.agg} onChange={(e) => set({ agg: e.target.value as ChartData['agg'] })} aria-label="Cálculo">
          <option value="count">contar</option>
          <option value="sum">sumar</option>
          <option value="avg">promediar</option>
        </select>
        {chart.agg !== 'count' && (
          <select className="ws-mini-input" value={chart.y} onChange={(e) => set({ y: e.target.value })} aria-label="Columna con números">
            <option value="">—</option>
            {table.columns.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        )}
      </div>
      {data.length === 0 ? (
        <div className="text-[13px]" style={{ color: 'var(--color-text-secondary)' }}>Elija una columna para agrupar.</div>
      ) : (
        <div style={{ width: '100%', height: 220 }}>
          <ResponsiveContainer>
            {chart.kind === 'pie' ? (
              <PieChart>
                <Tooltip />
                <Pie data={data} dataKey="value" nameKey="name" innerRadius={48} outerRadius={84} stroke="var(--color-bg)" label={({ name }) => name}>
                  {data.map((_, i) => (
                    <Cell key={i} fill={INKS[i % INKS.length]} />
                  ))}
                </Pie>
              </PieChart>
            ) : chart.kind === 'line' ? (
              <LineChart data={data}>
                <CartesianGrid stroke="var(--color-border-subtle)" vertical={false} />
                <XAxis dataKey="name" {...axis} />
                <YAxis {...axis} width={36} />
                <Tooltip />
                <Line type="monotone" dataKey="value" stroke="var(--color-ink)" strokeWidth={1.5} dot={{ r: 2.5 }} />
              </LineChart>
            ) : (
              <BarChart data={data}>
                <CartesianGrid stroke="var(--color-border-subtle)" vertical={false} />
                <XAxis dataKey="name" {...axis} />
                <YAxis {...axis} width={36} />
                <Tooltip cursor={{ fill: 'var(--color-border-subtle)' }} />
                <Bar dataKey="value" fill="var(--color-ink)" radius={[2, 2, 0, 0]} maxBarSize={36} />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
