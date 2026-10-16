// Connectors (/v1/mcp) and Claude-format plugins (/v1/hub/…), the way Claude
// shows them: a directory, custom connectors, per-tool permissions, and
// plugins from marketplaces.

import { apiFetch, getBase } from './api';

export type Permission = 'allow' | 'ask' | 'block';
export const PERMISSION_ES: Record<Permission, string> = {
  allow: 'Permitir siempre',
  ask: 'Pedir permiso',
  block: 'Nunca',
};

export interface DirectoryEntry {
  id: string;
  name: string;
  kind: 'remote' | 'local';
  url?: string;
  command?: string[];
  category: string;
  description: string;
  featured: boolean;
  note: string;
  needs?: string;
  args_hint?: string;
  added: boolean;
  setup_url?: string;
  requires_client_id?: boolean;
}

export interface ConnectorTool {
  name: string;
  title: string;
  description: string;
  read_only: boolean;
  permission: Permission;
}

export type ConnectorStatus = 'connected' | 'needs_auth' | 'error' | 'disabled' | 'off';

export interface Connector {
  id: string;
  name: string;
  kind: 'remote' | 'local';
  url: string;
  command: string[];
  source: string;
  directory_id: string;
  enabled: boolean;
  status: ConnectorStatus;
  error: string;
  oauth: boolean;
  own_client: boolean;
  tools: ConnectorTool[];
}

export interface Marketplace {
  name: string;
  source: string;
  plugins: number;
}

export interface ClaudePlugin {
  id: string;
  name: string;
  display_name: string;
  description: string;
  category: string;
  marketplace: string;
  installed: boolean;
  enabled: boolean;
}

export interface InstalledPlugin {
  id: string;
  name: string;
  display_name: string;
  description: string;
  version: string;
  author: string;
  marketplace: string;
  enabled: boolean;
  skills: string[];
  connectors: string[];
  commands: string[];
  agents: string[];
  hooks: boolean;
  connector_errors?: string[];
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

const post = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

export const fetchDirectory = () => call<{ categories: string[]; connectors: DirectoryEntry[] }>('/v1/mcp/directory');
export const fetchConnectors = () => call<{ servers: Connector[]; redirect_uri: string }>('/v1/mcp/servers');
export const addConnector = (body: {
  directory_id?: string;
  name?: string;
  url?: string;
  command?: string[];
  args?: string[];
  client_id?: string;
  client_secret?: string;
  headers?: Record<string, string>;
}) => post<{ server: Connector }>('/v1/mcp/servers', body);
export const configureConnector = (id: string, body: { client_id?: string; client_secret?: string; headers?: Record<string, string> }) =>
  post<{ server: Connector }>(`/v1/mcp/servers/${encodeURIComponent(id)}/credentials`, body);
export const removeConnector = (id: string) => call(`/v1/mcp/servers/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const connectConnector = (id: string) =>
  post<{ status: 'connected' | 'needs_auth'; auth_url?: string; server?: Connector }>(`/v1/mcp/servers/${encodeURIComponent(id)}/connect`);
export const disconnectConnector = (id: string) => post<{ server: Connector }>(`/v1/mcp/servers/${encodeURIComponent(id)}/disconnect`);
export const refreshConnector = (id: string) => post<{ server: Connector }>(`/v1/mcp/servers/${encodeURIComponent(id)}/refresh`);
export const setConnectorEnabled = (id: string, enabled: boolean) =>
  post<{ server: Connector }>(`/v1/mcp/servers/${encodeURIComponent(id)}/enabled`, { enabled });
export const setToolPermission = (id: string, permission: Permission, tool?: string) =>
  post<{ server: Connector }>(`/v1/mcp/servers/${encodeURIComponent(id)}/permissions`, { tool: tool ?? null, permission });

export const fetchMarketplaces = () => call<{ marketplaces: Marketplace[] }>('/v1/hub/marketplaces');
export const addMarketplace = (source: string) => post<{ name: string; plugins: number }>('/v1/hub/marketplaces', { source });
export const fetchClaudePlugins = (q = '', marketplace = '') =>
  call<{ available: ClaudePlugin[]; installed: InstalledPlugin[] }>(
    `/v1/hub/claude-plugins?q=${encodeURIComponent(q)}&marketplace=${encodeURIComponent(marketplace)}`,
  );
export const installClaudePlugin = (id: string) => post<{ plugin: InstalledPlugin }>('/v1/hub/claude-plugins/install', { id });
export const setClaudePluginEnabled = (id: string, enabled: boolean) =>
  post<{ plugin: InstalledPlugin }>(`/v1/hub/claude-plugins/enabled?enabled=${enabled}`, { id });
export const removeClaudePlugin = (id: string) => post('/v1/hub/claude-plugins/remove', { id });

/** Opens the service's sign-in page and resolves when Sergio's callback page
 * reports back (or the window closes). */
export const reserveSignInWindow = (): Window | null => window.open('about:blank', '_blank', 'width=520,height=720');

export function signInWindow(url: string, reserved?: Window | null, verify?: () => Promise<boolean>): Promise<boolean> {
  const win = reserved === undefined ? reserveSignInWindow() : reserved;
  if (!win) return Promise.reject(new Error('Permita la ventana de inicio de sesión y vuelva a conectar.'));
  const expectedOrigin = new URL(getBase() || window.location.origin, window.location.origin).origin;
  return new Promise((resolve) => {
    let done = false;
    let checking = false;
    const finish = (ok: boolean) => {
      if (done) return;
      done = true;
      window.removeEventListener('message', onMessage);
      clearInterval(timer);
      clearTimeout(expiry);
      win.close();
      resolve(ok);
    };
    const onMessage = (e: MessageEvent) => {
      if (e.origin === expectedOrigin && e.source === win && e.data?.sergio === 'mcp-connected') finish(Boolean(e.data.ok));
    };
    window.addEventListener('message', onMessage);
    const timer = setInterval(() => {
      if (verify && !checking && !done) {
        checking = true;
        void verify().then((ok) => {
          if (ok) finish(true);
          else if (win.closed) finish(false);
        }).catch(() => { if (win.closed) finish(false); }).finally(() => { checking = false; });
      } else if (!verify && win.closed) finish(false);
    }, 1000);
    const expiry = setTimeout(() => finish(false), 15 * 60 * 1000);
    win.location.href = url;
  });
}

/** Two letters for the plain monogram tile (no logos, by the owner's rule). */
export function monogram(name: string): string {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/);
  return ((words[0]?.[0] || '') + (words[1]?.[0] || words[0]?.[1] || '')).toUpperCase();
}

export const STATUS_ES: Record<ConnectorStatus, string> = {
  connected: 'Conectado',
  needs_auth: 'Sin conectar',
  error: 'Con error',
  disabled: 'Desactivado',
  off: 'Sin probar',
};
