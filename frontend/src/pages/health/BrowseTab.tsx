import { useEffect, useState } from 'react';
import { ArrowLeft, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { fmt, salud, STATUS_ES, type Catalog, type MetricDetail, type Summary } from '../../lib/salud';
import { DayBars } from './Sparkline';

export function MetricView({ metricKey, onBack, onChanged }: { metricKey: string; onBack: () => void; onChanged: () => void }) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<MetricDetail | null>(null);
  const [value, setValue] = useState('');
  const [goal, setGoal] = useState('');
  const load = () =>
    salud
      .metric(metricKey, days)
      .then((d) => {
        setData(d);
        setGoal(d.goal ? String(d.goal) : '');
      })
      .catch(() => setData(null));
  useEffect(() => {
    void load();
  }, [metricKey, days]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!data) return <p className="paper-meta">Leyendo…</p>;
  const m = data.metric;
  const s = data.summary;
  const values = data.daily.map((d) => d[1]);
  const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  return (
    <div className="salud-detail">
      <button type="button" className="paper-button" data-variant="quiet" onClick={onBack}>
        <ArrowLeft size={14} /> Volver
      </button>
      <h2 className="salud-detail-title">{m.label}</h2>
      <div className="salud-detail-head">
        <div>
          <b>{fmt(s?.value ?? null, m.unit, m.decimals)}</b>
          <span>{s ? `Último día con datos: ${s.day}` : 'Sin datos todavía'}</span>
        </div>
        <div>
          <b>{fmt(avg, m.unit, m.decimals)}</b>
          <span>Media de {days} días</span>
        </div>
        {s?.status && (
          <div>
            <b>{STATUS_ES[s.status]}</b>
            <span>{m.low != null || m.high != null ? `Rango: ${m.low ?? '…'} – ${m.high ?? '…'} ${m.unit}` : ''}</span>
          </div>
        )}
      </div>
      <div className="node-seg" role="radiogroup" aria-label="Periodo">
        {[7, 30, 90, 365].map((d) => (
          <button key={d} type="button" role="radio" aria-checked={days === d} onClick={() => setDays(d)}>
            {d === 365 ? '1 año' : `${d} días`}
          </button>
        ))}
      </div>
      {data.daily.length ? <DayBars points={data.daily} goal={data.goal} /> : <p className="paper-meta">Sin datos en este periodo.</p>}
      {m.guide && <p className="salud-guide">{m.guide}</p>}
      <div className="salud-add">
        <input className="paper-input" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder={`Añadir un valor (${m.unit || 'número'})`} aria-label="Nuevo valor" />
        <button
          type="button"
          className="paper-button"
          disabled={!value.trim()}
          onClick={async () => {
            try {
              await salud.add(m.key, Number(value.replace(',', '.')));
              setValue('');
              await load();
              onChanged();
            } catch (e) {
              toast.error(e instanceof Error ? e.message : 'No se pudo.');
            }
          }}
        >
          Añadir
        </button>
        <input className="paper-input" inputMode="decimal" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Meta diaria" aria-label="Meta" />
        <button
          type="button"
          className="paper-button"
          data-variant="quiet"
          onClick={async () => {
            await salud.goal(m.key, goal.trim() ? Number(goal.replace(',', '.')) : null);
            toast.success(goal.trim() ? 'Meta guardada.' : 'Meta quitada.');
            await load();
            onChanged();
          }}
        >
          Guardar meta
        </button>
      </div>
      {data.readings.length > 0 && (
        <section className="salud-block">
          <h3 className="paper-label">Últimos registros</h3>
          <ul className="salud-readings">
            {data.readings.map((r) => (
              <li key={r.uid}>
                <span>{new Date(r.at * 1000).toLocaleString('es', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
                <b>{fmt(r.value, m.unit, m.decimals)}</b>
                <em>{r.source}</em>
                <button
                  type="button"
                  className="mac-icon-btn"
                  aria-label="Borrar este registro"
                  onClick={async () => {
                    await salud.remove(r.uid);
                    await load();
                    onChanged();
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function BrowseTab({ catalog, summary, onOpen }: { catalog: Catalog; summary: Summary; onOpen: (key: string) => void }) {
  const [q, setQ] = useState('');
  const query = q.trim().toLowerCase();
  return (
    <div className="salud-browse">
      <label className="salud-search">
        <Search size={15} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar una medida" aria-label="Buscar una medida" />
      </label>
      {catalog.categories.map((c) => {
        const metrics = catalog.metrics.filter((m) => m.category === c.key && (!query || m.label.toLowerCase().includes(query)));
        if (!metrics.length) return null;
        return (
          <section key={c.key} className="salud-block">
            <h2 className="paper-label">{c.label}</h2>
            <div className="salud-list">
              {metrics.map((m) => {
                const s = summary.metrics[m.key];
                return (
                  <button key={m.key} type="button" className="salud-row" onClick={() => onOpen(m.key)}>
                    <span>{m.label}</span>
                    <b>{s ? fmt(s.value, m.unit, m.decimals) : '—'}</b>
                    <em>{s ? s.day : 'Sin datos'}</em>
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
