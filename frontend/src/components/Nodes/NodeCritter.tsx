import { useId, useMemo, type ReactElement } from 'react';
import type { NodeStatus } from '../../lib/nodes';
import './nodes.css';

// The Nodes: a fixed team of four (owner, oct. 2026). Nobody designs them.
//
//   Rihno      the rhino: black and white, a cream horn, a sky-blue striped shirt
//   Manchas    the dalmatian: white with black spots
//   Hous       an inflated blue medical glove with a beret and a marker face
//   Tennessee  an invisible orb: leopard glasses and black eyes
//
// The drawing follows the owner's references: thick black ink, flat shapes,
// grey made of a printed dot screen (halftone), black shoes, and one or two
// colours per character. They move like hand-drawn animation: 12 frames per
// turn, every frame inked afresh, so the line «boils». The frames are played
// by CSS (steps), so a list of Nodes costs no script at all.

export type CritterShape = 'rhino' | 'dalmatian' | 'glove' | 'orb';
export const CRITTER_SHAPES: CritterShape[] = ['rhino', 'dalmatian', 'glove', 'orb'];
export const CAST_NAMES: Record<CritterShape, string> = {
  rhino: 'Rihno',
  dalmatian: 'Manchas',
  glove: 'Hous',
  orb: 'Tennessee',
};

/** Loose on purpose: Nodes saved before the cast was fixed carry other shapes. */
export interface CritterLook {
  shape: string;
  color?: string;
  accessory?: string;
  eyes?: string;
}

export const FRAMES = 12;
const INK = '#111111';
const SW = 4.6;

/** An older custom shape becomes one of the four, always the same one. */
export function castOf(shape: string | undefined): CritterShape {
  if (shape && (CRITTER_SHAPES as string[]).includes(shape)) return shape as CritterShape;
  let h = 0;
  for (const ch of shape || '') h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return CRITTER_SHAPES[h % CRITTER_SHAPES.length];
}

// -- the hand: wobbly ink lines --------------------------------------------------

type Pt = [number, number];
type Rand = () => number;
const f = (x: number) => Math.round(x * 10) / 10;

export function rng(seed: number): Rand {
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

/** A smooth path through the points (Catmull-Rom as cubic curves). */
export function smooth(pts: Pt[], closed: boolean): string {
  const n = pts.length;
  const at = (i: number): Pt => (closed ? pts[(i + n) % n] : pts[Math.min(n - 1, Math.max(0, i))]);
  let d = `M${f(pts[0][0])} ${f(pts[0][1])}`;
  const last = closed ? n : n - 1;
  for (let i = 0; i < last; i++) {
    const p0 = at(i - 1);
    const p1 = at(i);
    const p2 = at(i + 1);
    const p3 = at(i + 2);
    d += `C${f(p1[0] + (p2[0] - p0[0]) / 6)} ${f(p1[1] + (p2[1] - p0[1]) / 6)} ${f(p2[0] - (p3[0] - p1[0]) / 6)} ${f(p2[1] - (p3[1] - p1[1]) / 6)} ${f(p2[0])} ${f(p2[1])}`;
  }
  return closed ? `${d}Z` : d;
}

/** An ellipse drawn by hand: every point is a little off. */
export function blob(cx: number, cy: number, rx: number, ry: number, r: Rand, amt = 1.1, n = Math.max(7, Math.min(12, Math.round((rx + ry) / 3.2)))): string {
  const pts: Pt[] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    pts.push([cx + Math.cos(a) * (rx + (r() - 0.5) * 2 * amt), cy + Math.sin(a) * (ry + (r() - 0.5) * 2 * amt)]);
  }
  return smooth(pts, true);
}

const jitter = (pts: Pt[], r: Rand, amt: number): Pt[] => pts.map(([x, y]): Pt => [x + (r() - 0.5) * 2 * amt, y + (r() - 0.5) * 2 * amt]);
const shape = (pts: Pt[], r: Rand, amt = 0.8) => smooth(jitter(pts, r, amt), true);
const line = (pts: Pt[], r: Rand, amt = 0.7) => smooth(jitter(pts, r, amt), false);

/** A hand-cut polygon (straight edges, slightly off), like a cut-paper shape. */
function cut(pts: Pt[], r: Rand, amt = 0.7): string {
  return `${jitter(pts, r, amt)
    .map(([x, y], i) => `${i ? 'L' : 'M'}${f(x)} ${f(y)}`)
    .join('')}Z`;
}

// -- the pose of each frame -------------------------------------------------------

export interface Pose {
  bob: number; // up (+) and down
  sq: number; // squash and stretch
  lean: number; // degrees
  blink: number; // 0 open .. 1 shut
  mouth: number; // 0 closed .. 1 wide
  wave: number; // -1..1, an arm or a tail
  look: number; // -1..1, where the eyes go
}

const TALK = [0, 0.7, 0.3, 1, 0.2, 0.8, 0, 0.6, 1, 0.3, 0.7, 0.1];

export function poseAt(i: number, talking: boolean): Pose {
  const t = (i / FRAMES) * Math.PI * 2;
  return {
    bob: Math.sin(t) * 2.2,
    sq: Math.cos(t) * 0.02,
    lean: Math.sin(t) * 1.5,
    blink: i === 7 ? 1 : i === 6 || i === 8 ? 0.45 : 0,
    mouth: talking ? TALK[i % TALK.length] : 0,
    wave: Math.sin(t * 2),
    look: [0, 0.3, 0.7, 1, 0.7, 0.3, 0, -0.3, -0.7, -1, -0.7, -0.3][i % FRAMES],
  };
}

const lift = (p: Pose, k = 1) =>
  `translate(0 ${f(-p.bob * k)}) rotate(${f(p.lean)} 60 112) translate(60 112) scale(${f(1 - p.sq)} ${f(1 + p.sq)}) translate(-60 -112)`;

const ink = { stroke: INK, strokeWidth: SW, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const };

interface Draw {
  p: Pose;
  r: Rand;
  dots: string; // url(#…) of the black dot screen
  blueDots: string; // url(#…) of the dark-blue dot screen
}

/** A stripe across a body, as wide as the body is at that height. */
function band(cx: number, cy: number, rx: number, ry: number, y: number, h: number, r: Rand): string {
  const half = (yy: number) => rx * Math.sqrt(Math.max(0, 1 - ((yy - cy) / ry) ** 2)) - 1.5;
  const w1 = half(y);
  const w2 = half(y + h);
  const j = () => (r() - 0.5) * 1.2;
  return `M${f(cx - w1 + j())} ${f(y + j())}L${f(cx + w1 + j())} ${f(y + j())}L${f(cx + w2 + j())} ${f(y + h + j())}L${f(cx - w2 + j())} ${f(y + h + j())}Z`;
}

/** Black shoes, like the man behind the newspaper. */
function Shoes({ r, y = 108 }: { r: Rand; y?: number }) {
  return (
    <g fill={INK} stroke="none">
      <path d={cut([[36, y - 6], [52, y - 6], [55, y + 3], [31, y + 3]], r, 0.6)} />
      <path d={cut([[68, y - 6], [84, y - 6], [89, y + 3], [65, y + 3]], r, 0.6)} />
    </g>
  );
}

// -- the four ----------------------------------------------------------------------

const CELESTE = '#8ecdf5';
const CREAM = '#efe3c4';

/** Rihno: black and white rhino, a cream horn, a sky-blue striped shirt. */
function Rihno({ p, r, dots }: Draw) {
  const torso = shape([[34, 66], [86, 66], [92, 88], [86, 102], [34, 102], [28, 88]], r, 0.8);
  const mouthOpen = p.mouth > 0.12;
  return (
    <g {...ink} transform={lift(p)}>
      <Shoes r={r} />
      {/* arms, skin made of dots */}
      <g transform={`rotate(${f(-4 - p.wave * 3)} 32 72)`}>
        <path d={blob(27, 86, 7, 15, r)} fill="#fff" />
        <path d={blob(27, 86, 7, 15, r)} fill={dots} />
      </g>
      <g transform={`rotate(${f(6 - p.wave * 18)} 88 72)`}>
        <path d={blob(93, 86, 7, 15, r)} fill="#fff" />
        <path d={blob(93, 86, 7, 15, r)} fill={dots} />
      </g>
      {/* the shirt: white with sky-blue stripes */}
      <path d={torso} fill="#fff" />
      {[70, 79, 88, 97].map((y) => (
        <path key={y} d={band(60, 84, 32, 22, y, 4.4, r)} fill={CELESTE} stroke="none" />
      ))}
      <path d={torso} fill="none" />
      {/* the head: ears, skin of dots, a big snout */}
      <path d={blob(36, 26, 7, 8.5, r)} fill={INK} />
      <path d={blob(84, 26, 7, 8.5, r)} fill={INK} />
      <path d={blob(60, 44, 27, 23, r)} fill="#fff" />
      <path d={blob(60, 44, 27, 23, r)} fill={dots} />
      <path d={blob(60, 57, 18, 12, r)} fill="#fff" />
      <path
        d={shape(
          [
            [52, 51],
            [56, 38],
            [60, 22],
            [64, 38],
            [68, 51],
            [60, 53],
          ],
          r,
          0.5,
        )}
        fill={CREAM}
      />
      {/* closed eyes, always */}
      <path d={line([[39, 39], [45, 43.5], [51, 39]], r, 0.4)} fill="none" strokeWidth={SW + p.blink} />
      <path d={line([[69, 39], [75, 43.5], [81, 39]], r, 0.4)} fill="none" strokeWidth={SW + p.blink} />
      <ellipse cx={53} cy={60} rx={1.9} ry={2.4} fill={INK} stroke="none" />
      <ellipse cx={67} cy={60} rx={1.9} ry={2.4} fill={INK} stroke="none" />
      {mouthOpen ? (
        <ellipse cx={60} cy={66} rx={5.4} ry={1.3 + p.mouth * 3.2} fill={INK} />
      ) : (
        <path d={line([[54, 65], [60, 67.5], [66, 65]], r, 0.3)} fill="none" strokeWidth={3} />
      )}
    </g>
  );
}

/** Manchas: white dalmatian with black spots. */
function Manchas({ p, r, dots }: Draw) {
  const mouthOpen = p.mouth > 0.12;
  const eye = (cx: number, cy: number) => (
    <g>
      <ellipse cx={cx} cy={cy} rx={5.8} ry={Math.max(0.9, 6 * (1 - p.blink))} fill="#fff" strokeWidth={3} />
      {p.blink < 0.6 && <circle cx={cx + p.look * 1.8} cy={cy + 0.8} r={2.7} fill={INK} stroke="none" />}
    </g>
  );
  return (
    <g {...ink} transform={lift(p)}>
      <Shoes r={r} />
      {/* the tail wags */}
      <g transform={`rotate(${f(p.wave * 16)} 86 94)`}>
        <path d={line([[84, 96], [97, 90], [102, 76]], r, 0.5)} fill="none" strokeWidth={8.4} />
        <path d={line([[84, 96], [97, 90], [102, 76]], r, 0.5)} fill="none" stroke="#fff" strokeWidth={2.4} />
      </g>
      <path d={blob(31, 86, 7, 14, r)} fill="#fff" />
      <path d={blob(60, 84, 27, 24, r)} fill="#fff" />
      {/* the shadow side, printed in dots */}
      <path d={blob(72, 92, 12, 11, r, 0.6)} fill={dots} stroke="none" />
      <g fill={INK} stroke="none">
        <path d={blob(46, 76, 5.4, 5, r)} />
        <path d={blob(66, 70, 4, 3.6, r)} />
        <path d={blob(52, 96, 4.4, 4, r)} />
        <path d={blob(78, 78, 3.4, 3.8, r)} />
      </g>
      <g transform={`rotate(${f(-p.wave * 14)} 88 72)`}>
        <path d={blob(89, 86, 7, 14, r)} fill="#fff" />
      </g>
      {/* floppy black ears */}
      <g transform="rotate(10 35 44)">
        <path d={blob(35, 45, 9, 16.5, r)} fill={INK} />
      </g>
      <g transform="rotate(-10 85 44)">
        <path d={blob(85, 45, 9, 16.5, r)} fill={INK} />
      </g>
      <path d={blob(60, 44, 23, 20.5, r)} fill="#fff" />
      <path d={blob(73, 37, 8.8, 9, r)} fill={INK} stroke="none" />
      <path d={blob(46, 28, 5, 4.5, r)} fill={INK} stroke="none" />
      <path d={blob(60, 54.5, 12, 9, r)} fill="#fff" />
      {eye(50, 40)}
      {eye(71, 40)}
      <ellipse cx={60} cy={50.5} rx={5.2} ry={3.6} fill={INK} stroke="none" />
      {mouthOpen ? (
        <path d={`M53 58.5 Q60 ${f(60 + p.mouth * 9)} 67 58.5 Q60 59 53 58.5Z`} fill={INK} />
      ) : (
        <path d={line([[60, 54], [60, 57.5], [54.5, 59]], r, 0.25)} fill="none" strokeWidth={3} />
      )}
    </g>
  );
}

const BLUE = '#3d82dc';
const CUFF = '#e6eef9';

/** Hous: an inflated blue medical glove, a beret and a face drawn in marker. */
function Hous({ p, r, blueDots }: Draw) {
  const fingers: Array<{ x: number; y: number; a: number; len: number; w: number; ph: number }> = [
    { x: 41, y: 64, a: -20, len: 29, w: 11.5, ph: 0 },
    { x: 51.5, y: 58, a: -7, len: 34, w: 12, ph: 1.4 },
    { x: 64, y: 58, a: 6, len: 32, w: 11.8, ph: 2.6 },
    { x: 75, y: 64, a: 21, len: 25, w: 10.5, ph: 3.8 },
    { x: 36, y: 83, a: -72, len: 22, w: 12.5, ph: 5 },
  ];
  const sway = (ph: number) => Math.sin(((p.wave + 1) / 2) * Math.PI * 2 + ph) * 3.2;
  const tip = (fg: (typeof fingers)[number]): Pt => {
    const a = ((fg.a + sway(fg.ph) - 90) * Math.PI) / 180;
    return [fg.x + Math.cos(a) * fg.len, fg.y + Math.sin(a) * fg.len];
  };
  const mouthOpen = p.mouth > 0.12;
  const shut = p.blink > 0.6;
  return (
    <g {...ink} transform={lift(p, 1.3)}>
      {/* fingers: ink first, blue after, so they join the palm */}
      {fingers.map((fg, i) => (
        <path key={`o${i}`} d={line([[fg.x, fg.y], tip(fg)], r, 0.6)} fill="none" strokeWidth={fg.w + 8} />
      ))}
      <path d={blob(60, 81, 28.5, 27, r)} fill={INK} stroke="none" />
      <path d={cut([[42, 102], [78, 102], [80, 114], [40, 114]], r, 0.6)} fill={CUFF} />
      <path d={line([[43, 108], [77, 108]], r, 0.4)} fill="none" strokeWidth={2.2} />
      {fingers.map((fg, i) => (
        <path key={`b${i}`} d={line([[fg.x, fg.y], tip(fg)], r, 0.6)} fill="none" stroke={BLUE} strokeWidth={fg.w} />
      ))}
      <path d={blob(60, 81, 25.5, 24, r)} fill={BLUE} stroke="none" />
      {/* the shadow side of the balloon, printed in dark-blue dots */}
      <path d={blob(70, 88, 13, 12, r, 0.6)} fill={blueDots} stroke="none" />
      <path d="M40 79 Q40.5 69 47 64" fill="none" stroke="#fff" strokeWidth={3} />
      {/* the beret */}
      <g transform={`rotate(${f(-9 + p.wave * 2)} 60 62)`}>
        <path d={blob(60, 62, 21, 8.8, r)} fill={INK} />
        <path d={line([[60, 54], [63, 48.5]], r, 0.2)} fill="none" strokeWidth={4.2} />
      </g>
      {/* a face drawn with a marker */}
      {shut ? (
        <>
          <path d={line([[47, 76], [53, 76]], r, 0.4)} fill="none" strokeWidth={3.2} />
          <path d={line([[67, 76], [73, 76]], r, 0.4)} fill="none" strokeWidth={3.2} />
        </>
      ) : (
        <>
          <path d={blob(50 + p.look * 1.2, 76, 2.8, 3.4, r, 0.35, 8)} fill={INK} stroke="none" />
          <path d={blob(70 + p.look * 1.2, 76, 2.8, 3.4, r, 0.35, 8)} fill={INK} stroke="none" />
        </>
      )}
      {mouthOpen ? (
        <ellipse cx={60} cy={88} rx={5.4} ry={1.5 + p.mouth * 3.6} fill={INK} />
      ) : (
        <path d={line([[51, 86], [60, 90.5], [69, 86]], r, 0.35)} fill="none" strokeWidth={3.2} />
      )}
    </g>
  );
}

const LEOPARD = '#d9a24a';

/** Tennessee: an invisible orb wearing leopard glasses, with black eyes. */
function Tennessee({ p, r, dots }: Draw) {
  const mouthOpen = p.mouth > 0.12;
  const lens = (cx: number) => {
    const d = blob(cx, 64, 13, 11, r, 0.5, 10);
    return (
      <g>
        <path d={d} fill="#fff" stroke={INK} strokeWidth={9.4} />
        <path d={d} fill="none" stroke={LEOPARD} strokeWidth={5.6} />
        <path d={d} fill="none" stroke={INK} strokeWidth={2.6} strokeDasharray="2.2 5" />
      </g>
    );
  };
  const eye = (cx: number) => (
    <g>
      <ellipse cx={cx + p.look * 2.4} cy={64.5} rx={3.9} ry={Math.max(0.8, 5.4 * (1 - p.blink))} fill={INK} stroke="none" />
      {p.blink < 0.6 && <circle cx={cx + p.look * 2.4 + 1.3} cy={62.2} r={1.1} fill="#fff" stroke="none" />}
    </g>
  );
  return (
    <g {...ink} transform={lift(p, 1.9)}>
      {/* the orb is invisible: a broken outline and a little dot-screen shade */}
      <path d={blob(60, 66, 38, 38, r, 0.9, 16)} fill="none" strokeWidth={2.6} strokeDasharray="1.2 6" />
      <path d={blob(68, 84, 20, 14, r, 0.8)} fill={dots} stroke="none" opacity={0.55} />
      <path d={line([[33, 63], [25, 60]], r, 0.3)} fill="none" strokeWidth={8.6} />
      <path d={line([[87, 63], [95, 60]], r, 0.3)} fill="none" strokeWidth={8.6} />
      <path d={line([[33, 63], [25, 60]], r, 0.3)} fill="none" stroke={LEOPARD} strokeWidth={4} />
      <path d={line([[87, 63], [95, 60]], r, 0.3)} fill="none" stroke={LEOPARD} strokeWidth={4} />
      <path d={line([[57, 62], [60, 59], [63, 62]], r, 0.2)} fill="none" strokeWidth={7.4} />
      <path d={line([[57, 62], [60, 59], [63, 62]], r, 0.2)} fill="none" stroke={LEOPARD} strokeWidth={3.2} />
      {lens(46)}
      {lens(74)}
      {eye(46)}
      {eye(74)}
      {mouthOpen ? (
        <ellipse cx={60} cy={86} rx={5} ry={1.3 + p.mouth * 3.4} fill={INK} />
      ) : (
        <path d={line([[53, 84], [60, 87.5], [67, 84]], r, 0.3)} fill="none" strokeWidth={3} />
      )}
    </g>
  );
}

const DRAW: Record<CritterShape, (d: Draw) => ReactElement> = {
  rhino: Rihno,
  dalmatian: Manchas,
  glove: Hous,
  orb: Tennessee,
};

/** The 12 hand-drawn frames of a character (every frame inked afresh). */
export function critterFrames(shapeName: CritterShape, talking: boolean, dots = 'url(#dots)', blueDots = 'url(#blue-dots)'): ReactElement[] {
  const base = CRITTER_SHAPES.indexOf(shapeName) * 131;
  const Character = DRAW[shapeName];
  return Array.from({ length: FRAMES }, (_, i) => (
    <g key={i}>
      <Character p={poseAt(i, talking)} r={rng(base + i * 977 + 11)} dots={dots} blueDots={blueDots} />
    </g>
  ));
}

// -- the component -----------------------------------------------------------------

interface CritterProps {
  look: CritterLook;
  status?: NodeStatus;
  size?: number;
  label?: string;
  talking?: boolean;
}

export function NodeCritter({ look, status = 'idle', size = 48, label, talking = false }: CritterProps) {
  const shapeName = castOf(look?.shape);
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const frames = useMemo(() => critterFrames(shapeName, talking, `url(#${uid}d)`, `url(#${uid}b)`), [shapeName, talking, uid]);
  const alert = status === 'needs_you' || status === 'waiting_approval';
  return (
    <span
      className="critter"
      data-status={status}
      data-shape={shapeName}
      data-talking={talking || undefined}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      style={{ width: size, height: size }}
    >
      <svg viewBox="-4 4 128 120" width={size} height={size}>
        <defs>
          <pattern id={`${uid}d`} width={3.4} height={3.4} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <circle cx={1.7} cy={1.7} r={0.95} fill={INK} />
          </pattern>
          <pattern id={`${uid}b`} width={3.4} height={3.4} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <circle cx={1.7} cy={1.7} r={1.05} fill="#1d4f9a" />
          </pattern>
        </defs>
        {frames.map((fr, i) => (
          <g key={i} className="critter-frame" style={{ ['--n' as string]: (FRAMES - i) / FRAMES }}>
            {fr}
          </g>
        ))}
      </svg>
      {alert && (
        <svg className="critter-alert" viewBox="0 0 24 24" width={Math.max(10, size * 0.3)} height={Math.max(10, size * 0.3)} aria-hidden="true">
          <path d="M12 3 V13 M12 18 V20" stroke={INK} strokeWidth={3.2} strokeLinecap="round" />
        </svg>
      )}
    </span>
  );
}
