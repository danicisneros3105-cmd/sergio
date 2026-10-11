import { describe, expect, it } from 'vitest';
import { columnLetter, computeCell, evaluateFormula, letterIndex, toNumber } from './formula';
import type { TableData } from './model';

function table(rows: string[][], names = ['Nombre', 'Precio', 'Cantidad', 'Total']): TableData {
  const columns = names.map((name, i) => ({ id: `c${i}`, name, type: (i === 0 ? 'text' : 'number') as 'text' | 'number' }));
  return {
    columns,
    rows: rows.map((cells, r) => ({ id: `r${r}`, cells: Object.fromEntries(cells.map((v, i) => [`c${i}`, v])) })),
    views: [{ id: 'v', name: 'Tabla', kind: 'table' }],
    view: 'v',
  };
}

describe('formulas', () => {
  const t = table([
    ['Café', '2,5', '4', '={Precio} * {Cantidad}'],
    ['Pan', '1.234,5', '2', '=B2*C2'],
    ['Té', '3', '', '=SUMA({Total})'],
  ]);

  it('reads numbers people type', () => {
    expect(toNumber('2,5')).toBe(2.5);
    expect(toNumber('1.234,5')).toBe(1234.5);
    expect(toNumber('1234.5')).toBe(1234.5);
    expect(toNumber('12 €')).toBe(12);
    expect(toNumber('abc')).toBeNull();
    expect(toNumber('')).toBeNull();
  });

  it('computes named columns, A1 cells and whole-column aggregates', () => {
    expect(computeCell(t, 0, 3)).toBe('10');
    expect(computeCell(t, 1, 3)).toBe('2469');
    // a total row in the same column leaves itself out
    expect(computeCell(t, 2, 3)).toBe('2479');
    expect(evaluateFormula(t, 0, '=SUM(D1:D2)')).toBe('2479');
    expect(evaluateFormula(t, 0, '=PROMEDIO(C:C)')).toBe('3');
    expect(evaluateFormula(t, 0, '=CONTAR({Nombre})')).toBe('3');
    expect(evaluateFormula(t, 0, '=MAX(B1:B3) - MIN(B:B)')).toBe('1232');
  });

  it('handles text, logic, rounding and errors', () => {
    expect(evaluateFormula(t, 0, '=SI({Cantidad} > 3, "mucho", "poco")')).toBe('mucho');
    expect(evaluateFormula(t, 1, '=IF({Cantidad} > 3; "mucho"; "poco")')).toBe('poco');
    expect(evaluateFormula(t, 0, '={Nombre} & " x" & {Cantidad}')).toBe('Café x4');
    expect(evaluateFormula(t, 0, '=REDONDEAR(10/3, 2)')).toBe('3.33');
    expect(evaluateFormula(t, 0, '=2^3^2')).toBe('512');
    expect(evaluateFormula(t, 0, '=-(2+3)*2')).toBe('-10');
    expect(evaluateFormula(t, 0, '=1/0')).toBe('#DIV/0');
    expect(evaluateFormula(t, 0, '={No existe}')).toBe('#REF');
    expect(evaluateFormula(t, 0, '=Z9')).toBe('#REF');
    expect(evaluateFormula(t, 0, '=SUM(')).toBe('#ERROR');
    expect(evaluateFormula(t, 0, '=alert(1)')).toBe('#ERROR');
    expect(evaluateFormula(t, 0, '=DIAS("2026-10-10", "2026-10-01")')).toBe('9');
    expect(evaluateFormula(t, 0, '=Y(VERDADERO, NO(FALSO))')).toBe('VERDADERO');
  });

  it('archived rows drop out and plain cells show as typed', () => {
    const u = table([['a', '1'], ['b', '2'], ['c', '=SUM(B:B)']], ['N', 'V']);
    u.rows[1].archived = true;
    expect(computeCell(u, 1, 1)).toBe('1'); // B:B without itself and the archived row
    u.rows[0].cells.c1 = '=C1';
    expect(computeCell(u, 0, 1)).toBe('#REF');
    u.rows[0].cells.c1 = '=B2';
    u.rows[2].cells.c1 = '=B1';
    expect(computeCell(u, 0, 1)).toBe('#CICLO'); // a real loop is still a loop
    expect(computeCell(u, 0, 0)).toBe('a');
  });

  it('column letters round-trip', () => {
    expect(letterIndex('A')).toBe(0);
    expect(letterIndex('AA')).toBe(26);
    expect(columnLetter(0)).toBe('A');
    expect(columnLetter(27)).toBe('AB');
  });
});
