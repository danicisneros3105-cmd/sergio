import { describe, expect, it } from 'vitest';
import { SHORTCUTS, fold, innate, rank } from './connectome';

describe('shortcuts (lateral horn and central complex)', () => {
  it('matches Spanish words with or without accents', () => {
    expect(fold('Presión Arterial')).toBe('presion arterial');
    const top = rank('presión')[0];
    expect(top.shortcut.id).toBe('salud:explorar');
    expect(rank('salud mental')[0].shortcut.id).toBe('salud:mente');
    expect(rank('ajustes')[0].shortcut.id).toBe('ajustes');
  });

  it('lets what the owner learned outrank a weaker reflex', () => {
    const plain = rank('tension');
    expect(plain[0].shortcut.id).toBe('salud:explorar');
    const learned = rank('reporte', [{ action: 'salud:explorar', score: 0.9 }]);
    expect(learned[0].shortcut.id).toBe('salud:explorar');
    expect(learned[0].why).toBe('aprendido');
  });

  it('has unique ids and unique key sequences', () => {
    const ids = SHORTCUTS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    const keys = SHORTCUTS.map((s) => s.keys).filter(Boolean);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('never offers messages, calls or purchases', () => {
    const words = SHORTCUTS.flatMap((s) => [s.title, ...s.words]).join(' ').toLowerCase();
    for (const w of ['whatsapp', 'llamar', 'comprar', 'enviar mensaje', 'borrar']) expect(words).not.toContain(w);
    expect(innate('', SHORTCUTS[0])).toBe(0);
  });
});
