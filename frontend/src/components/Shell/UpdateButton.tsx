// «Actualizar»: the owner's universal update command, from the app. While
// it runs the server restarts; the page reconnects and reloads by itself
// (freshness.ts) when the new web is there.

import { useEffect, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';

export function UpdateButton() {
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    apiFetch('/v1/sistema/actualizar')
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => s?.running && setBusy(true))
      .catch(() => undefined);
  }, []);
  return (
    <button
      type="button"
      className="sb-update"
      title="Actualizar Sergio"
      aria-label="Actualizar Sergio"
      disabled={busy}
      onClick={async () => {
        try {
          const r = await apiFetch('/v1/sistema/actualizar', { method: 'POST' });
          const body = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(body.detail || 'No se pudo actualizar.');
          setBusy(true);
          toast.success('Actualizando. Sergio se reinicia solo en unos minutos.');
        } catch (e) {
          toast.error(e instanceof Error ? e.message : String(e));
        }
      }}
    >
      {busy ? <Loader2 size={15} className="ext-spin" /> : <RefreshCw size={15} strokeWidth={1.7} />}
      <span className="sb-label">{busy ? 'Actualizando…' : 'Actualizar'}</span>
    </button>
  );
}
