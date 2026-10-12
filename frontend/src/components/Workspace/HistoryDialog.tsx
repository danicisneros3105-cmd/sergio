// A page's history, like Notion's: the versions the server kept (at most one
// every 10 minutes, the last 50), each with a preview; restoring one makes
// it the current version (the replaced one is kept in history too).

import { useEffect, useState } from 'react';
import { History, RotateCcw, X } from 'lucide-react';
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

export function HistoryDialog({ page, onRestore, onClose }: { page: Page; onRestore: (old: Page) => void; onClose: () => void }) {
  const [versions, setVersions] = useState<Version[] | null>(null);
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
              <button type="button" className="paper-button" data-variant="quiet" onClick={() => void restore(v)}>
                <RotateCcw size={14} /> Restaurar
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
