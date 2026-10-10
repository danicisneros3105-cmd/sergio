// Small helpers of the Digital Paper pages (kept apart so tests need no store).

export interface HealthSummary {
  text?: string;
  metrics?: Record<string, number | string>;
  trends?: Record<string, { '7d'?: number; '30d'?: number } | unknown>;
  report?: { resumen?: string; metas?: string[] };
}

// The few numbers worth a glance, with their units.
export const FIGURES: Array<{ key: string; label: string; unit: string; from: 'metrics' | 'trends' }> = [
  { key: 'imc', label: 'IMC', unit: '', from: 'metrics' },
  { key: 'gasto_diario', label: 'Gasto diario', unit: 'kcal', from: 'metrics' },
  { key: 'pasos', label: 'Pasos · 7 días', unit: '', from: 'trends' },
  { key: 'sueno_h', label: 'Sueño · 7 días', unit: 'h', from: 'trends' },
  { key: 'fc_reposo', label: 'Pulso en reposo', unit: 'lpm', from: 'trends' },
];

export function figureValue(data: HealthSummary, f: (typeof FIGURES)[number]): string {
  const raw =
    f.from === 'metrics'
      ? data.metrics?.[f.key]
      : (data.trends?.[f.key] as { '7d'?: number } | undefined)?.['7d'];
  if (raw === undefined || raw === null || raw === '') return '';
  const n = Number(raw);
  const shown = Number.isFinite(n) ? n.toLocaleString('es', { maximumFractionDigits: 1 }) : String(raw);
  return f.unit ? `${shown} ${f.unit}` : shown;
}

export function relativeDay(ms: number, now = Date.now()): string {
  const days = Math.floor((new Date(now).setHours(0, 0, 0, 0) - new Date(ms).setHours(0, 0, 0, 0)) / 86_400_000);
  if (days <= 0) return 'Hoy';
  if (days === 1) return 'Ayer';
  if (days < 7) return `Hace ${days} días`;
  return new Date(ms).toLocaleDateString('es', { day: 'numeric', month: 'short' });
}

