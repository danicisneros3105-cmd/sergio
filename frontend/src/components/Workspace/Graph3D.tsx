import { useEffect, useMemo, useRef, useState } from 'react';
import { buildGraph, layout3d, project, type GraphNode } from '../../lib/workspace/graph';
import type { Page } from '../../lib/workspace/model';

// The knowledge graph in 3D on a plain canvas: drag to turn it, wheel or
// pinch to zoom, click a page to open it. It turns slowly on its own and
// stops drawing when nothing moves (no idle CPU).
export function Graph3D({ pages, onOpen }: { pages: Page[]; onOpen: (id: string) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<GraphNode | null>(null);
  const view = useRef({ yaw: 0.6, pitch: -0.35, zoom: 1, spin: true, drag: null as null | { x: number; y: number; moved: boolean } });
  const graph = useMemo(() => {
    const g = buildGraph(pages);
    return { nodes: layout3d(g.nodes, g.links), links: g.links };
  }, [pages]);
  const screen = useRef<Array<{ n: GraphNode; sx: number; sy: number; r: number }>>([]);
  const hoverRef = useRef<string | null>(null);
  const kickRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const ctx = el.getContext('2d');
    if (!ctx) return;
    let raf = 0;
    let last = performance.now();
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const styles = getComputedStyle(document.documentElement);
    const ink = styles.getPropertyValue('--color-ink').trim() || '#1d1d1c';
    const faint = styles.getPropertyValue('--color-text-tertiary').trim() || '#858683';
    const draw = (t: number) => {
      const dt = Math.min(0.05, (t - last) / 1000);
      last = t;
      const v = view.current;
      if (v.spin && !v.drag && !reduce) v.yaw += dt * 0.12;
      const dpr = window.devicePixelRatio || 1;
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (el.width !== Math.round(w * dpr)) {
        el.width = Math.round(w * dpr);
        el.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const pos = new Map(graph.nodes.map((n) => [n.id, { n, ...project(n, v.yaw, v.pitch, v.zoom, w, h) }]));
      ctx.lineWidth = 1;
      for (const l of graph.links) {
        const a = pos.get(l.a);
        const b = pos.get(l.b);
        if (!a || !b) continue;
        const depth = (a.depth + b.depth) / 2;
        ctx.globalAlpha = 0.12 + 0.2 * ((depth + 1) / 2);
        ctx.strokeStyle = l.kind === 'concept' ? faint : ink;
        ctx.setLineDash(l.kind === 'concept' ? [2, 3] : []);
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(b.sx, b.sy);
        ctx.stroke();
      }
      ctx.setLineDash([]);
      const sorted = [...pos.values()].sort((a, b) => a.depth - b.depth);
      screen.current = [];
      ctx.font = '12px "Source Sans 3 Variable", "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      for (const p of sorted) {
        const r = (p.n.kind === 'page' ? 3 + Math.min(6, p.n.weight * 0.6) : 2.2) * p.scale;
        ctx.globalAlpha = 0.35 + 0.65 * ((p.depth + 1) / 2);
        ctx.fillStyle = p.n.kind === 'page' ? ink : faint;
        ctx.beginPath();
        if (p.n.kind === 'page') ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
        else ctx.rect(p.sx - r, p.sy - r, r * 2, r * 2);
        ctx.fill();
        if (p.n.kind === 'page' || p.n.weight > 3 || hoverRef.current === p.n.id) {
          ctx.fillStyle = p.n.kind === 'page' ? ink : faint;
          ctx.fillText(p.n.label.slice(0, 32), p.sx, p.sy - r - 5);
        }
        screen.current.push({ n: p.n, sx: p.sx, sy: p.sy, r: Math.max(6, r + 3) });
      }
      ctx.globalAlpha = 1;
      if ((v.spin && !reduce) || v.drag) raf = requestAnimationFrame(draw);
      else raf = 0;
    };
    const kick = () => {
      if (!raf) raf = requestAnimationFrame(draw);
    };
    kickRef.current = kick;
    kick();
    const hit = (x: number, y: number) => {
      let best: GraphNode | null = null;
      let bestD = Infinity;
      for (const s of screen.current) {
        const d = Math.hypot(s.sx - x, s.sy - y);
        if (d < s.r && d < bestD) {
          best = s.n;
          bestD = d;
        }
      }
      return best;
    };
    const down = (e: PointerEvent) => {
      view.current.drag = { x: e.clientX, y: e.clientY, moved: false };
      view.current.spin = false;
      el.setPointerCapture(e.pointerId);
      kick();
    };
    const moveH = (e: PointerEvent) => {
      const v = view.current;
      const rect = el.getBoundingClientRect();
      if (v.drag) {
        const dx = e.clientX - v.drag.x;
        const dy = e.clientY - v.drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 2) v.drag.moved = true;
        v.yaw += dx * 0.008;
        v.pitch = Math.max(-1.4, Math.min(1.4, v.pitch + dy * 0.008));
        v.drag = { x: e.clientX, y: e.clientY, moved: v.drag.moved };
        kick();
      } else {
        const found = hit(e.clientX - rect.left, e.clientY - rect.top);
        el.style.cursor = found && found.kind === 'page' ? 'pointer' : 'grab';
        if ((found?.id || null) !== hoverRef.current) {
          hoverRef.current = found?.id || null;
          setHover(found);
          kick();
        }
      }
    };
    const up = (e: PointerEvent) => {
      const v = view.current;
      const rect = el.getBoundingClientRect();
      if (v.drag && !v.drag.moved) {
        const found = hit(e.clientX - rect.left, e.clientY - rect.top);
        if (found && found.kind === 'page') onOpen(found.id);
      }
      v.drag = null;
    };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      view.current.zoom = Math.max(0.4, Math.min(3, view.current.zoom * (e.deltaY > 0 ? 0.92 : 1.08)));
      kick();
    };
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', moveH);
    el.addEventListener('pointerup', up);
    el.addEventListener('wheel', wheel, { passive: false });
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', moveH);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('wheel', wheel);
    };
  }, [graph, onOpen]);

  const pagesCount = graph.nodes.filter((n) => n.kind === 'page').length;
  const concepts = graph.nodes.filter((n) => n.kind === 'concept').length;
  return (
    <div className="ws-graph">
      <canvas ref={canvas} className="w-full h-full touch-none" aria-label="Grafo de conocimiento" role="img" />
      <div className="ws-graph-legend">
        ● {pagesCount} páginas · ▪ {concepts} conceptos en común · arrastre para girar, rueda para acercar
        {hover && <strong> · {hover.label}</strong>}
      </div>
      <button
        type="button"
        className="paper-tab ws-graph-spin"
        onClick={() => {
          view.current.spin = !view.current.spin;
          kickRef.current();
        }}
      >
        Girar
      </button>
    </div>
  );
}
