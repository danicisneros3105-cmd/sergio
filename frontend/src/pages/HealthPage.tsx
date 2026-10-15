import { useEffect, useState } from 'react';
import { Armchair, Brain, ChartNoAxesColumn, HeartPulse, Moon } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { FIGURES, figureValue, type HealthSummary } from '../lib/paper';
import { PaperPage, PaperSection } from '../components/Paper/PaperPage';
import { DesktopSections, type DesktopSection } from '../components/Paper/DesktopSections';

const SECTIONS: DesktopSection[] = [
  { key: 'health', label: 'Mi salud', meta: 'Cuestionario y registro', icon: HeartPulse },
  { key: 'night', label: 'Luz de noche', meta: 'Sueño y luz', icon: Moon },
  { key: 'gym', label: 'Gimnasio mental', meta: 'Ejercicios de hoy', icon: Brain },
  { key: 'results', label: 'Resultados', meta: 'Su progreso', icon: ChartNoAxesColumn },
  { key: 'consult', label: 'Consulta', meta: 'Hablar con calma', icon: Armchair },
];

export function HealthPage() {
  const [data, setData] = useState<HealthSummary | null>(null);
  const [problem, setProblem] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch('/v1/desktop/health');
        const body = await res.json();
        if (cancelled) return;
        if (res.ok) setData(body as HealthSummary);
        else setProblem(String(body.detail ?? `Error ${res.status}`));
      } catch {
        if (!cancelled) setProblem('No puedo conectar con Sergio.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const figures = data ? FIGURES.map((f) => ({ ...f, value: figureValue(data, f) })).filter((f) => f.value) : [];

  return (
    <PaperPage title="Salud" wide>
      <PaperSection label="Hoy">
        {problem ? (
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            {problem}
          </p>
        ) : !data ? (
          <p className="text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
            Leyendo…
          </p>
        ) : (
          <div className="space-y-5">
            {figures.length > 0 && (
              <dl className="grid grid-cols-2 sm:grid-cols-5 gap-px paper-sheet overflow-hidden" style={{ background: 'var(--color-border)' }}>
                {figures.map((f) => (
                  <div key={f.key} className="px-4 py-3" style={{ background: 'var(--color-surface)' }}>
                    <dt className="paper-label">{f.label}</dt>
                    <dd className="mt-1 text-[22px]" style={{ fontFamily: 'var(--font-display)' }}>
                      {f.value}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            <p className="text-[14.5px] leading-relaxed max-w-2xl">{data.text}</p>
            {(data.report?.metas ?? []).length > 0 && (
              <ul className="text-[13.5px] space-y-1" style={{ color: 'var(--color-text-secondary)' }}>
                {data.report!.metas!.map((m) => (
                  <li key={m}>— {m}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </PaperSection>
      <PaperSection label="Abrir en el PC">
        <DesktopSections sections={SECTIONS} />
      </PaperSection>
    </PaperPage>
  );
}
