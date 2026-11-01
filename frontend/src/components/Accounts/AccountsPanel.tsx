// Configuración › Cuentas: who can sign in to this Sergio. The owner approves,
// blocks or removes the other accounts (each one waits until approved), and
// saves the face (or finger, or PIN) of each device to sign in with it.

import { useCallback, useEffect, useState } from 'react';
import { Check, Ban, ScanFace, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { addThisDevice, deviceName, passkeyProblem, passkeyReady } from '../../lib/passkey';

interface Key {
  id: string;
  name: string;
  created: number;
  used: number;
}

/** The devices whose face (or finger, or PIN) opens this account. */
function Faces() {
  const [keys, setKeys] = useState<Key[] | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    apiFetch('/v1/cuentas/llave/lista')
      .then((r) => (r.ok ? r.json() : { llaves: null }))
      .then((d) => setKeys(d.llaves))
      .catch(() => setKeys(null));
  }, []);
  useEffect(() => {
    load();
    void passkeyReady().then(setReady);
  }, [load]);
  if (keys === null) return null;
  return (
    <div className="acc-faces">
      <ul className="acc-list">
        {keys.map((k) => (
          <li key={k.id}>
            <span className="acc-who">
              <b>{k.name}</b>
              <small>{k.used ? `Usada ${new Date(k.used * 1000).toLocaleDateString('es')}` : 'Aún sin usar'}</small>
            </span>
            <span className="acc-actions">
              <button type="button" className="mac-icon-btn" aria-label="Quitar este dispositivo" title="Quitar"
                onClick={async () => {
                  if (!window.confirm('¿Quitar la cara de este dispositivo?')) return;
                  await apiFetch(`/v1/cuentas/llave/${encodeURIComponent(k.id)}`, { method: 'DELETE' });
                  load();
                }}>
                <Trash2 size={15} />
              </button>
            </span>
          </li>
        ))}
      </ul>
      {ready && (
        <button
          type="button"
          className="paper-button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await addThisDevice(deviceName());
              toast.success('Listo: la próxima vez, entre con la cara.');
              load();
            } catch (e) {
              toast.error(passkeyProblem(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          <ScanFace size={15} /> Entrar con la cara en este dispositivo
        </button>
      )}
    </div>
  );
}

interface Account {
  id: string;
  email: string | null;
  phone: string | null;
  name: string;
  provider: string;
  role: 'dueño' | 'aprobado' | 'pendiente' | 'bloqueado';
}

const ROLE: Record<Account['role'], string> = { dueño: 'Dueño', aprobado: 'Puede entrar', pendiente: 'Espera', bloqueado: 'Bloqueada' };

export function AccountsPanel() {
  const navigate = useNavigate();
  const [list, setList] = useState<Account[] | null>(null);
  const load = useCallback(() => {
    apiFetch('/v1/cuentas/lista')
      .then((r) => (r.ok ? r.json() : { accounts: null }))
      .then((d) => setList(d.accounts))
      .catch(() => setList(null));
  }, []);
  useEffect(load, [load]);

  const act = async (path: string, init: RequestInit) => {
    const r = await apiFetch(path, init);
    if (!r.ok) toast.error((await r.json().catch(() => ({}))).detail || 'No se pudo.');
    load();
  };

  if (list === null) return null;
  return (
    <div className="acc">
      {(list ?? []).length === 0 ? (
        <button type="button" className="paper-button" onClick={() => navigate('/entrar')}>
          Crear la cuenta del dueño
        </button>
      ) : (
        <ul className="acc-list">
          {list.map((a) => (
            <li key={a.id}>
              <span className="acc-who">
                <b>{a.name || a.email || a.phone}</b>
                <small>{[a.email && a.name ? a.email : '', a.provider, ROLE[a.role]].filter(Boolean).join(' · ')}</small>
              </span>
              {a.role !== 'dueño' && (
                <span className="acc-actions">
                  {a.role !== 'aprobado' && (
                    <button type="button" className="mac-icon-btn" aria-label="Dejar entrar" title="Dejar entrar"
                      onClick={() => void act(`/v1/cuentas/${a.id}/rol`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role: 'aprobado' }) })}>
                      <Check size={15} />
                    </button>
                  )}
                  {a.role !== 'bloqueado' && (
                    <button type="button" className="mac-icon-btn" aria-label="Bloquear" title="Bloquear"
                      onClick={() => void act(`/v1/cuentas/${a.id}/rol`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role: 'bloqueado' }) })}>
                      <Ban size={15} />
                    </button>
                  )}
                  <button type="button" className="mac-icon-btn" aria-label="Quitar" title="Quitar"
                    onClick={() => window.confirm('¿Quitar esta cuenta?') && void act(`/v1/cuentas/${a.id}`, { method: 'DELETE' })}>
                    <Trash2 size={15} />
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {(list ?? []).length > 0 && <Faces />}
    </div>
  );
}
