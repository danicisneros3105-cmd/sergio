// A fan of cards: the pictures, videos and 3D models people made with Sergio
// spread from one pivot like a hand of cards. Hover (or arrow keys) lifts one;
// a click opens it. On a phone the fan is narrower and swipes.
import { useCallback, useEffect, useRef, useState } from 'react';
import './gallery.css';

export interface FanItem {
  key: string;
  kind: 'imagen' | 'video' | '3d';
  title: string;
  src?: string;
  note?: string;
}

interface Props {
  items: FanItem[];
  onOpen: (item: FanItem, index: number) => void;
  /** how many cards are in the hand at once */
  hand?: number;
}

export function FanGallery({ items, onOpen, hand = 9 }: Props) {
  const [start, setStart] = useState(0);
  const [lift, setLift] = useState<number | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const shown = items.slice(start, start + hand);
  const n = shown.length;
  const spread = Math.min(70, 8 * (n - 1));

  const page = useCallback(
    (dir: number) => {
      setLift(null);
      setStart((s) => Math.max(0, Math.min(Math.max(0, items.length - hand), s + dir * Math.max(1, hand - 2))));
    },
    [items.length, hand],
  );

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

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight') setLift((l) => Math.min(n - 1, (l ?? -1) + 1));
    else if (e.key === 'ArrowLeft') setLift((l) => Math.max(0, (l ?? n) - 1));
    else if (e.key === 'Enter' && lift !== null) onOpen(shown[lift], start + lift);
    else if (e.key === 'PageDown') page(1);
    else if (e.key === 'PageUp') page(-1);
  };

  return (
    <div className="fan-wrap">
      <div
        ref={host}
        className="fan"
        role="listbox"
        tabIndex={0}
        aria-label="Su galería"
        onKeyDown={onKey}
        onMouseLeave={() => setLift(null)}
      >
        {shown.map((it, i) => {
          const t = n > 1 ? i / (n - 1) - 0.5 : 0;
          const angle = t * spread;
          const up = lift === i;
          const near = lift !== null && Math.abs(lift - i) === 1;
          return (
            <button
              key={it.key}
              type="button"
              role="option"
              aria-selected={up}
              className="fan-card"
              data-up={up || undefined}
              style={{
                transform: `rotate(${angle + (near ? (lift! < i ? 4 : -4) : 0)}deg) translateY(${up ? -36 : 0}px) scale(${up ? 1.06 : 1})`,
                zIndex: up ? 100 : 10 + i,
              }}
              onMouseEnter={() => setLift(i)}
              onFocus={() => setLift(i)}
              onClick={() => onOpen(it, start + i)}
              title={it.title}
            >
              {it.kind === 'imagen' && it.src && <img src={it.src} alt={it.title} loading="lazy" draggable={false} />}
              {it.kind === 'video' && it.src && <video src={`${it.src}#t=0.5`} muted playsInline preload="metadata" />}
              {it.kind === '3d' && (
                <span className="fan-3d" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <path d="M12 2 3 7v10l9 5 9-5V7z" />
                    <path d="m3 7 9 5 9-5M12 12v10" />
                  </svg>
                </span>
              )}
              <span className="fan-label">
                <b>{it.title}</b>
                <small>{it.note || { imagen: 'Imagen', video: 'Video', '3d': 'Modelo 3D' }[it.kind]}</small>
              </span>
            </button>
          );
        })}
      </div>
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
