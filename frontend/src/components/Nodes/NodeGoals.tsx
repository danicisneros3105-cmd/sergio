// Codex's half of the Nodes, on the same Node: goals run by the agent manager
// (one agent, a sequence or two experts in parallel), notes you hand it one by
// one, the audit trail, and reviewed CLI/MCP integrations (Browser-use,
// OpenClaw…) where every run needs a one-time review.

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import {
  nodesRequest,
  type IntegrationPreset,
  type NodeConnection,
  type NodeGoal,
  type NodeMemory,
} from '../../lib/nodes-api';
import { IntegrationCards } from './IntegrationCards';

const GOAL_ES: Record<string, string> = {
  pending: 'Pendiente',
  running: 'En ejecución',
  needs_review: 'Pendiente de revisión',
  completed: 'Completado',
  failed: 'Falló',
  unavailable: 'Sin registro',
};

function useAction() {
  const [busy, setBusy] = useState(false);
  const run = async (work: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    try {
      await work();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'La acción falló');
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}

export function NodeGoals({ nodeId }: { nodeId: string }) {
  const [goals, setGoals] = useState<NodeGoal[]>([]);
  const [notes, setNotes] = useState<NodeMemory[]>([]);
  const [events, setEvents] = useState<Array<{ action: string; at: number }>>([]);
  const [interval, setIntervalMinutes] = useState(0);
  const [text, setText] = useState('');
  const [note, setNote] = useState('');
  const [workflow, setWorkflow] = useState('single');
  const { busy, run } = useAction();

  const load = useCallback(async () => {
    const [g, m, a] = await Promise.all([
      nodesRequest<{ goals: NodeGoal[] }>(`/${nodeId}/goals`),
      nodesRequest<{ memories: NodeMemory[] }>(`/${nodeId}/notes`),
      nodesRequest<{ events: Array<{ action: string; at: number }> }>(`/${nodeId}/audit`),
    ]);
    setGoals(g.goals);
    setNotes(m.memories);
    setEvents(a.events);
  }, [nodeId]);

  useEffect(() => {
    load().catch(() => {});
    const poll = window.setInterval(() => !document.hidden && load().catch(() => {}), 5000);
    return () => window.clearInterval(poll);
  }, [load]);

  const addGoal = (scheduled: boolean) =>
    run(async () => {
      if (scheduled) await nodesRequest(`/${nodeId}/goal-settings`, 'PATCH', { interval_minutes: interval });
      const goal = await nodesRequest<NodeGoal>(`/${nodeId}/goals`, 'POST', { text, scheduled, workflow });
      if (!scheduled) {
        const res = await apiFetch(`/v1/managed-agents/${goal.agent_id}/run`, { method: 'POST' });
        if (!res.ok) throw new Error('El objetivo quedó guardado, pero no pudo arrancar.');
      }
      setText('');
      await load();
    });

  return (
    <div className="node-goals">
      <section>
        <h3 className="paper-label">Objetivos</h3>
        <p className="node-hint">
          Un objetivo lo ejecuta el gestor de agentes con herramientas de lectura. Los modos con especialistas usan tres
          agentes (más consumo). Las tareas que se repiten se pausan tras tres fallos seguidos.
        </p>
        <textarea className="paper-input" rows={3} value={text} maxLength={4000} onChange={(e) => setText(e.target.value)} placeholder="Ej. Busca la documentación oficial de…" />
        <div className="node-conn-form">
          <select className="paper-input" value={workflow} onChange={(e) => setWorkflow(e.target.value)} aria-label="Coordinación">
            <option value="single">Un agente · menor consumo</option>
            <option value="sequential">Secuencial · análisis, solución y revisión</option>
            <option value="parallel_review">Dos especialistas en paralelo y revisión</option>
          </select>
          <input
            className="paper-input"
            type="number"
            min={0}
            max={10080}
            value={interval}
            onChange={(e) => setIntervalMinutes(Number(e.target.value))}
            aria-label="Repetir cada (minutos)"
            title="Repetir cada (minutos, mínimo 5)"
          />
          <button type="button" className="paper-button" disabled={busy || !text.trim()} onClick={() => addGoal(false)}>
            Guardar y ejecutar
          </button>
          <button type="button" className="paper-button" data-variant="quiet" disabled={busy || !text.trim() || interval < 5} onClick={() => addGoal(true)}>
            Programar
          </button>
        </div>
        <ul>
          {goals.map((g) => (
            <li key={g.id}>
              <span className="flex-1 min-w-0">
                {g.text} <small className="node-hint">— {GOAL_ES[g.status] ?? g.status}</small>
                {(g.consecutive_failures ?? 0) >= 3 && <em className="node-hint"> · pausado tras tres fallos: corrija y reanude</em>}
                {g.findings?.map((f, i) => (
                  <span key={i} className="node-goal-finding">
                    {f.text}
                    <em> · pendiente de revisión</em>
                  </span>
                ))}
              </span>
              <button type="button" className="mac-chip" disabled={busy || g.status === 'running'} onClick={() => run(async () => (await nodesRequest(`/${nodeId}/goals/${g.id}`, 'DELETE'), load()))}>
                Quitar
              </button>
            </li>
          ))}
        </ul>
        <div className="node-row-end">
          <button type="button" className="paper-button" data-variant="quiet" disabled={busy} onClick={() => run(async () => (await nodesRequest(`/${nodeId}/goals/pause`, 'POST'), load()))}>
            Pausar objetivos
          </button>
          <button type="button" className="paper-button" data-variant="quiet" disabled={busy} onClick={() => run(async () => (await nodesRequest(`/${nodeId}/goals/resume`, 'POST'), load()))}>
            Reanudar
          </button>
        </div>
      </section>

      <section>
        <h3 className="paper-label">Datos que usted le dio</h3>
        <div className="node-conn-form">
          <input className="paper-input" value={note} maxLength={4000} onChange={(e) => setNote(e.target.value)} placeholder="Ej. Trabajo en Python" />
          <button type="button" className="paper-button" disabled={busy || !note.trim()} onClick={() => run(async () => (await nodesRequest(`/${nodeId}/notes`, 'POST', { text: note }), setNote(''), load()))}>
            Recordar
          </button>
        </div>
        <ul>
          {notes.map((m) => (
            <li key={m.id}>
              <span className="flex-1 min-w-0">
                {m.text} <small className="node-hint">({m.source})</small>
              </span>
              <button type="button" className="mac-chip" disabled={busy} onClick={() => run(async () => (await nodesRequest(`/${nodeId}/notes/${m.id}`, 'DELETE'), load()))}>
                Olvidar
              </button>
            </li>
          ))}
        </ul>
      </section>

      <details>
        <summary className="paper-label">Auditoría</summary>
        <ul>
          {events.map((e, i) => (
            <li key={i}>
              {new Date(e.at * 1000).toLocaleString('es')} — {e.action}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

/** Reviewed integrations: nothing runs without a one-time review of the exact command. */
export function ReviewedIntegrations({ nodeId }: { nodeId: string }) {
  const [presets, setPresets] = useState<IntegrationPreset[]>([]);
  const [items, setItems] = useState<NodeConnection[]>([]);
  const [cliArgs, setCliArgs] = useState('[]');
  const [mcpTool, setMcpTool] = useState('');
  const [mcpArgs, setMcpArgs] = useState('{}');
  const [output, setOutput] = useState('');
  const { busy, run } = useAction();

  const load = useCallback(async () => {
    const [p, c] = await Promise.all([
      nodesRequest<{ presets: IntegrationPreset[] }>('/integration-presets'),
      nodesRequest<{ integrations: NodeConnection[] }>(`/${nodeId}/integrations`),
    ]);
    setPresets(p.presets);
    setItems(c.integrations);
  }, [nodeId]);
  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  const execute = (c: NodeConnection, call = false) =>
    run(async () => {
      const action = {
        arguments: c.kind === 'cli' ? JSON.parse(cliArgs) : [],
        tool: call ? mcpTool : '',
        tool_arguments: call ? JSON.parse(mcpArgs) : {},
      };
      const review = await nodesRequest<{ ticket: string; command: string[] }>(`/${nodeId}/integrations/${c.id}/review`, 'POST', action);
      if (!window.confirm(`Ejecutar en su equipo:\n${JSON.stringify({ ...action, command: review.command })}\nPuede usar archivos o la red. ¿Lo autoriza?`)) return;
      const result = await nodesRequest(`/${nodeId}/integrations/${c.id}/execute`, 'POST', { ...action, ticket: review.ticket });
      setOutput(JSON.stringify(result, null, 2));
      await load();
    });

  return (
    <section>
      <h3 className="paper-label">Integraciones revisadas</h3>
      <p className="node-hint">
        Programas ya instalados (Browser-use, OpenClaw…). Cada ejecución le muestra el comando exacto y espera su
        autorización. No escriba claves en los comandos.
      </p>
      <IntegrationCards
        presets={presets}
        busy={busy}
        onAdd={(p) =>
          run(async () => {
            await nodesRequest(`/${nodeId}/integration-presets`, 'POST', { preset_id: p.id });
            if (p.kind === 'cli') setCliArgs('["--version"]');
            await load();
          })
        }
      />
      <div className="node-conn-form">
        <input className="paper-input" value={cliArgs} onChange={(e) => setCliArgs(e.target.value)} aria-label="Argumentos CLI (lista JSON)" placeholder='Argumentos CLI: ["--version"]' />
        <input className="paper-input" value={mcpTool} onChange={(e) => setMcpTool(e.target.value)} aria-label="Herramienta MCP" placeholder="Herramienta MCP" />
        <input className="paper-input" value={mcpArgs} onChange={(e) => setMcpArgs(e.target.value)} aria-label="Argumentos MCP (objeto JSON)" placeholder="Argumentos MCP: {}" />
      </div>
      <ul>
        {items.map((c) => (
          <li key={c.id}>
            <b>{c.name}</b>
            <code>{c.command.join(' ')}</code>
            <button type="button" className="mac-chip" disabled={busy || c.policy === 'block'} onClick={() => execute(c)}>
              Revisar y probar
            </button>
            {c.kind === 'mcp' && (
              <button type="button" className="mac-chip" disabled={busy || !mcpTool || c.policy === 'block'} onClick={() => execute(c, true)}>
                Revisar herramienta
              </button>
            )}
            {c.session_mode === 'persistent' && (
              <button type="button" className="mac-chip" disabled={busy} onClick={() => run(async () => (await nodesRequest(`/${nodeId}/integrations/${c.id}/close-session`, 'POST'), setOutput('Sesión cerrada.')))}>
                Cerrar sesión
              </button>
            )}
            <button
              type="button"
              className="mac-chip"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  await nodesRequest(`/${nodeId}/integrations/${c.id}`, 'PATCH', {
                    name: c.name,
                    kind: c.kind,
                    command: c.command,
                    session_mode: c.session_mode ?? 'ephemeral',
                    policy: c.policy === 'block' ? 'confirm' : 'block',
                  });
                  await load();
                })
              }
            >
              {c.policy === 'block' ? 'Habilitar' : 'Bloquear'}
            </button>
            <button type="button" className="mac-chip" disabled={busy} onClick={() => run(async () => (await nodesRequest(`/${nodeId}/integrations/${c.id}`, 'DELETE'), load()))}>
              Revocar
            </button>
          </li>
        ))}
      </ul>
      {output && <pre className="node-path">{output}</pre>}
    </section>
  );
}
