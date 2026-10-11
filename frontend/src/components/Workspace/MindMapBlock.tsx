import { useMemo, useState } from 'react';
import { newId, type MindNode } from '../../lib/workspace/model';

// A concept map: a central idea, branches around it, leaves around those.
// Drawn as a radial tree (hairlines, ink dots); edited as an outline where
// Enter adds a sibling and Tab makes a child.
export function radialLayout(nodes: MindNode[], width: number, height: number) {
  const pos = new Map<string, { x: number; y: number; depth: number }>();
  const root = nodes.find((n) => n.parent === null);
  if (!root) return pos;
  const cx = width / 2;
  const cy = height / 2;
  pos.set(root.id, { x: cx, y: cy, depth: 0 });
  const leaves = (id: string): number => {
    const kids = nodes.filter((n) => n.parent === id);
    return kids.length ? kids.reduce((s, k) => s + leaves(k.id), 0) : 1;
  };
  const place = (id: string, from: number, to: number, depth: number) => {
    const kids = nodes.filter((n) => n.parent === id);
    const total = kids.reduce((s, k) => s + leaves(k.id), 0) || 1;
    let at = from;
    for (const k of kids) {
      const span = ((to - from) * leaves(k.id)) / total;
      const angle = at + span / 2;
      const radius = Math.min(width, height) * (0.24 + 0.17 * (depth - 1));
      pos.set(k.id, { x: cx + Math.cos(angle) * radius * 1.35, y: cy + Math.sin(angle) * radius, depth });
      place(k.id, at, at + span, depth + 1);
      at += span;
    }
  };
  place(root.id, -Math.PI / 2, (Math.PI * 3) / 2, 1);
  return pos;
}

export function MindMapBlock({ nodes, onChange }: { nodes: MindNode[]; onChange: (nodes: MindNode[]) => void }) {
  const [editing, setEditing] = useState(false);
  const W = 640;
  const H = 300;
  const pos = useMemo(() => radialLayout(nodes, W, H), [nodes]);
  const depthOf = (n: MindNode): number => (n.parent ? 1 + depthOf(nodes.find((x) => x.id === n.parent)!) : 0);
  const ordered: MindNode[] = [];
  const walk = (parent: string | null) => {
    for (const n of nodes.filter((x) => x.parent === parent)) {
      ordered.push(n);
      walk(n.id);
    }
  };
  walk(null);

  return (
    <div className="ws-card">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Mapa conceptual">
        {nodes.map((n) => {
          const a = pos.get(n.id);
          const b = n.parent ? pos.get(n.parent) : null;
          return a && b ? <line key={`l${n.id}`} x1={b.x} y1={b.y} x2={a.x} y2={a.y} stroke="var(--color-border)" /> : null;
        })}
        {nodes.map((n) => {
          const a = pos.get(n.id);
          if (!a) return null;
          return (
            <g key={n.id}>
              <circle cx={a.x} cy={a.y} r={a.depth === 0 ? 5 : 3} fill="var(--color-ink)" />
              <text
                x={a.x}
                y={a.y - 9}
                textAnchor="middle"
                fontSize={a.depth === 0 ? 15 : 12}
                fontWeight={a.depth === 0 ? 600 : 400}
                fill="var(--color-text)"
              >
                {n.text || '…'}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="flex justify-end">
        <button type="button" className="paper-button" data-variant="quiet" onClick={() => setEditing(!editing)}>
          {editing ? 'Listo' : 'Editar ideas'}
        </button>
      </div>
      {editing && (
        <div className="mt-2 flex flex-col gap-1">
          {ordered.map((n) => (
            <input
              key={n.id}
              value={n.text}
              className="ws-outline"
              style={{ marginLeft: depthOf(n) * 20 }}
              aria-label="Idea"
              onChange={(e) => onChange(nodes.map((x) => (x.id === n.id ? { ...x, text: e.target.value } : x)))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  onChange([...nodes, { id: newId('n'), text: '', parent: n.parent ?? n.id }]);
                } else if (e.key === 'Tab' && !e.shiftKey) {
                  e.preventDefault();
                  onChange([...nodes, { id: newId('n'), text: '', parent: n.id }]);
                } else if (e.key === 'Backspace' && !n.text && n.parent) {
                  e.preventDefault();
                  const drop = new Set([n.id]);
                  let grew = true;
                  while (grew) {
                    grew = false;
                    for (const x of nodes) if (x.parent && drop.has(x.parent) && !drop.has(x.id)) (drop.add(x.id), (grew = true));
                  }
                  onChange(nodes.filter((x) => !drop.has(x.id)));
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
