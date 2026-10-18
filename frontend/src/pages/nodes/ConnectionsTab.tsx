import { useState } from 'react';
import { Lock, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { nodesApi, type Catalog, type SergioNode } from '../../lib/nodes';

export function ConnectionsTab({ node, catalog, onChanged }: { node: SergioNode; catalog: Catalog | null; onChanged: () => void }) {
  const [cli, setCli] = useState({ name: '', command: '' });
  const [mcp, setMcp] = useState({ name: '', command: '', url: '' });
  const [api, setApi] = useState({ name: '', base_url: '', auth_header: 'Authorization', prefix: 'Bearer', secret: '' });
  const [tools, setTools] = useState<Record<string, string[]>>({});
  const add = async (kind: 'cli' | 'mcp' | 'api', body: Record<string, string>, reset: () => void) => {
    try {
      await nodesApi.addConnection(node.id, kind, body);
      reset();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude.');
    }
  };
  const remove = async (kind: string, id: string) => {
    await nodesApi.removeConnection(node.id, kind, id);
    onChanged();
  };
  return (
    <div className="node-connections">
      <section>
        <h3 className="paper-label">Comandos (CLI)</h3>
        <p className="node-hint">
          Programas que {node.name} puede ejecutar en su computadora, uno a la vez y sin tuberías. «git status» permite
          solo «git status…»; «git» permite cualquier orden de git. Nunca: shells, sudo, rm.
        </p>
        <ul>
          {node.connections.cli.map((c) => (
            <li key={c.id}>
              <b>{c.name}</b>
              <code>{c.command}</code>
              <button type="button" className="mac-icon-btn" aria-label={`Quitar ${c.name}`} onClick={() => remove('cli', c.id)}>
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
        <div className="node-conn-form">
          <input className="paper-input" placeholder="Nombre (p. ej. git)" value={cli.name} onChange={(e) => setCli({ ...cli, name: e.target.value })} />
          <input className="paper-input" placeholder="Programa permitido (p. ej. git status)" value={cli.command} onChange={(e) => setCli({ ...cli, command: e.target.value })} />
          <button type="button" className="paper-button" disabled={!cli.name || !cli.command} onClick={() => add('cli', cli, () => setCli({ name: '', command: '' }))}>
            <Plus size={14} /> Añadir
          </button>
        </div>
      </section>

      <section>
        <h3 className="paper-label">Servidores MCP</h3>
        <p className="node-hint">Por comando (stdio) o por URL. Pruébelo para ver sus herramientas.</p>
        <ul>
          {node.connections.mcp.map((c) => (
            <li key={c.id}>
              <b>{c.name}</b>
              <code>{c.url || c.command}</code>
              <button
                type="button"
                className="mac-chip"
                onClick={async () => {
                  try {
                    const list = await nodesApi.mcpTools(node.id, c.id);
                    setTools({ ...tools, [c.id]: list.map((t) => t.name) });
                  } catch (e) {
                    toast.error(e instanceof Error ? e.message : 'No respondió.');
                  }
                }}
              >
                Probar
              </button>
              <button type="button" className="mac-icon-btn" aria-label={`Quitar ${c.name}`} onClick={() => remove('mcp', c.id)}>
                <Trash2 size={14} />
              </button>
              {tools[c.id] && <span className="node-hint node-conn-tools">{tools[c.id].join(' · ') || 'Sin herramientas'}</span>}
            </li>
          ))}
        </ul>
        <div className="node-conn-form">
          <input className="paper-input" placeholder="Nombre" value={mcp.name} onChange={(e) => setMcp({ ...mcp, name: e.target.value })} />
          <input className="paper-input" placeholder="Comando (npx -y servidor) o https://…" value={mcp.url || mcp.command} onChange={(e) => (/^https?:/.test(e.target.value) ? setMcp({ ...mcp, url: e.target.value, command: '' }) : setMcp({ ...mcp, command: e.target.value, url: '' }))} />
          <button type="button" className="paper-button" disabled={!mcp.name || !(mcp.url || mcp.command)} onClick={() => add('mcp', mcp, () => setMcp({ name: '', command: '', url: '' }))}>
            <Plus size={14} /> Añadir
          </button>
        </div>
      </section>

      <section>
        <h3 className="paper-label">
          APIs propias {!catalog?.api_allowed && <Lock size={12} />}
        </h3>
        {catalog?.api_allowed ? (
          <>
            <p className="node-hint">
              Su clave se guarda solo en este equipo y {node.name} nunca la ve: el código la añade. Leer (GET) sigue la
              regla «APIs»; cambiar datos siempre le pregunta.
            </p>
            <ul>
              {node.connections.api.map((c) => (
                <li key={c.id}>
                  <b>{c.name}</b>
                  <code>{c.base_url}</code>
                  {c.has_secret && <span className="node-hint">con clave</span>}
                  <button type="button" className="mac-icon-btn" aria-label={`Quitar ${c.name}`} onClick={() => remove('api', c.id)}>
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
            <div className="node-conn-form">
              <input className="paper-input" placeholder="Nombre (p. ej. crm)" value={api.name} onChange={(e) => setApi({ ...api, name: e.target.value })} />
              <input className="paper-input" placeholder="https://api.suempresa.com/v1" value={api.base_url} onChange={(e) => setApi({ ...api, base_url: e.target.value })} />
              <input className="paper-input" placeholder="Cabecera (Authorization)" value={api.auth_header} onChange={(e) => setApi({ ...api, auth_header: e.target.value })} />
              <input className="paper-input" placeholder="Prefijo (Bearer)" value={api.prefix} onChange={(e) => setApi({ ...api, prefix: e.target.value })} />
              <input className="paper-input" type="password" placeholder="Clave" value={api.secret} onChange={(e) => setApi({ ...api, secret: e.target.value })} autoComplete="off" />
              <button
                type="button"
                className="paper-button"
                disabled={!api.name || !api.base_url}
                onClick={() => add('api', api, () => setApi({ name: '', base_url: '', auth_header: 'Authorization', prefix: 'Bearer', secret: '' }))}
              >
                <Plus size={14} /> Añadir
              </button>
            </div>
          </>
        ) : (
          <div className="node-locked">
            <Lock size={16} />
            <p>
              Conectar sus propias APIs a un Node es parte del <b>plan Dev</b>. Su plan ahora: {catalog?.plan || 'free'}. Véalo
              con <code>sergio planes</code>.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
