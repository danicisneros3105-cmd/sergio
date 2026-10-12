// Creator's 3D scene model: plain data (undo-able, saveable) and how each
// item becomes a three.js mesh. Units are metres; y is up (like three.js).

import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';

export type Shape =
  | 'box'
  | 'rounded_box'
  | 'cylinder'
  | 'sphere'
  | 'cone'
  | 'torus'
  | 'capsule'
  | 'wedge'
  | 'lathe'
  | 'extrude'
  | 'tube'
  | 'plane'
  | 'wall'
  | 'door'
  | 'window'
  | 'slab';

export interface Item {
  id: string;
  name: string;
  shape: Shape;
  size: [number, number, number];
  pos: [number, number, number];
  rot: [number, number, number]; // degrees, XYZ
  scale: [number, number, number];
  color: string; // #rrggbb
  visible: boolean;
  profile?: [number, number][];
  outline?: [number, number][];
  path?: [number, number, number][];
  radius?: number;
  group?: string; // parts of one generated object
}

/** A part as Sergio's designer returns it (/v1/vision/holo_model). */
export interface RecipePart {
  name: string;
  shape: string;
  size: number[];
  pos: number[];
  rot: number[];
  color: number[];
  profile?: number[][];
  outline?: number[][];
  path?: number[][];
  radius?: number;
}

export const ADDABLE: Array<{ shape: Shape; label: string }> = [
  { shape: 'box', label: 'Cubo' },
  { shape: 'rounded_box', label: 'Caja redondeada' },
  { shape: 'sphere', label: 'Esfera' },
  { shape: 'cylinder', label: 'Cilindro' },
  { shape: 'cone', label: 'Cono' },
  { shape: 'torus', label: 'Toro' },
  { shape: 'capsule', label: 'Cápsula' },
  { shape: 'plane', label: 'Plano' },
];

let counter = 0;
export function newId(): string {
  counter += 1;
  return `i${Date.now().toString(36)}${counter}`;
}

const toHex = (c: number[]) =>
  '#' +
  [0, 1, 2]
    .map((i) => Math.round(Math.min(1, Math.max(0, Number(c?.[i] ?? 0.6))) * 255).toString(16).padStart(2, '0'))
    .join('');

const finite = (v: unknown, d: number) => (typeof v === 'number' && Number.isFinite(v) ? v : d);
const vec3 = (v: unknown, d: number): [number, number, number] => {
  const a = Array.isArray(v) ? v : [];
  return [finite(a[0], d), finite(a[1], d), finite(a[2], d)];
};

/** A primitive the owner adds from the toolbar, sized to be visible. */
export function primitive(shape: Shape, at: [number, number, number] = [0, 0.5, 0]): Item {
  const label = ADDABLE.find((a) => a.shape === shape)?.label ?? 'Objeto';
  return {
    id: newId(),
    name: label,
    shape,
    size: shape === 'plane' ? [2, 0.01, 2] : [1, 1, 1],
    pos: shape === 'plane' ? [at[0], 0, at[2]] : at,
    rot: [0, 0, 0],
    scale: [1, 1, 1],
    color: '#8ea7ff',
    visible: true,
  };
}

/** "cuerpo_taza" → "Cuerpo taza": part names read like words. */
export function partName(raw: unknown, fallback: string): string {
  const words = String(raw ?? '').replace(/[_\-.]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 40);
  if (!words) return fallback;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The floor-plan box of some items (approximate: sizes times scale). */
export function boundsOf(items: Item[]): { min: [number, number, number]; max: [number, number, number] } | null {
  if (!items.length) return null;
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  for (const it of items) {
    const r = Math.max(...it.size.map((v, i) => v * it.scale[i])) / 2;
    for (let i = 0; i < 3; i++) {
      const half = it.rot.some((a) => Math.abs(a) > 1) ? r : (it.size[i] * it.scale[i]) / 2;
      min[i] = Math.min(min[i], it.pos[i] - half);
      max[i] = Math.max(max[i], it.pos[i] + half);
    }
  }
  return { min, max };
}

/** Put a new object on the floor, beside what is already in the scene. */
export function placeBeside(existing: Item[], added: Item[], gap = 0.15): Item[] {
  const b = boundsOf(added);
  if (!b) return added;
  const lift = -b.min[1];
  const others = boundsOf(existing.filter((i) => i.visible));
  const shift = others ? others.max[0] + gap - b.min[0] : -(b.min[0] + b.max[0]) / 2;
  const centreZ = -(b.min[2] + b.max[2]) / 2;
  return added.map((it) => ({ ...it, pos: [it.pos[0] + shift, it.pos[1] + lift, it.pos[2] + centreZ] }));
}

/** Sergio's designed parts → scene items (one group per object). */
export function fromRecipe(parts: RecipePart[], group: string): Item[] {
  return parts.map((p) => {
    const shape = (
      ['box', 'rounded_box', 'cylinder', 'sphere', 'cone', 'torus', 'capsule', 'wedge', 'lathe', 'extrude', 'tube'].includes(p.shape)
        ? p.shape
        : 'box'
    ) as Shape;
    const item: Item = {
      id: newId(),
      name: partName(p.name, shape),
      shape,
      size: vec3(p.size, 0.05).map((v) => Math.max(0.0005, Math.abs(v))) as [number, number, number],
      pos: vec3(p.pos, 0),
      rot: vec3(p.rot, 0),
      scale: [1, 1, 1],
      color: toHex(p.color),
      visible: true,
      group,
    };
    if (shape === 'lathe' && Array.isArray(p.profile)) item.profile = p.profile.map((q) => [Math.abs(finite(q[0], 0)), finite(q[1], 0)]);
    if (shape === 'extrude' && Array.isArray(p.outline)) item.outline = p.outline.map((q) => [finite(q[0], 0), finite(q[1], 0)]);
    if (shape === 'tube' && Array.isArray(p.path)) {
      item.path = p.path.map((q) => vec3(q, 0));
      item.radius = finite(p.radius, 0.005);
    }
    return item;
  });
}

/** A wall from floor point a to floor point b (x, z), thickness and height in m. */
export function wall(a: [number, number], b: [number, number], height = 2.6, thickness = 0.2): Item {
  const dx = b[0] - a[0];
  const dz = b[1] - a[1];
  const length = Math.hypot(dx, dz);
  return {
    id: newId(),
    name: `Muro ${length.toFixed(2)} m`,
    shape: 'wall',
    size: [length, height, thickness],
    pos: [(a[0] + b[0]) / 2, height / 2, (a[1] + b[1]) / 2],
    rot: [0, (-Math.atan2(dz, dx) * 180) / Math.PI, 0],
    scale: [1, 1, 1],
    color: '#e9e6df',
    visible: true,
  };
}

export function opening(kind: 'door' | 'window', at: [number, number], angleDeg: number): Item {
  const door = kind === 'door';
  const size: [number, number, number] = door ? [0.9, 2.1, 0.26] : [1.2, 1.1, 0.26];
  return {
    id: newId(),
    name: door ? 'Puerta' : 'Ventana',
    shape: kind,
    size,
    pos: [at[0], door ? size[1] / 2 : 0.9 + size[1] / 2, at[1]],
    rot: [0, angleDeg, 0],
    scale: [1, 1, 1],
    color: door ? '#8a5a3b' : '#9fd3ff',
    visible: true,
  };
}

/** The geometry signature: rebuild the mesh only when this changes. */
export function geometryKey(it: Item): string {
  return JSON.stringify([it.shape, it.size, it.profile, it.outline, it.path, it.radius]);
}

function wedgeGeometry(w: number, h: number, d: number): THREE.BufferGeometry {
  const s = new THREE.Shape();
  s.moveTo(-w / 2, -h / 2);
  s.lineTo(w / 2, -h / 2);
  s.lineTo(-w / 2, h / 2);
  s.closePath();
  const g = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: false });
  g.translate(0, 0, -d / 2);
  return g;
}

export function buildGeometry(it: Item): THREE.BufferGeometry {
  const [w, h, d] = it.size;
  switch (it.shape) {
    case 'rounded_box':
      return new RoundedBoxGeometry(w, h, d, 4, Math.min(w, h, d) * 0.18);
    case 'sphere': {
      const g = new THREE.SphereGeometry(0.5, 40, 24);
      g.scale(w, h, d);
      return g;
    }
    case 'cylinder':
      return new THREE.CylinderGeometry(w / 2, d / 2, h, 40);
    case 'cone':
      return new THREE.ConeGeometry(w / 2, h, 40);
    case 'torus': {
      const tube = Math.max(0.0005, h / 2);
      const g = new THREE.TorusGeometry(Math.max(tube, w / 2 - tube), tube, 18, 56);
      g.rotateX(Math.PI / 2);
      return g;
    }
    case 'capsule': {
      const r = w / 2;
      return new THREE.CapsuleGeometry(r, Math.max(0.0001, h - 2 * r), 8, 20);
    }
    case 'wedge':
      return wedgeGeometry(w, h, d);
    case 'lathe': {
      const pts = (it.profile?.length ? it.profile : [[0, 0], [w / 2, 0], [w / 2, h], [0, h]]).map(
        ([r, y]) => new THREE.Vector2(Math.max(0, r), y),
      );
      return new THREE.LatheGeometry(pts, 48);
    }
    case 'extrude': {
      const out = it.outline?.length && it.outline.length >= 3 ? it.outline : [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]];
      const s = new THREE.Shape(out.map(([x, y]) => new THREE.Vector2(x, y)));
      const g = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: false });
      g.translate(0, 0, -d / 2);
      return g;
    }
    case 'tube': {
      const path = it.path?.length && it.path.length >= 2 ? it.path : [[0, 0, 0], [0, h, 0]];
      const curve = new THREE.CatmullRomCurve3(path.map(([x, y, z]) => new THREE.Vector3(x, y, z)));
      return new THREE.TubeGeometry(curve, Math.max(16, path.length * 12), it.radius ?? 0.01, 12, false);
    }
    case 'plane':
      return new THREE.BoxGeometry(w, Math.max(h, 0.01), d);
    default: // box, wall, door, window, slab
      return new THREE.BoxGeometry(w, h, d);
  }
}

export function buildMaterial(it: Item): THREE.MeshStandardMaterial {
  const glass = it.shape === 'window';
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(it.color),
    roughness: glass ? 0.08 : 0.55,
    metalness: 0.05,
    transparent: glass,
    opacity: glass ? 0.45 : 1,
    side: it.shape === 'lathe' ? THREE.DoubleSide : THREE.FrontSide,
  });
}

export const DEG = Math.PI / 180;

/** Walls and openings as a floor plan (metres; y of the plan = -z of the scene). */
export function planOf(items: Item[]) {
  const walls = items
    .filter((i) => i.shape === 'wall' && i.visible)
    .map((i) => {
      const half = (i.size[0] * i.scale[0]) / 2;
      const a = -i.rot[1] * DEG;
      return {
        x1: i.pos[0] - Math.cos(a) * half,
        y1: -(i.pos[2] - Math.sin(a) * half),
        x2: i.pos[0] + Math.cos(a) * half,
        y2: -(i.pos[2] + Math.sin(a) * half),
        thickness: i.size[2],
      };
    });
  const openings = items
    .filter((i) => (i.shape === 'door' || i.shape === 'window') && i.visible)
    .map((i) => ({
      x: i.pos[0],
      y: -i.pos[2],
      width: i.size[0] * i.scale[0],
      angle: -i.rot[1],
      kind: i.shape === 'door' ? 'puerta' : 'ventana',
    }));
  return { walls, openings };
}
