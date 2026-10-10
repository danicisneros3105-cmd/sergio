import { describe, expect, it } from 'vitest';
import { FIGURES, figureValue, relativeDay } from '../lib/paper';

describe('health figures', () => {
  it('shows only the numbers it has, with units', () => {
    const data = {
      metrics: { imc: 23.14, gasto_diario: 2350 },
      trends: { sueno_h: { '7d': 7.25 }, pasos: { '7d': 8123 } },
    };
    const shown = Object.fromEntries(FIGURES.map((f) => [f.key, figureValue(data, f)]));
    expect(shown.imc).toBe('23,1');
    expect(shown.gasto_diario).toMatch(/^2\.?350 kcal$/);
    expect(shown.sueno_h).toBe('7,3 h');
    expect(shown.fc_reposo).toBe('');
  });
});

describe('conversation dates', () => {
  it('reads like the e-paper list', () => {
    const now = new Date(2026, 9, 10, 15, 0).getTime();
    expect(relativeDay(new Date(2026, 9, 10, 9, 0).getTime(), now)).toBe('Hoy');
    expect(relativeDay(new Date(2026, 9, 9, 23, 0).getTime(), now)).toBe('Ayer');
    expect(relativeDay(new Date(2026, 9, 6, 12, 0).getTime(), now)).toBe('Hace 4 días');
  });
});
