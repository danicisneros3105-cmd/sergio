// Extensiones › Conectores, laid out like Claude's: your connectors, «Explorar
// conectores» (the directory), «Añadir conector personalizado», and each
// connector's page with the permission of every tool.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { ChevronDown, ChevronLeft, Loader2, Monitor, Plus, Search, X } from 'lucide-react';
import { toast } from 'sonner';
import {
  PERMISSION_ES,
  STATUS_ES,
  addConnector,
  connectConnector,
  configureConnector,
  disconnectConnector,
  fetchConnectors,
  fetchDirectory,
  monogram,
  refreshConnector,
  removeConnector,
  setConnectorEnabled,
  setToolPermission,
  signInWindow,
  reserveSignInWindow,
  type Connector,
  type DirectoryEntry,
  type Permission,
} from '../../lib/mcp';
import { listConnectors } from '../../lib/connectors-api';
import type { ConnectorInfo } from '../../types/connectors';
import './extensions.css';

const fail = (e: unknown) => toast.error(e instanceof Error ? e.message : String(e));

function Tile({ name, size = 36 }: { name: string; size?: number }) {
  return (
    <span className="cx-tile" style={{ width: size, height: size, fontSize: size * 0.36 }} aria-hidden>
      {monogram(name)}
    </span>
  );
}

/** Connect: open the service's sign-in page when it asks for one. */
async function runConnect(id: string, popup: Window | null = reserveSignInWindow()): Promise<Connector | null> {
  let started;
  try { started = await connectConnector(id); }
  catch (e) { popup?.close(); throw e; }
  if (started.status === 'connected') { popup?.close(); return started.server ?? null; }
  if (!started.auth_url) { popup?.close(); throw new Error('El servicio no devolvió una URL para iniciar sesión.'); }
  const ok = await signInWindow(started.auth_url, popup, async () => {
    const { servers } = await fetchConnectors();
    return servers.some((server) => server.id === id && server.status === 'connected');
  });
  const { servers } = await fetchConnectors();
  const server = servers.find((s) => s.id === id) ?? null;
  if (!ok && server?.status !== 'connected') toast('No se completó el inicio de sesión.');
  return server;
}

function Sheet({ label, onClose, wide, children }: { label: string; onClose: () => void; wide?: boolean; children: React.ReactNode }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onClose]);
  return (
    <div className="cx-sheet" role="dialog" aria-modal="true" aria-label={label} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`cx-card${wide ? ' cx-card-wide' : ''}`}>
        <button type="button" className="cx-x" aria-label="Cerrar" onClick={onClose}>
          <X size={18} />
        </button>
        {children}
      </div>
    </div>
  );
}

// ── the directory ───────────────────────────────────────────────────────────
function Browse({ onClose, onAdded }: { onClose: () => void; onAdded: (c: Connector) => void }) {
  const [data, setData] = useState<{ categories: string[]; connectors: DirectoryEntry[] } | null>(null);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('Destacados');
  const [picked, setPicked] = useState<DirectoryEntry | null>(null);
  useEffect(() => {
    fetchDirectory().then(setData, fail);
  }, []);
  const shown = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.connectors.filter((c) =>
      q
        ? `${c.name} ${c.description}`.toLowerCase().includes(q)
        : category === 'Destacados'
          ? c.featured
          : c.category === category,
    );
  }, [data, query, category]);

  return (
    <Sheet label="Conectores" onClose={onClose} wide>
      {picked ? (
        <EntryDetail entry={picked} onBack={() => setPicked(null)} onAdded={onAdded} />
      ) : (
        <>
          <h2 className="cx-h2">Conectores</h2>
          <label className="cx-search">
            <Search size={16} />
            <input autoFocus placeholder="Buscar" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          {!query && data && (
            <div className="cx-chips" role="tablist">
              {data.categories.map((c) => (
                <button key={c} type="button" role="tab" aria-selected={category === c} onClick={() => setCategory(c)}>
                  {c}
                </button>
              ))}
            </div>
          )}
          {!data ? (
            <Loader2 className="ext-spin" size={18} />
          ) : (
            <div className="cx-grid">
              {shown.map((c) => (
                <button key={c.id} type="button" className="cx-entry" onClick={() => setPicked(c)}>
                  <Tile name={c.name} size={40} />
                  <span className="cx-entry-text">
                    <b>{c.name}</b>
                    <span>{c.description}</span>
                    {c.added && <em className="cx-badge">Añadido</em>}
                  </span>
                  {c.kind === 'local' && <Monitor size={14} className="cx-local" aria-label="En su PC" />}
                </button>
              ))}
              {shown.length === 0 && <p className="cx-dim">Nada con ese nombre.</p>}
            </div>
          )}
        </>
      )}
    </Sheet>
  );
}

function EntryDetail({ entry, onBack, onAdded }: { entry: DirectoryEntry; onBack: () => void; onAdded: (c: Connector) => void }) {
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(Boolean(entry.note.includes('Client ID')));
  const [clientId, setClientId] = useState('');
  const [secret, setSecret] = useState('');
  const [args, setArgs] = useState('');
  const add = async () => {
    const popup = entry.kind === 'remote' ? reserveSignInWindow() : null;
    setBusy(true);
    try {
      const { server } = await addConnector({
        directory_id: entry.id,
        client_id: clientId.trim() || undefined,
        client_secret: secret.trim() || undefined,
        args: args.trim() ? args.trim().split(/\s+/) : undefined,
      });
      const connected = await runConnect(server.id, popup).catch((e) => {
        fail(e);
        return server;
      });
      onAdded(connected ?? server);
    } catch (e) {
      popup?.close();
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="cx-detail">
      <button type="button" className="cx-back" onClick={onBack}>
        <ChevronLeft size={16} /> Conectores
      </button>
      <div className="cx-detail-head">
        <Tile name={entry.name} size={52} />
        <div>
          <h2 className="cx-h2">{entry.name}</h2>
          <p className="cx-dim">{entry.kind === 'local' ? 'En su PC' : entry.category}</p>
        </div>
      </div>
      <p>{entry.description}</p>
      {entry.note && <p className="cx-note">{entry.note}</p>}
      {entry.setup_url && <a className="cx-back" href={entry.setup_url} target="_blank" rel="noopener noreferrer">Requisitos del servicio</a>}
      {entry.kind === 'local' ? (
        <>
          <code className="cx-code">{entry.command?.join(' ')}</code>
          {entry.needs && <p className="cx-dim">Necesita {entry.needs} en su PC.</p>}
          {entry.args_hint && (
            <input className="cx-input" placeholder={entry.args_hint} value={args} onChange={(e) => setArgs(e.target.value)} />
          )}
        </>
      ) : (
        <>
          <code className="cx-code">{entry.url}</code>
          <button type="button" className="cx-adv" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
            Opciones avanzadas <ChevronDown size={14} />
          </button>
          {advanced && (
            <div className="cx-fields">
              <input className="cx-input" placeholder="OAuth Client ID (opcional)" value={clientId} onChange={(e) => setClientId(e.target.value)} />
              <input className="cx-input" type="password" placeholder="OAuth Client Secret (opcional)" value={secret} onChange={(e) => setSecret(e.target.value)} />
            </div>
          )}
        </>
      )}
      <button type="button" className="ext-btn cx-wide" data-primary disabled={busy || entry.added || (entry.requires_client_id && !clientId.trim())} onClick={() => void add()}>
        {busy ? <Loader2 className="ext-spin" size={15} /> : entry.added ? 'Ya añadido' : 'Conectar'}
      </button>
    </div>
  );
}

// ── a custom connector ──────────────────────────────────────────────────────
function Custom({ redirect, onClose, onAdded }: { redirect: string; onClose: () => void; onAdded: (c: Connector) => void }) {
  const [kind, setKind] = useState<'remote' | 'local'>('remote');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [command, setCommand] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [clientId, setClientId] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const [bearer, setBearer] = useState('');
  const ready = kind === 'remote' ? /^https?:\/\/\S+/.test(url.trim()) : command.trim().length > 0;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const popup = kind === 'remote' ? reserveSignInWindow() : null;
    setBusy(true);
    try {
      const { server } =
        kind === 'remote'
          ? await addConnector({ name: name.trim(), url: url.trim(), client_id: clientId.trim() || undefined, client_secret: secret.trim() || undefined, headers: bearer.trim() ? { Authorization: `Bearer ${bearer.trim()}` } : undefined })
          : await addConnector({ name: name.trim(), command: command.trim().split(/\s+/) });
      const connected = await runConnect(server.id, popup).catch((err) => {
        fail(err);
        return server;
      });
      onAdded(connected ?? server);
    } catch (err) {
      popup?.close();
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet label="Añadir conector personalizado" onClose={onClose}>
      <form className="cx-form" onSubmit={(e) => void submit(e)}>
        <h2 className="cx-h2">Añadir conector personalizado</h2>
        <div className="cx-seg" role="radiogroup">
          <button type="button" role="radio" aria-checked={kind === 'remote'} onClick={() => setKind('remote')}>
            Remoto
          </button>
          <button type="button" role="radio" aria-checked={kind === 'local'} onClick={() => setKind('local')}>
            En su PC
          </button>
        </div>
        <input className="cx-input" placeholder="Nombre" value={name} onChange={(e) => setName(e.target.value)} />
        {kind === 'remote' ? (
          <>
            <input className="cx-input" placeholder="URL del servidor MCP remoto" value={url} onChange={(e) => setUrl(e.target.value)} inputMode="url" />
            <button type="button" className="cx-adv" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
              Opciones avanzadas <ChevronDown size={14} />
            </button>
            {advanced && (
              <div className="cx-fields">
                <input className="cx-input" placeholder="OAuth Client ID (opcional)" value={clientId} onChange={(e) => setClientId(e.target.value)} />
                <input className="cx-input" type="password" placeholder="OAuth Client Secret (opcional)" value={secret} onChange={(e) => setSecret(e.target.value)} />
                <input className="cx-input" type="password" autoComplete="off" placeholder="Token Bearer (opcional)" value={bearer} onChange={(e) => setBearer(e.target.value)} />
                <p className="cx-dim">
                  URL de retorno: <code>{redirect}</code>
                </p>
              </div>
            )}
          </>
        ) : (
          <input className="cx-input" placeholder="Orden, p. ej. npx -y @modelcontextprotocol/server-memory" value={command} onChange={(e) => setCommand(e.target.value)} />
        )}
        <p className="cx-note">Conecte solo servidores de confianza: podrán leer y hacer lo que sus herramientas permitan.</p>
        <button type="submit" className="ext-btn cx-wide" data-primary disabled={busy || !ready}>
          {busy ? <Loader2 className="ext-spin" size={15} /> : 'Añadir'}
        </button>
      </form>
    </Sheet>
  );
}

// ── one connector ───────────────────────────────────────────────────────────
function ConnectorPage({ server, onBack, onChange, onRemoved }: { server: Connector; onBack: () => void; onChange: (c: Connector) => void; onRemoved: () => void }) {
  const [busy, setBusy] = useState('');
  const [configure, setConfigure] = useState(false);
  const [clientId, setClientId] = useState('');
  const [secret, setSecret] = useState('');
  const [bearer, setBearer] = useState('');
  const act = async (what: string, fn: () => Promise<Connector | null | void>) => {
    setBusy(what);
    try {
      const out = await fn();
      if (out) onChange(out);
    } catch (e) {
      fail(e);
    } finally {
      setBusy('');
    }
  };
  const all = server.tools.length && server.tools.every((t) => t.permission === server.tools[0].permission) ? server.tools[0].permission : '';
  return (
    <div className="cx-page">
      <button type="button" className="cx-back" onClick={onBack}>
        <ChevronLeft size={16} /> Conectores
      </button>
      <div className="cx-detail-head">
        <Tile name={server.name} size={52} />
        <div className="cx-grow">
          <h2 className="cx-h2">{server.name}</h2>
          <p className="cx-dim">
            {STATUS_ES[server.status]}
            {server.source.startsWith('plugin:') ? ` · del plugin ${server.source.slice(7)}` : ''}
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={server.enabled}
          aria-label="Activo"
          className="ext-switch"
          onClick={() => void act('on', async () => (await setConnectorEnabled(server.id, !server.enabled)).server)}
        />
      </div>
      <code className="cx-code">{server.url || server.command.join(' ')}</code>
      {server.error && <p className="cx-note">{server.error}</p>}
      {server.kind === 'remote' && <button type="button" className="cx-adv" aria-expanded={configure} onClick={() => setConfigure(!configure)}>Configurar <ChevronDown size={14} /></button>}
      {configure && <form className="cx-fields" onSubmit={(e) => {
        e.preventDefault();
        void act('configure', async () => {
          const result = await configureConnector(server.id, { client_id: clientId.trim() || undefined, client_secret: secret.trim() || undefined, headers: bearer.trim() ? { Authorization: `Bearer ${bearer.trim()}` } : undefined });
          setSecret(''); setBearer(''); setConfigure(false);
          return result.server;
        });
      }}>
        <input className="cx-input" aria-label="OAuth Client ID" placeholder="OAuth Client ID" value={clientId} onChange={(e) => setClientId(e.target.value)} />
        <input className="cx-input" aria-label="OAuth Client Secret" placeholder="OAuth Client Secret" type="password" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} />
        <input className="cx-input" aria-label="Token Bearer" placeholder="Token Bearer (opcional)" type="password" autoComplete="off" value={bearer} onChange={(e) => setBearer(e.target.value)} />
        <button className="ext-btn" type="submit" disabled={!!busy || (!clientId.trim() && !bearer.trim())}>Guardar credenciales</button>
      </form>}
      <div className="cx-actions">
        {server.status !== 'connected' ? (
          <button type="button" className="ext-btn" data-primary disabled={!!busy || !server.enabled} onClick={() => void act('connect', () => runConnect(server.id))}>
            {busy === 'connect' ? <Loader2 className="ext-spin" size={15} /> : 'Conectar'}
          </button>
        ) : (
          <>
            <button type="button" className="ext-btn" disabled={!!busy} onClick={() => void act('refresh', async () => (await refreshConnector(server.id)).server)}>
              {busy === 'refresh' ? <Loader2 className="ext-spin" size={15} /> : 'Actualizar herramientas'}
            </button>
            {server.kind === 'remote' && (
              <button type="button" className="ext-btn" disabled={!!busy} onClick={() => void act('off', async () => (await disconnectConnector(server.id)).server)}>
                Desconectar
              </button>
            )}
          </>
        )}
        <button
          type="button"
          className="ext-btn cx-danger"
          disabled={!!busy}
          onClick={() =>
            void act('remove', async () => {
              await removeConnector(server.id);
              onRemoved();
            })
          }
        >
          Quitar
        </button>
      </div>

      {server.tools.length > 0 && (
        <section className="cx-tools" aria-label="Permisos de las herramientas">
          <header>
            <h3>Permisos de las herramientas</h3>
            <select
              className="cx-select"
              value={all}
              aria-label="Todas las herramientas"
              onChange={(e) => void act('all', async () => (await setToolPermission(server.id, e.target.value as Permission)).server)}
            >
              <option value="" disabled>
                Varias
              </option>
              {(Object.keys(PERMISSION_ES) as Permission[]).map((p) => (
                <option key={p} value={p}>
                  {PERMISSION_ES[p]}
                </option>
              ))}
            </select>
          </header>
          <ul>
            {server.tools.map((t) => (
              <li key={t.name}>
                <div className="cx-tool-text">
                  <b>{t.title || t.name}</b>
                  {t.read_only && <span className="cx-badge">Solo lectura</span>}
                  {t.description && <span className="cx-dim">{t.description}</span>}
                </div>
                <select
                  className="cx-select"
                  value={t.permission}
                  aria-label={`Permiso de ${t.title || t.name}`}
                  onChange={(e) => void act(t.name, async () => (await setToolPermission(server.id, e.target.value as Permission, t.name)).server)}
                >
                  {(Object.keys(PERMISSION_ES) as Permission[]).map((p) => (
                    <option key={p} value={p}>
                      {PERMISSION_ES[p]}
                    </option>
                  ))}
                </select>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ── the tab ─────────────────────────────────────────────────────────────────
export function ConnectorsPanel() {
  const [servers, setServers] = useState<Connector[] | null>(null);
  const [redirect, setRedirect] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [browse, setBrowse] = useState(false);
  const [custom, setCustom] = useState(false);
  const [sources, setSources] = useState<ConnectorInfo[] | null>(null);
  const [busy, setBusy] = useState('');
  const navigate = useNavigate();

  const reload = useCallback(() => {
    fetchConnectors().then(
      (d) => {
        setServers(d.servers);
        setRedirect(d.redirect_uri);
      },
      (e) => {
        setServers([]);
        fail(e);
      },
    );
  }, []);
  useEffect(() => {
    reload();
    listConnectors().then(setSources, () => setSources([]));
  }, [reload]);

  const added = (c: Connector) => {
    setBrowse(false);
    setCustom(false);
    reload();
    setOpen(c.id);
    if (c.status === 'connected') toast.success(`${c.name} conectado.`);
  };
  const current = servers?.find((s) => s.id === open);
  if (current) {
    return (
      <ConnectorPage
        server={current}
        onBack={() => setOpen(null)}
        onChange={(c) => setServers((list) => (list || []).map((s) => (s.id === c.id ? c : s)))}
        onRemoved={() => {
          setOpen(null);
          reload();
        }}
      />
    );
  }

  return (
    <div className="cx">
      <div className="cx-bar">
        <button type="button" className="ext-btn" data-primary onClick={() => setBrowse(true)}>
          Explorar conectores
        </button>
        <button type="button" className="ext-btn" onClick={() => setCustom(true)}>
          <Plus size={15} /> Añadir conector personalizado
        </button>
      </div>
      {!servers ? (
        <Loader2 className="ext-spin" size={18} />
      ) : servers.length === 0 ? (
        <p className="cx-empty">Aún no hay conectores.</p>
      ) : (
        <ul className="cx-list">
          {servers.map((s) => (
            <li key={s.id}>
              <button type="button" className="cx-row" onClick={() => setOpen(s.id)}>
                <Tile name={s.name} />
                <span className="cx-row-text">
                  <b>{s.name}</b>
                  <span>
                    {STATUS_ES[s.status]}
                    {s.tools.length ? ` · ${s.tools.length} herramientas` : ''}
                  </span>
                </span>
              </button>
              {s.status !== 'connected' && s.enabled && (
                <button
                  type="button"
                  className="ext-btn"
                  disabled={busy === s.id}
                  onClick={async () => {
                    setBusy(s.id);
                    try {
                      await runConnect(s.id);
                    } catch (e) {
                      fail(e);
                    } finally {
                      setBusy('');
                      reload();
                    }
                  }}
                >
                  {busy === s.id ? <Loader2 className="ext-spin" size={15} /> : 'Conectar'}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {sources && sources.length > 0 && (
        <details className="cx-sources">
          <summary>Fuentes para la memoria</summary>
          <ul className="cx-list">
            {[...sources]
              .sort((a, b) => Number(b.connected) - Number(a.connected) || a.display_name.localeCompare(b.display_name, 'es'))
              .map((c) => (
                <li key={c.connector_id}>
                  <button type="button" className="cx-row" onClick={() => navigate(`/data-sources?connect=${encodeURIComponent(c.connector_id)}`)}>
                    <Tile name={c.display_name} />
                    <span className="cx-row-text">
                      <b>{c.display_name}</b>
                      <span>{c.connected ? 'Conectado' : 'Sin conectar'}</span>
                    </span>
                  </button>
                </li>
              ))}
          </ul>
        </details>
      )}

      {browse && <Browse onClose={() => setBrowse(false)} onAdded={added} />}
      {custom && <Custom redirect={redirect} onClose={() => setCustom(false)} onAdded={added} />}
    </div>
  );
}

export default ConnectorsPanel;
