import { describe, expect, it } from 'vitest';
import {
  applyRules,
  blockDiff,
  datedItems,
  detectRelations,
  evolveTemplate,
  inferTable,
  kpis,
  merge3,
  naturalFormula,
  parseGrid,
  projectRisk,
  relatedPages,
  rollup,
  runButton,
  schedule,
  searchPages,
  staleness,
  submitForm,
  visibleFields,
  wordDiff,
  type Rule,
} from './brain';
import { computeCell } from './formula';
import { block, newPage, type Block, type Page, type TableData } from './model';

const DAY = 86_400_000;
const NOW = Date.parse('2026-10-13T12:00:00');

function page(title: string, texts: string[], extra: Partial<Page> = {}): Page {
  return { ...newPage(title, null, texts.map((t) => block('text', t)), NOW), ...extra };
}

function grid(rows: string[][]): TableData {
  return inferTable(rows);
}

describe('memory and search', () => {
  const pages = [
    page('Reunión con Ana', ['Hablamos del presupuesto de la campaña de otoño']),
    page('Campaña de otoño', ['Objetivo: vender más abrigos. Presupuesto 5000']),
    page('Receta de pan', ['Harina, agua, sal y levadura']),
  ];
  it('finds by meaning and synonyms, not only exact words', () => {
    const hits = searchPages(pages, 'junta presupuesto');
    expect(hits[0].page.title).toBe('Reunión con Ana');
    expect(hits.map((h) => h.page.title)).not.toContain('Receta de pan');
  });
  it('searches inside image captions and audio transcripts', () => {
    const p = page('Fotos', []);
    p.blocks = [block('image', '', { media: { file: 'f_1.png', name: 'x.png', mime: 'image/png', caption: 'una pizarra con el plan de ventas' } })];
    expect(searchPages([...pages, p], 'pizarra')[0].page.title).toBe('Fotos');
  });
  it('relates pages that share a topic', () => {
    const rel = relatedPages(pages, pages[0]);
    expect(rel[0].page.title).toBe('Campaña de otoño');
  });
});

describe('databases', () => {
  it('builds a typed table from pasted rows', () => {
    const t = inferTable(parseGrid('Nombre,Precio,Estado,Fecha,Correo\nPan,1.5,Hecho,13/10/2026,a@b.co\nLeche,2,Por hacer,2026-10-20,c@d.co\nQueso,7,Hecho,2026-10-21,e@f.co'));
    expect(t.columns.map((c) => c.type)).toEqual(['text', 'number', 'select', 'date', 'email']);
    expect(t.rows[0].cells[t.columns[3].id]).toBe('2026-10-13');
    expect(t.views.map((v) => v.kind)).toEqual(['table', 'board', 'calendar']);
  });
  it('reads Markdown tables', () => {
    expect(parseGrid('| a | b |\n|---|---|\n| 1 | 2 |')).toEqual([['a', 'b'], ['1', '2']]);
  });
  it('detects relations nobody configured', () => {
    const people = page('Equipo', []);
    people.blocks = [block('table', '', { table: grid([['Nombre', 'Rol'], ['Ana', 'Diseño'], ['Luis', 'Ventas'], ['Eva', 'Dev']]) })];
    const tasks = page('Tareas', []);
    tasks.blocks = [block('table', '', { table: grid([['Tarea', 'Responsable'], ['Logo', 'Ana'], ['Web', 'Eva'], ['Precios', 'Luis']]) })];
    const hints = detectRelations([people, tasks]);
    expect(hints).toHaveLength(1);
    expect(hints[0].column.name).toBe('Responsable');
    expect(hints[0].target.kind).toBe('table');
  });
  it('rolls up each column the right way', () => {
    const t = grid([['Cosa', 'Precio', 'Estado', 'Listo'], ['a', '2', 'Hecho', 'sí'], ['b', '4', 'Hecho', 'no'], ['c', '6', 'En curso', 'no']]);
    expect(rollup(t, t.columns[1].id)).toBe('Σ 12 · x̄ 4');
    expect(rollup(t, t.columns[2].id)).toBe('Hecho 2 · En curso 1');
    expect(rollup(t, t.columns[3].id)).toBe('33 % hecho');
  });
  it('turns sentences into formulas the parser computes', () => {
    const t = grid([['Cosa', 'Precio', 'Cantidad'], ['a', '2', '3'], ['b', '4', '5']]);
    const f1 = naturalFormula('precio por cantidad', t);
    expect(f1).toBe('={Precio} * {Cantidad}');
    const f2 = naturalFormula('la suma de precio', t);
    expect(f2).toBe('=SUMA({Precio})');
    const f3 = naturalFormula('si precio mayor que 3 entonces caro si no barato', t);
    expect(f3).toBe('=SI({Precio} > 3, "caro", "barato")');
    t.columns.push({ id: 'cx', name: 'Total', type: 'text' });
    t.rows[0].cells.cx = f1;
    t.rows[1].cells.cx = f3;
    expect(computeCell(t, 0, 3)).toBe('6');
    expect(computeCell(t, 1, 3)).toBe('caro');
    expect(naturalFormula('baila conmigo', t)).toBe('');
  });
});

describe('projects', () => {
  const t = grid([
    ['Tarea', 'Duración', 'Depende de', 'Fecha', 'Estado', 'Responsable', 'Presupuesto', 'Gastado'],
    ['Diseño', '3', '', '2026-10-10', 'En curso', 'Ana', '1000', '900'],
    ['Web', '5', 'Diseño', '2026-10-18', 'Por hacer', 'Eva', '2000', '0'],
    ['Lanzamiento', '1', 'Web', '2026-10-20', 'Por hacer', '', '500', '0'],
    ['Logo', '1', '', '2026-10-30', 'Hecho', 'Ana', '200', '250'],
  ]);
  it('schedules by dependencies and finds the critical path', () => {
    const s = schedule(t, NOW);
    const by = Object.fromEntries(s.tasks.map((x) => [x.name, x]));
    expect(by.Web.start).toBe(by['Diseño'].end);
    expect(by.Lanzamiento.start).toBe(by.Web.end);
    expect(by.Lanzamiento.critical).toBe(true);
    expect(by.Logo.slack).toBeGreaterThan(0);
    expect(s.cycle).toEqual([]);
  });
  it('predicts the delay, the budget and the risks', () => {
    const r = projectRisk(t, NOW);
    expect(r.delayDays).toBeGreaterThan(0);
    expect(r.risks[0].level).toBe('alto');
    expect(r.risks.find((x) => x.name === 'Diseño')!.reasons).toContain('vencida');
    expect(r.risks.find((x) => x.name === 'Lanzamiento')!.reasons).toContain('sin responsable');
    expect(r.budget!.forecast).toBeGreaterThan(r.budget!.spent);
    expect(r.needs.some((n) => n.includes('entrega'))).toBe(true);
  });
  it('reports dependency loops', () => {
    const loop = grid([['Tarea', 'Depende de'], ['A', 'B'], ['B', 'A'], ['C', '']]);
    expect(schedule(loop, NOW).cycle.sort()).toEqual(['A', 'B']);
  });
});

describe('wikis', () => {
  it('says what to verify and why', () => {
    const old = page('Política', ['Vigente desde 2023. Próximamente cambiará. Ver [[Manual]]'], { updatedAt: NOW - 200 * DAY });
    const s = staleness(old, [old], NOW);
    expect(s.score).toBeGreaterThan(0.5);
    expect(s.reasons.join(' ')).toMatch(/sin revisar.*2023.*Manual/s);
    expect(staleness({ ...old, verifiedAt: NOW, blocks: [block('text', 'ok')] }, [old], NOW).score).toBe(0);
  });
});

describe('automations', () => {
  it('fires on the change into the condition (AND / OR) and runs its actions', () => {
    const t = grid([['Tarea', 'Estado', 'Prioridad'], ['a', 'Por hacer', 'Alta'], ['b', 'Por hacer', 'Baja'], ['c', 'Hecho', 'Alta']]);
    const [, status, prio] = t.columns;
    const rule: Rule = {
      id: 'r1',
      name: 'Alta hecha',
      on: true,
      any: false,
      when: [
        { column: status.id, op: 'is', value: 'hecho' },
        { column: prio.id, op: 'is', value: 'alta' },
      ],
      then: [
        { kind: 'todo', text: 'Avisar del cierre de {Tarea}' },
        { kind: 'set', column: prio.id, value: 'Cerrada' },
      ],
    };
    const before = t.rows[0];
    const after = { ...t, rows: t.rows.map((r, i) => (i === 0 ? { ...r, cells: { ...r.cells, [status.id]: 'Hecho' } } : r)) };
    const fx = applyRules(after, [rule], before.id, before);
    expect(fx.todos).toEqual(['Avisar del cierre de a']);
    expect(fx.table.rows[0].cells[prio.id]).toBe('Cerrada');
    // an edit to a row that already matched does not fire again
    const again = applyRules(after, [rule], t.rows[2].id, t.rows[2]);
    expect(again.todos).toEqual([]);
  });
});

describe('forms and buttons', () => {
  const t = grid([['Nombre', 'Tipo', 'Empresa', 'Correo'], ['x', 'Persona', '', 'x@y.co'], ['y', 'Empresa', 'Z', 'y@z.co'], ['z', 'Persona', '', 'z@z.co']]);
  const [name, kind, company, mail] = t.columns;
  const spec = {
    table: 'b',
    title: 'Alta',
    fields: [
      { column: name.id, required: true },
      { column: kind.id },
      { column: company.id, required: true, showIf: { column: kind.id, op: 'is' as const, value: 'Empresa' } },
      { column: mail.id },
    ],
  };
  it('shows fields only when their condition holds and validates', () => {
    expect(visibleFields(spec, t, { [kind.id]: 'Persona' })).toHaveLength(3);
    expect(visibleFields(spec, t, { [kind.id]: 'Empresa' })).toHaveLength(4);
    expect(submitForm(spec, t, { [kind.id]: 'Empresa', [mail.id]: 'mal' }).errors).toEqual({ [name.id]: 'Obligatorio', [company.id]: 'Obligatorio', [mail.id]: 'Un correo válido' });
    const ok = submitForm(spec, t, { [name.id]: 'Ana', [kind.id]: 'Persona', [company.id]: 'oculto' });
    expect(ok.table!.rows[ok.table!.rows.length - 1].cells[company.id]).toBe(''); // hidden fields are not saved
  });
  it('buttons run their steps and leave the model ones to the caller', () => {
    const p = page('P', ['hola']);
    const at = p.blocks[0].id;
    const out = runButton(p, at, { label: 'Diario', steps: [{ kind: 'insert', text: 'Día {hoy}', as: 'h3' }, { kind: 'ai', prompt: 'resume' }] }, new Date(NOW));
    expect(out.page.blocks[1].type).toBe('h3');
    expect(out.page.blocks[1].text).toMatch(/^Día 13\/10\/2026$/);
    expect(out.pending).toEqual([{ kind: 'ai', prompt: 'resume' }]);
  });
});

describe('templates that learn', () => {
  it('adds what most people add and drops what most delete', () => {
    const base: Block[] = [block('h2', 'Asistentes'), block('text', ''), block('h2', 'Puntos'), block('text', '')];
    const use = (heads: string[]) => page('x', [], { blocks: heads.map((h) => block('h2', h)) });
    const out = evolveTemplate(base, [use(['Puntos', 'Riesgos']), use(['Puntos', 'Riesgos']), use(['Asistentes', 'Puntos'])]);
    expect(out.added).toEqual(['Riesgos']);
    expect(out.removed).toEqual(['Asistentes']);
    expect(out.blocks.map((b) => b.text)).toEqual(['Puntos', '', 'Riesgos', '']);
  });
});

describe('history and teams', () => {
  it('diffs blocks and words', () => {
    const a = [block('text', 'hola mundo'), block('text', 'adiós')];
    const b = [{ ...a[0], text: 'hola gran mundo' }, block('h2', 'nuevo')];
    const d = blockDiff(a, b);
    expect(d.map((x) => x.kind)).toEqual(['changed', 'removed', 'added']);
    expect(wordDiff('hola mundo', 'hola gran mundo').filter((w) => w.kind === 'added').map((w) => w.text.trim())).toEqual(['gran']);
  });
  it('merges edits to different blocks and keeps both sides of a clash', () => {
    const base = [block('text', 'uno'), block('text', 'dos'), block('text', 'tres')];
    const mine = [{ ...base[0], text: 'UNO' }, base[1], base[2], block('text', 'mío nuevo')];
    const theirs = [base[0], { ...base[1], text: 'DOS' }, { ...base[2], text: 'tres (de ellos)' }];
    const m = merge3(base, mine, theirs);
    expect(m.blocks.map((b) => b.text)).toEqual(['UNO', 'DOS', 'tres (de ellos)', 'mío nuevo']);
    expect(m.conflicts).toBe(0);
    const clash = merge3(base, [{ ...base[0], text: 'A' }, base[1], base[2]], [{ ...base[0], text: 'B' }, base[1], base[2]]);
    expect(clash.conflicts).toBe(1);
    expect(clash.blocks.map((b) => b.text)).toEqual(['B', 'A', 'dos', 'tres']);
    expect(clash.blocks[1].conflict).toBe(true);
  });
});

describe('dashboards and calendar', () => {
  it('computes KPIs and collects every date', () => {
    const t = grid([['Tarea', 'Fecha', 'Estado', 'Horas'], ['a', '2026-10-01', 'Por hacer', '2'], ['b', '2026-10-30', 'Hecho', '3'], ['c', '2026-11-02', 'En curso', '1']]);
    const k = Object.fromEntries(kpis(t, NOW).map((x) => [x.label, x.value]));
    expect(k).toMatchObject({ Filas: '3', Hecho: '33 %', Vencidas: '1', Horas: '6' });
    const p = page('Plan', ['Entregar el informe 2026-10-15']);
    p.blocks.push(block('table', '', { table: t }));
    expect(datedItems([p]).map((d) => d.date)).toEqual(['2026-10-01', '2026-10-15', '2026-10-30', '2026-11-02']);
  });
});
