import { describe, expect, it } from 'vitest';
import { describeStep, type ThinkEvent } from './ThinkPage';

describe('describeStep', () => {
  it('speaks Spanish for every stage', () => {
    const cases: [ThinkEvent, string][] = [
      [{ stage: 'plan', kind: 'math', strategy: 'consistency' }, 'Tipo de pregunta: math · estrategia: Votación entre varias soluciones'],
      [{ stage: 'call', n: 2, step: 'Checking the principles', seconds: 1.5 }, '2. Revisando los principios (1.5 s)'],
      [{ stage: 'call', n: 1, step: '¿A qué hora llega?', seconds: 3 }, '1. ¿A qué hora llega? (3 s)'],
      [{ stage: 'constitution', revised: true, fixed: ['honestidad'] }, 'Corregido por principios: honestidad'],
      [{ stage: 'constitution', revised: false }, 'Cumple los principios'],
      [{ stage: 'confidence', confidence: 0.973 }, 'Seguridad: 97%'],
      [{ stage: 'retry' }, 'Poca seguridad: una ronda más de reflexión'],
      [{ stage: 'error', message: 'Google Gemini rechazó la clave.' }, 'Google Gemini rechazó la clave.'],
    ];
    for (const [event, text] of cases) expect(describeStep(event)).toBe(text);
  });
});
