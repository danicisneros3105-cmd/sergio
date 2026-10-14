// A page's history, like Notion's: the versions the server kept (at most one
// every 10 minutes, the last 50), each with a preview; restoring one makes
// it the current version (the replaced one is kept in history too).

import { useEffect, useState } from 'react';
import { GitCompare, History, RotateCcw, Undo2, X } from 'lucide-react';
import { blockDiff, type DiffOp } from '../../lib/workspace/brain';
import type { Block } from '../../lib/workspace/model';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import type { Page } from '../../lib/workspace/model';

interface Version {
  rev: number;
  savedAt: number;
  title: string;
  blocks: number;
  preview: string;
  sealed: boolean;
}

/** Visual Git for a document: what changed since a version, block by block
 * and word by word; any single block can be brought back. */
function DiffView({ ops, onBlock }: { ops: DiffOp[]; onBlock: (op: DiffOp) => void }) {
  const changed = ops.filter((o) => o.kind !== 'same');
  if (!changed.length) return <p className="ws-empty">Sin cambios.</p>;
  return (
    <div className="ws-diff">
      {ops.map((o, i) =>
        o.kind === 'same' ? null : (
          <div key={i} className="ws-diff-row" data-kind={o.kind}>
            <span className="ws-diff-mark">{o.kind === 'added' ? '+' : o.kind === 'removed' ? '−' : '~'}</span>
            <span className="ws-diff-text">
              {o.kind === 'changed'
                ? o.words.map((w, k) => (
                    <span key={k} data-w={w.kind}>
                      {w.text}
                    </span>
                  ))
                : o.block.text || `(${o.block.type})`}
            </span>
            {o.kind !== 'added' && (
              <button type="button" className="mac-icon-btn" title="Devolver este bloque" aria-label="Devolver este bloque" onClick={() => onBlock(o)}>
                <Undo2 size={13} />
              </button>
            )}
          </div>
        ),
      )}
    </div>
  );
}

export function HistoryDialog({
  page,
  onRestore,
  onClose,
  onBlocks,
}: {
  page: Page;
  onRestore: (old: Page) => void;
  onClose: () => void;
  onBlocks?: (blocks: Block[]) => void;
}) {
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [diff, setDiff] = useState<{ rev: number; ops: DiffOp[] } | null>(null);
  const compare = async (v: Version) => {
    try {
      const r = await apiFetch(`/v1/workspace/pages/${page.id}/history/${v.rev}`);
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || 'No pude abrir esa versión.');
      setDiff({ rev: v.rev, ops: blockDiff((body.page as Page).blocks, page.blocks) });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  };
  const bringBack = (op: DiffOp) => {
    if (!onBlocks) return;
    const old = op.kind === 'changed' ? op.before : op.block;
    const next = op.kind === 'changed' ? page.blocks.map((b) => (b.id === old.id ? old : b)) : [...page.blocks, old];
    onBlocks(next);
    setDiff((d) => (d ? { ...d, ops: d.ops.filter((x) => x !== op) } : d));
    toast.success('Bloque devuelto.');
  };
  const [error, setError] = useState('');
  useEffect(() => {
    apiFetch(`/v1/workspace/pages/${page.id}/history`)
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.detail || 'No pude leer el historial.');
        setVersions(body.versions as Version[]);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [page.id]);

  const restore = async (v: Version) => {
    try {
      const r = await apiFetch(`/v1/workspace/pages/${page.id}/history/${v.rev}`);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || 'No pude abrir esa versión.');
      onRestore(body.page as Page);
      toast.success('Versión restaurada. La de antes queda en el historial.');
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude restaurarla.');
    }
  };

  return (
    <div className="ws-modal" role="dialog" aria-modal="true" aria-label="Historial de la página" onClick={onClose}>
      <div className="ws-history" onClick={(e) => e.stopPropagation()}>
        <header>
          <History size={16} />
          <b>Historial de «{page.title || 'Sin título'}»</b>
          <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={onClose}>
            <X size={15} />
          </button>
        </header>
        {error && <p className="ws-empty">{error}</p>}
        {versions && versions.length === 0 && (
          <p className="ws-empty">Todavía no hay versiones anteriores: se guarda una como mucho cada 10 minutos mientras edita.</p>
        )}
        <ul>
          {(versions || []).map((v) => (
            <li key={v.rev}>
              <span>
                <b>{new Date(v.savedAt).toLocaleString('es', { dateStyle: 'medium', timeStyle: 'short' })}</b>
                <small>
                  {v.title || 'Sin título'} · {v.blocks} bloques
                </small>
                {v.preview && <em>{v.preview}</em>}
                {v.sealed && <em>Página cifrada en esa versión</em>}
              </span>
              <button type="button" className="mac-icon-btn" title="Comparar con ahora" aria-label="Comparar" onClick={() => void compare(v)}>
                <GitCompare size={14} />
              </button>
              <button type="button" className="paper-button" data-variant="quiet" onClick={() => void restore(v)}>
                <RotateCcw size={14} /> Restaurar
              </button>
            </li>
          ))}
        </ul>
        {diff && <DiffView ops={diff.ops} onBlock={bringBack} />}
      </div>
    </div>
  );
}
