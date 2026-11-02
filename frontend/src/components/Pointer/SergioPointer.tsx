// Sergio's showcase pointer: a cursor with his name that glides to what he is
// showing, with a short line beside it, then leaves. One for the whole app.
import { useEffect, useRef, useState } from 'react';
import { findTarget, POINT_EVENT, type PointRequest } from '../../lib/pointer';
import './pointer.css';

interface Spot {
  x: number;
  y: number;
  text?: string;
  ring?: { x: number; y: number; w: number; h: number };
}

const reduced = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export function SergioPointer() {
  const [spot, setSpot] = useState<Spot | null>(null);
  const [shown, setShown] = useState(false);
  const last = useRef<{ x: number; y: number }>({ x: window.innerWidth - 80, y: window.innerHeight - 80 });
  const hide = useRef<number | undefined>(undefined);
  const queue = useRef<PointRequest[]>([]);
  const busy = useRef(false);

  useEffect(() => {
    const next = () => {
      const req = queue.current.shift();
      if (!req) {
        busy.current = false;
        return;
      }
      busy.current = true;
      let x = req.x ?? last.current.x;
      let y = req.y ?? last.current.y;
      let ring: Spot['ring'];
      if (req.target) {
        const el = findTarget(req.target);
        if (!el) {
          next();
          return;
        }
        el.scrollIntoView?.({ block: 'center', inline: 'nearest', behavior: 'instant' as ScrollBehavior });
        const r = el.getBoundingClientRect();
        x = r.left + Math.min(r.width * 0.5, 40);
        y = r.top + r.height * 0.6;
        ring = { x: r.left - 4, y: r.top - 4, w: r.width + 8, h: r.height + 8 };
        if (req.click) window.setTimeout(() => el.click(), reduced() ? 50 : 750);
      }
      last.current = { x, y };
      setShown(true);
      setSpot({ x, y, text: req.text, ring });
      const stay = req.ms ?? Math.min(7000, 1800 + (req.text?.length ?? 0) * 45);
      window.clearTimeout(hide.current);
      hide.current = window.setTimeout(() => {
        if (queue.current.length) next();
        else {
          setShown(false);
          busy.current = false;
        }
      }, stay);
    };
    const on = (e: Event) => {
      const req = (e as CustomEvent<PointRequest>).detail;
      if (!req) return;
      queue.current.push(req);
      if (!busy.current) next();
    };
    window.addEventListener(POINT_EVENT, on);
    return () => {
      window.removeEventListener(POINT_EVENT, on);
      window.clearTimeout(hide.current);
    };
  }, []);

  if (!spot) return null;
  const flip = spot.x > window.innerWidth - 260;
  return (
    <div className="sp-layer" aria-live="polite" data-shown={shown || undefined}>
      {spot.ring && shown && (
        <span className="sp-ring" style={{ left: spot.ring.x, top: spot.ring.y, width: spot.ring.w, height: spot.ring.h }} />
      )}
      <div className="sp-cursor" style={{ transform: `translate(${spot.x}px, ${spot.y}px)` }}>
        <svg width="22" height="26" viewBox="0 0 22 26" aria-hidden="true">
          <path d="M2 2 L2 21 L7.5 16.2 L11 24 L14.6 22.4 L11.2 14.8 L19 14.8 Z" />
        </svg>
        <span className="sp-tag" data-flip={flip || undefined}>
          <b>Sergio</b>
          {spot.text && <span>{spot.text}</span>}
        </span>
      </div>
    </div>
  );
}

export default SergioPointer;
