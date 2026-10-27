// The usage panel: how much of today's limit each thing has used, in
// percentages anyone can read («Mensajes 34 %»). From GET /v1/plans/me.

import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';
import { overallPercent, percentUsed, type Me } from '../lib/plans';

export function UsageMeters({ compact = false }: { compact?: boolean }) {
  const [usage, setUsage] = useState<Me['usage'] | null>(null);
  const [plan, setPlan] = useState('');

  useEffect(() => {
    let live = true;
    const load = () =>
      apiFetch('/v1/plans/me')
        .then((r) => (r.ok ? r.json() : null))
        .then((d: Me | null) => {
          if (!live || !d) return;
          setUsage(d.usage);
          setPlan(d.account?.plan_name || '');
        })
        .catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 60_000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);

  if (!usage) return null;
  const total = overallPercent(usage.items);
  return (
    <section className={`usage-meters${compact ? ' compact' : ''}`} aria-label="Uso de hoy">
      <div className="usage-meters-head">
        <b>{total} %</b>
        <span>de su uso de hoy{plan ? ` · Plan ${plan}` : ''}</span>
      </div>
      <ul>
        {usage.items.map((item) => {
          const pct = percentUsed(item);
          return (
            <li key={item.kind}>
              <span className="usage-meters-label">{item.label}</span>
              <span
                className="usage-meters-bar"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={pct}
                aria-label={item.label}
              >
                <i style={{ width: `${pct}%` }} />
              </span>
              <span className="usage-meters-pct">{pct} %</span>
            </li>
          );
        })}
      </ul>
      {!compact && (
        <p className="usage-meters-note">
          {usage.blocking
            ? 'Al llegar al 100 % se espera a mañana o se sube de plan.'
            : 'En su propio equipo nada se bloquea: solo se cuenta.'}
        </p>
      )}
    </section>
  );
}
