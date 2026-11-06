// Sign-in before the app (owner, 27 Oct 2026: «dame la nueva actualización con
// inicio de sesión»). The app asks the server who is here: nobody signed in →
// «/entrar» (or «Crear cuenta» the very first time). It fails open: if the
// server cannot answer, nothing is blocked (a bug must never lock the owner
// out); on the owner's own computer «Seguir sin cuenta» is always there.

import { apiFetch } from './api';
import { accountAtPageLoad } from './browserAccount';

export const NO_ACCOUNT = 'sergio-sin-cuenta';
export const TOUR_SEEN = 'sergio-tour-v1';

export type SessionNeed = 'ok' | 'entrar' | 'crear';

interface Estado {
  accounts: number;
  local: boolean;
  me: unknown;
}

function flag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

export function setFlag(key: string, on = true): void {
  try {
    if (on) localStorage.setItem(key, '1');
    else localStorage.removeItem(key);
  } catch {
    // storage blocked: the choice lasts this visit only
  }
}

export function needFrom(estado: Estado | null, skipped: boolean): SessionNeed {
  if (!estado || estado.me) return 'ok';
  if (skipped && estado.local) return 'ok';
  return estado.accounts === 0 ? 'crear' : 'entrar';
}

export async function sessionNeed(): Promise<SessionNeed> {
  try {
    const res = await apiFetch('/v1/cuentas/estado');
    if (!res.ok) return accountAtPageLoad ? 'entrar' : 'ok';
    const estado = (await res.json()) as Estado;
    if (accountAtPageLoad && (estado.me as { id?: string } | null)?.id !== accountAtPageLoad) return 'entrar';
    return needFrom(estado, flag(NO_ACCOUNT));
  } catch {
    return accountAtPageLoad ? 'entrar' : 'ok';
  }
}

export function tourSeen(): boolean {
  return flag(TOUR_SEEN);
}


// Closing the session on the server and clearing browser credentials are
// separate: a disconnected server must not leave this browser signed in.
export async function closeAccountSession(clearLocalSession: () => void): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const pending = apiFetch('/v1/cuentas/salir', { method: 'POST', signal: controller.signal });
    clearLocalSession();
    setFlag(NO_ACCOUNT, false);
    return (await pending).ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}
