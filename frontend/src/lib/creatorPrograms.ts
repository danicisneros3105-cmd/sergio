// Creator's real programs (OpenDesign, VSCodium, ArtCraft, Kdenlive, FreeCAD,
// Bonsai, LibreCAD, Blender, Kronos): what is installed, and the calls that
// install, start and open them.

import { apiFetch } from './api';

export type ProgramWhere = 'web' | 'windows' | 'local';

export interface WindowsSide {
  installed: boolean;
  installing: boolean;
  error: string;
  reachable: boolean;
}

export interface Program {
  id: string;
  name: string;
  space: string;
  where: ProgramWhere;
  what: string;
  license: string;
  installed?: boolean;
  installing?: boolean;
  running?: boolean;
  error?: string;
  reachable?: boolean;
  step?: string;
  port?: number;
  token?: string;
  windows?: WindowsSide; // VSCodium also has its desktop app
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || 'No pude hablar con Sergio.');
  return body as T;
}

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body ?? {}),
});

export const listPrograms = () => call<{ programs: Program[] }>('/v1/creator/programs').then((r) => r.programs);
export const startProgram = (id: string) =>
  call<{ outcome: string; running: boolean }>(`/v1/creator/programs/${id}/start`, post());
export const installProgram = (id: string, where = '') =>
  call<{ message?: string; installing?: boolean }>(`/v1/creator/programs/${id}/install`, post({ where }));
export const openProgram = (id: string) => call<{ message: string }>(`/v1/creator/programs/${id}/open`, post());

export async function openFileIn(id: string, name: string, blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  const out = await call<{ message: string }>(`/v1/creator/programs/${id}/open-file`, post({ name, data: btoa(binary) }));
  return out.message;
}

/** The address of a program served inside Sergio's web (same host name as
 * the page, so it works from Windows through WSL). */
export function embedUrl(p: Program, host = window.location.hostname): string {
  const base = `http://${host || '127.0.0.1'}:${p.port}/`;
  return p.id === 'vscodium' && p.token ? `${base}?tkn=${encodeURIComponent(p.token)}` : base;
}

export function programState(p: Program): 'listo' | 'instalando' | 'falta' | 'sin-escritorio' {
  if (p.installing || p.windows?.installing) return 'instalando';
  if (p.where === 'windows' && p.reachable === false) return 'sin-escritorio';
  return p.installed ? 'listo' : 'falta';
}
