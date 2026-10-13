// Sergio's Nodes, rendered in real 3D with the flocked look of OpenAI's
// Dots: soft velvet bodies (a sheen at the edges and a short fuzz on the
// silhouette), studio light from an environment map, glossy little eyes and
// a soft contact shadow. Our own cast:
//
//   rhino      eyes closed, a sky-blue and white striped shirt
//   dalmatian  white with black spots, floppy ears and a collar
//   glove      an inflated blue medical glove with a beret and a face
//              drawn on it with a marker
//   orb        an invisible orb: only its glassy rim, two solid black eyes
//              and a pair of leopard glasses floating in front
//
// One offscreen WebGL renderer draws each look once per size (eyes open,
// blinking, talking) into PNGs that the page shows as images and animates
// with CSS, so a list of fifty Nodes costs fifty <img>, not fifty canvases.

import type * as THREE_NS from 'three';
import type { CritterLook } from './NodeCritter';

type Three = typeof THREE_NS;
export type DotsFrame = 'open' | 'blink' | 'talk';
export type DotsFrames = Record<DotsFrame, string>;

export const DOTS_SHAPES = ['rhino', 'dalmatian', 'glove', 'orb'] as const;
export type DotsShape = (typeof DOTS_SHAPES)[number];

/** Older Nodes keep working: each old shape is drawn as one of the cast. */
export function castOf(shape: string): DotsShape {
  if ((DOTS_SHAPES as readonly string[]).includes(shape)) return shape as DotsShape;
  if (['bean', 'blob', 'bear'].includes(shape)) return 'rhino';
  if (['frog', 'cactus', 'mushroom'].includes(shape)) return 'dalmatian';
  if (['heart', 'star', 'drop'].includes(shape)) return 'glove';
  return 'orb'; // ghost, planet, anything unknown
}

export const DEFAULT_COLOR: Record<DotsShape, string> = {
  rhino: '#8f9fd1',
  dalmatian: '#e8505b',
  glove: '#5b9cf6',
  orb: '#bfe6ff',
};

/** Sizes are drawn in a few buckets so lists reuse the same images. */
export function bucket(px: number): number {
  for (const b of [64, 128, 256, 512]) if (px <= b) return b;
  return 768;
}

export function lookKey(look: CritterLook, px: number): string {
  return [castOf(look.shape), look.color.toLowerCase(), look.accessory, look.eyes, bucket(px)].join('|');
}

export function webglAvailable(): boolean {
  if (typeof window === 'undefined' || typeof WebGLRenderingContext === 'undefined') return false;
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Procedural textures (canvas), made once.

function canvas(w: number, h = w): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return [c, c.getContext('2d')!];
}

function seeded(seed: number) {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) % 100000) / 100000;
  };
}

interface Kit {
  T: Three;
  fuzzNormal: THREE_NS.Texture;
  fiber: THREE_NS.Texture;
  stripes: THREE_NS.Texture;
  spots: THREE_NS.Texture;
  leopard: THREE_NS.Texture;
  marker: THREE_NS.Texture;
  markerBlink: THREE_NS.Texture;
  markerTalk: THREE_NS.Texture;
}

function makeKit(T: Three): Kit {
  const rnd = seeded(7);
  const tex = (c: HTMLCanvasElement, repeat = 1, color = true) => {
    const t = new T.CanvasTexture(c);
    t.wrapS = t.wrapT = T.RepeatWrapping;
    t.repeat.set(repeat, repeat);
    if (color) t.colorSpace = T.SRGBColorSpace;
    t.anisotropy = 4;
    return t;
  };

  // Fine flock grain as a normal map: tiny random tilts.
  const [nc, nx] = canvas(256);
  const img = nx.createImageData(256, 256);
  for (let i = 0; i < img.data.length; i += 4) {
    img.data[i] = 128 + (rnd() - 0.5) * 90;
    img.data[i + 1] = 128 + (rnd() - 0.5) * 90;
    img.data[i + 2] = 255;
    img.data[i + 3] = 255;
  }
  nx.putImageData(img, 0, 0);
  const fuzzNormal = tex(nc, 8, false);

  // Fibre tips for the fuzz shells: dense dots, brighter = longer fibre.
  const [fc, fx] = canvas(256);
  fx.fillStyle = '#000';
  fx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 16000; i++) {
    const v = Math.floor(80 + rnd() * 175);
    fx.fillStyle = `rgb(${v},${v},${v})`;
    fx.fillRect(Math.floor(rnd() * 256), Math.floor(rnd() * 256), 1.4, 1.4);
  }
  const fiber = tex(fc, 10, false);

  // Horizontal stripes (sky blue and white) for the rhino's shirt.
  const [sc, sx] = canvas(64, 256);
  for (let i = 0; i < 8; i++) {
    sx.fillStyle = i % 2 ? '#ffffff' : '#8ecdf2';
    sx.fillRect(0, i * 32, 64, 32);
  }
  const stripes = tex(sc, 1);
  stripes.repeat.set(1, 1);

  // Dalmatian coat: white with irregular black spots.
  const [dc, dx] = canvas(512, 256);
  dx.fillStyle = '#f7f4ee';
  dx.fillRect(0, 0, 512, 256);
  const rs = seeded(21);
  for (let i = 0; i < 34; i++) {
    const x = rs() * 512;
    const y = 30 + rs() * 196;
    const r = 7 + rs() * 15;
    if ((x < 110 || x > 402) && y < 140) continue; // keep the face clean
    dx.fillStyle = '#1b1b1b';
    dx.beginPath();
    for (let a = 0; a <= 12; a++) {
      const ang = (a / 12) * Math.PI * 2;
      const rr = r * (0.75 + rs() * 0.45);
      const px = x + Math.cos(ang) * rr * 1.15;
      const py = y + Math.sin(ang) * rr;
      if (a) dx.lineTo(px, py);
      else dx.moveTo(px, py);
    }
    dx.closePath();
    dx.fill();
  }
  const spots = tex(dc, 1);

  // Leopard print for the orb's glasses.
  const [lc, lx] = canvas(256);
  lx.fillStyle = '#d39a4f';
  lx.fillRect(0, 0, 256, 256);
  const rl = seeded(5);
  for (let i = 0; i < 70; i++) {
    const x = rl() * 256;
    const y = rl() * 256;
    const r = 5 + rl() * 7;
    lx.fillStyle = '#8a5523';
    lx.beginPath();
    lx.ellipse(x, y, r * 0.8, r * 0.65, rl() * 3, 0, Math.PI * 2);
    lx.fill();
    lx.strokeStyle = '#2a170b';
    lx.lineWidth = 2.6;
    lx.beginPath();
    lx.arc(x, y, r, rl() * 1.5, rl() * 1.5 + 4.6);
    lx.stroke();
  }
  const leopard = tex(lc, 1);

  // The glove's face, drawn with a marker: wobbly strokes, transparent.
  const face = (kind: DotsFrame) => {
    const [c, x] = canvas(512);
    x.strokeStyle = '#141414';
    x.fillStyle = '#141414';
    x.lineCap = 'round';
    x.lineJoin = 'round';
    x.lineWidth = 13;
    const wob = seeded(11);
    const line = (pts: Array<[number, number]>) => {
      x.beginPath();
      pts.forEach(([px, py], i) => {
        const jx = px + (wob() - 0.5) * 3;
        const jy = py + (wob() - 0.5) * 3;
        if (i) x.lineTo(jx, jy);
        else x.moveTo(jx, jy);
      });
      x.stroke();
    };
    if (kind === 'blink') {
      line([[178, 236], [200, 244], [222, 236]]);
      line([[290, 236], [312, 244], [334, 236]]);
    } else {
      x.beginPath();
      x.ellipse(200, 232, 15, 19, 0.1, 0, Math.PI * 2);
      x.fill();
      x.beginPath();
      x.ellipse(312, 232, 15, 19, -0.1, 0, Math.PI * 2);
      x.fill();
    }
    if (kind === 'talk') {
      x.beginPath();
      x.ellipse(256, 312, 26, 22, 0, 0, Math.PI * 2);
      x.fill();
    } else {
      const pts: Array<[number, number]> = [];
      for (let i = 0; i <= 10; i++) {
        const t = i / 10;
        pts.push([214 + t * 84, 296 + Math.sin(t * Math.PI) * 30]);
      }
      line(pts);
    }
    const t = new T.CanvasTexture(c);
    t.colorSpace = T.SRGBColorSpace;
    return t;
  };

  return {
    T,
    fuzzNormal,
    fiber,
    stripes,
    spots,
    leopard,
    marker: face('open'),
    markerBlink: face('blink'),
    markerTalk: face('talk'),
  };
}

// ---------------------------------------------------------------------------
// Materials and helpers.

function lighten(T: Three, hex: string, amount: number): THREE_NS.Color {
  const c = new T.Color(hex);
  return c.lerp(new T.Color('#ffffff'), amount);
}

function flock(kit: Kit, color: string | THREE_NS.Color, map?: THREE_NS.Texture) {
  const { T } = kit;
  const base = typeof color === 'string' ? new T.Color(color) : color;
  return new T.MeshPhysicalMaterial({
    color: map ? new T.Color('#ffffff') : base,
    map: map || null,
    roughness: 0.92,
    metalness: 0,
    sheen: 1,
    sheenRoughness: 0.5,
    sheenColor: base.clone().lerp(new T.Color('#ffffff'), 0.28),
    normalMap: kit.fuzzNormal,
    normalScale: new T.Vector2(0.45, 0.45),
  });
}

function gloss(T: Three, color: string, rough = 0.18) {
  return new T.MeshPhysicalMaterial({ color, roughness: rough, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.12 });
}

/** A short fuzz on the silhouette: shells pushed out along the normals with
 * fewer fibres the further out they are (the classic shell-fur trick). */
function fuzz(kit: Kit, mesh: THREE_NS.Mesh, color: THREE_NS.Color, layers = 8, length = 0.055) {
  const { T } = kit;
  const src = mesh.geometry as THREE_NS.BufferGeometry;
  const pos = src.getAttribute('position');
  const nor = src.getAttribute('normal');
  if (!nor) return;
  for (let i = 1; i <= layers; i++) {
    const g = src.clone();
    const p = g.getAttribute('position') as THREE_NS.BufferAttribute;
    const d = (length * i) / layers;
    for (let v = 0; v < pos.count; v++) {
      p.setXYZ(v, pos.getX(v) + nor.getX(v) * d, pos.getY(v) + nor.getY(v) * d, pos.getZ(v) + nor.getZ(v) * d);
    }
    const mat = new T.MeshPhysicalMaterial({
      color: color.clone().lerp(new T.Color('#ffffff'), 0.03 + (0.1 * i) / layers),
      alphaMap: kit.fiber,
      alphaTest: 0.3 + (0.62 * i) / layers,
      roughness: 1,
      sheen: 1,
      sheenColor: color.clone().lerp(new T.Color('#ffffff'), 0.3),
      sheenRoughness: 0.5,
    });
    const shell = new T.Mesh(g, mat);
    shell.position.copy(mesh.position);
    shell.rotation.copy(mesh.rotation);
    shell.scale.copy(mesh.scale);
    mesh.parent?.add(shell);
  }
}

function ball(T: Three, mat: THREE_NS.Material, r: number, sx = 1, sy = 1, sz = 1, seg = 48) {
  const m = new T.Mesh(new T.SphereGeometry(r, seg, Math.round(seg * 0.75)), mat);
  m.scale.set(sx, sy, sz);
  return m;
}

/** A plump egg (wider at the bottom), as a lathe. */
function eggPoints(T: Three, R: number, H: number, bottom = 0.12, top = 0.08, n = 40) {
  const pts: THREE_NS.Vector2[] = [];
  for (let i = 0; i <= n; i++) {
    const th = (i / n) * Math.PI;
    const y = (H * (1 - Math.cos(th))) / 2;
    const k = y / H;
    const r = R * Math.pow(Math.sin(th), 0.82) * (1 + bottom * (1 - k) - top * k);
    pts.push(new T.Vector2(Math.max(r, 0.0001), y));
  }
  return pts;
}

function radiusAt(points: THREE_NS.Vector2[], y: number) {
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (y >= a.y && y <= b.y) return a.x + ((b.x - a.x) * (y - a.y)) / Math.max(b.y - a.y, 1e-6);
  }
  return 0;
}

interface Face {
  eyeY: number;
  eyeGap: number;
  frontZ: number; // z of the surface at eye height
  mouthY: number;
  top: number;
  neckY: number;
  headR: number;
  dark?: boolean; // light ink on dark bodies
  eyeScale?: number;
  zAt?: (x: number, y: number) => number; // the body's surface, for things worn on it
}

// things on the face sit just outside the fuzz (shells reach ~0.055)
const surface = (f: Face, x: number, y: number) => (f.zAt ? f.zAt(x, y) + 0.045 : f.frontZ);

/** The front surface of a lathe body (scaled in z) at (x, y). */
function latheZ(points: THREE_NS.Vector2[], zScale: number) {
  return (x: number, y: number) => Math.sqrt(Math.max(radiusAt(points, y) ** 2 - x * x, 0)) * zScale;
}

/** Eyes and mouth as separate groups so frames can switch them. */
function faceParts(kit: Kit, face: Face, eyes: CritterLook['eyes']) {
  const { T } = kit;
  const ink = gloss(T, face.dark ? '#f2f2f2' : '#111111', 0.12);
  const open = new T.Group();
  const shut = new T.Group();
  const k = face.eyeScale || 1;
  const arc = (x: number, y: number, up: boolean, r = 0.095) => {
    const m = new T.Mesh(new T.TorusGeometry(r * k, 0.026 * k, 12, 24, Math.PI), ink);
    const z = surface(face, x, y);
    m.position.set(x, y, z);
    m.rotation.y = Math.atan2(x, Math.max(z, 0.2)) * 0.8; // follow the curve
    if (!up) m.rotation.z = Math.PI;
    return m;
  };
  for (const side of [-1, 1]) {
    const x = side * face.eyeGap;
    const y = face.eyeY;
    if (eyes === 'happy') open.add(arc(x, y - 0.03, true));
    else if (eyes === 'sleepy') open.add(arc(x, y + 0.02, false));
    else if (eyes === 'googly') {
      const w = ball(T, gloss(T, '#ffffff', 0.25), 0.15, 1, 1, 0.55);
      const z = surface(face, x, y);
      w.position.set(x, y, z + 0.03);
      const p = ball(T, ink, 0.075, 1, 1, 0.5);
      p.position.set(x + side * 0.02, y - 0.03, z + 0.11);
      open.add(w, p);
    } else {
      const r = eyes === 'big' ? 0.12 : 0.078;
      const e = ball(T, ink, r, 0.86, 1.08, 0.45);
      const z = surface(face, x, y);
      e.position.set(x, y, z + 0.01);
      const glint = ball(T, new T.MeshBasicMaterial({ color: '#ffffff' }), r * 0.28);
      glint.position.set(x - r * 0.3, y + r * 0.38, z + r * 0.5);
      open.add(e, glint);
    }
    shut.add(eyes === 'happy' ? arc(x, y - 0.03, true) : arc(x, y + 0.01, false, 0.075));
  }
  const smile = new T.Mesh(new T.TorusGeometry(0.07, 0.017, 10, 20, Math.PI), ink);
  smile.position.set(0, face.mouthY, face.frontZ + 0.005);
  smile.rotation.z = Math.PI;
  const talk = ball(T, gloss(T, '#2a0d12', 0.3), 0.07, 1, 0.8, 0.4);
  talk.position.set(0, face.mouthY - 0.02, face.frontZ);
  const tongue = ball(T, gloss(T, '#ff7d9a', 0.4), 0.045, 1, 0.55, 0.4);
  tongue.position.set(0, face.mouthY - 0.05, face.frontZ + 0.02);
  const talkGroup = new T.Group();
  talkGroup.add(talk, tongue);
  const cheeks = new T.Group();
  for (const side of [-1, 1]) {
    const c = ball(T, new T.MeshPhysicalMaterial({ color: '#ff8fa8', roughness: 1, transparent: true, opacity: 0.45 }), 0.07, 1.3, 0.75, 0.25);
    const cx = side * (face.eyeGap + 0.13);
    c.position.set(cx, face.eyeY - 0.16, surface(face, cx, face.eyeY - 0.16) - 0.005);
    cheeks.add(c);
  }
  return { open, shut, smile, talk: talkGroup, cheeks };
}

// ---------------------------------------------------------------------------
// Accessories, placed from the face's anchors.

function accessory(kit: Kit, kind: CritterLook['accessory'], f: Face): THREE_NS.Object3D | null {
  const { T } = kit;
  const g = new T.Group();
  switch (kind) {
    case 'beret': {
      const cap = ball(T, flock(kit, '#24304f'), f.headR * 0.62, 1, 0.3, 1);
      const stem = ball(T, flock(kit, '#24304f'), 0.05, 1, 1.6, 1);
      stem.position.y = f.headR * 0.2;
      g.add(cap, stem);
      g.position.set(-0.08, f.top - 0.02, 0);
      g.rotation.z = 0.28;
      g.rotation.x = -0.1;
      return g;
    }
    case 'glasses':
    case 'sunglasses': {
      const frame = gloss(T, '#141414', 0.15);
      for (const side of [-1, 1]) {
        if (kind === 'glasses') {
          const ring = new T.Mesh(new T.TorusGeometry(0.15, 0.022, 14, 40), frame);
          ring.position.set(side * f.eyeGap, f.eyeY, surface(f, side * f.eyeGap, f.eyeY) + 0.1);
          g.add(ring);
        } else {
          const lens = ball(T, gloss(T, '#101418', 0.05), 0.17, 1.15, 0.8, 0.28);
          lens.position.set(side * f.eyeGap, f.eyeY, surface(f, side * f.eyeGap, f.eyeY) + 0.1);
          g.add(lens);
        }
      }
      const bridge = new T.Mesh(new T.CylinderGeometry(0.018, 0.018, f.eyeGap * 2 - 0.26, 12), frame);
      bridge.rotation.z = Math.PI / 2;
      bridge.position.set(0, f.eyeY + 0.02, surface(f, f.eyeGap, f.eyeY) + 0.1);
      g.add(bridge);
      return g;
    }
    case 'headphones': {
      const band = new T.Mesh(new T.TorusGeometry(f.headR * 1.02, 0.045, 14, 48, Math.PI), gloss(T, '#1b1b1b', 0.3));
      band.position.set(0, f.eyeY, 0);
      const cupMat = gloss(T, '#1b1b1b', 0.35);
      g.add(band);
      for (const side of [-1, 1]) {
        const cup = new T.Mesh(new T.CylinderGeometry(0.17, 0.17, 0.12, 32), cupMat);
        cup.rotation.z = Math.PI / 2;
        cup.position.set(side * f.headR * 1.02, f.eyeY, 0);
        g.add(cup);
      }
      return g;
    }
    case 'bow': {
      const mat = flock(kit, '#ff5c8a');
      for (const side of [-1, 1]) {
        const wing = new T.Mesh(new T.ConeGeometry(0.11, 0.2, 24), mat);
        wing.rotation.z = (side * Math.PI) / 2;
        wing.position.set(side * 0.1, 0, 0);
        g.add(wing);
      }
      g.add(ball(T, mat, 0.05));
      g.position.set(0, f.neckY, surface(f, 0, f.neckY) + 0.06);
      return g;
    }
    case 'cap': {
      const dome = new T.Mesh(new T.SphereGeometry(f.headR * 0.72, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2), flock(kit, '#f2f2f2'));
      const visor = ball(T, flock(kit, '#8ecdf2'), f.headR * 0.55, 1, 0.08, 0.9);
      visor.position.set(0, 0.01, f.headR * 0.55);
      g.add(dome, visor);
      g.position.set(0, f.top - f.headR * 0.32, 0);
      return g;
    }
    case 'beanie': {
      const dome = new T.Mesh(new T.SphereGeometry(f.headR * 0.78, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2), flock(kit, '#e94b4b'));
      const rim = new T.Mesh(new T.TorusGeometry(f.headR * 0.78, 0.07, 16, 48), flock(kit, '#c93a3a'));
      rim.rotation.x = Math.PI / 2;
      const pom = ball(T, flock(kit, '#f5f5f5'), 0.11);
      pom.position.y = f.headR * 0.8;
      g.add(dome, rim, pom);
      g.position.set(0, f.top - f.headR * 0.4, 0);
      return g;
    }
    case 'crown': {
      const gold = new T.MeshPhysicalMaterial({ color: '#f2c14e', metalness: 1, roughness: 0.25 });
      const ring = new T.Mesh(new T.CylinderGeometry(0.32, 0.3, 0.14, 40, 1, true), gold);
      g.add(ring);
      for (let i = 0; i < 5; i++) {
        const a = (i / 5) * Math.PI * 2;
        const spike = new T.Mesh(new T.ConeGeometry(0.06, 0.16, 16), gold);
        spike.position.set(Math.sin(a) * 0.31, 0.14, Math.cos(a) * 0.31);
        g.add(spike);
      }
      g.position.set(0, f.top + 0.02, 0);
      return g;
    }
    case 'scarf': {
      const mat = flock(kit, '#e94b4b');
      const loop = new T.Mesh(new T.TorusGeometry(f.headR * 0.95, 0.09, 16, 48), mat);
      loop.rotation.x = Math.PI / 2;
      const tail = ball(T, mat, 0.1, 1, 2.2, 0.6);
      tail.position.set(0.32, -0.18, f.headR * 0.85);
      tail.rotation.z = 0.2;
      g.add(loop, tail);
      g.position.set(0, f.neckY, 0);
      return g;
    }
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// The cast.

interface Built {
  root: THREE_NS.Group;
  frames: Record<DotsFrame, () => void>;
}

function standardFrames(parts: ReturnType<typeof faceParts>, extra?: Partial<Record<DotsFrame, () => void>>) {
  const set = (eyesOpen: boolean, talking: boolean) => {
    parts.open.visible = eyesOpen;
    parts.shut.visible = !eyesOpen;
    parts.smile.visible = !talking;
    parts.talk.visible = talking;
  };
  return {
    open: () => (set(true, false), extra?.open?.()),
    blink: () => (set(false, false), extra?.blink?.()),
    talk: () => (set(true, true), extra?.talk?.()),
  };
}

function nubs(kit: Kit, mat: THREE_NS.Material, color: THREE_NS.Color, root: THREE_NS.Group, armY: number, armX: number, feetZ = 0.35) {
  const { T } = kit;
  for (const side of [-1, 1]) {
    const arm = ball(T, mat, 0.17, 0.8, 1.25, 0.8);
    arm.position.set(side * armX, armY, 0.1);
    arm.rotation.z = side * 0.35;
    root.add(arm);
    fuzz(kit, arm, color, 3, 0.02);
    const foot = ball(T, mat, 0.2, 1.1, 0.6, 1.2);
    foot.position.set(side * 0.3, 0.06, feetZ);
    root.add(foot);
    fuzz(kit, foot, color, 3, 0.02);
  }
}

function rhino(kit: Kit, look: CritterLook): Built {
  const { T } = kit;
  const root = new T.Group();
  const skin = new T.Color(look.color);
  const mat = flock(kit, skin);
  const pts = eggPoints(T, 0.9, 1.9, 0.14, 0.12);
  const body = new T.Mesh(new T.LatheGeometry(pts, 64), mat);
  body.scale.z = 0.92;
  root.add(body);
  fuzz(kit, body, skin);

  // The striped shirt over the lower half, with short sleeves.
  const shirtPts = pts.filter((p) => p.y >= 0.12 && p.y <= 0.92).map((p) => new T.Vector2(p.x + 0.035, p.y));
  const shirt = new T.Mesh(new T.LatheGeometry(shirtPts, 64), flock(kit, '#ffffff', kit.stripes));
  shirt.scale.z = 0.92;
  root.add(shirt);
  const hem = new T.Mesh(new T.TorusGeometry(radiusAt(pts, 0.92) + 0.03, 0.03, 12, 64), flock(kit, '#8ecdf2'));
  hem.rotation.x = Math.PI / 2;
  hem.scale.y = 0.92;
  hem.position.y = 0.92;
  root.add(hem);

  const muzzleColor = lighten(T, look.color, 0.18);
  const muzzle = ball(T, flock(kit, muzzleColor), 0.42, 1.15, 0.78, 0.8);
  muzzle.position.set(0, 1.02, 0.66);
  root.add(muzzle);
  fuzz(kit, muzzle, muzzleColor, 3, 0.02);
  const hornMat = flock(kit, '#efe4d0');
  const horn = new T.Mesh(new T.ConeGeometry(0.12, 0.42, 32), hornMat);
  horn.position.set(0, 1.38, 0.9);
  horn.rotation.x = 0.55;
  const horn2 = new T.Mesh(new T.ConeGeometry(0.08, 0.22, 32), hornMat);
  horn2.position.set(0, 1.5, 0.66);
  horn2.rotation.x = 0.35;
  root.add(horn, horn2);
  for (const side of [-1, 1]) {
    const ear = ball(T, mat, 0.16, 0.7, 1.15, 0.5);
    ear.position.set(side * 0.52, 1.82, 0.0);
    ear.rotation.z = -side * 0.45;
    const inner = ball(T, flock(kit, '#f2a7b5'), 0.09, 0.6, 1, 0.3);
    inner.position.set(side * 0.53, 1.81, 0.07);
    inner.rotation.z = -side * 0.45;
    root.add(ear, inner);
    const nostril = ball(T, gloss(T, '#4b4f5a', 0.5), 0.035, 1.3, 0.8, 0.5);
    nostril.position.set(side * 0.16, 1.08, 1.0);
    root.add(nostril);
  }
  nubs(kit, flock(kit, skin), skin, root, 0.62, 0.86);
  // sleeves over the shoulders of the arms
  for (const side of [-1, 1]) {
    const sleeve = ball(T, flock(kit, '#ffffff', kit.stripes), 0.2, 1, 0.8, 1);
    sleeve.position.set(side * 0.8, 0.82, 0.05);
    root.add(sleeve);
  }

  const face: Face = {
    eyeY: 1.46,
    eyeGap: 0.32,
    frontZ: 0.72,
    mouthY: 0.86,
    top: 1.9,
    neckY: 0.98,
    headR: 0.62,
    dark: skin.getHSL({ h: 0, s: 0, l: 0 }).l < 0.3,
    eyeScale: 1.35,
    zAt: latheZ(pts, 0.92),
  };
  const parts = faceParts(kit, face, look.eyes === 'dots' ? 'sleepy' : look.eyes);
  parts.smile.position.set(0, 0.86, 0.95);
  parts.talk.position.set(0, 0.0, 0.25);
  root.add(parts.open, parts.shut, parts.smile, parts.talk, parts.cheeks);
  const acc = accessory(kit, look.accessory, face);
  if (acc) root.add(acc);
  return { root, frames: standardFrames(parts) };
}

function dalmatian(kit: Kit, look: CritterLook): Built {
  const { T } = kit;
  const root = new T.Group();
  const white = new T.Color('#f7f4ee');
  const pts = eggPoints(T, 0.88, 1.85, 0.12, 0.06);
  const body = new T.Mesh(new T.LatheGeometry(pts, 64), flock(kit, white, kit.spots));
  body.scale.z = 0.92;
  root.add(body);
  fuzz(kit, body, white);
  const earMat = flock(kit, '#1d1d1d');
  for (const side of [-1, 1]) {
    const ear = ball(T, earMat, 0.24, 0.8, 1.7, 0.45);
    ear.position.set(side * 0.78, 1.42, 0.05);
    ear.rotation.z = side * 0.42;
    root.add(ear);
    fuzz(kit, ear, new T.Color('#1d1d1d'), 3, 0.02);
  }
  const muzzle = ball(T, flock(kit, white), 0.36, 1.2, 0.72, 0.75);
  muzzle.position.set(0, 1.0, 0.66);
  root.add(muzzle);
  fuzz(kit, muzzle, white, 3, 0.02);
  const nose = ball(T, gloss(T, '#121212', 0.15), 0.12, 1.3, 0.9, 0.8);
  nose.position.set(0, 1.14, 0.94);
  root.add(nose);
  const collar = new T.Mesh(new T.TorusGeometry(radiusAt(pts, 0.82) + 0.02, 0.06, 16, 64), flock(kit, look.color));
  collar.rotation.x = Math.PI / 2;
  collar.scale.y = 0.92;
  collar.position.y = 0.82;
  const tag = new T.Mesh(new T.CylinderGeometry(0.08, 0.08, 0.03, 24), new T.MeshPhysicalMaterial({ color: '#f2c14e', metalness: 1, roughness: 0.25 }));
  tag.rotation.x = Math.PI / 2;
  tag.position.set(0, 0.7, radiusAt(pts, 0.75) * 0.92 + 0.06);
  root.add(collar, tag);
  nubs(kit, flock(kit, white), white, root, 0.55, 0.84);

  const face: Face = { eyeY: 1.38, eyeGap: 0.3, frontZ: 0.74, mouthY: 0.86, top: 1.85, neckY: 0.82, headR: 0.62, zAt: latheZ(pts, 0.92) };
  const parts = faceParts(kit, face, look.eyes);
  parts.smile.position.set(0, 0.86, 0.97);
  parts.talk.position.set(0, 0.0, 0.27);
  root.add(parts.open, parts.shut, parts.smile, parts.talk, parts.cheeks);
  const acc = accessory(kit, look.accessory, face);
  if (acc) root.add(acc);
  return { root, frames: standardFrames(parts) };
}

function glove(kit: Kit, look: CritterLook): Built {
  const { T } = kit;
  const root = new T.Group();
  const blue = new T.Color(look.color);
  const mat = flock(kit, blue);
  const palm = ball(T, mat, 0.82, 1.05, 0.95, 0.62, 64);
  palm.position.y = 0.98;
  root.add(palm);
  fuzz(kit, palm, blue, 3, 0.015);
  const fingers: Array<[number, number, number]> = [
    // angle from vertical, length, radius
    [-0.5, 0.56, 0.2],
    [-0.17, 0.7, 0.21],
    [0.17, 0.66, 0.21],
    [0.5, 0.52, 0.19],
  ];
  let tallest = 0;
  let tallestTop = new T.Vector3();
  for (const [a, len, r] of fingers) {
    const f = new T.Mesh(new T.CapsuleGeometry(r, len, 12, 32), mat);
    const baseY = 1.55;
    const bx = Math.sin(a) * 0.62;
    f.position.set(bx + Math.sin(a) * (len / 2), baseY + Math.cos(a) * (len / 2) - 0.05, 0);
    f.rotation.z = -a;
    f.scale.z = 0.85;
    root.add(f);
    fuzz(kit, f, blue, 3, 0.02);
    const topY = f.position.y + Math.cos(a) * (len / 2 + r);
    if (topY > tallest) {
      tallest = topY;
      tallestTop = new T.Vector3(f.position.x + Math.sin(a) * (len / 2 + r), topY, 0);
    }
  }
  const thumb = new T.Mesh(new T.CapsuleGeometry(0.17, 0.42, 12, 32), mat);
  thumb.position.set(-0.98, 1.12, 0.05);
  thumb.rotation.z = 1.05;
  thumb.scale.z = 0.85;
  root.add(thumb);
  fuzz(kit, thumb, blue, 3, 0.02);
  // The cuff, narrowing to the tied knot of the balloon.
  // The cuff: a short wide sleeve with a rolled rim, standing on the floor.
  const cuffPts = [
    new T.Vector2(0.001, 0.08),
    new T.Vector2(0.5, 0.08),
    new T.Vector2(0.52, 0.2),
    new T.Vector2(0.54, 0.38),
    new T.Vector2(0.6, 0.5),
  ];
  const cuff = new T.Mesh(new T.LatheGeometry(cuffPts, 48), mat);
  cuff.scale.z = 0.72;
  root.add(cuff);
  const rim = new T.Mesh(new T.TorusGeometry(0.5, 0.08, 16, 48), flock(kit, lighten(T, look.color, 0.12)));
  rim.rotation.x = Math.PI / 2;
  rim.scale.y = 0.72;
  rim.position.y = 0.08;
  root.add(rim);

  // The marker face: a decal patch over the front of the palm.
  const decalGeo = new T.SphereGeometry(0.82, 48, 32, Math.PI * 0.25, Math.PI * 0.5, Math.PI * 0.18, Math.PI * 0.6);
  const decalMat = new T.MeshPhysicalMaterial({ map: kit.marker, transparent: true, roughness: 0.6, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 });
  const decal = new T.Mesh(decalGeo, decalMat);
  decal.scale.set(1.075, 0.975, 0.66);
  decal.position.y = 0.98;
  root.add(decal);

  const face: Face = { eyeY: 1.12, eyeGap: 0.28, frontZ: 0.5, mouthY: 0.84, top: 1.62, neckY: 0.52, headR: 0.62 };
  // The beret sits on the tallest finger, tilted.
  const beret = new T.Group();
  const cap = ball(T, flock(kit, '#24304f'), 0.36, 1, 0.3, 1);
  const stem = ball(T, flock(kit, '#24304f'), 0.04, 1, 1.6, 1);
  stem.position.y = 0.11;
  beret.add(cap, stem);
  beret.position.copy(tallestTop).add(new T.Vector3(0, -0.04, 0));
  beret.rotation.z = 0.32;
  root.add(beret);
  if (look.accessory !== 'beret' && look.accessory !== 'none') {
    const acc = accessory(kit, look.accessory, face);
    if (acc) root.add(acc);
  }
  root.scale.setScalar(0.9);
  return {
    root,
    frames: {
      open: () => (decalMat.map = kit.marker),
      blink: () => (decalMat.map = kit.markerBlink),
      talk: () => (decalMat.map = kit.markerTalk),
    },
  };
}

function orb(kit: Kit, look: CritterLook): Built {
  const { T } = kit;
  const root = new T.Group();
  const tint = new T.Color(look.color);
  // Only the rim of the orb shows: a Fresnel edge, glass-clear inside.
  const rimMat = new T.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: { tint: { value: tint } },
    vertexShader: `
      varying vec3 vN; varying vec3 vV;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal);
        vV = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      uniform vec3 tint; varying vec3 vN; varying vec3 vV;
      void main() {
        float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.6);
        vec3 col = mix(vec3(1.0), tint, 0.55);
        float spec = pow(max(dot(normalize(vN), normalize(vec3(-0.5, 0.7, 0.6))), 0.0), 60.0);
        gl_FragColor = vec4(col, clamp(f * 0.75 + spec * 0.6, 0.0, 0.9));
      }`,
  });
  const sphere = new T.Mesh(new T.SphereGeometry(0.92, 64, 48), rimMat);
  sphere.position.y = 1.0;
  root.add(sphere);

  const black = gloss(T, '#0b0b0b', 0.2);
  const eyesOpen = new T.Group();
  const eyesShut = new T.Group();
  for (const side of [-1, 1]) {
    const e = new T.Mesh(new T.CircleGeometry(0.12, 48), black);
    e.position.set(side * 0.27, 1.05, 0.55);
    eyesOpen.add(e);
    const s = new T.Mesh(new T.TorusGeometry(0.1, 0.022, 10, 24, Math.PI), black);
    s.position.set(side * 0.27, 1.06, 0.56);
    s.rotation.z = Math.PI;
    eyesShut.add(s);
  }
  root.add(eyesOpen, eyesShut);

  // Leopard glasses: extruded rounded frames with a bevel, clear lenses.
  const leopard = new T.MeshPhysicalMaterial({ map: kit.leopard, roughness: 0.28, clearcoat: 1, clearcoatRoughness: 0.1 });
  const glasses = new T.Group();
  const lensShape = (w: number, h: number, r: number) => {
    const s = new T.Shape();
    s.moveTo(-w / 2 + r, -h / 2);
    s.lineTo(w / 2 - r, -h / 2);
    s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
    s.lineTo(w / 2, h / 2 - r);
    s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
    s.lineTo(-w / 2 + r, h / 2);
    s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
    s.lineTo(-w / 2, -h / 2 + r);
    s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
    return s;
  };
  for (const side of [-1, 1]) {
    const outer = lensShape(0.46, 0.36, 0.14);
    const hole = new T.Path(lensShape(0.34, 0.24, 0.09).getPoints(24));
    outer.holes.push(hole);
    const frame = new T.Mesh(
      new T.ExtrudeGeometry(outer, { depth: 0.05, bevelEnabled: true, bevelThickness: 0.025, bevelSize: 0.02, bevelSegments: 4, curveSegments: 24 }),
      leopard,
    );
    frame.position.set(side * 0.27, 1.06, 0.78);
    glasses.add(frame);
    const lens = new T.Mesh(
      new T.ShapeGeometry(lensShape(0.34, 0.24, 0.09)),
      new T.MeshPhysicalMaterial({ color: '#9fb4c8', transparent: true, opacity: 0.18, roughness: 0.05, clearcoat: 1 }),
    );
    lens.position.set(side * 0.27, 1.06, 0.8);
    glasses.add(lens);
    const arm = new T.Mesh(new T.BoxGeometry(0.035, 0.05, 0.62), leopard);
    arm.position.set(side * 0.5, 1.1, 0.48);
    arm.rotation.y = side * 0.08;
    glasses.add(arm);
  }
  const bridge = new T.Mesh(new T.TorusGeometry(0.06, 0.022, 10, 20, Math.PI), leopard);
  bridge.position.set(0, 1.12, 0.81);
  glasses.add(bridge);
  glasses.rotation.z = -0.05;
  root.add(glasses);
  if (look.accessory !== 'none' && look.accessory !== 'glasses' && look.accessory !== 'sunglasses') {
    const acc = accessory(kit, look.accessory, { eyeY: 1.06, eyeGap: 0.27, frontZ: 0.6, mouthY: 0.8, top: 1.9, neckY: 0.3, headR: 0.62 });
    if (acc) root.add(acc);
  }
  return {
    root,
    frames: {
      open: () => ((eyesOpen.visible = true), (eyesShut.visible = false), (glasses.position.y = 0)),
      blink: () => ((eyesOpen.visible = false), (eyesShut.visible = true), (glasses.position.y = 0)),
      talk: () => ((eyesOpen.visible = true), (eyesShut.visible = false), (glasses.position.y = 0.04)),
    },
  };
}

const BUILDERS: Record<DotsShape, (kit: Kit, look: CritterLook) => Built> = { rhino, dalmatian, glove, orb };

// ---------------------------------------------------------------------------
// The shared offscreen renderer and the queue of looks to draw.

interface Stage {
  T: Three;
  kit: Kit;
  renderer: THREE_NS.WebGLRenderer;
  scene: THREE_NS.Scene;
  camera: THREE_NS.PerspectiveCamera;
  shadow: THREE_NS.Mesh;
}

let stagePromise: Promise<Stage | null> | null = null;

async function stage(): Promise<Stage | null> {
  if (!stagePromise) {
    stagePromise = (async () => {
      if (!webglAvailable()) return null;
      const T = await import('three');
      const { RoomEnvironment } = await import('three/examples/jsm/environments/RoomEnvironment.js');
      const c = document.createElement('canvas');
      const renderer = new T.WebGLRenderer({ canvas: c, alpha: true, antialias: true, preserveDrawingBuffer: true });
      renderer.setClearColor(0x000000, 0);
      renderer.outputColorSpace = T.SRGBColorSpace;
      renderer.toneMapping = T.NeutralToneMapping;
      renderer.toneMappingExposure = 0.98;
      const scene = new T.Scene();
      const pmrem = new T.PMREMGenerator(renderer);
      scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
      scene.environmentIntensity = 0.55;
      const key = new T.DirectionalLight('#ffffff', 2.1);
      key.position.set(-2.5, 4, 4);
      const rim = new T.DirectionalLight('#ffffff', 1.4);
      rim.position.set(2.5, 2.5, -3);
      scene.add(key, rim, new T.HemisphereLight('#ffffff', '#d9d4cc', 0.6));
      // Soft contact shadow: a radial gradient under the feet.
      const [sc, sx] = canvas(128);
      const grad = sx.createRadialGradient(64, 64, 0, 64, 64, 64);
      grad.addColorStop(0, 'rgba(0,0,0,0.42)');
      grad.addColorStop(0.55, 'rgba(0,0,0,0.14)');
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      sx.fillStyle = grad;
      sx.fillRect(0, 0, 128, 128);
      const shadow = new T.Mesh(
        new T.PlaneGeometry(2.4, 2.4),
        new T.MeshBasicMaterial({ map: new T.CanvasTexture(sc), transparent: true, depthWrite: false }),
      );
      shadow.rotation.x = -Math.PI / 2;
      shadow.position.y = -0.01;
      scene.add(shadow);
      const camera = new T.PerspectiveCamera(28, 1, 0.1, 50);
      camera.position.set(0, 1.55, 6.9);
      camera.lookAt(0, 1.08, 0);
      return { T, kit: makeKit(T), renderer, scene, camera, shadow };
    })().catch(() => null);
  }
  return stagePromise;
}

const cache = new Map<string, DotsFrames>();
const waiting = new Map<string, Array<(f: DotsFrames | null) => void>>();
const queue: Array<{ key: string; look: CritterLook; px: number }> = [];
let draining = false;

function dispose(obj: THREE_NS.Object3D) {
  obj.traverse((o) => {
    const m = o as THREE_NS.Mesh;
    m.geometry?.dispose?.();
    const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
    for (const mat of mats) mat.dispose();
  });
}

function draw(s: Stage, look: CritterLook, px: number): DotsFrames {
  const shape = castOf(look.shape);
  const color = /^#[0-9a-f]{6}$/i.test(look.color) ? look.color : DEFAULT_COLOR[shape];
  const built = BUILDERS[shape](s.kit, { ...look, color });
  s.scene.add(built.root);
  s.renderer.setPixelRatio(1);
  s.renderer.setSize(px, px, false);
  const out = {} as DotsFrames;
  for (const frame of ['open', 'blink', 'talk'] as DotsFrame[]) {
    built.frames[frame]();
    s.renderer.render(s.scene, s.camera);
    out[frame] = (s.renderer.domElement as HTMLCanvasElement).toDataURL('image/png');
  }
  s.scene.remove(built.root);
  dispose(built.root);
  return out;
}

async function drain() {
  if (draining) return;
  draining = true;
  const s = await stage();
  while (queue.length) {
    const job = queue.shift()!;
    let frames: DotsFrames | null = null;
    if (s) {
      try {
        frames = draw(s, job.look, job.px);
        cache.set(job.key, frames);
      } catch {
        frames = null;
      }
    }
    for (const done of waiting.get(job.key) || []) done(frames);
    waiting.delete(job.key);
    // let the page breathe between characters
    await new Promise((r) => setTimeout(r, 0));
  }
  draining = false;
}

export function cachedFrames(look: CritterLook, px: number): DotsFrames | undefined {
  return cache.get(lookKey(look, px));
}

/** The three frames of a look at about *px* pixels (null without WebGL). */
export function renderFrames(look: CritterLook, px: number): Promise<DotsFrames | null> {
  const key = lookKey(look, px);
  const hit = cache.get(key);
  if (hit) return Promise.resolve(hit);
  return new Promise((resolve) => {
    const list = waiting.get(key);
    if (list) {
      list.push(resolve);
      return;
    }
    waiting.set(key, [resolve]);
    queue.push({ key, look, px: bucket(px) });
    void drain();
  });
}
