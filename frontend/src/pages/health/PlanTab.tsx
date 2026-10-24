// Comida y ejercicio: Sergio arma una receta o una rutina a su medida (con sus
// datos, sin nombre), y la deja como recordatorio si usted quiere.

import { useState } from 'react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { reminders } from '../../lib/reminders';

interface Plan {
  kind: 'receta' | 'rutina';
  title: string;
  minutes: number | null;
  for: string;
  items: string[];
  steps: string[];
  why: string;
  tip: string;
}

const IDEAS: Record<Plan['kind'], string[]> = {
  receta: ['Desayuno rápido con proteína', 'Cena ligera en 15 minutos', 'Algo dulce y sano'],
  rutina: ['10 minutos en casa sin equipo', 'Caminar y estirar', 'Fuerza para principiantes'],
};

export function PlanTab() {
  const [kind, setKind] = useState<Plan['kind']>('receta');
  const [ask, setAsk] = useState('');
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);

  const make = async (text: string) => {
    setBusy(true);
    setPlan(null);
    try {
      const res = await apiFetch('/v1/healthdata/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind, ask: text }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.detail || 'No pude prepararlo.');
      setPlan((await res.json()) as Plan);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude prepararlo.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="plan">
      <div className="plan-kind" role="tablist" aria-label="Qué quiere">
        {(['receta', 'rutina'] as const).map((k) => (
          <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => (setKind(k), setPlan(null))}>
            {k === 'receta' ? 'Receta' : 'Rutina'}
          </button>
        ))}
      </div>
      <form
        className="plan-ask"
        onSubmit={(e) => {
          e.preventDefault();
          void make(ask);
        }}
      >
        <input
          value={ask}
          onChange={(e) => setAsk(e.target.value)}
          placeholder={kind === 'receta' ? '¿Qué le apetece? Ingredientes, tiempo…' : '¿Cuánto tiempo y dónde?'}
          aria-label="Su pedido"
        />
        <button type="submit" className="paper-button" disabled={busy}>
          {busy ? 'Preparando…' : 'Hacer'}
        </button>
      </form>
      <div className="plan-ideas">
        {IDEAS[kind].map((idea) => (
          <button key={idea} type="button" className="mac-chip" disabled={busy} onClick={() => (setAsk(idea), void make(idea))}>
            {idea}
          </button>
        ))}
      </div>
      {plan && (
        <article className="plan-card">
          <header>
            <h3>{plan.title}</h3>
            <span>{[plan.minutes ? `${plan.minutes} min` : '', plan.for].filter(Boolean).join(' · ')}</span>
          </header>
          {plan.items.length > 0 && (
            <ul className="plan-items">
              {plan.items.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          )}
          <ol className="plan-steps">
            {plan.steps.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ol>
          {plan.why && <p className="plan-why">{plan.why}</p>}
          {plan.tip && <p className="paper-meta">{plan.tip}</p>}
          <button
            type="button"
            className="paper-button"
            data-variant="quiet"
            onClick={async () => {
              await reminders.add({ kind: 'recordatorio', title: plan.title, times: [kind === 'receta' ? '13:00' : '18:00'], detail: plan.steps.join('\n') });
              toast.success('Se lo recordaré cada día. Puede cambiar la hora en Hoy.');
            }}
          >
            Recordármelo cada día
          </button>
        </article>
      )}
    </div>
  );
}
