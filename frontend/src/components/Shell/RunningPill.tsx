// «En marcha»: everything Sergio is doing in the background (videos, Nodes,
// swarms, channels, trading), one tap away, each with its own Stop button
// (owner, 28 Oct 2026: «el control y las acciones en segundo plano»). It only
// shows when something runs, so a quiet app stays quiet.

import { useCallback, useEffect, useState } from 'react';
import { Activity, Square } from 'lucide-react';
import { apiFetch } from '../../lib/api';
import './running.css';

interface Row {
  tipo: string;
  id: string;
  quien: string;
  que: string;
  detener?: string;
  etapa?: string;
  avance?: number;
}

export function RunningPill() {
  const [rows, setRows] = useState<Row[]>([]);
  const [open, setOpen] = useState(false);
  const load = useCallback(() => {
    apiFetch('/v1/personal/en-marcha')
      .then((r) => (r.ok ? r.json() : { en_marcha: [] }))
      .then((d: { en_marcha?: Row[] }) => setRows(d.en_marcha ?? []))
      .catch(() => setRows([]));
  }, []);
  useEffect(() => {
    load();
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, [load]);

  if (!rows.length) return null;
  const stop = async (row: Row) => {
    if (!row.detener) return;
    try {
      await apiFetch(row.detener, { method: 'POST' });
    } finally {
      load();
    }
  };
  return (
    <div className="run" data-open={open || undefined}>
      {open && (
        <ul className="run-list" aria-label="En marcha">
          {rows.map((r) => (
            <li key={`${r.tipo}-${r.id}`}>
              <span>
                <b>{r.quien}</b>
                <small>
                  {r.que}
                  {r.etapa ? ` · ${r.etapa}` : ''}
                </small>
                {typeof r.avance === 'number' && r.avance > 0 && (
                  <i className="run-bar" style={{ ['--p' as string]: `${Math.round(r.avance * 100)}%` }} />
                )}
              </span>
              {r.detener && (
                <button type="button" aria-label={`Detener ${r.quien}`} title="Detener" onClick={() => void stop(r)}>
                  <Square size={13} strokeWidth={2} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="run-pill" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Activity size={15} strokeWidth={1.8} aria-hidden="true" />
        {rows.length} en marcha
      </button>
    </div>
  );
}
