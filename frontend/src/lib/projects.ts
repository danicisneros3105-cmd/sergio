// Projects (server: /v1/proyectos): chats that share standing instructions
// and files. Owner, 29 Oct 2026: «no veo dónde creas proyectos».

import { apiFetch } from './api';

export interface ProjectFile {
  nombre: string;
  bytes: number;
}

export interface Project {
  id: string;
  nombre: string;
  instrucciones: string;
  archivos: ProjectFile[];
  creado: number;
  actualizado: number;
}

async function json<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail || 'No se pudo.');
  return data as T;
}

export async function listProjects(): Promise<Project[]> {
  return (await json<{ proyectos: Project[] }>(await apiFetch('/v1/proyectos'))).proyectos;
}

export async function createProject(nombre: string, instrucciones = ''): Promise<Project> {
  return json(
    await apiFetch('/v1/proyectos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre, instrucciones }),
    }),
  );
}

export async function updateProject(id: string, change: Partial<Pick<Project, 'nombre' | 'instrucciones'>>): Promise<Project> {
  forget(id);
  return json(
    await apiFetch(`/v1/proyectos/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(change),
    }),
  );
}

export async function deleteProject(id: string): Promise<void> {
  forget(id);
  await json(await apiFetch(`/v1/proyectos/${id}`, { method: 'DELETE' }));
}

export async function addProjectFile(id: string, file: File): Promise<Project> {
  forget(id);
  const form = new FormData();
  form.append('archivo', file, file.name);
  return json(await apiFetch(`/v1/proyectos/${id}/archivos`, { method: 'POST', body: form }));
}

export async function removeProjectFile(id: string, name: string): Promise<Project> {
  forget(id);
  return json(await apiFetch(`/v1/proyectos/${id}/archivos/${encodeURIComponent(name)}`, { method: 'DELETE' }));
}

const cache = new Map<string, { at: number; text: string }>();

function forget(id: string): void {
  cache.delete(id);
}

/** What a chat of the project starts with (kept 60 s between messages). */
export async function projectContext(id: string): Promise<string> {
  const hit = cache.get(id);
  if (hit && Date.now() - hit.at < 60_000) return hit.text;
  try {
    const { contexto } = await json<{ contexto: string }>(await apiFetch(`/v1/proyectos/${id}/contexto`));
    cache.set(id, { at: Date.now(), text: contexto });
    return contexto;
  } catch {
    return hit?.text ?? '';
  }
}
