// Configuración › Cuentas: who can sign in to this Sergio. The owner approves,
// blocks or removes the other accounts (each one waits until approved).

import { useCallback, useEffect, useState } from 'react';
import { Check, Ban, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';

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
      {list.length === 0 ? (
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
    </div>
  );
}
