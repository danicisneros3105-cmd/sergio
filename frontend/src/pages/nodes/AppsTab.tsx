import { useNavigate } from 'react-router';
import { nodesApi, type SergioNode } from '../../lib/nodes';
import { useConnectors } from './shared';

export function AppsTab({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const apps = useConnectors();
  const navigate = useNavigate();
  const set = async (id: string, level: 'none' | 'read' | 'write') => {
    const next = { ...node.apps };
    if (level === 'none') delete next[id];
    else next[id] = level;
    await nodesApi.update(node.id, { apps: next });
    onChanged();
  };
  return (
    <div className="node-apps">
      <p className="node-hint">
        A qué apps entra {node.name} y cómo: solo leer, o leer y preparar cambios (escritura). Escribir siempre pasa por su
        aprobación.
      </p>
      {apps.map((a) => {
        const level = node.apps[a.connector_id] || 'none';
        return (
          <div key={a.connector_id} className="node-rule">
            <span>
              {a.display_name}
              {!a.connected && <em className="node-hint"> · sin conectar</em>}
            </span>
            <div className="node-seg" role="radiogroup" aria-label={a.display_name}>
              {(
                [
                  ['none', 'Sin acceso'],
                  ['read', 'Leer'],
                  ['write', 'Leer y escribir'],
                ] as const
              ).map(([k, label]) => (
                <button key={k} type="button" role="radio" aria-checked={level === k} disabled={!a.connected && k !== 'none'} onClick={() => set(a.connector_id, k)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
      <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/data-sources')}>
        Conectar más apps
      </button>
    </div>
  );
}
