import { useId, useMemo, type ReactElement } from 'react';
import type { NodeStatus } from '../../lib/nodes';
import './nodes.css';

// The Nodes: a fixed cast of four, drawn in ink and animated like a
// phenakistoscope (owner, oct. 2026). Nobody designs them.
//
//   rhino      closed eyes, a sky-blue and white striped shirt
//   dalmatian  white with black spots
//   glove      an inflated blue medical glove, a beret, a marker-drawn face
//   orb        an invisible orb: leopard glasses and black eyes
//
// Each one is drawn in 12 frames. Every frame is a fresh hand-drawn pass (the
// outlines wobble a little differently each time, the way ink animation
// boils) and the frames play in order, 12 to a turn, like the drawings
// around the edge of a phenakistoscope disc. Large, the disc itself is shown:
// the ring of frames turns one step at a time while its window plays the
// result. Small, a round paper medallion plays the same frames. The timing
// is pure CSS (steps), so a list of Nodes costs no script at all.

export type CritterShape = 'rhino' | 'dalmatian' | 'glove' | 'orb';
export const CRITTER_SHAPES: CritterShape[] = ['rhino', 'dalmatian', 'glove', 'orb'];

/** Loose on purpose: Nodes saved before the cast was fixed carry other shapes. */
export interface CritterLook {
  shape: string;
  color?: string;
  accessory?: string;
  eyes?: string;
}

export const FRAMES = 12;
const INK = '#17171a';
const PAPER = '#f2ecdc';
const PAPER_HUB = '#f8f4ea';
const SW = 3.9;

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

/** A closed shape through the given points, each a little off. */
function shape(pts: Pt[], r: Rand, amt = 0.8): string {
  return smooth(
    pts.map(([x, y]): Pt => [x + (r() - 0.5) * 2 * amt, y + (r() - 0.5) * 2 * amt]),
    true,
  );
}

/** An open line through the points, each a little off. */
function line(pts: Pt[], r: Rand, amt = 0.7): string {
  return smooth(
    pts.map(([x, y]): Pt => [x + (r() - 0.5) * 2 * amt, y + (r() - 0.5) * 2 * amt]),
    false,
  );
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
    bob: Math.sin(t) * 2.4,
    sq: Math.cos(t) * 0.022,
    lean: Math.sin(t) * 1.7,
    blink: i === 7 ? 1 : i === 6 || i === 8 ? 0.45 : 0,
    mouth: talking ? TALK[i % TALK.length] : 0,
    wave: Math.sin(t * 2),
    look: [0, 0.3, 0.7, 1, 0.7, 0.3, 0, -0.3, -0.7, -1, -0.7, -0.3][i % FRAMES],
  };
}

const lift = (p: Pose, k = 1) =>
  `translate(0 ${f(-p.bob * k)}) rotate(${f(p.lean)} 60 110) translate(60 112) scale(${f(1 - p.sq)} ${f(1 + p.sq)}) translate(-60 -112)`;

const ink = { stroke: INK, strokeWidth: SW, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const };

interface Draw {
  p: Pose;
  r: Rand;
}

/** A stripe across a body, as wide as the body is at that height. */
function band(cx: number, cy: number, rx: number, ry: number, y: number, h: number, r: Rand): string {
  const half = (yy: number) => rx * Math.sqrt(Math.max(0, 1 - ((yy - cy) / ry) ** 2)) - 1;
  const w1 = half(y);
  const w2 = half(y + h);
  const j = () => (r() - 0.5) * 1.2;
  return `M${f(cx - w1 + j())} ${f(y + j())}L${f(cx + w1 + j())} ${f(y + j())}L${f(cx + w2 + j())} ${f(y + h + j())}L${f(cx - w2 + j())} ${f(y + h + j())}Z`;
}

// -- the four ----------------------------------------------------------------------

const GREY = '#a7a9b1';
const GREY_LIGHT = '#c9cbd1';
const CELESTE = '#9fd3ff';
const CREAM = '#efe6cf';

function Rhino({ p, r }: Draw) {
  const torso = blob(60, 82, 29, 27, r);
  const mouthOpen = p.mouth > 0.12;
  return (
    <g {...ink} transform={lift(p)}>
      <path d={blob(46, 105, 8.5, 9, r)} fill={GREY} />
      <path d={blob(74, 105, 8.5, 9, r)} fill={GREY} />
      <g transform={`rotate(${f(-6 - p.wave * 3)} 34 70)`}>
        <path d={blob(30, 84, 7, 13.5, r)} fill={GREY} />
      </g>
      <path d={torso} fill="#fff" />
      {[64, 73, 82, 91, 100].map((y) => (
        <path key={y} d={band(60, 82, 29, 27, y, 4.6, r)} fill={CELESTE} stroke="none" />
      ))}
      <path d={torso} fill="none" />
      <g transform={`rotate(${f(8 - p.wave * 16)} 86 70)`}>
        <path d={blob(90, 84, 7, 13.5, r)} fill={GREY} />
      </g>
      <path d={blob(37, 27, 7.5, 8.5, r)} fill={GREY} />
      <path d={blob(83, 27, 7.5, 8.5, r)} fill={GREY} />
      <path d={blob(60, 44, 26, 22, r)} fill={GREY} />
      <path d={blob(60, 55, 17, 12.5, r)} fill={GREY_LIGHT} />
      <path
        d={shape(
          [
            [53, 49],
            [56, 38],
            [60, 25],
            [64, 38],
            [67, 49],
            [60, 51],
          ],
          r,
          0.5,
        )}
        fill={CREAM}
      />
      {/* closed eyes */}
      <path d={line([[40, 40.5], [46, 45.5], [52, 40.5]], r, 0.5)} fill="none" strokeWidth={SW + p.blink * 0.9} />
      <path d={line([[68, 40.5], [74, 45.5], [80, 40.5]], r, 0.5)} fill="none" strokeWidth={SW + p.blink * 0.9} />
      <ellipse cx={53.5} cy={58} rx={1.7} ry={2.2} fill={INK} stroke="none" />
      <ellipse cx={66.5} cy={58} rx={1.7} ry={2.2} fill={INK} stroke="none" />
      {mouthOpen ? (
        <ellipse cx={60} cy={65} rx={5.4} ry={1.3 + p.mouth * 3.4} fill={INK} />
      ) : (
        <path d={line([[54, 63], [60, 66], [66, 63]], r, 0.3)} fill="none" strokeWidth={2.6} />
      )}
    </g>
  );
}

function Dalmatian({ p, r }: Draw) {
  const mouthOpen = p.mouth > 0.12;
  const eye = (cx: number, cy: number) => (
    <g>
      <ellipse cx={cx} cy={cy} rx={5.6} ry={Math.max(0.8, 5.8 * (1 - p.blink))} fill="#fff" strokeWidth={2.6} />
      {p.blink < 0.6 && <circle cx={cx + p.look * 1.7} cy={cy + 0.8} r={2.5} fill={INK} stroke="none" />}
    </g>
  );
  return (
    <g {...ink} transform={lift(p)}>
      {/* the tail wags */}
      <g transform={`rotate(${f(p.wave * 14)} 86 94)`}>
        <path d={line([[84, 96], [96, 90], [101, 77]], r, 0.5)} fill="none" strokeWidth={7.4} />
        <path d={line([[84, 96], [96, 90], [101, 77]], r, 0.5)} fill="none" stroke="#fff" strokeWidth={2.2} />
      </g>
      <path d={blob(46, 106, 8.5, 8, r)} fill="#fff" />
      <path d={blob(74, 106, 8.5, 8, r)} fill="#fff" />
      <path d={blob(33, 85, 6.5, 12.5, r)} fill="#fff" />
      <path d={blob(60, 82, 26.5, 26, r)} fill="#fff" />
      <g fill={INK} stroke="none">
        <path d={blob(48, 76, 5, 4.6, r)} />
        <path d={blob(70, 90, 6.2, 5.4, r)} />
        <path d={blob(64, 69, 3.8, 3.4, r)} />
        <path d={blob(50, 97, 4, 3.6, r)} />
        <path d={blob(76, 74, 3, 3.4, r)} />
      </g>
      <g transform={`rotate(${f(-p.wave * 12)} 86 72)`}>
        <path d={blob(87, 85, 6.5, 12.5, r)} fill="#fff" />
      </g>
      {/* floppy ears */}
      <g transform="rotate(10 36 44)">
        <path d={blob(36, 45, 8.2, 15.5, r)} fill={INK} />
      </g>
      <g transform="rotate(-10 84 44)">
        <path d={blob(84, 45, 8.2, 15.5, r)} fill={INK} />
      </g>
      <path d={blob(60, 44, 22.5, 20, r)} fill="#fff" />
      <path d={blob(72, 37.5, 8.4, 8.6, r)} fill={INK} stroke="none" />
      <path d={blob(46.5, 29, 5, 4.4, r)} fill={INK} stroke="none" />
      <path d={blob(60, 54, 11.5, 8.8, r)} fill="#fff" />
      {eye(50, 40)}
      {eye(70, 40)}
      <ellipse cx={60} cy={50} rx={4.8} ry={3.4} fill={INK} stroke="none" />
      {mouthOpen ? (
        <path d={`M53 58 Q60 ${f(60 + p.mouth * 9)} 67 58 Q60 58.5 53 58Z`} fill={INK} />
      ) : (
        <path d={line([[60, 53], [60, 57], [54.5, 58.6]], r, 0.25)} fill="none" strokeWidth={2.4} />
      )}
    </g>
  );
}

const BLUE = '#4a8fe0';
const CUFF = '#dfeaf9';

function Glove({ p, r }: Draw) {
  const fingers: Array<{ x: number; y: number; a: number; len: number; w: number; ph: number }> = [
    { x: 41, y: 64, a: -20, len: 29, w: 11, ph: 0 },
    { x: 51.5, y: 58, a: -7, len: 34, w: 11.4, ph: 1.4 },
    { x: 64, y: 58, a: 6, len: 32, w: 11.2, ph: 2.6 },
    { x: 75, y: 64, a: 21, len: 25, w: 10, ph: 3.8 },
    { x: 36, y: 83, a: -72, len: 22, w: 12, ph: 5 },
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
      {/* fingers: outline first, blue after, so they join the palm */}
      {fingers.map((fg, i) => (
        <path key={`o${i}`} d={line([[fg.x, fg.y], tip(fg)], r, 0.6)} fill="none" strokeWidth={fg.w + 6.4} />
      ))}
      <path d={blob(60, 81, 28, 26.5, r)} fill={INK} stroke="none" />
      <path d={blob(60, 107, 19, 8, r)} fill={CUFF} />
      <path d={line([[44, 104], [60, 108], [76, 104]], r, 0.3)} fill="none" strokeWidth={1.8} />
      {fingers.map((fg, i) => (
        <path key={`b${i}`} d={line([[fg.x, fg.y], tip(fg)], r, 0.6)} fill="none" stroke={BLUE} strokeWidth={fg.w} />
      ))}
      <path d={blob(60, 81, 25.5, 24, r)} fill={BLUE} stroke="none" />
      {/* the shine on the balloon */}
      <path d="M40 78 Q40.5 68 47 63" fill="none" stroke="#fff" strokeWidth={2.8} opacity={0.75} />
      {/* the beret */}
      <g transform={`rotate(${f(-9 + p.wave * 2)} 60 62)`}>
        <path d={blob(60, 62, 20, 8.4, r)} fill="#3a3a42" />
        <path d={line([[60, 54.5], [62.5, 49.5]], r, 0.2)} fill="none" strokeWidth={3.6} />
      </g>
      {/* a face drawn with a marker */}
      {shut ? (
        <>
          <path d={line([[47, 76], [53, 76]], r, 0.4)} fill="none" strokeWidth={2.8} />
          <path d={line([[67, 76], [73, 76]], r, 0.4)} fill="none" strokeWidth={2.8} />
        </>
      ) : (
        <>
          <path d={blob(50 + p.look * 1.2, 76, 2.6, 3.2, r, 0.35, 8)} fill={INK} stroke="none" />
          <path d={blob(70 + p.look * 1.2, 76, 2.6, 3.2, r, 0.35, 8)} fill={INK} stroke="none" />
        </>
      )}
      {mouthOpen ? (
        <ellipse cx={60} cy={88} rx={5.4} ry={1.5 + p.mouth * 3.6} fill={INK} />
      ) : (
        <path d={line([[51, 86], [60, 90.5], [69, 86]], r, 0.35)} fill="none" strokeWidth={2.8} />
      )}
    </g>
  );
}

const LEOPARD = '#d6a24a';

function Orb({ p, r }: Draw) {
  const mouthOpen = p.mouth > 0.12;
  const lens = (cx: number) => {
    const d = blob(cx, 64, 12.6, 10.8, r, 0.5, 10);
    return (
      <g>
        <path d={d} fill="#fff" fillOpacity={0.55} stroke={INK} strokeWidth={8.2} />
        <path d={d} fill="none" stroke={LEOPARD} strokeWidth={5.2} />
        {/* the spots of the leopard print */}
        <path d={d} fill="none" stroke={INK} strokeWidth={2.4} strokeDasharray="2.2 5.2" />
      </g>
    );
  };
  const eye = (cx: number) => (
    <g>
      <ellipse cx={cx + p.look * 2.4} cy={64.5} rx={3.7} ry={Math.max(0.7, 5.2 * (1 - p.blink))} fill={INK} stroke="none" />
      {p.blink < 0.6 && <circle cx={cx + p.look * 2.4 + 1.3} cy={62.3} r={1.1} fill="#fff" stroke="none" />}
    </g>
  );
  return (
    <g {...ink} transform={lift(p, 1.9)}>
      {/* the orb is invisible: only a dotted outline and a glint */}
      <path d={blob(60, 66, 37, 37, r, 0.9, 16)} fill="#fff" fillOpacity={0.35} strokeWidth={2.2} strokeDasharray="1.4 5.4" />
      <path d="M33 56 Q36 44 48 38" fill="none" stroke="#fff" strokeWidth={3} opacity={0.9} />
      <path d={line([[34, 63], [27, 60.5]], r, 0.3)} fill="none" strokeWidth={7.4} />
      <path d={line([[86, 63], [93, 60.5]], r, 0.3)} fill="none" strokeWidth={7.4} />
      <path d={line([[34, 63], [27, 60.5]], r, 0.3)} fill="none" stroke={LEOPARD} strokeWidth={3.6} />
      <path d={line([[86, 63], [93, 60.5]], r, 0.3)} fill="none" stroke={LEOPARD} strokeWidth={3.6} />
      <path d={line([[57, 62], [60, 59.5], [63, 62]], r, 0.2)} fill="none" strokeWidth={6.6} />
      <path d={line([[57, 62], [60, 59.5], [63, 62]], r, 0.2)} fill="none" stroke={LEOPARD} strokeWidth={3} />
      {lens(46)}
      {lens(74)}
      {eye(46)}
      {eye(74)}
      {mouthOpen ? (
        <ellipse cx={60} cy={85} rx={5} ry={1.3 + p.mouth * 3.4} fill={INK} />
      ) : (
        <path d={line([[53, 83], [60, 86.5], [67, 83]], r, 0.3)} fill="none" strokeWidth={2.6} />
      )}
    </g>
  );
}

const DRAW: Record<CritterShape, (d: Draw) => ReactElement> = {
  rhino: Rhino,
  dalmatian: Dalmatian,
  glove: Glove,
  orb: Orb,
};

/** The 12 hand-drawn frames of a character (every frame inked afresh). */
export function critterFrames(shapeName: CritterShape, talking: boolean): ReactElement[] {
  const base = CRITTER_SHAPES.indexOf(shapeName) * 131;
  return Array.from({ length: FRAMES }, (_, i) => {
    const Character = DRAW[shapeName];
    const r = rng(base + i * 977 + 11);
    const grounded = shapeName !== 'orb';
    const shadow = 24 - (grounded ? 0 : Math.max(0, poseAt(i, false).bob) * 1.4);
    return (
      <g key={i}>
        <ellipse cx={60} cy={116} rx={shadow} ry={3.4} fill={INK} opacity={0.14} />
        <Character p={poseAt(i, talking)} r={r} />
      </g>
    );
  });
}

// -- the component -----------------------------------------------------------------

interface CritterProps {
  look: CritterLook;
  status?: NodeStatus;
  size?: number;
  label?: string;
  talking?: boolean;
  /** Show the whole phenakistoscope disc (by default from 96 px up). */
  disc?: boolean;
}

/** Each frame plays during its twelfth of the turn (CSS steps, no script). */
function Playing({ frames, from }: { frames: ReactElement[]; from?: string }) {
  return (
    <>
      {frames.map((fr, i) => {
        const style = { ['--n' as string]: (FRAMES - i) / FRAMES };
        return from ? (
          <use key={i} href={`#${from}${i}`} className="critter-frame" style={style} />
        ) : (
          <g key={i} className="critter-frame" style={style}>
            {fr}
          </g>
        );
      })}
    </>
  );
}

const slit = (angle: number, r1: number, r2: number, c: number) => (
  <line
    key={angle}
    x1={c}
    y1={c - r1}
    x2={c}
    y2={c - r2}
    stroke={INK}
    strokeWidth={4.2}
    strokeLinecap="round"
    transform={`rotate(${angle} ${c} ${c})`}
  />
);

export function NodeCritter({ look, status = 'idle', size = 48, label, talking = false, disc }: CritterProps) {
  const shapeName = castOf(look?.shape);
  const frames = useMemo(() => critterFrames(shapeName, talking), [shapeName, talking]);
  const showDisc = disc ?? size >= 96;
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const alert = status === 'needs_you' || status === 'waiting_approval';
  return (
    <span
      className="critter"
      data-status={status}
      data-shape={shapeName}
      data-talking={talking || undefined}
      data-disc={showDisc || undefined}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      style={{ width: size, height: size }}
    >
      {showDisc ? (
        <svg viewBox="0 0 240 240" width={size} height={size}>
          <defs>
            {frames.map((fr, i) => (
              <g key={i} id={`${uid}f${i}`}>
                {fr}
              </g>
            ))}
          </defs>
          <circle cx={120} cy={120} r={117} fill={PAPER} stroke={INK} strokeWidth={4} />
          <g className="critter-ring" style={{ transformOrigin: '120px 120px' }}>
            {Array.from({ length: FRAMES }, (_, i) => slit(i * 30 + 15, 106, 114, 120))}
            {frames.map((_, i) => (
              <use
                key={i}
                href={`#${uid}f${i}`}
                transform={`rotate(${i * 30} 120 120) translate(${f(120 - 60 * 0.33)} ${f(120 - 81 - 62 * 0.33)}) scale(0.33)`}
              />
            ))}
          </g>
          <circle cx={120} cy={120} r={43} fill={PAPER_HUB} stroke={INK} strokeWidth={3.4} />
          <g transform="translate(120 123) scale(0.5) translate(-60 -62)">
            <Playing frames={frames} from={`${uid}f`} />
          </g>
          <path d="M112 3 L128 3 L120 17 Z" fill={INK} />
        </svg>
      ) : (
        <svg viewBox="0 0 120 120" width={size} height={size}>
          <circle cx={60} cy={60} r={57} fill={PAPER} stroke={INK} strokeWidth={3.4} />
          <g className="critter-ring" style={{ transformOrigin: '60px 60px' }}>
            {Array.from({ length: FRAMES }, (_, i) => slit(i * 30 + 15, 47, 53, 60))}
          </g>
          <g transform="translate(16 12) scale(0.72)">
            <Playing frames={frames} />
          </g>
        </svg>
      )}
      {alert && (
        <svg className="critter-alert" viewBox="0 0 24 24" width={Math.max(10, size * 0.3)} height={Math.max(10, size * 0.3)} aria-hidden="true">
          <path d="M12 3 V13 M12 18 V20" stroke={INK} strokeWidth={3.2} strokeLinecap="round" />
        </svg>
      )}
    </span>
  );
}
