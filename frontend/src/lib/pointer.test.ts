import { describe, expect, it } from 'vitest';
import { pointMarks } from './pointer';
import { plainReply } from './plainReply';

describe('Sergio pointer marks', () => {
  it('takes the marks out of the text and keeps the order', () => {
    const { clean, points } = pointMarks('Está en Ajustes. [[señalar: Ajustes | Aquí]] Luego [[senalar:Complementos]]');
    expect(clean).toBe('Está en Ajustes. Luego');
    expect(points).toEqual([
      { target: 'Ajustes', text: 'Aquí' },
      { target: 'Complementos', text: undefined },
    ]);
  });

  it('leaves a reply without marks untouched', () => {
    expect(pointMarks('Hola, señor.')).toEqual({ clean: 'Hola, señor.', points: [] });
  });

  it('plainReply never shows the mark', () => {
    const out = plainReply('Toque el botón. [[señalar: Dividir | Este]]');
    expect(out.text).toBe('Toque el botón.');
    expect(out.points[0].target).toBe('Dividir');
  });
});
