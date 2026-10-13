// Extensiones: plugins and skills (/v1/hub), connectors (/v1/connectors) and
// the programs behind Creator (/v1/creator/programs), in one place.

import { apiFetch } from './api';

export interface HubPlugin {
  name: string;
  version?: string;
  description: string;
  permissions: string[];
  installed: boolean;
  enabled: boolean;
}

export interface HubSkill {
  name: string;
  keys: string[];
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, {
    ...init,
    headers: init.body ? { 'Content-Type': 'application/json', ...(init.headers || {}) } : init.headers,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || 'Sergio no respondió.');
  return body as T;
}

export const fetchHub = () => call<{ plugins: HubPlugin[]; skills: HubSkill[] }>('/v1/hub');

export const installPlugin = (name: string, accept: boolean) =>
  call<{ tools: string[] }>(`/v1/hub/plugins/${encodeURIComponent(name)}/install`, {
    method: 'POST',
    body: JSON.stringify({ accept_permissions: accept }),
  });

export const setPluginEnabled = (name: string, enabled: boolean) =>
  call(`/v1/hub/plugins/${encodeURIComponent(name)}/enabled`, { method: 'POST', body: JSON.stringify({ enabled }) });

export const removePlugin = (name: string) => call(`/v1/hub/plugins/${encodeURIComponent(name)}`, { method: 'DELETE' });

export async function learnSkill(name: string, text: string, pdf?: File): Promise<void> {
  let pdf_b64 = '';
  if (pdf) {
    const bytes = new Uint8Array(await pdf.arrayBuffer());
    let bin = '';
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    pdf_b64 = btoa(bin);
  }
  await call('/v1/skills/learn', { method: 'POST', body: JSON.stringify({ name, text, pdf_b64 }) });
}

/** A plugin's name as a title: «tipo-de-cambio» → «Tipo de cambio». */
export function prettyName(name: string): string {
  const words = name.replace(/[-_]+/g, ' ').trim();
  return words ? words[0].toUpperCase() + words.slice(1) : name;
}
