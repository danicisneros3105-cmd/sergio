import { describe, expect, it } from 'vitest';
import { applySlash, filesIn, slashMatches, timeAgo, workedFor, type ComposerOptions } from './cowork';

const base: ComposerOptions = { autonomy: 'normal', maxActions: 50, planFirst: false };

describe('slash commands', () => {
  it('shows the commands that match what is typed', () => {
    expect(slashMatches('/').length).toBeGreaterThan(3);
    expect(slashMatches('/pl').map((c) => c.cmd)).toEqual(['/plan']);
    expect(slashMatches('hola /plan')).toEqual([]);
  });

  it('applies a command to the options', () => {
    expect(applySlash('/plan', base)?.planFirst).toBe(true);
    expect(applySlash('/cauteloso', base)?.autonomy).toBe('cauteloso');
    expect(applySlash('/tope 120', base)?.maxActions).toBe(120);
    expect(applySlash('/tope 9999', base)?.maxActions).toBe(500);
    expect(applySlash('/nada', base)).toBeNull();
    expect(applySlash('compara portátiles', base)).toBeNull();
  });
});

describe('filesIn', () => {
  it('finds the files a run produced, once each', () => {
    const files = filesIn([
      'Tabla guardada en C:\\Users\\señor\\Documentos\\portatiles.xlsx',
      'Resumen en ~/sergio/informe.md y otra vez portatiles.xlsx',
      'Visité https://example.com/page.html',
    ]);
    expect(files.map((f) => f.name)).toEqual(['portatiles.xlsx', 'informe.md']);
    expect(files[0].path).toContain('Documentos');
    expect(filesIn(['Lo dejé en Documentos/Sergio/tabla.md'])[0].path).toBe('Documentos/Sergio/tabla.md');
  });
});

describe('times', () => {
  it('says how long ago in plain Spanish', () => {
    expect(timeAgo(1000, 1030)).toBe('ahora');
    expect(timeAgo(1000, 1000 + 5 * 60)).toBe('hace 5 min');
    expect(timeAgo(0, 3 * 3600)).toBe('hace 3 h');
    expect(timeAgo(0, 100000)).toBe('ayer');
  });

  it('says how long it worked', () => {
    expect(workedFor(0, 20)).toBe('Trabajó 20 s');
    expect(workedFor(0, 240)).toBe('Trabajó 4 min');
  });
});
