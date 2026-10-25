import { describe, expect, it } from 'vitest';
import { TEMPLATES } from './model';

describe('professional templates', () => {
  it('every template makes a page with real blocks', () => {
    for (const t of TEMPLATES) {
      const page = t.make();
      expect(page.blocks.length, t.key).toBeGreaterThan(0);
    }
  });

  it('tables carry their own columns and a board when there are stages', () => {
    const crm = TEMPLATES.find((t) => t.key === 'crm')!.make();
    const table = crm.blocks.find((b) => b.type === 'table')!.table!;
    expect(table.columns.map((c) => c.name)).toEqual(['Cliente', 'Etapa', 'Valor', 'Próximo paso', 'Fecha', 'Correo', 'Teléfono']);
    const stage = table.columns.find((c) => c.name === 'Etapa')!;
    expect(table.views.find((v) => v.kind === 'board')?.groupBy).toBe(stage.id);
    expect(table.views.some((v) => v.kind === 'calendar')).toBe(true);
    expect(table.rows[0].cells[stage.id]).toBe('Contacto');
  });

  it('each new page gets fresh ids', () => {
    const okr = TEMPLATES.find((t) => t.key === 'okr')!;
    const a = okr.make().blocks.map((b) => b.id);
    const b = okr.make().blocks.map((x) => x.id);
    expect(a.some((id) => b.includes(id))).toBe(false);
  });
});
