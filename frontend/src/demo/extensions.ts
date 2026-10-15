// Demo mode only: connectors and Claude-format plugins without a server.
// The directory and the plugin list are the real ones (extensions.json is
// generated from Sergio's directory and Claude's two official marketplaces);
// connecting and installing are simulated in memory.

import data from './extensions.json';

type Json = Record<string, unknown>;
type Entry = (typeof data.connectors)[number];
type Plugin = (typeof data.plugins)[number];

interface Server {
  id: string;
  name: string;
  kind: 'remote' | 'local';
  url: string;
  command: string[];
  source: string;
  directory_id: string;
  enabled: boolean;
  status: string;
  error: string;
  oauth: boolean;
  own_client: boolean;
  tools: Array<{ name: string; title: string; description: string; read_only: boolean; permission: string }>;
}

const servers = new Map<string, Server>();
const installed = new Map<string, Json>();
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const slug = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'conector';

function toolsFor(name: string) {
  const base = [
    ['buscar', `Busca en ${name}.`, true],
    ['leer', `Lee un elemento de ${name}.`, true],
    ['crear', `Crea un elemento nuevo en ${name}.`, false],
    ['actualizar', `Cambia un elemento de ${name}.`, false],
  ] as const;
  return base.map(([tool, description, ro]) => ({
    name: tool,
    title: tool[0].toUpperCase() + tool.slice(1),
    description,
    read_only: ro,
    permission: ro ? 'allow' : 'ask',
  }));
}

function add(entry: { name: string; url?: string; command?: string[]; directory_id?: string; source?: string }): Server {
  let id = slug(entry.name);
  for (let n = 2; servers.has(id); n++) id = `${slug(entry.name)}-${n}`;
  const server: Server = {
    id,
    name: entry.name,
    kind: entry.url ? 'remote' : 'local',
    url: entry.url || '',
    command: entry.command || [],
    source: entry.source || (entry.directory_id ? 'directory' : 'custom'),
    directory_id: entry.directory_id || '',
    enabled: true,
    status: 'needs_auth',
    error: '',
    oauth: Boolean(entry.url),
    own_client: false,
    tools: [],
  };
  servers.set(id, server);
  return server;
}

function plugins(q: string, market: string) {
  const query = q.toLowerCase();
  return data.plugins
    .filter((p: Plugin) => (!market || p.marketplace === market) && (!query || `${p.name} ${p.display_name} ${p.description}`.toLowerCase().includes(query)))
    .map((p: Plugin) => {
      const id = `${p.name}@${p.marketplace}`;
      const mine = installed.get(id);
      return { id, name: p.name, display_name: p.display_name, description: p.description, category: '', marketplace: p.marketplace, installed: !!mine, enabled: !!mine?.enabled };
    });
}

/** /v1/mcp and /v1/hub (plugins) in the demo; null when not theirs. */
export function handleExtensions(method: string, path: string, url: URL, body: Json): Response | null {
  if (path === '/v1/mcp/directory') {
    const added = new Set([...servers.values()].map((s) => s.directory_id));
    return json({ categories: data.categories, connectors: data.connectors.map((c: Entry) => ({ ...c, added: added.has(c.id) })) });
  }
  if (path === '/v1/mcp/servers' && method === 'GET') {
    return json({ servers: [...servers.values()], redirect_uri: `${location.origin}/v1/mcp/oauth/callback` });
  }
  if (path === '/v1/mcp/servers' && method === 'POST') {
    if (body.directory_id) {
      const entry = data.connectors.find((c: Entry) => c.id === body.directory_id);
      if (!entry) return json({ detail: 'Ese conector no está en el directorio.' }, 400);
      const existing = [...servers.values()].find((s) => s.directory_id === entry.id);
      return json({ server: existing || add({ name: entry.name, url: (entry as Json).url as string, command: (entry as Json).command as string[], directory_id: entry.id }) });
    }
    if (body.url) {
      if (!/^https:\/\//.test(String(body.url))) return json({ detail: 'Por seguridad, un servidor remoto debe usar https://' }, 400);
      return json({ server: add({ name: String(body.name || new URL(String(body.url)).hostname), url: String(body.url) }) });
    }
    if (Array.isArray(body.command) && body.command.length) {
      return json({ server: add({ name: String(body.name || body.command[0]), command: body.command as string[] }) });
    }
    return json({ detail: 'Indique la URL del servidor MCP o la orden que lo arranca.' }, 400);
  }
  const m = path.match(/^\/v1\/mcp\/servers\/([^/]+)(?:\/(\w+))?$/);
  if (m) {
    const server = servers.get(decodeURIComponent(m[1]));
    if (!server) return json({ detail: 'No existe ese conector.' }, 404);
    const action = m[2];
    if (!action && method === 'DELETE') {
      servers.delete(server.id);
      return json({ ok: true });
    }
    if (!action) return json({ server });
    if (action === 'connect' || action === 'refresh') {
      // In the demo the service's sign-in page is skipped: it just connects.
      server.status = 'connected';
      if (!server.tools.length) server.tools = toolsFor(server.name);
      return json(action === 'connect' ? { status: 'connected', server } : { server });
    }
    if (action === 'disconnect') {
      server.status = 'needs_auth';
      return json({ server });
    }
    if (action === 'enabled') {
      server.enabled = Boolean(body.enabled);
      server.status = server.enabled ? (server.tools.length ? 'connected' : 'needs_auth') : 'disabled';
      return json({ server });
    }
    if (action === 'permissions') {
      for (const tool of server.tools) if (!body.tool || tool.name === body.tool) tool.permission = String(body.permission);
      return json({ server });
    }
  }
  if (path === '/v1/hub/marketplaces' && method === 'GET') {
    const count = (name: string) => data.plugins.filter((p: Plugin) => p.marketplace === name).length;
    return json({
      marketplaces: [
        { name: 'claude-plugins-official', source: 'anthropics/claude-plugins-official', plugins: count('claude-plugins-official') },
        { name: 'knowledge-work-plugins', source: 'anthropics/knowledge-work-plugins', plugins: count('knowledge-work-plugins') },
      ],
    });
  }
  if (path === '/v1/hub/marketplaces' && method === 'POST') {
    return json({ detail: 'En el demo no se pueden añadir marketplaces: hágalo en su PC.' }, 400);
  }
  if (path === '/v1/hub/claude-plugins') {
    return json({ available: plugins(url.searchParams.get('q') || '', url.searchParams.get('marketplace') || ''), installed: [...installed.values()] });
  }
  if (path === '/v1/hub/claude-plugins/install') {
    const [name, market] = String(body.id).split('@');
    const p = data.plugins.find((x: Plugin) => x.name === name && x.marketplace === market);
    if (!p) return json({ detail: 'No encuentro ese plugin.' }, 404);
    const connectors = p.connectors.map((c: string) => add({ name: c[0].toUpperCase() + c.slice(1), url: `https://mcp.${slug(c)}.example/mcp`, source: `plugin:${p.name}` }).id);
    const info = { id: body.id, name: p.name, display_name: p.display_name, description: p.description, version: '1.0.0', author: '', marketplace: p.marketplace, enabled: true, skills: p.skills, connectors, commands: [], agents: [], hooks: false };
    installed.set(String(body.id), info);
    return json({ plugin: info });
  }
  if (path === '/v1/hub/claude-plugins/enabled') {
    const info = installed.get(String(body.id));
    if (!info) return json({ detail: 'No está instalado.' }, 404);
    info.enabled = url.searchParams.get('enabled') !== 'false';
    return json({ plugin: info });
  }
  if (path === '/v1/hub/claude-plugins/remove') {
    const info = installed.get(String(body.id));
    for (const id of (info?.connectors as string[]) || []) servers.delete(id);
    installed.delete(String(body.id));
    return json({ ok: true });
  }
  return null;
}
