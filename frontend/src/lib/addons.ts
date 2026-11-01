// Optional add-ons (/v1/personal/complementos): off until the person adds them.
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from './api';

export interface Addon {
  clave: string;
  nombre: string;
  lema: string;
  hace: string;
  activo: boolean;
}

export function useAddons() {
  const [addons, setAddons] = useState<Addon[] | null>(null);
  const [problem, setProblem] = useState('');
  useEffect(() => {
    apiFetch('/v1/personal/complementos')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Error ${r.status}`))))
      .then((d) => setAddons(Array.isArray(d?.complementos) ? d.complementos : []))
      .catch(() => setProblem('Sergio no responde ahora.'));
  }, []);
  const set = useCallback(async (key: string, on: boolean) => {
    setProblem('');
    setAddons((all) => all?.map((a) => (a.clave === key ? { ...a, activo: on } : a)) ?? null);
    const r = await apiFetch(`/v1/personal/complementos/${encodeURIComponent(key)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ activa: on }),
    }).catch(() => null);
    if (r?.ok) {
      const d = await r.json();
      setAddons(Array.isArray(d?.complementos) ? d.complementos : []);
    } else {
      setAddons((all) => all?.map((a) => (a.clave === key ? { ...a, activo: !on } : a)) ?? null);
      setProblem('No se pudo cambiar.');
    }
  }, []);
  return { addons, problem, set };
}
