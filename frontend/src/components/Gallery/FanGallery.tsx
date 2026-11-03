// A fan of cards: the pictures, videos and 3D models people made with Sergio
// spread from one pivot like a hand of cards. Smooth like a dock (owner,
// 2 Nov 2026: «más smooth el movimiento de la galería y más cool
// visualmente»): the pointer is followed continuously, the card under it rises
// and its neighbours a little less, everything eases with a spring written to
// the DOM directly (no React render per frame, and the loop stops once still).
// The lifted card tilts toward the pointer with a moving sheen, the picture's
// own colour glows behind the fan, and a new hand is dealt in.
import { useCallback, useEffect, useRef, useState } from 'react';
import './gallery.css';

export interface FanItem {
  key: string;
  kind: 'imagen' | 'video' | '3d';
  title: string;
  src?: string;
  /** a small JPEG of it (the card shows this, the full file opens on click) */
  thumb?: string;
  note?: string;
}

interface Props {
  items: FanItem[];
  /** a click anywhere on the fan: the preview opens the whole gallery, on this
   *  card, out of the fan's own rectangle */
  onOpen: (item: FanItem, index: number, from: DOMRect | null) => void;
  /** how many cards are in the hand at once */
  hand?: number;
}

const EASE = 0.16; // how much of the way each frame covers
const REACH = 0.9; // how far the rise spreads to the neighbours (in cards)

/** The rise of card *i* when the pointer is over card *at* (0..1). */
export function rise(i: number, at: number | null): number {
  if (at === null) return 0;
  const d = i - at;
  return Math.exp(-(d * d) / (2 * REACH * REACH));
}

function transformOf(angle: number, lift: number, push: number): string {
  return `rotate(${(angle + push).toFixed(2)}deg) translateY(${(-44 * lift).toFixed(1)}px) scale(${(1 + 0.08 * lift).toFixed(3)})`;
}

function reducedMotion(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

export function FanGallery({ items, onOpen, hand = 9 }: Props) {
  const [start, setStart] = useState(0);
  const [lift, setLift] = useState<number | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const cards = useRef<(HTMLButtonElement | null)[]>([]);
  const target = useRef<number | null>(null);
  const now = useRef<number[]>([]);
  const tilt = useRef<number[]>([]);
  const frame = useRef(0);
  const pointer = useRef<string>('mouse');
  const shown = items.slice(start, start + hand);
  const n = shown.length;
  const spread = Math.min(70, 8 * (n - 1));
  const angleOf = useCallback((i: number) => (n > 1 ? (i / (n - 1) - 0.5) * spread : 0), [n, spread]);

  // The spring: every card eases toward its rise; the loop ends when still.
  const step = useCallback(() => {
    frame.current = 0;
    const k = reducedMotion() ? 1 : EASE;
    let moving = false;
    let top = -1;
    let best = 0.02;
    for (let i = 0; i < n; i++) {
      const el = cards.current[i];
      if (!el) continue;
      const goal = rise(i, target.current);
      const was = now.current[i] ?? 0;
      const v = was + (goal - was) * k;
      now.current[i] = Math.abs(goal - v) < 0.001 ? goal : v;
      if (now.current[i] !== goal) moving = true;
      const at = target.current;
      // neighbours lean away from the raised card, as fingers spread a hand
      const lean = at === null ? 0 : Math.sign(i - at) * 6 * Math.min(1, Math.abs(i - at)) * (1 - rise(i, at));
      const p0 = tilt.current[i] ?? 0;
      const p = p0 + (lean - p0) * k;
      tilt.current[i] = Math.abs(lean - p) < 0.01 ? lean : p;
      if (tilt.current[i] !== lean) moving = true;
      el.style.transform = transformOf(angleOf(i), now.current[i], tilt.current[i]);
      el.style.zIndex = String(Math.round(10 + i + now.current[i] * 100));
      if (now.current[i] > best) {
        best = now.current[i];
        top = i;
      }
    }
    for (let i = 0; i < n; i++) cards.current[i]?.toggleAttribute('data-up', i === top && best > 0.6);
    if (moving) frame.current = requestAnimationFrame(step);
  }, [n, angleOf]);

  const kick = useCallback(() => {
    if (!frame.current) frame.current = requestAnimationFrame(step);
  }, [step]);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  const aim = useCallback(
    (at: number | null) => {
      target.current = at;
      const nearest = at === null ? null : Math.max(0, Math.min(n - 1, Math.round(at)));
      setLift((l) => (l === nearest ? l : nearest));
      kick();
    },
    [n, kick],
  );

  const page = useCallback(
    (dir: number) => {
      target.current = null;
      now.current = [];
      tilt.current = [];
      setLift(null);
      setStart((s) => Math.max(0, Math.min(Math.max(0, items.length - hand), s + dir * Math.max(1, hand - 2))));
    },
    [items.length, hand],
  );

  // Which card the pointer is over: its angle around the fan's pivot.
  const onMove = (e: React.PointerEvent) => {
    const el = host.current;
    if (!el || n === 0 || e.pointerType === 'touch') return;
    const r = el.getBoundingClientRect();
    const phone = r.width <= 640;
    const pivotY = r.top + r.height + (phone ? 212 : 300);
    const deg = (Math.atan2(e.clientX - (r.left + r.width / 2), pivotY - e.clientY) * 180) / Math.PI;
    const at = n > 1 && spread > 0 ? (deg / spread + 0.5) * (n - 1) : 0;
    aim(Math.max(-0.6, Math.min(n - 0.4, at)));
  };

  // Tilt and sheen of the card under the pointer (CSS variables only).
  const onCardMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const b = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - b.left) / b.width;
    const y = (e.clientY - b.top) / b.height;
    e.currentTarget.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`);
    e.currentTarget.style.setProperty('--my', `${(y * 100).toFixed(1)}%`);
    e.currentTarget.style.setProperty('--ry', `${((x - 0.5) * 14).toFixed(2)}deg`);
    e.currentTarget.style.setProperty('--rx', `${((0.5 - y) * 10).toFixed(2)}deg`);
  };
  const onCardLeave = (e: React.PointerEvent<HTMLButtonElement>) => {
    e.currentTarget.style.setProperty('--ry', '0deg');
    e.currentTarget.style.setProperty('--rx', '0deg');
  };

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let x0 = 0;
    const down = (e: TouchEvent) => {
      x0 = e.touches[0]?.clientX ?? 0;
    };
    const up = (e: TouchEvent) => {
      const dx = (e.changedTouches[0]?.clientX ?? 0) - x0;
      if (Math.abs(dx) > 50) page(dx < 0 ? 1 : -1);
    };
    el.addEventListener('touchstart', down, { passive: true });
    el.addEventListener('touchend', up, { passive: true });
    return () => {
      el.removeEventListener('touchstart', down);
      el.removeEventListener('touchend', up);
    };
  }, [page]);

  // One click handler for the whole fan. The cards move under the pointer, so a
  // press can start on one card and end on another: the click then lands here,
  // on the fan, and opens the card that is lifted (the one the person is on).
  const openFrom = (e: React.MouseEvent) => {
    if (n === 0) return;
    let at: number | null = null;
    if (pointer.current === 'touch' || lift === null) {
      const card = (e.target as HTMLElement).closest?.('[data-i]') as HTMLElement | null;
      if (card) at = Number(card.dataset.i);
    }
    if (at === null) at = lift ?? Math.floor((n - 1) / 2);
    at = Math.max(0, Math.min(n - 1, at));
    onOpen(shown[at], start + at, host.current?.getBoundingClientRect() ?? null);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight') aim(Math.min(n - 1, (lift ?? -1) + 1));
    else if (e.key === 'ArrowLeft') aim(Math.max(0, (lift ?? n) - 1));
    else if (e.key === 'Enter' && e.target === e.currentTarget && lift !== null) onOpen(shown[lift], start + lift, host.current?.getBoundingClientRect() ?? null);
    else if (e.key === 'PageDown') page(1);
    else if (e.key === 'PageUp') page(-1);
  };

  const glow = lift !== null ? shown[lift] : undefined;

  return (
    <div className="fan-wrap">
      <div
        ref={host}
        className="fan"
        role="listbox"
        tabIndex={0}
        aria-label="Su galería"
        onKeyDown={onKey}
        onPointerMove={onMove}
        onPointerDown={(e) => {
          pointer.current = e.pointerType;
        }}
        onPointerLeave={() => aim(null)}
        onClick={openFrom}
      >
        <div
          className="fan-glow"
          aria-hidden="true"
          data-on={glow?.kind === 'imagen' && glow.src ? true : undefined}
          style={glow?.kind === 'imagen' && glow.src ? { backgroundImage: `url("${glow.src}")` } : undefined}
        />
        {shown.map((it, i) => (
          <button
            key={`${start}-${it.key}`}
            ref={(el) => {
              cards.current[i] = el;
            }}
            type="button"
            role="option"
            aria-selected={lift === i}
            className="fan-card"
            style={{
              transform: transformOf(angleOf(i), 0, 0),
              zIndex: 10 + i,
              ['--i' as string]: i,
            }}
            data-i={i}
            onFocus={() => aim(i)}
            onPointerMove={onCardMove}
            onPointerLeave={onCardLeave}
            title={it.title}
          >
            <span className="fan-face">
              {it.kind !== '3d' && it.src && (
                <img
                  src={it.thumb || it.src}
                  alt={it.title}
                  loading="lazy"
                  decoding="async"
                  draggable={false}
                  onError={(e) => {
                    // no thumbnail: the picture itself (a video then shows its title only)
                    const img = e.currentTarget;
                    if (it.kind === 'imagen' && it.src && img.src.indexOf(it.src) === -1) img.src = it.src;
                    else img.style.visibility = 'hidden';
                  }}
                />
              )}
              {it.kind === 'video' && <span className="fan-play" aria-hidden="true" />}
              {it.kind === '3d' && (
                <span className="fan-3d" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <path d="M12 2 3 7v10l9 5 9-5V7z" />
                    <path d="m3 7 9 5 9-5M12 12v10" />
                  </svg>
                </span>
              )}
              <span className="fan-sheen" aria-hidden="true" />
              <span className="fan-label">
                <b>{it.title}</b>
                <small>{it.note || { imagen: 'Imagen', video: 'Video', '3d': 'Modelo 3D' }[it.kind]}</small>
              </span>
            </span>
          </button>
        ))}
      </div>
      <button
        type="button"
        className="fan-open"
        onClick={() => onOpen(shown[Math.floor((n - 1) / 2)] ?? items[0], start + Math.floor((n - 1) / 2), host.current?.getBoundingClientRect() ?? null)}
      >
        Abrir la galería · {items.length}
      </button>
      {items.length > hand && (
        <div className="fan-pager">
          <button type="button" onClick={() => page(-1)} disabled={start === 0} aria-label="Anteriores">
            ‹
          </button>
          <span>
            {start + 1}–{Math.min(items.length, start + hand)} de {items.length}
          </span>
          <button type="button" onClick={() => page(1)} disabled={start + hand >= items.length} aria-label="Siguientes">
            ›
          </button>
        </div>
      )}
    </div>
  );
}

export default FanGallery;
