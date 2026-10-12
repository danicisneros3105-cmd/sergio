import { describe, expect, it } from 'vitest';
import { buildGeometry, fromRecipe, geometryKey, opening, planOf, primitive, wall } from './scene';

describe('Creator scene', () => {
  it('turns Sergio parts into safe items (bad numbers, unknown shapes, colours)', () => {
    const items = fromRecipe(
      [
        { name: 'Cuerpo', shape: 'cylinder', size: [0.08, 0.1, 0.08], pos: [0, 0.05, 0], rot: [0, 0, 0], color: [1, 1, 1] },
        { name: 'Raro', shape: 'blob', size: [Number.NaN, -2, 0.1], pos: [1], rot: [], color: [2, -1, 0.5] },
      ],
      'g1',
    );
    expect(items).toHaveLength(2);
    expect(items[0].color).toBe('#ffffff');
    expect(items[1].shape).toBe('box');
    expect(items[1].size.every((v) => Number.isFinite(v) && v > 0)).toBe(true);
    expect(items[1].pos).toEqual([1, 0, 0]);
    expect(items[1].color).toBe('#ff0080');
    expect(items.every((i) => i.group === 'g1')).toBe(true);
  });

  it('builds a geometry for every shape without throwing', () => {
    for (const shape of ['box', 'rounded_box', 'sphere', 'cylinder', 'cone', 'torus', 'capsule', 'plane'] as const) {
      const g = buildGeometry(primitive(shape));
      expect(g.attributes.position.count).toBeGreaterThan(0);
    }
    const lathe = fromRecipe([{ name: 'Vaso', shape: 'lathe', size: [0.1, 0.1, 0.1], pos: [0, 0, 0], rot: [0, 0, 0], color: [1, 1, 1], profile: [[0, 0], [0.04, 0], [0.05, 0.1]] }], 'g')[0];
    expect(buildGeometry(lathe).attributes.position.count).toBeGreaterThan(0);
  });

  it('only rebuilds a mesh when its shape changes', () => {
    const a = primitive('box');
    expect(geometryKey({ ...a, pos: [3, 2, 1], color: '#000000' })).toBe(geometryKey(a));
    expect(geometryKey({ ...a, size: [2, 1, 1] })).not.toBe(geometryKey(a));
  });

  it('draws walls and gives the plan back in the same place', () => {
    const w = wall([0, 0], [4, 0]);
    expect(w.size[0]).toBeCloseTo(4);
    expect(w.pos).toEqual([2, 1.3, 0]);
    const diagonal = wall([1, 1], [4, 5]);
    const door = opening('door', [2, 0], 0);
    const plan = planOf([w, diagonal, door]);
    expect(plan.walls).toHaveLength(2);
    expect(plan.walls[0].x1).toBeCloseTo(0);
    expect(plan.walls[0].x2).toBeCloseTo(4);
    // the plan's y is the scene's -z
    const d = plan.walls[1];
    expect([d.x1, d.y1, d.x2, d.y2].map((v) => Math.round(v * 1000) / 1000)).toEqual([1, -1, 4, -5]);
    expect(plan.openings).toEqual([{ x: 2, y: -0, width: 0.9, angle: -0, kind: 'puerta' }]);
  });
});
