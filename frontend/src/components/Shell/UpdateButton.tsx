// «Actualizar»: the owner's universal update command, from the app. While
// it runs the server restarts; the page reconnects and reloads by itself
// (freshness.ts) when the new web is there.

import { useEffect, useRef, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';

export function UpdateButton() {
  const [busy, setBusy] = useState(false);
  const requested = useRef(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const check = async () => {
      try {
        const response = await apiFetch('/v1/sistema/actualizar');
        if (!response.ok) return;
        const state = await response.json();
        if (!active) return;
        setBusy(Boolean(state.running));
        if (requested.current && !state.running) {
          requested.current = false;
          if (state.last_exit_code === 0) toast.success('Actualización terminada.');
          else toast.error('La actualización no terminó. Revisa el registro de actualización.');
        }
      } catch {
        // The local server may be temporarily unavailable during its restart.
      } finally {
        if (active && (busy || requested.current)) timer = setTimeout(check, 2500);
      }
    };
    if (busy) timer = setTimeout(check, 2500);
    else void check();
    return () => { active = false; clearTimeout(timer); };
  }, [busy]);
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
          requested.current = true;
          setBusy(true);
          toast.info('Actualización iniciada.');
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
