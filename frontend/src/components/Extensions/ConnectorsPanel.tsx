// Extensiones › Conectores, laid out like Claude's: your connectors, «Explorar
// conectores» (the directory), «Añadir conector personalizado», and each
// connector's page with the permission of every tool.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { ChevronDown, ChevronLeft, Loader2, Monitor, Plus, Search } from 'lucide-react';
import { toast } from 'sonner';
import {
  PERMISSION_ES,
  STATUS_ES,
  addConnector,
  connectConnector,
  callConnector,
  configureConnector,
  disconnectConnector,
  fetchConnectors,
  fetchDirectory,
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
import { parseArguments, parseEnvironment } from '../../lib/connector-input';
import { ExtensionSheet as Sheet } from './ExtensionSheet';
import './extensions.css';
import { BrandMark, brandStyle } from '../Brand/BrandMark';
import { celebrate } from '../../lib/celebrate';

const fail = (e: unknown) => toast.error(e instanceof Error ? e.message : String(e));

/** The service's own logo and colour (Simple Icons); a monogram otherwise. */
function Tile({ name, id, size = 36, url }: { name: string; id?: string; size?: number; url?: string }) {
  return <BrandMark name={name} id={id} size={size} url={url} />;
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

// ── the directory ───────────────────────────────────────────────────────────
function Browse({ onClose, onAdded }: { onClose: () => void; onAdded: (c: Connector) => void }) {
  const [data, setData] = useState<{ categories: string[]; connectors: DirectoryEntry[] } | null>(null);
  const [query, setQuery] = useState('');
  const [directoryError, setDirectoryError] = useState('');
  const [category, setCategory] = useState('Destacados');
  const [picked, setPicked] = useState<DirectoryEntry | null>(null);
  const loadDirectory = useCallback(() => {
    setDirectoryError('');
    fetchDirectory().then(setData, e => setDirectoryError(e instanceof Error ? e.message : String(e)));
  }, []);
  useEffect(loadDirectory, [loadDirectory]);
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
            <input autoFocus aria-label="Buscar conectores" placeholder="Buscar" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          {!query && data && (
            <div className="cx-chips" role="group" aria-label="Categorías">
              {data.categories.map((c) => (
                <button key={c} type="button" aria-pressed={category === c} onClick={() => setCategory(c)}>
                  {c}
                </button>
              ))}
            </div>
          )}
          {directoryError ? <div role="alert" className="cx-note">{directoryError}<button className="ext-btn" type="button" onClick={loadDirectory}>Reintentar</button></div> : !data ? (
            <Loader2 className="ext-spin" size={18} />
          ) : (
            <div className="cx-grid">
              {shown.map((c) => (
                <button key={c.id} type="button" className="cx-entry" style={brandStyle(c.id, c.name)} onClick={() => setPicked(c)}>
                  <Tile name={c.name} id={c.id} size={40} url={c.url} />
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
        args: parseArguments(args),
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
      <div className="cx-detail-head" style={brandStyle(entry.id, entry.name)}>
        <Tile name={entry.name} id={entry.id} size={52} url={entry.url} />
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
            <input className="cx-input" aria-label="Argumentos JSON" placeholder={JSON.stringify([entry.args_hint])} value={args} onChange={(e) => setArgs(e.target.value)} />
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
              <input className="cx-input" aria-label="OAuth Client ID (opcional)" placeholder="OAuth Client ID (opcional)" value={clientId} onChange={(e) => setClientId(e.target.value)} />
              <input className="cx-input" type="password" aria-label="OAuth Client Secret (opcional)" placeholder="OAuth Client Secret (opcional)" value={secret} onChange={(e) => setSecret(e.target.value)} />
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
  const [kind, setKind] = useState<'remote' | 'local' | 'cli'>('remote');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [command, setCommand] = useState('');
  const [argumentsText, setArgumentsText] = useState('[]');
  const [environment, setEnvironment] = useState('{}');
  const [cwd, setCwd] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [clientId, setClientId] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const [bearer, setBearer] = useState('');
  const ready = kind === 'remote' ? /^https?:\/\/\S+/.test(url.trim()) : command.trim().length > 0 && (kind !== 'cli' || cwd.trim().length > 0);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const popup = kind === 'remote' ? reserveSignInWindow() : null;
    setBusy(true);
    try {
      const { server } =
        kind === 'remote'
          ? await addConnector({ name: name.trim(), url: url.trim(), client_id: clientId.trim() || undefined, client_secret: secret.trim() || undefined, headers: bearer.trim() ? { Authorization: `Bearer ${bearer.trim()}` } : undefined })
          : await addConnector({ name: name.trim(), kind: kind === 'cli' ? 'cli' : 'mcp', command: [command.trim()], args: parseArguments(argumentsText), env: parseEnvironment(environment), cwd: kind === 'cli' ? cwd.trim() : undefined });
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
        <div className="cx-seg" role="radiogroup" aria-label="Tipo de conexión">
          <button type="button" role="radio" aria-checked={kind === 'remote'} onClick={() => setKind('remote')}>
            MCP remoto
          </button>
          <button type="button" role="radio" aria-checked={kind === 'local'} onClick={() => setKind('local')}>
            MCP local
          </button>
          <button type="button" role="radio" aria-checked={kind === 'cli'} onClick={() => setKind('cli')}>CLI</button>
        </div>
        <input className="cx-input" aria-label="Nombre del conector" placeholder="Nombre" value={name} onChange={(e) => setName(e.target.value)} />
        {kind === 'remote' ? (
          <>
            <input className="cx-input" aria-label="URL del servidor MCP remoto" placeholder="URL del servidor MCP remoto" value={url} onChange={(e) => setUrl(e.target.value)} inputMode="url" />
            <button type="button" className="cx-adv" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
              Opciones avanzadas <ChevronDown size={14} />
            </button>
            {advanced && (
              <div className="cx-fields">
                <input className="cx-input" aria-label="OAuth Client ID (opcional)" placeholder="OAuth Client ID (opcional)" value={clientId} onChange={(e) => setClientId(e.target.value)} />
                <input className="cx-input" type="password" aria-label="OAuth Client Secret (opcional)" placeholder="OAuth Client Secret (opcional)" value={secret} onChange={(e) => setSecret(e.target.value)} />
                <input className="cx-input" type="password" autoComplete="off" aria-label="Token Bearer (opcional)" placeholder="Token Bearer (opcional)" value={bearer} onChange={(e) => setBearer(e.target.value)} />
                <p className="cx-dim">
                  URL de retorno: <code>{redirect}</code>
                </p>
              </div>
            )}
          </>
        ) : (
          <>
            <label className="cx-field">Ejecutable<input className="cx-input" value={command} onChange={(e) => setCommand(e.target.value)} placeholder={kind === 'cli' ? 'git' : 'npx'} /></label>
            <label className="cx-field">Argumentos (JSON)<textarea className="cx-input cx-json" value={argumentsText} onChange={(e) => setArgumentsText(e.target.value)} placeholder='["--version"]' spellCheck={false} /></label>
            {kind === 'cli' && <label className="cx-field">Carpeta de trabajo<input className="cx-input" value={cwd} onChange={(e) => setCwd(e.target.value)} placeholder="Ruta completa de su proyecto" /></label>}
            <details><summary>Variables privadas</summary><label className="cx-field">Variables (JSON)<textarea className="cx-input cx-json" value={environment} onChange={(e) => setEnvironment(e.target.value)} autoComplete="off" spellCheck={false} /></label></details>
            <p className="cx-dim">Se ejecuta donde está el motor de Sergio; con WSL, dentro de Ubuntu. Las CLI piden permiso antes de ejecutar.</p>
          </>
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
  const [testing, setTesting] = useState('');
  const [testArgs, setTestArgs] = useState('{}');
  const [testResult, setTestResult] = useState<{ text: string; error: boolean } | null>(null);
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
        <Tile name={server.name} id={server.id} size={52} url={server.url} />
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
      <code className="cx-code">{server.url || server.command.map(p => JSON.stringify(p)).join(' ')}</code>
      {server.cwd && <p className="cx-dim">Carpeta: {server.cwd}</p>}
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
          <button type="button" className="ext-btn" data-primary disabled={!!busy || !server.enabled} onClick={() => void act('connect', () => runConnect(server.id, server.kind === 'remote' ? reserveSignInWindow() : null))}>
            {busy === 'connect' ? <Loader2 className="ext-spin" size={15} /> : 'Conectar'}
          </button>
        ) : (
          <>
            <button type="button" className="ext-btn" disabled={!!busy} onClick={() => void act('refresh', async () => (await refreshConnector(server.id)).server)}>
              {busy === 'refresh' ? <Loader2 className="ext-spin" size={15} /> : 'Actualizar herramientas'}
            </button>
            {(server.kind === 'remote' || server.kind === 'local' || server.kind === 'cli') && (
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
                <button type="button" className="ext-btn" disabled={!!busy || t.permission === 'block' || server.status !== 'connected'} onClick={() => { setTesting(t.name); setTestArgs('{}'); setTestResult(null); }}>Probar</button>
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
      {testing && <section className="cx-test" aria-label="Probar herramienta">
        <form className="cx-fields" onSubmit={async e => {
          e.preventDefault(); setBusy('test'); setTestResult(null);
          try {
            const args: unknown = JSON.parse(testArgs);
            if (!args || typeof args !== 'object' || Array.isArray(args)) throw new Error('Los argumentos deben ser un objeto JSON.');
            const result = await callConnector(server.id, testing, args as Record<string, unknown>);
            setTestResult({ text: JSON.stringify(result, null, 2).slice(0, 65536), error: Boolean(result.isError) });
          } catch (e) { setTestResult({ text: e instanceof Error ? e.message : String(e), error: true }); }
          finally { setBusy(''); }
        }}>
          <h3>{testing}</h3>
          <label className="cx-field">Argumentos (JSON)<textarea className="cx-input cx-json" value={testArgs} onChange={e => setTestArgs(e.target.value)} spellCheck={false} /></label>
          <div className="cx-actions"><button className="ext-btn" data-primary disabled={!!busy || server.status !== 'connected'} type="submit">{busy === 'test' ? 'Ejecutando…' : 'Autorizar y ejecutar'}</button><button className="ext-btn" type="button" disabled={!!busy} onClick={() => setTesting('')}>Cerrar</button></div>
          <p className="cx-dim">Esta prueba ejecuta la herramienta y puede modificar datos.</p>
        </form>
        {testResult && <div role="status" aria-live="polite"><p>{testResult.error ? 'La herramienta devolvió un error' : 'Ejecución completada'}</p><pre className="cx-result">{testResult.text}</pre></div>}
      </section>}

    </div>
  );
}

// ── the tab ─────────────────────────────────────────────────────────────────
export function ConnectorsPanel() {
  const [servers, setServers] = useState<Connector[] | null>(null);
  const [redirect, setRedirect] = useState('');
  const [loadError, setLoadError] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [browse, setBrowse] = useState(false);
  const [custom, setCustom] = useState(false);
  const [sources, setSources] = useState<ConnectorInfo[] | null>(null);
  const [busy, setBusy] = useState('');
  const navigate = useNavigate();

  const reload = useCallback(() => {
    fetchConnectors().then(
      (d) => {
        setLoadError('');
        setServers(d.servers);
        setRedirect(d.redirect_uri);
      },
      (e) => {
        setLoadError(e instanceof Error ? e.message : String(e));
        setServers([]);
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
    if (c.status === 'connected') celebrate({ kind: 'connector', title: `${c.name} conectado`, detail: 'Sergio ya puede usarlo.', brand: { name: c.name, id: c.id } });
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
      {loadError ? <div role="alert" className="cx-note">{loadError}<button type="button" className="ext-btn" onClick={reload}>Reintentar</button></div> : !servers ? (
        <Loader2 className="ext-spin" size={18} />
      ) : servers.length === 0 ? (
        <p className="cx-empty">Aún no hay conectores.</p>
      ) : (
        <ul className="cx-list">
          {servers.map((s) => (
            <li key={s.id}>
              <button type="button" className="cx-row" style={brandStyle(s.id, s.name)} onClick={() => setOpen(s.id)}>
                <Tile name={s.name} id={s.id} url={s.url} />
                <span className="cx-row-text">
                  <b>{s.name}</b>
                  <span>
                    {s.kind === 'cli' ? 'CLI · ' : 'MCP · '}{STATUS_ES[s.status]}
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
                      await runConnect(s.id, s.kind === 'remote' ? reserveSignInWindow() : null);
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
                  <button type="button" className="cx-row" style={brandStyle(c.connector_id, c.display_name)} onClick={() => navigate(`/data-sources?connect=${encodeURIComponent(c.connector_id)}`)}>
                    <Tile name={c.display_name} id={c.connector_id} />
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
