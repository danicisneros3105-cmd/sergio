import { describe, expect, it } from 'vitest';
import { greetingLine } from './greetings';
import { DEFAULT_PERSONAL, type Personal } from './personal';

const at = new Date(2026, 9, 26, 10, 0);
const lines = (p: Personal, kind: 'chat' | 'voice' = 'chat', lang = 'es') =>
  // Every phrase this person can get today (one per three-hour slot).
  new Set(Array.from({ length: 8 }, (_, i) => greetingLine(p, { now: new Date(2026, 9, 26, i * 3, 0), kind, lang })));

describe('greetingLine', () => {
  it('keeps «señor» for the owner by default', () => {
    for (const line of lines(DEFAULT_PERSONAL)) expect(line).toMatch(/señor/);
  });

  it('never uses a gendered word for someone who chose neutral', () => {
    const p: Personal = { ...DEFAULT_PERSONAL, trato: 'neutro', tono_saludo: 'cercano' };
    for (const line of [...lines(p), ...lines({ ...p, tono_saludo: 'formal' }), ...lines({ ...p, tono_saludo: 'divertido' })]) {
      expect(line).not.toMatch(/señor|señora|bienvenid[oa]/i);
    }
  });

  it('uses the name and tú when asked', () => {
    const p: Personal = { ...DEFAULT_PERSONAL, nombre: 'Ana', trato: 'tu', tono_saludo: 'cercano' };
    const all = [...lines(p)];
    expect(all.some((l) => l.includes('Ana'))).toBe(true);
    expect(all.join(' ')).not.toMatch(/\b(le|suyo|usted)\b/);
    expect([...lines(p, 'voice')].some((l) => l.startsWith('El micrófono es tuyo') || l.startsWith('Te escucho'))).toBe(true);
  });

  it('speaks the person\'s language and uses their own phrases', () => {
    const p: Personal = { ...DEFAULT_PERSONAL, nombre: 'Ana', trato: 'nombre', tono_saludo: 'cercano' };
    expect([...lines(p, 'chat', 'en')].join(' ')).toMatch(/Ana|Good to see you|What shall/);
    const own: Personal = { ...p, saludos_propios: ['¡{nombre} ha vuelto!'] };
    expect(greetingLine(own, { now: at })).toBe('¡Ana ha vuelto!');
  });

  it('stays the same for a while', () => {
    const p = { ...DEFAULT_PERSONAL, tono_saludo: 'divertido' as const };
    expect(greetingLine(p, { now: at })).toBe(greetingLine(p, { now: new Date(2026, 9, 26, 11, 59) }));
  });
});
