import { useEffect, useMemo, useState } from 'react';
import { groupByDay, nodesApi, type ActivityItem, type SergioNode } from '../../lib/nodes';

const ACTIVITY_ICON: Record<string, string> = {
  started: '▸',
  tool: '·',
  result: '↳',
  done: '✓',
  approval: '?',
  approved: '✓',
  denied: '×',
  needs_you: '!',
  memory: '◦',
  failed: '×',
  stopped: '■',
  resumed: '▸',
  routine: '↻',
  created: '●',
  handed_back: '▸',
  blocked: '×',
  discarded: '×',
  watch: '◌',
  trigger: '↯',
  verify: '!',
  swarm: '*',
  connection: '⌁',
};

export function ActivityTab({ node }: { node: SergioNode }) {
  const [items, setItems] = useState<ActivityItem[]>([]);
  useEffect(() => {
    let alive = true;
    const load = () =>
      nodesApi
        .activity(node.id)
        .then((r) => alive && setItems(r.activity))
        .catch(() => {});
    load();
    const t = window.setInterval(load, 2000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [node.id]);
  const days = useMemo(() => groupByDay(items), [items]);
  if (!items.length) return <p className="node-empty">Aquí verá todo lo que hace, en vivo.</p>;
  return (
    <div className="node-activity">
      {days.map((d) => (
        <section key={d.day}>
          <h3 className="paper-label">{d.day}</h3>
          <ol>
            {d.items.map((a) => (
              <li key={a.id} data-kind={a.kind}>
                <span className="node-act-icon" aria-hidden="true">
                  {ACTIVITY_ICON[a.kind] || '·'}
                </span>
                <span className="node-act-text">{a.text}</span>
                <time>{new Date(a.at * 1000).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })}</time>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
