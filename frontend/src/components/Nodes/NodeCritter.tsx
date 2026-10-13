import { useId } from 'react';
import type { NodeStatus } from '../../lib/nodes';

// Sergio's own plush characters (inspired by the felt toys of Dots and Muse,
// drawn from scratch): a fuzzy edge (turbulence-displaced outline), felt
// fibres (fine noise), soft volume (light from the top left), little arms
// that wave, and things they wear. Any combination of shape × colour ×
// accessory × eyes is a character. Pure SVG: no images, no lag.

export type CritterShape = 'bean' | 'blob' | 'drop' | 'heart' | 'frog' | 'bear' | 'star' | 'ghost';
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
  extra?: string; // ears, eye bumps (same felt)
}

const SHAPES: Record<CritterShape, ShapeSpec> = {
  bean: {
    body: 'M60 16 C86 16 96 36 96 58 C96 86 82 104 60 104 C38 104 24 86 24 58 C24 36 34 16 60 16 Z',
    top: 16,
    eyeY: 50,
    eyeGap: 12,
    mouthY: 62,
    arms: [25, 95, 70],
    feet: 103,
  },
  blob: {
    body: 'M60 22 C80 18 100 32 101 54 C103 76 96 100 70 103 C52 106 22 102 19 78 C16 56 30 26 60 22 Z',
    top: 22,
    eyeY: 54,
    eyeGap: 13,
    mouthY: 66,
    arms: [20, 100, 72],
    feet: 102,
  },
  drop: {
    body: 'M60 14 C68 14 100 78 100 92 C100 104 86 106 60 106 C34 106 20 104 20 92 C20 78 52 14 60 14 Z',
    top: 14,
    eyeY: 66,
    eyeGap: 12,
    mouthY: 78,
    arms: [28, 92, 82],
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
    body: 'M60 12 C64 12 66 16 70 32 C72 40 74 42 82 42 C100 42 106 44 106 48 C106 52 98 58 88 66 C82 70 82 74 84 80 C90 98 90 104 86 106 C82 108 74 102 66 96 C62 92 58 92 54 96 C46 102 38 108 34 106 C30 104 30 98 36 80 C38 74 38 70 32 66 C22 58 14 52 14 48 C14 44 20 42 38 42 C46 42 48 40 50 32 C54 16 56 12 60 12 Z',
    top: 14,
    eyeY: 58,
    eyeGap: 10,
    mouthY: 70,
  },
  ghost: {
    body: 'M60 16 C84 16 98 34 98 60 L98 98 C98 104 92 106 88 100 C84 94 80 94 76 100 C72 106 66 106 62 100 C58 94 54 94 50 100 C46 106 40 106 36 100 C32 94 28 94 24 100 C20 106 22 104 22 98 L22 60 C22 34 36 16 60 16 Z',
    top: 16,
    eyeY: 52,
    eyeGap: 12,
    mouthY: 64,
    arms: [23, 97, 68],
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
            <circle cx={x} cy={y} r={5} fill="#fff" stroke="rgba(0,0,0,0.1)" />
            <circle className="critter-pupil" cx={x + 1.5} cy={y + 1} r={2.8} fill="#292431" />
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
  const color = /^#[0-9a-f]{6}$/i.test(look.color) ? look.color : '#9fd3ff';
  const ink = luminance(color) < 0.32 ? '#f4f4f4' : '#1a1a1a';
  const fuzz = size >= 40 ? 2.0 : 0.7;
  const arm = shade(color, -0.08);
  const [ax1, ax2, ay] = spec.arms || [0, 0, 0];
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
          <filter id={`fur${uid}`} x="-15%" y="-15%" width="130%" height="130%">
            <feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="1" seed="7" result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale={fuzz} xChannelSelector="R" yChannelSelector="G" result="d" />
            <feTurbulence type="fractalNoise" baseFrequency="2.2" numOctaves="1" seed="3" result="f" />
            <feColorMatrix in="f" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.08 0" result="fibres" />
            <feComposite in="fibres" in2="d" operator="in" result="fibresIn" />
            <feMerge>
              <feMergeNode in="d" />
              <feMergeNode in="fibresIn" />
            </feMerge>
          </filter>
          <radialGradient id={`vol${uid}`} cx="34%" cy="26%" r="78%">
            <stop offset="0" stopColor="#fff" stopOpacity="0.42" />
            <stop offset="0.45" stopColor="#fff" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity="0.14" />
          </radialGradient>
        </defs>
        <ellipse className="critter-shadow" cx="60" cy="116" rx="30" ry="5" fill="#000" opacity="0.08" />
        <g className="critter-body">
          {spec.arms && (
            <g filter={`url(#fur${uid})`}>
              <ellipse className="critter-arm critter-arm-l" cx={ax1} cy={ay} rx={8} ry={12} fill={arm} />
              <ellipse className="critter-arm critter-arm-r" cx={ax2} cy={ay} rx={8} ry={12} fill={arm} />
            </g>
          )}
          {spec.feet && (
            <g filter={`url(#fur${uid})`} fill={shade(color, -0.12)}>
              <ellipse cx={46} cy={spec.feet + 4} rx={10} ry={6} />
              <ellipse cx={74} cy={spec.feet + 4} rx={10} ry={6} />
            </g>
          )}
          <g filter={`url(#fur${uid})`}>
            <path d={spec.body} fill={color} />
            {spec.extra && <path d={spec.extra} fill={color} />}
          </g>
          <path d={spec.body} fill={`url(#vol${uid})`} />
          {spec.extra && <path d={spec.extra} fill={`url(#vol${uid})`} />}
          {!OVER_FACE.has(look.accessory) && <Accessory kind={look.accessory} spec={spec} />}
          <ellipse cx={60 - spec.eyeGap - 7} cy={spec.eyeY + 9} rx={5} ry={3} fill="#ff7a9a" opacity={0.35} />
          <ellipse cx={60 + spec.eyeGap + 7} cy={spec.eyeY + 9} rx={5} ry={3} fill="#ff7a9a" opacity={0.35} />
          <Eyes kind={look.eyes} spec={spec} ink={ink} status={status} />
          <path
            className="critter-mouth"
            d={`M${54} ${spec.mouthY} Q60 ${spec.mouthY + 5} ${66} ${spec.mouthY}`}
            stroke={ink}
            strokeWidth={2.2}
            strokeLinecap="round"
            fill={talking ? ink : 'none'}
          />
          {OVER_FACE.has(look.accessory) && <Accessory kind={look.accessory} spec={spec} />}
        </g>
        {(status === 'needs_you' || status === 'waiting_approval') && (
          <g className="critter-alert">
            <path d="M96 10 L100 2 M104 14 L112 10 M92 6 L92 -2" stroke="var(--color-accent, #9fd3ff)" strokeWidth={3} strokeLinecap="round" />
          </g>
        )}
      </svg>
    </span>
  );
}

const SHAPE_LIST: CritterShape[] = ['bean', 'blob', 'drop', 'heart', 'frog', 'bear', 'star', 'ghost'];
export const CRITTER_SHAPES = SHAPE_LIST;
