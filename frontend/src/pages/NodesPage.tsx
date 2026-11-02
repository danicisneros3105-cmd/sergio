// The Nodes: a fixed team of four (Rihno, Manchas, Hous, Tennessee) that works
// for the owner. This file is the page shell; each tab lives in ./nodes/.
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { CircleSlash, Hand, Octagon, Play } from 'lucide-react';
import { toast } from 'sonner';
import { NodeCritter } from '../components/Nodes/NodeCritter';
import { NodeGoals, ReviewedIntegrations } from '../components/Nodes/NodeGoals';
import { NodesIntro, introSeen } from '../components/Nodes/NodesIntro';
import { nodesApi, STATUS_ES, statusLine, type Catalog, type SergioNode } from '../lib/nodes';
import { ActivityTab } from './nodes/ActivityTab';
import { AppsTab } from './nodes/AppsTab';
import { ChatTab } from './nodes/ChatTab';
import { ComputerTab } from './nodes/ComputerTab';
import { ConnectionsTab } from './nodes/ConnectionsTab';
import { MemoryTab } from './nodes/MemoryTab';
import { RoutinesTab } from './nodes/RoutinesTab';
import { RulesTab } from './nodes/RulesTab';
import { SettingsTab } from './nodes/SettingsTab';
import { isActive, look, memberOf } from './nodes/shared';

type Tab = 'chat' | 'activity' | 'goals' | 'computer' | 'memory' | 'routines' | 'rules' | 'apps' | 'connections' | 'settings';
const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'chat', label: 'Chat' },
  { key: 'activity', label: 'Actividad' },
  { key: 'goals', label: 'Objetivos' },
  { key: 'computer', label: 'Computadora' },
  { key: 'memory', label: 'Memoria' },
  { key: 'routines', label: 'Rutinas' },
  { key: 'rules', label: 'Reglas' },
  { key: 'apps', label: 'Apps' },
  { key: 'connections', label: 'Conexiones' },
  { key: 'settings', label: 'Ajustes' },
];

export function NodesPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [nodes, setNodes] = useState<SergioNode[] | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [tab, setTab] = useState<Tab>('chat');
  const [intro, setIntro] = useState(() => !introSeen());

  const refresh = useCallback(() => {
    nodesApi
      .list()
      .then(setNodes)
      .catch(() => setNodes((n) => n ?? []));
  }, []);

  useEffect(() => {
    refresh();
    nodesApi
      .catalog()
      .then(setCatalog)
      .catch(() => {});
    const t = window.setInterval(refresh, 2500);
    return () => window.clearInterval(t);
  }, [refresh]);

  const node = nodes?.find((n) => n.id === id) || (!id && nodes?.[0]) || undefined;
  useEffect(() => {
    if (node && node.unread) nodesApi.seen(node.id).catch(() => {});
  }, [node?.id, node?.unread]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = (n: SergioNode) => {
    setTab('chat');
    navigate(`/nodes/${n.id}`);
  };

  const cancel = async (n: SergioNode) => {
    try {
      await nodesApi.cancel(n.id);
      toast('Acción cancelada.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude cancelar.');
    }
    refresh();
  };

  // The team is always there; an empty list only means the server is still starting.
  if (!Array.isArray(nodes) || !nodes.length) return <div className="paper-page" aria-busy="true" />;

  return (
    <div className="nodes">
      {intro && nodes.some((n) => n.team) && (
        <NodesIntro nodes={nodes} catalog={catalog} onClose={() => setIntro(false)} />
      )}
      <aside className="nodes-list" aria-label="Sus Nodes">
        <div className="nodes-list-head">
          <span className="wordmark">Nodes</span>
        </div>
        {nodes.map((n) => (
          <button
            key={n.id}
            type="button"
            className="nodes-item"
            style={{ '--node': look(n).color } as React.CSSProperties}
            aria-current={node?.id === n.id ? 'true' : undefined}
            onClick={() => open(n)}
          >
            <NodeCritter look={look(n)} status={n.status} size={48} />
            <span className="min-w-0 flex-1 text-left">
              <span className="nodes-item-name">{n.name}</span>
              <span className="nodes-item-status">{n.status === 'idle' ? memberOf(n, catalog)?.does || memberOf(n, catalog)?.role || statusLine(n) : statusLine(n)}</span>
            </span>
            {n.approvals.length > 0 || n.status === 'needs_you' ? (
              <span className="nodes-badge" aria-label="Le necesita">
                !
              </span>
            ) : n.unread > 0 && node?.id !== n.id ? (
              <span className="nodes-badge nodes-badge-quiet">{n.unread}</span>
            ) : null}
          </button>
        ))}
      </aside>

      {node && (
        <section className="node-page" aria-label={node.name} style={{ '--node': look(node).color } as React.CSSProperties}>
          <header className="node-head">
            <NodeCritter look={look(node)} status={node.status} size={64} label={`${node.name}: ${STATUS_ES[node.status]}`} />
            <div className="min-w-0 flex-1">
              <h1 className="node-name">{node.name}</h1>
              <p className="node-status" data-status={node.status}>
                <i />
                {statusLine(node)}
              </p>
            </div>
            {isActive(node) && (
              <button type="button" className="paper-button" data-variant="quiet" title="Deja lo que está haciendo y sigue disponible" onClick={() => void cancel(node)}>
                <CircleSlash size={14} /> Cancelar acción
              </button>
            )}
            {node.status === 'paused' ? (
              <button type="button" className="paper-button" onClick={async () => (await nodesApi.resume(node.id), refresh())}>
                <Play size={14} /> Reanudar
              </button>
            ) : (
              <button
                type="button"
                className="paper-button node-stop"
                data-variant="danger"
                title="Parada de emergencia: deja todo y espera"
                onClick={async () => (await nodesApi.stop(node.id), refresh(), toast('Detenido.'))}
              >
                <Octagon size={14} /> Detener
              </button>
            )}
          </header>
          <nav className="node-tabs paper-tabs" role="tablist">
            {TABS.map((t) => (
              <button key={t.key} type="button" role="tab" className="paper-tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}>
                {t.label}
                {t.key === 'chat' && node.approvals.length > 0 && <span className="node-tab-dot" />}
              </button>
            ))}
          </nav>
          <div className="node-body">
            {tab === 'chat' && <ChatTab key={node.id} node={node} onChanged={refresh} onCancel={() => void cancel(node)} />}
            {tab === 'activity' && <ActivityTab node={node} />}
            {tab === 'computer' && <ComputerTab node={node} />}
            {tab === 'memory' && <MemoryTab node={node} onChanged={refresh} />}
            {tab === 'routines' && <RoutinesTab key={node.id} node={node} onChanged={refresh} />}
            {tab === 'rules' && <RulesTab node={node} catalog={catalog} onChanged={refresh} />}
            {tab === 'apps' && <AppsTab node={node} onChanged={refresh} />}
            {tab === 'goals' && <NodeGoals nodeId={node.id} />}
            {tab === 'connections' && (
              <div className="node-connections">
                <ConnectionsTab node={node} catalog={catalog} onChanged={refresh} />
                <ReviewedIntegrations nodeId={node.id} />
              </div>
            )}
            {tab === 'settings' && (
              <SettingsTab
                key={node.id}
                node={node}
                catalog={catalog}
                onChanged={refresh}
                onDeleted={() => {
                  refresh();
                  navigate('/nodes');
                }}
              />
            )}
          </div>
          {node.status === 'needs_you' && tab !== 'chat' && (
            <button type="button" className="node-floating" onClick={() => setTab('chat')}>
              <Hand size={14} /> {node.name} le necesita
            </button>
          )}
        </section>
      )}
    </div>
  );
}

export default NodesPage;
