// Extensiones › Plugins, like Claude's: plugins from marketplaces (Claude's
// own two come added), each bundling skills, connectors, commands and agents.
// Sergio's older plugins (tools in Python) stay listed below.

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, Search } from 'lucide-react';
import { toast } from 'sonner';
import {
  addMarketplace,
  fetchClaudePlugins,
  fetchMarketplaces,
  installClaudePlugin,
  monogram,
  removeClaudePlugin,
  setClaudePluginEnabled,
  type ClaudePlugin,
  type InstalledPlugin,
  type Marketplace,
} from '../../lib/mcp';
import { ExtensionSheet as Sheet } from './ExtensionSheet';
import './extensions.css';

const fail = (e: unknown) => toast.error(e instanceof Error ? e.message : String(e));

function counts(p: InstalledPlugin): string {
  const parts = [];
  if (p.skills.length) parts.push(`${p.skills.length} skills`);
  if (p.connectors.length) parts.push(`${p.connectors.length} conectores`);
  return parts.join(' · ') || 'Sin contenido';
}

function Detail({ plugin, installed, onClose, onChanged }: { plugin: ClaudePlugin; installed?: InstalledPlugin; onClose: () => void; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    try {
      await fn();
      if (done) toast.success(done);
      onChanged();
      return true;
    } catch (e) {
      fail(e);
      return false;
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet label={plugin.display_name} onClose={onClose}>
        <div className="cx-detail-head">
          <span className="cx-tile" style={{ width: 52, height: 52, fontSize: 18 }} aria-hidden>
            {monogram(plugin.display_name)}
          </span>
          <div>
            <h2 className="cx-h2">{plugin.display_name}</h2>
            <p className="cx-dim">
              {plugin.marketplace}
              {installed?.version ? ` · v${installed.version}` : ''}
            </p>
          </div>
        </div>
        <p className="cx-plugin-desc">{plugin.description}</p>
        {installed && (
          <dl className="cx-contents">
            {installed.skills.length > 0 && (
              <div>
                <dt>Skills</dt>
                <dd>{installed.skills.join(', ')}</dd>
              </div>
            )}
            {installed.connectors.length > 0 && (
              <div>
                <dt>Conectores</dt>
                <dd>{installed.connectors.join(', ')} — conéctelos en Conectores</dd>
              </div>
            )}
            {installed.hooks && (
              <div>
                <dt>Hooks</dt>
                <dd>Sergio no ejecuta los hooks de los plugins.</dd>
              </div>
            )}
          </dl>
        )}
        <div className="cx-actions">
          {!installed ? (
            <button
              type="button"
              className="ext-btn cx-wide"
              data-primary
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const { plugin: p } = await installClaudePlugin(plugin.id);
                  if (p.connector_errors?.length) toast.error(p.connector_errors.join(' '));
                  else toast.success(`${p.display_name} instalado: ${counts(p)}.`);
                })
              }
            >
              {busy ? <Loader2 className="ext-spin" size={15} /> : 'Instalar'}
            </button>
          ) : (
            <>
              <button type="button" className="ext-btn" disabled={busy} onClick={() => void run(() => setClaudePluginEnabled(plugin.id, !installed.enabled))}>
                {installed.enabled ? 'Desactivar' : 'Activar'}
              </button>
              <button type="button" className="ext-btn cx-danger" disabled={busy} onClick={() => void run(() => removeClaudePlugin(plugin.id), 'Desinstalado.').then(ok => { if (ok) onClose(); })}>
                Desinstalar
              </button>
            </>
          )}
        </div>
    </Sheet>
  );
}

export function PluginsPanel({ legacy }: { legacy?: React.ReactNode }) {
  const [markets, setMarkets] = useState<Marketplace[] | null>(null);
  const [market, setMarket] = useState('');
  const [query, setQuery] = useState('');
  const [data, setData] = useState<{ available: ClaudePlugin[]; installed: InstalledPlugin[] } | null>(null);
  const [picked, setPicked] = useState<ClaudePlugin | null>(null);
  const [adding, setAdding] = useState(false);
  const [source, setSource] = useState('');
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    fetchClaudePlugins(query, market).then(setData, fail);
  }, [query, market]);
  useEffect(() => {
    fetchMarketplaces().then((d) => setMarkets(d.marketplaces), (e) => {
      setMarkets([]);
      fail(e);
    });
  }, []);
  useEffect(() => {
    if (markets === null) return;
    const t = setTimeout(reload, 200);
    return () => clearTimeout(t);
  }, [reload, markets]);

  const installedById = new Map((data?.installed || []).map((p) => [p.id, p]));
  const installedList = data?.installed || [];

  return (
    <div className="cx">
      <div className="cx-bar">
        <label className="cx-search cx-grow">
          <Search size={16} />
          <input aria-label="Buscar plugins" placeholder="Buscar plugins" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        {markets && markets.length > 1 && (
          <select className="cx-select" value={market} onChange={(e) => setMarket(e.target.value)} aria-label="Marketplace">
            <option value="">Todos</option>
            {markets.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name}
              </option>
            ))}
          </select>
        )}
        <button type="button" className="ext-btn" onClick={() => setAdding(true)}>
          <Plus size={15} /> Marketplace
        </button>
      </div>

      {installedList.length > 0 && !query && (
        <section className="cx-section">
          <h3>Instalados</h3>
          <ul className="cx-list">
            {installedList.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className="cx-row"
                  onClick={() =>
                    setPicked({ id: p.id, name: p.name, display_name: p.display_name, description: p.description, category: '', marketplace: p.marketplace, installed: true, enabled: p.enabled })
                  }
                >
                  <span className="cx-tile" aria-hidden>
                    {monogram(p.display_name)}
                  </span>
                  <span className="cx-row-text">
                    <b>{p.display_name}</b>
                    <span>{counts(p)}</span>
                  </span>
                </button>
                <button
                  type="button"
                  role="switch"
                  aria-checked={p.enabled}
                  aria-label={`${p.display_name} activo`}
                  className="ext-switch"
                  onClick={() => setClaudePluginEnabled(p.id, !p.enabled).then(reload, fail)}
                />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="cx-section">
        <h3>Explorar</h3>
        {!data ? (
          <Loader2 className="ext-spin" size={18} />
        ) : data.available.length === 0 ? (
          <p className="cx-empty">{markets?.length ? 'Nada con ese nombre.' : 'Añada un marketplace para ver plugins.'}</p>
        ) : (
          <div className="cx-grid">
            {data.available.slice(0, 240).map((p) => (
              <button key={p.id} type="button" className="cx-entry" onClick={() => setPicked(p)}>
                <span className="cx-tile" style={{ width: 40, height: 40, fontSize: 14 }} aria-hidden>
                  {monogram(p.display_name)}
                </span>
                <span className="cx-entry-text">
                  <b>{p.display_name}</b>
                  <span>{p.description}</span>
                  {p.installed && <em className="cx-badge">Instalado</em>}
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      {legacy}

      {picked && (
        <Detail
          plugin={picked}
          installed={installedById.get(picked.id)}
          onClose={() => setPicked(null)}
          onChanged={reload}
        />
      )}
      {adding && (
        <Sheet label="Añadir marketplace" onClose={() => setAdding(false)}>
          <form
            className="cx-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                const out = await addMarketplace(source.trim());
                toast.success(`${out.name}: ${out.plugins} plugins.`);
                setAdding(false);
                setSource('');
                const d = await fetchMarketplaces();
                setMarkets(d.marketplaces);
              } catch (err) {
                fail(err);
              } finally {
                setBusy(false);
              }
            }}
          >
            <h2 className="cx-h2">Añadir marketplace</h2>
            <input className="cx-input" autoFocus aria-label="Repositorio del marketplace" placeholder="propietario/repositorio o URL git" value={source} onChange={(e) => setSource(e.target.value)} />
            {markets && markets.length > 0 && (
              <ul className="cx-markets">
                {markets.map((m) => (
                  <li key={m.name}>
                    {m.name} <span className="cx-dim">· {m.plugins} plugins</span>
                  </li>
                ))}
              </ul>
            )}
            <button type="submit" className="ext-btn cx-wide" data-primary disabled={busy || !source.trim()}>
              {busy ? <Loader2 className="ext-spin" size={15} /> : 'Añadir'}
            </button>
          </form>
        </Sheet>
      )}
    </div>
  );
}

export default PluginsPanel;
