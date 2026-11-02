// Connecting the AI: OpenRouter's own sign-in (one click, no pasting) and the
// owner's management key for customers' keys, typed in a password field on
// this computer only (never in the chat).
import { apiFetch } from './api';

export interface AiState {
  ia: boolean;
  gestion: boolean;
  local: boolean;
}

export async function aiState(): Promise<AiState | null> {
  try {
    const r = await apiFetch('/v1/conectar/estado');
    return r.ok ? ((await r.json()) as AiState) : null;
  } catch {
    return null;
  }
}

/** Opens OpenRouter's sign-in; it comes back with the key saved. */
export async function connectOneClick(): Promise<void> {
  const r = await apiFetch(`/v1/conectar/openrouter?vuelta=${encodeURIComponent(window.location.pathname)}`);
  const body = (await r.json().catch(() => ({}))) as { url?: string; detail?: string };
  if (!r.ok || !body.url) throw new Error(body.detail || 'No pude abrir la conexión.');
  window.location.assign(body.url);
}

export async function saveManagementKey(clave: string): Promise<{ gestion: boolean; ia: boolean }> {
  const r = await apiFetch('/v1/conectar/gestion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clave }),
  });
  const body = (await r.json().catch(() => ({}))) as { detail?: string; gestion?: boolean; ia?: boolean };
  if (!r.ok) throw new Error(body.detail || 'No pude guardar la clave.');
  return { gestion: !!body.gestion, ia: !!body.ia };
}
