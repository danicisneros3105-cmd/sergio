import { describe, expect, it } from 'vitest';
import { buildGraph, keywords, layout3d, project } from './graph';
import { block, newPage } from './model';

describe('knowledge graph', () => {
  const viaje = newPage('Viaje a Madrid', null, [block('text', 'Reservar hotel cerca del museo del Prado. Presupuesto del viaje.')]);
  const presupuesto = newPage('Presupuesto anual', null, [block('text', 'El presupuesto incluye el viaje a Madrid y el hotel.')]);
  const museo = newPage('Museos', null, [block('text', 'Ver [[Viaje a Madrid]]. Museo del Prado, museo Reina Sofía.')]);
  const hijo = newPage('Hoteles', viaje.id, [block('text', 'Opciones de hotel')]);
  presupuesto.tags = ['finanzas'];
  const archived = { ...newPage('Vieja', null, [block('text', 'presupuesto hotel viaje')]), archived: true };

  it('finds written links, tags and shared concepts, ignoring the vault', () => {
    const { nodes, links } = buildGraph([viaje, presupuesto, museo, hijo, archived]);
    const has = (a: string, b: string, kind: string) =>
      links.some((l) => l.kind === kind && ((l.a === a && l.b === b) || (l.a === b && l.b === a)));
    expect(has(museo.id, viaje.id, 'mention')).toBe(true);
    expect(has(viaje.id, hijo.id, 'child')).toBe(true);
    expect(has(presupuesto.id, 'tag:finanzas', 'tag')).toBe(true);
    const concepts = nodes.filter((n) => n.kind === 'concept').map((n) => n.label);
    expect(concepts).toContain('hotel');
    expect(concepts).toContain('presupuesto');
    expect(nodes.some((n) => n.label === 'Vieja')).toBe(false);
  });

  it('keywords skip stop words and fold plurals', () => {
    const k = keywords('Los proyectos y el proyecto, para que todo esté bien');
    expect(k.get('proyecto')).toBe(2);
    expect(k.has('para')).toBe(false);
  });

  it('lays out deterministically inside a unit sphere and projects', () => {
    const { nodes, links } = buildGraph([viaje, presupuesto, museo, hijo]);
    const a = layout3d(nodes, links, 60);
    const b = layout3d(nodes, links, 60);
    expect(a.map((n) => n.x)).toEqual(b.map((n) => n.x));
    expect(Math.max(...a.map((n) => Math.hypot(n.x, n.y, n.z)))).toBeLessThanOrEqual(1.0000001);
    const p = project({ x: 0, y: 0, z: 0 }, 0.3, 0.2, 1, 800, 600);
    expect(p.sx).toBe(400);
    expect(p.sy).toBe(300);
    expect(project({ x: 0, y: 0, z: 0.5 }, 0, 0, 1, 800, 600).scale).toBeGreaterThan(1);
  });
});
