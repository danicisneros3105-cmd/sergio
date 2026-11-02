// Every automation in one list, whichever Node runs it: what, when, who, the
// last time it ran, and pause or remove in one tap.
import { Pause, Play, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { describeRoutine, nodesApi, relative, type Routine, type SergioNode } from '../../lib/nodes';

export function MyAutomations({ nodes, onChanged }: { nodes: SergioNode[]; onChanged: () => void }) {
  const rows: Array<{ node: SergioNode; r: Routine }> = nodes.flatMap((node) => node.routines.map((r) => ({ node, r })));
  if (rows.length === 0) {
    return <p className="am-empty">Aún no hay automatizaciones. Elija una plantilla o cree la suya arriba.</p>;
  }
  const run = (p: Promise<unknown>, ok: string) =>
    p.then(() => (toast.success(ok), onChanged())).catch((e: Error) => toast.error(e.message || 'No pude.'));
  return (
    <ul className="am">
      {rows.map(({ node, r }) => (
        <li key={`${node.id}-${r.id}`} data-off={!r.enabled || undefined}>
          <div className="am-text">
            <b>{r.task.replace(/^Hazlo en este orden y avísame al terminar:\s*/, '').split('\n').join(' · ')}</b>
            <small>
              {describeRoutine(r)} · {node.name}
              {(r.last_check || r.last_run) > 0 && ` · ${relative(r.last_check || r.last_run)}`}
              {!!r.failures && ` · ${r.failures} fallos`}
            </small>
          </div>
          <button
            type="button"
            className="ab-icon"
            aria-label={r.enabled ? 'Pausar' : 'Reanudar'}
            title={r.enabled ? 'Pausar' : 'Reanudar'}
            onClick={() => void run(nodesApi.setRoutineEnabled(node.id, r.id, !r.enabled), r.enabled ? 'En pausa.' : 'Reanudada.')}
          >
            {r.enabled ? <Pause size={14} /> : <Play size={14} />}
          </button>
          <button
            type="button"
            className="ab-icon"
            aria-label="Quitar"
            title="Quitar"
            onClick={() => {
              if (window.confirm('¿Quitar esta automatización?')) void run(nodesApi.removeRoutine(node.id, r.id), 'Quitada.');
            }}
          >
            <Trash2 size={14} />
          </button>
        </li>
      ))}
    </ul>
  );
}

export default MyAutomations;
