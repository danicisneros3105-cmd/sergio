// What a Node has waiting (owner, 3 Nov 2026: «nodes con más control»): the
// queue in order, with «Primero» and «Quitar». Shown only when it has any.
import { useCallback, useEffect, useState } from 'react';
import { ArrowUp, X } from 'lucide-react';
import { nodesApi, type QueuedTask } from '../../lib/nodes';

export function QueueStrip({ nodeId }: { nodeId: string }) {
  const [queue, setQueue] = useState<QueuedTask[]>([]);
  const load = useCallback(() => {
    nodesApi.queue(nodeId).then((d) => setQueue(d.queue), () => setQueue([]));
  }, [nodeId]);
  useEffect(() => {
    load();
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, [load]);
  if (!queue.length) return null;
  return (
    <section className="node-queue" aria-label="En cola">
      <h3>En cola · {queue.length}</h3>
      <ol>
        {queue.map((q) => (
          <li key={`${q.i}-${q.request.slice(0, 20)}`}>
            <span>{q.request}</span>
            <small>{q.source}</small>
            {q.i > 0 && (
              <button type="button" aria-label="Hacer esto primero" title="Primero" onClick={() => void nodesApi.firstQueued(nodeId, q.i).then((d) => setQueue(d.queue))}>
                <ArrowUp size={14} />
              </button>
            )}
            <button type="button" aria-label="Quitar de la cola" title="Quitar" onClick={() => void nodesApi.dropQueued(nodeId, q.i).then((d) => setQueue(d.queue))}>
              <X size={14} />
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default QueueStrip;
