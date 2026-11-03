// The whole gallery, opened from the fan like Apple's Photos: the fan is only
// the preview; a click grows it into a full grid grouped by day (the clip-path
// opens from the fan's own rectangle), and a tile grows into the viewer (a
// shared-element zoom from the tile to the middle). Videos ask the server
// whether the browser can play them (a 10-bit HEVC master cannot): if not, a
// copy it can play is made, and a video that still fails says so with a way out.
import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { WebVideo } from './WebVideo';
import './gallery-stage.css';

const PartsViewer = lazy(() => import('../Chat/PartsViewer'));

export interface GalleryRow {
  url: string;
  mini?: string;
  tipo: 'imagen' | 'video' | '3d';
  nombre: string;
  fecha: number;
  modelo?: string;
  piezas?: number;
}

type Filter = 'todo' | GalleryRow['tipo'];

const FILTERS: Array<{ key: Filter; label: string }> = [
  { key: 'todo', label: 'Todo' },
  { key: 'imagen', label: 'Imágenes' },
  { key: 'video', label: 'Videos' },
  { key: '3d', label: '3D' },
];

const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';

const NICE: Record<string, string> = { portada: 'Portada', video: 'Video', imagen: 'Imagen', foto: 'Foto' };
export const rowTitle = (r: GalleryRow) => NICE[r.nombre] ?? r.nombre;
export const rowKey = (r: GalleryRow, i = 0) => r.url || r.modelo || `row-${i}`;

// No animation when asked not to, or where the browser cannot (old webviews, tests).
function reducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof Element === 'undefined' || typeof Element.prototype.animate !== 'function') return true;
  if (document.documentElement.dataset.ligero) return true; // a slow device: no long animations
  return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/** «Hoy», «Ayer», «3 de noviembre» (con el año si no es el actual). */
export function dayLabel(seconds: number, now: Date = new Date()): string {
  if (!seconds) return 'Sin fecha';
  const d = new Date(seconds * 1000);
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86_400_000);
  if (diff === 0) return 'Hoy';
  if (diff === 1) return 'Ayer';
  return d.toLocaleDateString('es', {
    day: 'numeric',
    month: 'long',
    ...(d.getFullYear() === now.getFullYear() ? {} : { year: 'numeric' }),
  });
}

export function groupByDay(rows: GalleryRow[], now: Date = new Date()): Array<{ label: string; rows: GalleryRow[] }> {
  const sorted = [...rows].sort((a, b) => b.fecha - a.fecha);
  const out: Array<{ label: string; rows: GalleryRow[] }> = [];
  for (const r of sorted) {
    const label = dayLabel(r.fecha, now);
    const last = out[out.length - 1];
    if (last && last.label === label) last.rows.push(r);
    else out.push({ label, rows: [r] });
  }
  return out;
}

const CubeIcon = () => (
  <svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
    <path d="M12 2 3 7v10l9 5 9-5V7z" />
    <path d="m3 7 9 5 9-5M12 12v10" />
  </svg>
);

/* ---------------------------------------------------------------- viewer */

function Viewer({
  rows,
  index,
  onIndex,
  onClose,
}: {
  rows: GalleryRow[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const row = rows[index];
  const box = useRef<HTMLDivElement>(null);
  const back = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  const touch = useRef(0);
  const dir = useRef(0);
  const closing = useRef(false);

  const tileOf = (r: GalleryRow) => document.querySelector<HTMLElement>(`[data-gkey="${CSS.escape(rowKey(r))}"]`);

  // The tile grows into the viewer: same centre, same size, then it opens out.
  useLayoutEffect(() => {
    if (!first.current) return;
    first.current = false;
    const el = box.current;
    const tile = tileOf(row);
    if (!el || reducedMotion()) return;
    back.current?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 320, easing: 'ease-out' });
    if (!tile) {
      el.animate([{ opacity: 0, transform: 'scale(0.94)' }, { opacity: 1, transform: 'none' }], { duration: 360, easing: EASE });
      return;
    }
    const a = tile.getBoundingClientRect();
    const b = el.getBoundingClientRect();
    if (!b.width || !b.height) return;
    const s = Math.max(a.width / b.width, a.height / b.height);
    const dx = a.left + a.width / 2 - (b.left + b.width / 2);
    const dy = a.top + a.height / 2 - (b.top + b.height / 2);
    const vx = Math.max(0, (b.width - a.width / s) / 2);
    const vy = Math.max(0, (b.height - a.height / s) / 2);
    el.animate(
      [
        { transform: `translate(${dx}px, ${dy}px) scale(${s})`, clipPath: `inset(${vy}px ${vx}px round ${4 / s}px)` },
        { transform: 'none', clipPath: 'inset(0px 0px 0px 0px round 16px)' },
      ],
      { duration: 520, easing: EASE },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const close = useCallback(() => {
    if (closing.current) return;
    closing.current = true;
    const el = box.current;
    const tile = tileOf(row);
    if (!el || reducedMotion()) return onClose();
    back.current?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, fill: 'forwards' });
    let anim: Animation;
    if (tile) {
      const a = tile.getBoundingClientRect();
      const b = el.getBoundingClientRect();
      const s = Math.max(a.width / b.width, a.height / b.height);
      const dx = a.left + a.width / 2 - (b.left + b.width / 2);
      const dy = a.top + a.height / 2 - (b.top + b.height / 2);
      const vx = Math.max(0, (b.width - a.width / s) / 2);
      const vy = Math.max(0, (b.height - a.height / s) / 2);
      anim = el.animate(
        [
          { transform: 'none', clipPath: 'inset(0px 0px 0px 0px round 16px)' },
          { transform: `translate(${dx}px, ${dy}px) scale(${s})`, clipPath: `inset(${vy}px ${vx}px round ${4 / s}px)` },
        ],
        { duration: 380, easing: EASE, fill: 'forwards' },
      );
    } else {
      anim = el.animate([{ opacity: 1 }, { opacity: 0, transform: 'scale(0.96)' }], { duration: 260, fill: 'forwards' });
    }
    anim.onfinish = onClose;
    window.setTimeout(onClose, 600); // never stuck if the animation is cut
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose, row]);

  const go = useCallback(
    (d: number) => {
      const next = index + d;
      if (next < 0 || next >= rows.length) return;
      dir.current = d;
      onIndex(next);
    },
    [index, rows.length, onIndex],
  );

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close();
      } else if (e.key === 'ArrowRight') go(1);
      else if (e.key === 'ArrowLeft') go(-1);
    };
    window.addEventListener('keydown', key, true);
    return () => window.removeEventListener('keydown', key, true);
  }, [close, go]);

  if (!row) return null;
  return (
    <div
      className="gv-viewer"
      role="dialog"
      aria-modal="true"
      aria-label={rowTitle(row)}
      onClick={close}
      onTouchStart={(e) => {
        touch.current = e.touches[0]?.clientX ?? 0;
      }}
      onTouchEnd={(e) => {
        const dx = (e.changedTouches[0]?.clientX ?? 0) - touch.current;
        if (Math.abs(dx) > 60) go(dx < 0 ? 1 : -1);
      }}
    >
      <div className="gv-back" ref={back} />
      <button type="button" className="gv-round gv-x" aria-label="Cerrar" onClick={close}>
        ×
      </button>
      {index > 0 && (
        <button
          type="button"
          className="gv-round gv-prev"
          aria-label="Anterior"
          onClick={(e) => {
            e.stopPropagation();
            go(-1);
          }}
        >
          ‹
        </button>
      )}
      {index < rows.length - 1 && (
        <button
          type="button"
          className="gv-round gv-next"
          aria-label="Siguiente"
          onClick={(e) => {
            e.stopPropagation();
            go(1);
          }}
        >
          ›
        </button>
      )}
      <div className="gv-box" ref={box} onClick={(e) => e.stopPropagation()}>
        <div className="gv-slide" key={rowKey(row)} data-dir={dir.current || undefined}>
          {row.tipo === 'imagen' && <img src={row.url} alt={rowTitle(row)} draggable={false} />}
          {row.tipo === 'video' && <WebVideo key={row.url} src={row.url} poster={row.mini} autoPlay />}
          {row.tipo === '3d' && row.modelo && (
            <div className="gv-3d">
              <Suspense fallback={null}>
                <PartsViewer name={row.modelo} />
              </Suspense>
            </div>
          )}
        </div>
      </div>
      <div className="gv-info" onClick={(e) => e.stopPropagation()}>
        <b>{rowTitle(row)}</b>
        <span>
          {dayLabel(row.fecha)} · {index + 1} de {rows.length}
        </span>
        {row.tipo !== '3d' && (
          <a href={row.url} download aria-label="Descargar">
            Descargar
          </a>
        )}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- stage */

export function GalleryStage({
  rows,
  from,
  focus,
  filter: startFilter = 'todo',
  onClose,
}: {
  rows: GalleryRow[];
  /** the fan's rectangle: the grid opens out of it and closes back into it */
  from: DOMRect | null;
  /** the picture to open on (its tile is brought into view) */
  focus?: string;
  filter?: Filter;
  onClose: () => void;
}) {
  const [filter, setFilter] = useState<Filter>(startFilter);
  const [view, setView] = useState<number | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const closing = useRef(false);
  const viewing = view !== null;

  const shown = useMemo(
    () => [...rows].sort((a, b) => b.fecha - a.fecha).filter((r) => filter === 'todo' || r.tipo === filter),
    [rows, filter],
  );
  const groups = useMemo(() => groupByDay(shown), [shown]);
  const order = useMemo(() => groups.flatMap((g) => g.rows), [groups]);
  const focusAt = Math.max(0, order.findIndex((r) => rowKey(r) === focus));

  const shape = useCallback(() => {
    const W = window.innerWidth;
    const H = window.innerHeight;
    const r = from;
    return r
      ? `inset(${Math.max(0, r.top)}px ${Math.max(0, W - r.right)}px ${Math.max(0, H - r.bottom)}px ${Math.max(0, r.left)}px round 28px)`
      : 'inset(50% 50% 50% 50% round 28px)';
  }, [from]);

  // Opens out of the fan.
  useLayoutEffect(() => {
    const el = root.current;
    if (!el || reducedMotion()) return;
    el.animate(
      [
        { clipPath: shape(), opacity: 0.2 },
        { clipPath: 'inset(0px 0px 0px 0px round 0px)', opacity: 1 },
      ],
      { duration: 600, easing: EASE },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The chosen picture is in view when it opens.
  useEffect(() => {
    if (!focus) return;
    document.querySelector<HTMLElement>(`[data-gkey="${CSS.escape(focus)}"]`)?.scrollIntoView({ block: 'center' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  const close = useCallback(() => {
    if (closing.current) return;
    closing.current = true;
    const el = root.current;
    if (!el || reducedMotion()) return onClose();
    const a = el.animate(
      [
        { clipPath: 'inset(0px 0px 0px 0px round 0px)', opacity: 1 },
        { clipPath: shape(), opacity: 0 },
      ],
      { duration: 460, easing: EASE, fill: 'forwards' },
    );
    a.onfinish = onClose;
    window.setTimeout(onClose, 700);
  }, [onClose, shape]);

  useEffect(() => {
    if (viewing) return;
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && close();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [viewing, close]);

  let n = 0;
  // On the page itself, not inside the app's frame: the gallery covers the whole window.
  return createPortal(
    <div ref={root} className="gs" role="dialog" aria-modal="true" aria-label="Galería">
      <header className="gs-bar">
        <div>
          <h2>Galería</h2>
          <span>
            {shown.length} {shown.length === 1 ? 'elemento' : 'elementos'}
          </span>
        </div>
        <div className="gs-seg" role="group" aria-label="Qué mostrar">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
              {f.label}
            </button>
          ))}
        </div>
        <button type="button" className="gs-close" onClick={close} aria-label="Cerrar la galería">
          Listo
        </button>
      </header>
      <div className="gs-scroll">
        {order.length === 0 && <p className="gs-empty">No hay nada de este tipo todavía.</p>}
        {groups.map((g) => (
          <section key={g.label} className="gs-day">
            <h3>{g.label}</h3>
            <div className="gs-grid">
              {g.rows.map((r) => {
                const i = n++;
                const wait = Math.min(Math.abs(i - focusAt) * 22, 420);
                return (
                  <button
                    key={rowKey(r, i)}
                    type="button"
                    className="gs-tile"
                    data-gkey={rowKey(r)}
                    data-kind={r.tipo}
                    style={{ ['--wait' as string]: `${wait}ms` }}
                    onClick={() => setView(i)}
                    aria-label={`${rowTitle(r)}, ${r.tipo === '3d' ? 'modelo 3D' : r.tipo}`}
                  >
                    {r.tipo !== '3d' && (r.mini || r.url) && (
                      <img
                        src={r.mini || r.url}
                        alt=""
                        loading="lazy"
                        decoding="async"
                        draggable={false}
                        onError={(e) => {
                          const img = e.currentTarget;
                          if (r.tipo === 'imagen' && img.src.indexOf(r.url) === -1) img.src = r.url;
                          else img.style.visibility = 'hidden';
                        }}
                      />
                    )}
                    {r.tipo === '3d' && (
                      <span className="gs-cube">
                        <CubeIcon />
                        <small>{r.piezas ? `${r.piezas} piezas` : 'Modelo 3D'}</small>
                      </span>
                    )}
                    {r.tipo === 'video' && <span className="gs-play" aria-hidden="true" />}
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </div>
      {view !== null && order[view] && (
        <Viewer rows={order} index={view} onIndex={setView} onClose={() => setView(null)} />
      )}
    </div>,
    document.body,
  );
}

export default GalleryStage;
