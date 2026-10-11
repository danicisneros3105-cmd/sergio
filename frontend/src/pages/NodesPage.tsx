import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, saveCloudKey } from '../lib/api';
import { nodesRequest, type NodeProfile, type NodeGoal, type NodeMemory, type NodeConnection } from '../lib/nodes-api';
import { NodeAvatar } from '../components/Nodes/NodeAvatar';
import { FoldReveal } from '../components/Nodes/FoldReveal';

interface Capabilities { plan: string; custom_api: boolean; external_requirements: string[]; }
const field = 'rounded-lg border p-2 bg-transparent w-full';
const button = 'rounded-lg border px-3 py-2 hover:bg-black/5 disabled:opacity-40';
const statuses: Record<string, string> = {pending:'pendiente', running:'en ejecución', needs_review:'pendiente de revisión', completed:'completado', failed:'falló', unavailable:'sin registro'};

export function NodesPage() {
  const [nodes, setNodes] = useState<NodeProfile[]>([]);
  const [selected, setSelected] = useState('');
  const [caps, setCaps] = useState<Capabilities>();
  const [goals, setGoals] = useState<NodeGoal[]>([]);
  const [memories, setMemories] = useState<NodeMemory[]>([]);
  const [connections, setConnections] = useState<NodeConnection[]>([]);
  const [events, setEvents] = useState<Array<{action: string; at: number}>>([]);
  const [name, setName] = useState(''); const [role, setRole] = useState('Asistente personal');
  const [colour, setColour] = useState('#b98998'); const [fur, setFur] = useState(.65);
  const [species, setSpecies] = useState<NodeProfile['species']>('lumen');
  const [interval, setIntervalMinutes] = useState(0);
  const [text, setText] = useState(''); const [note, setNote] = useState('');
  const [mcpTool, setMcpTool] = useState(''); const [mcpArgs, setMcpArgs] = useState('{}');
  const [kind, setKind] = useState<'cli' | 'mcp'>('cli'); const [command, setCommand] = useState('["git","--version"]');
  const [keyName, setKeyName] = useState('MOONSHOT_API_KEY'); const [keyValue, setKeyValue] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [output, setOutput] = useState('');
  const activeNode = useRef(selected); activeNode.current = selected;
  const node = nodes.find(n => n.id === selected);
  const run = async (work: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true); setError('');
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : 'La acción falló'); }
    finally { setBusy(false); }
  };
  const refresh = useCallback(async () => {
    const [list, capabilities] = await Promise.all([nodesRequest<{nodes: NodeProfile[]}>(''), nodesRequest<Capabilities>('/capabilities')]);
    setNodes(list.nodes); setCaps(capabilities);
  }, []);
  useEffect(() => { refresh().catch(e => setError(String(e))); }, [refresh]);
  const refreshDetails = useCallback(async () => {
    if (!selected) return;
    const [g, m, c, a] = await Promise.all([
      nodesRequest<{goals: NodeGoal[]}>(`/${selected}/goals`), nodesRequest<{memories: NodeMemory[]}>(`/${selected}/memory`),
      nodesRequest<{connections: NodeConnection[]}>(`/${selected}/connections`), nodesRequest<{events: typeof events}>(`/${selected}/audit`),
    ]);
    if (activeNode.current !== selected) return;
    setGoals(g.goals); setMemories(m.memories); setConnections(c.connections); setEvents(a.events);
  }, [selected]);
  useEffect(() => {
    setGoals([]); setMemories([]); setConnections([]); setEvents([]); setOutput('');
    refreshDetails().catch(e => { if (activeNode.current === selected) setError(String(e)); });
  }, [refreshDetails]);
  useEffect(() => {
    if (!selected) return;
    let live = true;
    const poll = window.setInterval(() => {
      if (document.hidden) return;
      nodesRequest<{goals: NodeGoal[]}>(`/${selected}/goals`).then(g => { if (live && activeNode.current === selected) setGoals(g.goals); }).catch(() => {});
    }, 5000);
    return () => { live = false; window.clearInterval(poll); };
  }, [selected]);
  useEffect(() => {
    if (!node) return;
    setName(node.name); setRole(node.role); setColour(node.colour); setFur(node.fur); setSpecies(node.species); setIntervalMinutes(node.interval_minutes);
  }, [node?.id]);
  const create = () => run(async () => {
    const created = await nodesRequest<NodeProfile>('', 'POST', { name, role, colour, species, fur, interval_minutes: interval });
    await refresh(); setSelected(created.id); setName('');
  });
  const addGoal = (scheduled: boolean) => run(async () => {
    const goal = await nodesRequest<NodeGoal>(`/${selected}/goals`, 'POST', { text, scheduled });
    if (!scheduled) {
      const response = await apiFetch(`/v1/managed-agents/${goal.agent_id}/run`, { method: 'POST' });
      if (!response.ok) throw new Error('El objetivo quedó guardado, pero no pudo arrancar; revísalo en Agent Swarm.');
    }
    setText(''); await refreshDetails(); await refresh();
  });
  const execute = (connection: NodeConnection, call = false) => run(async () => {
    const action = {arguments: [], tool: call ? mcpTool : '', tool_arguments: call ? JSON.parse(mcpArgs) : {}};
    const review = await nodesRequest<{ticket: string; command: string[]}>(`/${selected}/connections/${connection.id}/review`, 'POST', action);
    if (!window.confirm(`Ejecutar en tu equipo:\n${JSON.stringify({...action, command: review.command})}\nPuede usar archivos o la red. ¿Autorizar esta ejecución?`)) return;
    const result = await nodesRequest(`/${selected}/connections/${connection.id}/execute`, 'POST', { ...action, ticket: review.ticket });
    setOutput(JSON.stringify(result, null, 2)); await refreshDetails();
  });
  return <main className="max-w-5xl mx-auto p-6 space-y-6">
    <header><h1 className="text-2xl font-semibold">Nodes</h1><p className="opacity-70">Personajes propios, objetivos y memoria bajo tu control.</p></header>
    {error && <p role="alert" className="text-red-600">{error}</p>}
    <section className="grid gap-3 sm:grid-cols-3" aria-label="Tus Nodes">
      {nodes.map(n => <button key={n.id} onClick={() => setSelected(n.id)} className={`${button} ${selected === n.id ? 'ring-2 ring-current' : ''}`} aria-pressed={selected === n.id}>
        <NodeAvatar colour={n.colour} species={n.species} fur={n.fur} /><div>{n.name}</div><small>{n.role}</small>
      </button>)}
    </section>
    <section className="border rounded-xl p-4 space-y-3"><h2 className="font-semibold">{selected ? 'Diseño y perfil' : 'Crear un Node'}</h2>
      <label className="block">Nombre<input className={field} value={name} maxLength={40} onChange={e => setName(e.target.value)} /></label>
      <label className="block">Responsabilidad<textarea className={field} value={role} maxLength={800} onChange={e => setRole(e.target.value)} /></label>
      <div className="flex flex-wrap gap-4 items-center"><NodeAvatar colour={colour} species={species} fur={fur} />
        <label>Color<input aria-label="Color del personaje" type="color" value={colour} onChange={e => setColour(e.target.value)} /></label>
        <label>Personaje<select className={field} value={species} onChange={e => setSpecies(e.target.value as NodeProfile['species'])}><option value="lumen">Lumen</option><option value="bruma">Bruma</option><option value="nival">Nival</option></select></label>
        <label>Pelaje<input aria-label="Cantidad de pelaje" type="range" min="0" max="1" step=".05" value={fur} onChange={e => setFur(Number(e.target.value))} /></label>
        <label>Intervalo (minutos; 0 = manual)<input className={field} type="number" min="0" max="10080" value={interval} onChange={e => setIntervalMinutes(Number(e.target.value))} /></label>
      </div><button className={button} disabled={busy || !name.trim()} onClick={create}>{selected ? 'Crear otro Node' : 'Crear Node'}</button>
    </section>
    {node && <section className="relative border rounded-xl p-4 space-y-4">
      <FoldReveal colour={node.colour} species={node.species} trigger={node.id} />
      <h2 className="font-semibold">{node.name}</h2><p>{node.role}</p><a href="/agents" className="underline">Canales, trazas y aprendizaje en Agent Swarm</a>
      <button className={button} disabled={busy} onClick={() => run(async () => {
        await nodesRequest(`/${selected}`, 'PATCH', {name: name.trim() || node.name, role, colour, species, fur, interval_minutes: interval}); await refresh();
      })}>Aplicar los ajustes de arriba a este Node</button>
      <p className="text-sm opacity-70">Las tareas automáticas usan herramientas de lectura. Las integraciones locales requieren revisión. El equipo y el servidor deben permanecer encendidos.</p>
      <div className="flex gap-2"><button className={button} disabled={busy} onClick={() => run(refreshDetails)}>Actualizar actividad</button>
        <button className={button} disabled={busy} onClick={() => run(async () => { await nodesRequest(`/${selected}/pause`, 'POST'); await refreshDetails(); })}>Pausar agente</button>
        <button className={button} disabled={busy} onClick={() => run(async () => { await nodesRequest(`/${selected}/resume`, 'POST'); await refreshDetails(); })}>Reanudar</button></div>
      <label className="block">Objetivo<textarea className={field} value={text} maxLength={4000} onChange={e => setText(e.target.value)} /></label>
      <div className="flex gap-2"><button className={button} disabled={busy || !text.trim()} onClick={() => addGoal(false)}>Guardar y ejecutar</button>
        <button className={button} disabled={busy || !text.trim() || node.interval_minutes < 5} onClick={() => addGoal(true)}>Programar</button></div>
      <ul>{goals.map(g => <li key={g.id} className="py-2">{g.text} <small className="opacity-70">— {statuses[g.status] ?? g.status}</small>{g.findings?.map((f, i) => <p key={i} className="whitespace-pre-wrap text-sm">{f.text}<em className="block">Resultado pendiente de revisión</em></p>)}<button className={button} disabled={busy || g.status === 'running'} onClick={() => run(async () => { await nodesRequest(`/${selected}/goals/${g.id}`, 'DELETE'); await refreshDetails(); })}>Eliminar objetivo</button></li>)}</ul>
      <h3 className="font-semibold">Memoria editable</h3>
      <label className="block">Dato que debe recordar<input className={field} value={note} maxLength={4000} onChange={e => setNote(e.target.value)} /></label>
      <button className={button} disabled={busy || !note.trim()} onClick={() => run(async () => { await nodesRequest(`/${selected}/memory`, 'POST', {text: note}); setNote(''); await refreshDetails(); })}>Recordar</button>
      <ul>{memories.map(m => <li key={m.id} className="flex gap-2 py-2"><span>{m.text} <small>({m.source})</small></span>
        <button className={button} disabled={busy} onClick={() => run(async () => { await nodesRequest(`/${selected}/memory/${m.id}`, 'DELETE'); await refreshDetails(); })}>Olvidar</button></li>)}</ul>
      <h3 className="font-semibold">Conectar MCP o CLI</h3>
      <p className="text-sm opacity-70">Agrega un programa ya instalado. MCP descubre herramientas y permite llamar una herramienta tras revisar sus argumentos. No escribas claves en los comandos.</p>
      <label>Tipo<select className={field} value={kind} onChange={e => setKind(e.target.value as 'cli' | 'mcp')}><option value="cli">CLI</option><option value="mcp">MCP stdio</option></select></label>
      <label className="block">Comando como lista JSON<input className={field} value={command} onChange={e => setCommand(e.target.value)} /></label>
      <button className={button} disabled={busy} onClick={() => run(async () => { await nodesRequest(`/${selected}/connections`, 'POST', {name: `${kind.toUpperCase()} ${connections.length + 1}`, kind, command: JSON.parse(command)}); await refreshDetails(); })}>Agregar conexión</button>
      <label className="block">Herramienta MCP (nombre de la lista descubierta)<input className={field} value={mcpTool} onChange={e => setMcpTool(e.target.value)} /></label>
      <label className="block">Argumentos MCP como objeto JSON<input className={field} value={mcpArgs} onChange={e => setMcpArgs(e.target.value)} /></label>
      <ul>{connections.map(c => <li key={c.id} className="py-2 flex gap-2 items-center"><span>{c.name} ({c.policy}): {JSON.stringify(c.command)}</span><button className={button} onClick={() => execute(c)} disabled={busy || c.policy === 'block'}>Revisar y probar</button>{c.kind === 'mcp' && <button className={button} disabled={busy || !mcpTool || c.policy === 'block'} onClick={() => execute(c, true)}>Revisar herramienta</button>}
        <button className={button} disabled={busy} onClick={() => run(async () => { await nodesRequest(`/${selected}/connections/${c.id}`, 'PATCH', {name:c.name,kind:c.kind,command:c.command,policy:c.policy === 'block' ? 'confirm' : 'block'}); await refreshDetails(); })}>{c.policy === 'block' ? 'Habilitar con revisión' : 'Bloquear'}</button>
        <button className={button} disabled={busy} onClick={() => run(async () => { await nodesRequest(`/${selected}/connections/${c.id}`, 'DELETE'); await refreshDetails(); })}>Revocar</button></li>)}</ul>
      {output && <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-sm">{output}</pre>}
      <details><summary>Auditoría</summary><ul>{events.map((e, i) => <li key={i}>{new Date(e.at * 1000).toLocaleString()} — {e.action}</li>)}</ul></details>
    </section>}
    <section className="border rounded-xl p-4 space-y-3"><h2 className="font-semibold">API propia · Dev y superiores</h2>
      <p>Plan actual: {caps?.plan ?? 'comprobando'}</p>
      <label>Proveedor<select className={field} value={keyName} onChange={e => setKeyName(e.target.value)} disabled={!caps?.custom_api}>
        {['MOONSHOT_API_KEY', 'GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY', 'MINIMAX_API_KEY', 'ATLASCLOUD_API_KEY'].map(k => <option key={k}>{k}</option>)}</select></label>
      <label className="block">Clave<input className={field} type="password" autoComplete="off" value={keyValue} onChange={e => setKeyValue(e.target.value)} disabled={!caps?.custom_api} /></label>
      <button className={button} disabled={busy || !caps?.custom_api || !keyValue} onClick={() => run(async () => { await saveCloudKey(keyName, keyValue); setKeyValue(''); setOutput('Clave guardada.'); })}>Guardar API</button>
    </section>
    <details className="text-sm opacity-70"><summary>Capacidades que requieren servicios externos</summary><ul>{caps?.external_requirements.map(c => <li key={c}>{c}</li>)}</ul></details>
  </main>;
}
