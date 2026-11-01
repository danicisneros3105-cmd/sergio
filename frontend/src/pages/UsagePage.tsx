// Usage and models: what Sergio spent per model and provider (every provider,
// not only Gemini), and which providers are connected, without a key or out
// of quota right now. Data from GET /v1/usage.

import { useEffect, useState } from 'react';
import { PaperPage } from '../components/Paper/PaperPage';
import { apiFetch } from '../lib/api';
import { useAppStore } from '../lib/store';
import { UsageMeters } from '../components/UsageMeters';
import './usage.css';

interface UsageRow {
  model: string;
  provider: string;
  calls: number;
  tokens: number;
  cost: number;
  avg_seconds: number;
}

interface Provider {
  key: string;
  name: string;
  state: 'conectado' | 'sin clave' | 'sin cuota' | 'apagado';
  models: string[];
  calls: number;
  cost: number;
}

interface Usage {
  days: number;
  default_model: string;
  totals: { calls: number; tokens: number; cost: number };
  models: UsageRow[];
  providers: Provider[];
  out_of_quota: Array<{ model: string; minutes: number }>;
}

const PERIODS = [
  { days: 1, label: 'Hoy' },
  { days: 7, label: '7 días' },
  { days: 30, label: '30 días' },
];

const fmt = new Intl.NumberFormat('es');
const money = (v: number) => (v > 0 && v < 0.01 ? '< $0,01' : `$${v.toFixed(2).replace('.', ',')}`);

export function UsagePage() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<Usage | null>(null);
  const [problem, setProblem] = useState('');

  useEffect(() => {
    let live = true;
    apiFetch(`/v1/usage?days=${days}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Usage) => {
        if (!live) return;
        setData(d);
        setProblem('');
      })
      .catch(() => live && setProblem('No pude leer el uso. Compruebe que Sergio está en marcha.'));
    return () => {
      live = false;
    };
  }, [days]);

  const names = Object.fromEntries((data?.providers ?? []).map((p) => [p.key, p.name]));

  return (
    <PaperPage title="Uso y modelos" wide>
      <UsageMeters />
      <div className="usage-periods" role="tablist" aria-label="Periodo">
        {PERIODS.map((p) => (
          <button
            key={p.days}
            type="button"
            role="tab"
            aria-selected={days === p.days}
            className="paper-button"
            data-variant={days === p.days ? undefined : 'quiet'}
            onClick={() => setDays(p.days)}
          >
            {p.label}
          </button>
        ))}
      </div>
      {problem && <p className="paper-meta">{problem}</p>}
      {data && (
        <>
          <dl className="usage-totals">
            <div>
              <dt>Respuestas</dt>
              <dd>{fmt.format(data.totals?.calls ?? 0)}</dd>
            </div>
            <div>
              <dt>Tokens</dt>
              <dd>{fmt.format(data.totals?.tokens ?? 0)}</dd>
            </div>
            <div>
              <dt>Costo estimado</dt>
              <dd>{money(data.totals?.cost ?? 0)}</dd>
            </div>
          </dl>

          <section className="salud-block">
            <h2 className="paper-label">Modelos usados</h2>
            {data.models.length ? (
              <table className="usage-table">
                <thead>
                  <tr>
                    <th>Modelo</th>
                    <th>Proveedor</th>
                    <th>Respuestas</th>
                    <th>Tokens</th>
                    <th>Costo</th>
                    <th>Tarda</th>
                  </tr>
                </thead>
                <tbody>
                  {data.models.map((m) => (
                    <tr key={m.model}>
                      <td>
                        {m.model}
                        {m.model === data.default_model && <small> · por defecto</small>}
                      </td>
                      <td>{names[m.provider] ?? m.provider}</td>
                      <td>{fmt.format(m.calls)}</td>
                      <td>{fmt.format(m.tokens)}</td>
                      <td>{money(m.cost)}</td>
                      <td>{m.avg_seconds.toFixed(1).replace('.', ',')} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="cn-learned">Sin uso en este periodo.</p>
            )}
          </section>

          <section className="salud-block">
            <h2 className="paper-label">Proveedores</h2>
            <ul className="usage-providers">
              {data.providers.map((p) => (
                <li key={p.key} data-state={p.state}>
                  <span className="usage-dot" aria-hidden="true" />
                  <b>{p.name}</b>
                  <span>{p.state}</span>
                  <small>{p.models.length ? p.models.join(' · ') : ''}</small>
                </li>
              ))}
            </ul>
            {data.out_of_quota.length > 0 && (
              <p className="cn-learned">
                Sin cuota ahora:{' '}
                {data.out_of_quota.map((q) => `${q.model} (vuelve en ~${q.minutes} min)`).join(', ')}. Sergio usa
                otro modelo mientras tanto.
              </p>
            )}
            <button
              type="button"
              className="paper-button"
              data-variant="quiet"
              onClick={() => useAppStore.getState().setCommandPaletteOpen(true)}
            >
              Cambiar de modelo
            </button>
          </section>
        </>
      )}
    </PaperPage>
  );
}

export default UsagePage;
