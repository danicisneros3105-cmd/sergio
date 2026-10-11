import { apiFetch } from './api';

export async function nodesRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await apiFetch(`/v1/nodes${path}`, {
    method, headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : `Solicitud falló (${response.status})`);
  }
  return response.json();
}
export interface NodeProfile {
  id: string; name: string; role: string; colour: string;
  species: 'lumen' | 'bruma' | 'nival'; fur: number; interval_minutes: number;
  agent_id?: string;
}
export interface NodeGoal { id: string; text: string; status: string; consecutive_failures?: number; findings?: Array<{text: string; verified: boolean}>; agent_id: string; }
export interface NodeMemory { id: string; text: string; source: string; }
export interface NodeConnection { id: string; name: string; kind: 'cli' | 'mcp'; command: string[]; policy: 'confirm' | 'block'; session_mode?: 'ephemeral' | 'persistent'; }
export interface IntegrationPreset { id: string; name: string; kind: 'cli' | 'mcp'; available: boolean; note: string; repository: string; }
