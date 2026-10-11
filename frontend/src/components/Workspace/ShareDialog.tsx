import { useEffect, useState } from 'react';
import { Copy, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { flushWorkspace, useWorkspace } from '../../lib/workspace/store';

export interface ShareTarget {
  page: string;
  scope: 'page' | 'block' | 'rows' | 'view';
  block?: string;
  rows?: string[];
  view?: string;
}

interface Link {
  token: string;
  scope: string;
  expires?: number;
}

const SCOPE_TEXT: Record<ShareTarget['scope'], string> = {
  page: 'Toda la página (sus subpáginas no).',
  block: 'Solo este bloque.',
  rows: 'Solo las filas elegidas de la tabla.',
  view: 'Solo esta vista de la tabla (con su filtro).',
};

// Share exactly one part, read-only, with a link that can expire and be
// revoked. The rest of the Workspace stays closed.
export function ShareDialog({ target, onClose }: { target: ShareTarget; onClose: () => void }) {
  const [days, setDays] = useState('7');
  const [made, setMade] = useState('');
  const [links, setLinks] = useState<Link[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () =>
    apiFetch(`/v1/workspace/shares?page=${target.page}`)
      .then((r) => (r.ok ? r.json() : { shares: [] }))
      .then((d) => setLinks(d.shares || []))
      .catch(() => setLinks([]));

  useEffect(() => {
    void load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async () => {
    setBusy(true);
    setError('');
    try {
      // the server must have the latest version of the page first
      await flushWorkspace();
      await useWorkspace.getState().syncNow();
      const r = await apiFetch('/v1/workspace/shares', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page: target.page,
          scope: target.scope,
          block: target.block || '',
          rows: target.rows || [],
          view: target.view || '',
          days: days === '0' ? null : Number(days),
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'No se pudo crear el enlace.');
      setMade(data.url);
      try {
        await navigator.clipboard.writeText(data.url);
        toast.success('Enlace copiado.');
      } catch {
        // clipboard blocked: the link is on screen
      }
      void load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sin conexión con su servidor: compartir necesita que esté encendido.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ws-modal" role="dialog" aria-modal="true" aria-label="Compartir">
      <div className="ws-modal-sheet">
        <h3 className="paper-title" style={{ fontSize: 16 }}>Compartir</h3>
        <p className="text-[13.5px] mt-3">{SCOPE_TEXT[target.scope]} Solo lectura; nada más de su Workspace es visible.</p>
        <label className="flex items-center gap-2 mt-3 text-[13px]">
          Caduca
          <select className="ws-mini-input" value={days} onChange={(e) => setDays(e.target.value)}>
            <option value="1">en 1 día</option>
            <option value="7">en 7 días</option>
            <option value="30">en 30 días</option>
            <option value="0">nunca</option>
          </select>
        </label>
        <p className="text-[12px] mt-2" style={{ color: 'var(--color-text-tertiary)' }}>
          Para que alguien de fuera lo abra, su servidor debe ser accesible (por ejemplo con el túnel de Sergio).
        </p>
        {made && (
          <div className="mac-field mt-3 text-[12.5px]">
            <span className="truncate flex-1">{made}</span>
            <button type="button" className="mac-icon-btn" aria-label="Copiar" onClick={() => void navigator.clipboard?.writeText(made)}>
              <Copy size={14} />
            </button>
          </div>
        )}
        {error && <p className="mt-2 text-[13px]" style={{ color: 'var(--color-error)' }}>{error}</p>}
        {links.length > 0 && (
          <div className="mt-4">
            <div className="paper-label mb-1">Enlaces activos de esta página</div>
            {links.map((l) => (
              <div key={l.token} className="flex items-center gap-2 text-[12.5px] py-1">
                <span className="flex-1 truncate">
                  {l.scope} · …{l.token.slice(-6)}
                  {l.expires ? ` · hasta ${new Date(l.expires * 1000).toLocaleDateString('es')}` : ''}
                </span>
                <button
                  type="button"
                  className="mac-icon-btn"
                  aria-label="Revocar"
                  onClick={() => void apiFetch(`/v1/workspace/shares/${l.token}`, { method: 'DELETE' }).then(load)}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2 justify-end mt-4">
          <button type="button" className="paper-button" data-variant="quiet" onClick={onClose}>
            Cerrar
          </button>
          <button type="button" className="paper-button" disabled={busy} onClick={() => void create()}>
            {busy ? 'Creando…' : 'Crear enlace'}
          </button>
        </div>
      </div>
    </div>
  );
}
