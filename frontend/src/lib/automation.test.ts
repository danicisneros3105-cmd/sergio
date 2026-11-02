import { describe, expect, it } from 'vitest';
import { problem, sentence, TEMPLATES, toRoutine, whenText, WEEKDAYS } from './automation';

describe('automations in three choices', () => {
  it('says when in plain words', () => {
    expect(whenText({ kind: 'at', at: '09:00', days: WEEKDAYS })).toBe('De lunes a viernes a las 09:00');
    expect(whenText({ kind: 'at', at: '08:00', days: [0, 1, 2, 3, 4, 5, 6] })).toBe('Cada día a las 08:00');
    expect(whenText({ kind: 'every', minutes: 180 })).toBe('Cada 3 horas');
    expect(whenText({ kind: 'web', url: 'https://www.tienda.com/x', minutes: 60 })).toContain('tienda.com');
  });

  it('turns a simple one into one task and a complex one into ordered steps', () => {
    expect(toRoutine({ node: 'n', when: { kind: 'every', minutes: 60 }, steps: ['  revisa  el correo '] })).toEqual({
      task: 'revisa el correo',
      every_minutes: 60,
    });
    const many = toRoutine({ node: 'n', when: { kind: 'at', at: '08:00', days: [4, 0] }, steps: ['uno', '', 'dos'] });
    expect(many.task).toContain('1. uno\n2. dos');
    expect(many.days).toEqual([0, 4]);
  });

  it('a page watch needs a real address and never checks faster than every 15 min', () => {
    const d = { node: 'n', when: { kind: 'web' as const, url: 'tienda', minutes: 5 }, steps: ['avísame'] };
    expect(problem(d)).toMatch(/https/);
    const ok = { ...d, when: { kind: 'web' as const, url: 'https://tienda.com/p', minutes: 5 } };
    expect(problem(ok)).toBe('');
    expect(toRoutine(ok)).toMatchObject({ kind: 'web', every_minutes: 15 });
  });

  it('every template can be created as it is (only the page watch needs its address)', () => {
    for (const t of TEMPLATES) {
      const p = problem({ node: 'n', when: t.when, steps: t.steps });
      expect(t.when.kind === 'web' ? p : '').toBe(p);
    }
    expect(sentence({ node: 'n', when: { kind: 'every', minutes: 60 }, steps: ['a', 'b'] }, 'Rihno')).toBe(
      'Cada hora, Rihno: 1) a; 2) b',
    );
  });

  it('a template that writes a message only drafts it', () => {
    for (const t of TEMPLATES)
      for (const s of t.steps) if (/mensaje|correo para/i.test(s)) expect(s).toMatch(/no lo envíes/i);
  });
});
