import { useEffect, useState } from 'react';
import { fmt, salud, STATUS_ES, type Area } from '../../lib/salud';

const STATE_ES: Record<Area['state'], string> = { en_rango: 'En rango', atencion: 'Para mirar', sin_datos: 'Sin datos' };

export function LongevityTab({ onOpen }: { onOpen: (key: string) => void }) {
  const [areas, setAreas] = useState<Area[] | null>(null);
  useEffect(() => {
    salud.longevity().then(setAreas).catch(() => setAreas([]));
  }, []);
  if (!areas) return <p className="paper-meta">Leyendo…</p>;
  const counted = areas.filter((a) => a.state !== 'sin_datos');
  const good = counted.filter((a) => a.state === 'en_rango').length;
  return (
    <div className="salud-longevity">
      <p className="salud-lead">
        {counted.length
          ? `${good} de ${counted.length} áreas con datos están en rango en los últimos 30 días.`
          : 'Cuando haya datos de 30 días, aquí verá cómo está en las siete áreas que más pesan a largo plazo.'}
      </p>
      <div className="salud-areas">
        {areas.map((a) => (
          <section key={a.key} className="salud-area" data-state={a.state}>
            <header>
              <b>{a.label}</b>
              <span>{STATE_ES[a.state]}</span>
            </header>
            {a.checks.map((c) => (
              <button key={c.metric} type="button" className="salud-check" onClick={() => onOpen(c.metric)}>
                <span>{c.label}</span>
                <b>{fmt(c.value, c.unit, 1)}</b>
                <em>{STATUS_ES[c.status]}</em>
                <small>{c.guide}</small>
              </button>
            ))}
          </section>
        ))}
      </div>
      <p className="paper-meta">
        Rangos de orientación para adultos según guías públicas. No sustituyen la opinión de su médico, que conoce su edad, su historia y sus análisis.
      </p>
    </div>
  );
}
