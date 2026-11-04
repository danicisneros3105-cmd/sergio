// Under the greeting of an empty chat: what Sergio really did this week and
// the one thing left half done, one tap away. Real numbers only; nothing is
// shown when there is nothing (no streaks, no guilt: docs/ENGANCHE-SANO.md).
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { apiFetch } from '../../lib/api';

interface Week {
  semana: string[];
  seguir: { titulo: string; etapa: string; avance: number } | null;
}

export function WeekLine() {
  const [week, setWeek] = useState<Week | null>(null);
  const navigate = useNavigate();
  useEffect(() => {
    apiFetch('/v1/personal/semana')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setWeek({ semana: Array.isArray(d.semana) ? d.semana : [], seguir: d.seguir ?? null }))
      .catch(() => {});
  }, []);
  if (!week || !week.seguir) return null;
  return (
    <div className="week-line">
      {week.seguir && (
        <button type="button" className="week-continue" onClick={() => navigate('/nodes')}>
          Seguir con «{week.seguir.titulo}»
          <span>{Math.round(week.seguir.avance * 100)} %</span>
        </button>
      )}
    </div>
  );
}

export default WeekLine;
