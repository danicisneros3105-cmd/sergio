import { useId } from 'react';
import type { NodeStatus } from '../../lib/nodes';

// Sergio's own little characters, made like glossy vinyl toys (the look of
// OpenAI's Dots: smooth 3D shapes with a soft sheen, simple eyes and things
// they wear), but our own cast: a pebble, a mochi, a droplet, a heart, a
// frog, a bear, a star, a ghost, a mushroom, a cactus and a planet. Volume
// comes from a lit gradient, a blurred highlight and a soft shadow at the
// base; there is no fur. Pure SVG: no images, no lag.

export type CritterShape =
  | 'bean'
  | 'blob'
  | 'drop'
  | 'heart'
  | 'frog'
  | 'bear'
  | 'star'
  | 'ghost'
  | 'mushroom'
  | 'cactus'
  | 'planet';
export type CritterAccessory =
  | 'none'
  | 'headphones'
  | 'beret'
  | 'glasses'
  | 'sunglasses'
  | 'bow'
  | 'cap'
  | 'beanie'
  | 'crown'
  | 'scarf';
export type CritterEyes = 'dots' | 'happy' | 'big' | 'sleepy' | 'googly';

export interface CritterLook {
  shape: CritterShape;
  color: string;
  accessory: CritterAccessory;
  eyes: CritterEyes;
}

interface ShapeSpec {
  body: string;
  top: number; // y of the top of the head
  eyeY: number;
  eyeGap: number;
  mouthY: number;
  arms?: [number, number, number]; // left x, right x, y
  feet?: number; // y of the feet
  extra?: string; // ears, eye bumps, cactus arms (same colour)
  cap?: string; // the mushroom's cap: the chosen colour, over a cream stem
  spots?: Array<[number, number, number]>; // light spots on top (x, y, r)
  ring?: boolean; // the planet's ring
}

const SHAPES: Record<CritterShape, ShapeSpec> = {
  // 'bean' is drawn as a smooth pebble (wide and low)
  bean: {
    body: 'M60 34 C90 34 104 52 104 72 C104 94 86 104 60 104 C34 104 16 94 16 72 C16 52 30 34 60 34 Z',
    top: 34,
    eyeY: 64,
    eyeGap: 13,
    mouthY: 76,
    arms: [18, 102, 80],
    feet: 102,
  },
  // 'blob' is a soft mochi (a rounded square)
  blob: {
    body: 'M60 28 C92 28 100 36 100 66 C100 96 92 104 60 104 C28 104 20 96 20 66 C20 36 28 28 60 28 Z',
    top: 28,
    eyeY: 62,
    eyeGap: 13,
    mouthY: 74,
    arms: [20, 100, 78],
    feet: 102,
  },
  drop: {
    body: 'M60 12 C68 28 98 56 98 78 C98 96 82 106 60 106 C38 106 22 96 22 78 C22 56 52 28 60 12 Z',
    top: 16,
    eyeY: 72,
    eyeGap: 12,
    mouthY: 84,
    arms: [23, 97, 86],
    feet: 105,
  },
  heart: {
    body: 'M60 104 C40 92 14 74 14 50 C14 34 26 24 40 24 C50 24 56 30 60 38 C64 30 70 24 80 24 C94 24 106 34 106 50 C106 74 80 92 60 104 Z',
    top: 26,
    eyeY: 54,
    eyeGap: 14,
    mouthY: 66,
    arms: [17, 103, 58],
  },
  frog: {
    body: 'M60 36 C86 36 102 52 102 72 C102 94 84 104 60 104 C36 104 18 94 18 72 C18 52 34 36 60 36 Z',
    extra: 'M30 40 a14 14 0 1 1 28 0 a14 14 0 1 1 -28 0 Z M62 40 a14 14 0 1 1 28 0 a14 14 0 1 1 -28 0 Z',
    top: 26,
    eyeY: 39,
    eyeGap: 16,
    mouthY: 70,
    arms: [20, 100, 80],
    feet: 103,
  },
  bear: {
    body: 'M60 26 C84 26 100 44 100 66 C100 90 84 104 60 104 C36 104 20 90 20 66 C20 44 36 26 60 26 Z',
    extra: 'M22 34 a12 12 0 1 1 24 0 a12 12 0 1 1 -24 0 Z M74 34 a12 12 0 1 1 24 0 a12 12 0 1 1 -24 0 Z',
    top: 24,
    eyeY: 58,
    eyeGap: 13,
    mouthY: 70,
    arms: [21, 99, 76],
    feet: 103,
  },
  star: {
    body: 'M60 10 C66 10 69 18 73 30 C75 37 78 40 86 40 C100 40 108 42 108 48 C108 54 100 59 92 66 C86 71 85 74 87 81 C91 95 92 104 86 106 C80 108 72 102 66 97 C62 94 58 94 54 97 C48 102 40 108 34 106 C28 104 29 95 33 81 C35 74 34 71 28 66 C20 59 12 54 12 48 C12 42 20 40 34 40 C42 40 45 37 47 30 C51 18 54 10 60 10 Z',
    top: 14,
    eyeY: 60,
    eyeGap: 10,
    mouthY: 72,
  },
  ghost: {
    body: 'M60 16 C84 16 98 34 98 60 L98 96 C98 104 92 106 88 100 C84 94 80 94 76 100 C72 106 66 106 62 100 C58 94 54 94 50 100 C46 106 40 106 36 100 C32 94 28 94 24 100 C20 106 22 104 22 96 L22 60 C22 34 36 16 60 16 Z',
    top: 16,
    eyeY: 52,
    eyeGap: 12,
    mouthY: 64,
    arms: [23, 97, 68],
  },
  mushroom: {
    body: 'M40 62 L80 62 C84 76 85 94 80 101 C76 107 44 107 40 101 C35 94 36 76 40 62 Z',
    cap: 'M12 60 C12 30 34 12 60 12 C86 12 108 30 108 60 C108 68 102 70 94 70 L26 70 C18 70 12 68 12 60 Z',
    spots: [[38, 32, 7], [62, 24, 5], [84, 38, 8], [26, 52, 4], [96, 58, 4]],
    top: 14,
    eyeY: 82,
    eyeGap: 9,
    mouthY: 92,
    arms: [37, 83, 88],
    feet: 103,
  },
  cactus: {
    body: 'M60 18 C76 18 82 28 82 42 L82 92 C82 102 74 106 60 106 C46 106 38 102 38 92 L38 42 C38 28 44 18 60 18 Z',
    extra:
      'M40 74 C28 74 22 68 22 58 L22 46 C22 38 32 38 32 46 L32 58 C32 63 35 65 40 65 Z M80 64 C92 64 98 58 98 48 L98 38 C98 30 88 30 88 38 L88 48 C88 53 85 55 80 55 Z',
    spots: [[48, 36, 1.6], [72, 34, 1.6], [46, 90, 1.6], [74, 88, 1.6], [27, 50, 1.4], [93, 42, 1.4]],
    top: 20,
    eyeY: 54,
    eyeGap: 9,
    mouthY: 65,
    feet: 105,
  },
  planet: {
    body: 'M60 26 C81 26 98 43 98 64 C98 85 81 102 60 102 C39 102 22 85 22 64 C22 43 39 26 60 26 Z',
    ring: true,
    top: 28,
    eyeY: 58,
    eyeGap: 12,
    mouthY: 70,
  },
};

const OVER_FACE = new Set<CritterAccessory>(['glasses', 'sunglasses', 'headphones']);

function shade(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const mix = (c: number) => Math.round(amount < 0 ? c * (1 + amount) : c + (255 - c) * amount);
  return `#${[mix(r), mix(g), mix(b)].map((c) => c.toString(16).padStart(2, '0')).join('')}`;
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
}

function Eyes({ kind, spec, ink, status }: { kind: CritterEyes; spec: ShapeSpec; ink: string; status: NodeStatus }) {
  const y = spec.eyeY;
  const xs = [60 - spec.eyeGap, 60 + spec.eyeGap];
  const sleepy = status === 'paused' || kind === 'sleepy';
  if (sleepy) {
    return (
      <g stroke={ink} strokeWidth={2.4} strokeLinecap="round" fill="none">
        {xs.map((x) => (
          <path key={x} d={`M${x - 4.5} ${y + 1} Q${x} ${y + 4} ${x + 4.5} ${y + 1}`} />
        ))}
      </g>
    );
  }
  if (kind === 'happy') {
    return (
      <g stroke={ink} strokeWidth={2.6} strokeLinecap="round" fill="none">
        {xs.map((x) => (
          <path key={x} d={`M${x - 4.5} ${y + 2} Q${x} ${y - 4} ${x + 4.5} ${y + 2}`} />
        ))}
      </g>
    );
  }
  if (kind === 'googly') {
    return (
      <g className="critter-blink">
        {xs.map((x) => (
          <g key={x}>
            <circle cx={x} cy={y} r={7.5} fill="#fff" stroke="rgba(0,0,0,0.15)" />
            <circle className="critter-pupil" cx={x + 1.5} cy={y + 1} r={3.4} fill="#111" />
          </g>
        ))}
      </g>
    );
  }
  const r = kind === 'big' ? 4.6 : 3.2;
  return (
    <g className="critter-blink">
      {xs.map((x) => (
        <g key={x}>
          <ellipse cx={x} cy={y} rx={r} ry={r * 1.25} fill={ink} />
          <circle cx={x + r * 0.35} cy={y - r * 0.45} r={r * 0.32} fill="#fff" opacity={0.85} />
        </g>
      ))}
    </g>
  );
}

function Accessory({ kind, spec }: { kind: CritterAccessory; spec: ShapeSpec }) {
  const top = spec.top;
  const ey = spec.eyeY;
  const g = spec.eyeGap;
  switch (kind) {
    case 'headphones':
      return (
        <g>
          <path d={`M${30} ${ey + 2} C${30} ${top - 8} ${90} ${top - 8} ${90} ${ey + 2}`} fill="none" stroke="#1d1d1d" strokeWidth={5} strokeLinecap="round" />
          <rect x={20} y={ey - 6} width={14} height={20} rx={6} fill="#1d1d1d" />
          <rect x={86} y={ey - 6} width={14} height={20} rx={6} fill="#1d1d1d" />
          <rect x={23} y={ey - 3} width={5} height={14} rx={2.5} fill="#3a3a3a" />
          <rect x={92} y={ey - 3} width={5} height={14} rx={2.5} fill="#3a3a3a" />
        </g>
      );
    case 'beret':
      return (
        <g transform={`rotate(-12 60 ${top})`}>
          <ellipse cx={58} cy={top + 2} rx={30} ry={11} fill="#1f2a44" />
          <ellipse cx={58} cy={top - 1} rx={24} ry={6} fill="#2b3a5c" opacity={0.6} />
          <rect x={56} y={top - 13} width={4} height={6} rx={2} fill="#1f2a44" />
        </g>
      );
    case 'glasses':
      return (
        <g fill="none" stroke="#151515" strokeWidth={2.2}>
          <circle cx={60 - g} cy={ey} r={8.5} />
          <circle cx={60 + g} cy={ey} r={8.5} />
          <path d={`M${60 - g + 8.5} ${ey} Q60 ${ey - 3} ${60 + g - 8.5} ${ey}`} />
        </g>
      );
    case 'sunglasses':
      return (
        <g>
          <rect x={60 - g - 10} y={ey - 6} width={20} height={13} rx={6} fill="#111" />
          <rect x={60 + g - 10} y={ey - 6} width={20} height={13} rx={6} fill="#111" />
          <path d={`M${60 - g + 10} ${ey - 2} H${60 + g - 10}`} stroke="#111" strokeWidth={2.5} />
          <rect x={60 - g - 6} y={ey - 3} width={6} height={2.5} rx={1} fill="#fff" opacity={0.5} />
        </g>
      );
    case 'bow':
      return (
        <g transform={`translate(${78} ${top + 4})`}>
          <path d="M0 0 L-12 -8 L-12 8 Z M0 0 L12 -8 L12 8 Z" fill="#ff5c8a" />
          <circle r={3.5} fill="#e0406f" />
        </g>
      );
    case 'cap':
      return (
        <g>
          <path d={`M34 ${top + 10} C34 ${top - 10} 86 ${top - 10} 86 ${top + 10} Z`} fill="#f5f5f5" stroke="rgba(0,0,0,0.12)" />
          <path d={`M80 ${top + 9} Q104 ${top + 8} 108 ${top + 14} L82 ${top + 14} Z`} fill="#9fd3ff" />
          <circle cx={60} cy={top - 4} r={2.5} fill="#9fd3ff" />
        </g>
      );
    case 'beanie':
      return (
        <g>
          <path d={`M30 ${top + 12} C30 ${top - 14} 90 ${top - 14} 90 ${top + 12} Z`} fill="#e94b4b" />
          <rect x={28} y={top + 6} width={64} height={9} rx={4.5} fill="#c93a3a" />
          <circle cx={60} cy={top - 10} r={7} fill="#f3f3f3" />
        </g>
      );
    case 'crown':
      return (
        <path
          d={`M42 ${top + 4} L44 ${top - 12} L52 ${top - 3} L60 ${top - 15} L68 ${top - 3} L76 ${top - 12} L78 ${top + 4} Z`}
          fill="#f6c945"
          stroke="#d9a520"
          strokeWidth={1.5}
          strokeLinejoin="round"
        />
      );
    case 'scarf':
      return (
        <g>
          <path d={`M26 ${spec.mouthY + 10} Q60 ${spec.mouthY + 20} 94 ${spec.mouthY + 10} L94 ${spec.mouthY + 18} Q60 ${spec.mouthY + 28} 26 ${spec.mouthY + 18} Z`} fill="#e94b4b" />
          <rect x={70} y={spec.mouthY + 16} width={9} height={18} rx={3} fill="#c93a3a" />
        </g>
      );
    default:
      return null;
  }
}

export function NodeCritter({
  look,
  status = 'idle',
  size = 48,
  label,
  talking = false,
}: {
  look: CritterLook;
  status?: NodeStatus;
  size?: number;
  label?: string;
  talking?: boolean;
}) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const spec = SHAPES[look.shape] || SHAPES.bean;
  const chosen = /^#[0-9a-f]{6}$/i.test(look.color) ? look.color : '#9fd3ff';
  // The mushroom wears the chosen colour on its cap; its stem is cream.
  const color = spec.cap ? '#f6ead8' : chosen;
  const ink = luminance(color) < 0.32 ? '#f4f4f4' : '#1a1a1a';
  const [ax1, ax2, ay] = spec.arms || [0, 0, 0];
  const lit = (c: string, id: string) => (
    <radialGradient id={id} cx="34%" cy="24%" r="82%">
      <stop offset="0" stopColor={shade(c, 0.42)} />
      <stop offset="0.42" stopColor={c} />
      <stop offset="1" stopColor={shade(c, -0.3)} />
    </radialGradient>
  );
  const sheen = `sheen${uid}`;
  const soft = `soft${uid}`;
  const ringFront = 'M14 70 C14 82 106 66 106 54';
  const ringBack = 'M14 70 C14 58 106 42 106 54';
  return (
    <span
      className="critter"
      data-status={status}
      data-talking={talking || undefined}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 120 124" width={size} height={size}>
        <defs>
          {lit(color, `body${uid}`)}
          {lit(chosen, `cap${uid}`)}
          {lit(shade(color, -0.06), `limb${uid}`)}
          <filter id={soft} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3.2" />
          </filter>
          <linearGradient id={`base${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0.55" stopColor="#000" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity="0.16" />
          </linearGradient>
          <clipPath id={sheen}>
            <path d={spec.cap || spec.body} />
          </clipPath>
        </defs>
        <ellipse className="critter-shadow" cx="60" cy="114" rx="30" ry="5" fill="#000" opacity="0.18" filter={`url(#${soft})`} />
        <g className="critter-body">
          {spec.ring && <path d={ringBack} fill="none" stroke={shade(chosen, 0.55)} strokeWidth={7} strokeLinecap="round" opacity={0.9} />}
          {spec.arms && (
            <g fill={`url(#limb${uid})`}>
              <ellipse className="critter-arm critter-arm-l" cx={ax1} cy={ay} rx={7.5} ry={11} />
              <ellipse className="critter-arm critter-arm-r" cx={ax2} cy={ay} rx={7.5} ry={11} />
            </g>
          )}
          {spec.feet && (
            <g fill={`url(#limb${uid})`}>
              <ellipse cx={47} cy={spec.feet + 3} rx={10} ry={6} />
              <ellipse cx={73} cy={spec.feet + 3} rx={10} ry={6} />
            </g>
          )}
          <path d={spec.body} fill={`url(#body${uid})`} />
          {spec.extra && <path d={spec.extra} fill={`url(#body${uid})`} />}
          <path d={spec.body} fill={`url(#base${uid})`} />
          {spec.cap && <path d={spec.cap} fill={`url(#cap${uid})`} />}
          {spec.spots?.map(([x, y, r]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill="#fff" opacity={spec.cap ? 0.92 : 0.7} />
          ))}
          {/* the vinyl sheen: a soft highlight and a crisp glint, top left */}
          <g clipPath={`url(#${sheen})`}>
            <ellipse cx={42} cy={spec.top + 16} rx={20} ry={11} fill="#fff" opacity={0.55} filter={`url(#${soft})`} transform={`rotate(-24 42 ${spec.top + 16})`} />
          </g>
          <ellipse cx={38} cy={spec.top + 12} rx={5.5} ry={3} fill="#fff" opacity={0.85} transform={`rotate(-30 38 ${spec.top + 12})`} />
          {spec.ring && <path d={ringFront} fill="none" stroke={shade(chosen, 0.55)} strokeWidth={7} strokeLinecap="round" />}
          {!OVER_FACE.has(look.accessory) && <Accessory kind={look.accessory} spec={spec} />}
          <ellipse cx={60 - spec.eyeGap - 7} cy={spec.eyeY + 9} rx={5.5} ry={3.2} fill="#ff6f91" opacity={0.4} filter={`url(#${soft})`} />
          <ellipse cx={60 + spec.eyeGap + 7} cy={spec.eyeY + 9} rx={5.5} ry={3.2} fill="#ff6f91" opacity={0.4} filter={`url(#${soft})`} />
          <Eyes kind={look.shape === 'frog' ? 'googly' : look.eyes} spec={spec} ink={ink} status={status} />
          <path
            className="critter-mouth"
            d={`M${55} ${spec.mouthY} Q60 ${spec.mouthY + 4.5} ${65} ${spec.mouthY}`}
            stroke={ink}
            strokeWidth={2.2}
            strokeLinecap="round"
            fill={talking ? ink : 'none'}
          />
          {OVER_FACE.has(look.accessory) && <Accessory kind={look.accessory} spec={spec} />}
        </g>
        {(status === 'needs_you' || status === 'waiting_approval') && (
          <g className="critter-alert">
            <path d="M96 10 L100 2 M104 14 L112 10 M92 6 L92 -2" stroke="var(--color-text, #1a1a1a)" strokeWidth={3} strokeLinecap="round" />
          </g>
        )}
      </svg>
    </span>
  );
}

const SHAPE_LIST: CritterShape[] = ['bean', 'blob', 'drop', 'heart', 'frog', 'bear', 'star', 'ghost', 'mushroom', 'cactus', 'planet'];
export const CRITTER_SHAPES = SHAPE_LIST;
