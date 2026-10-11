import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { ArrowLeft, Paperclip, Plus, SendHorizontal, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { PaperHead } from '../components/Paper/PaperPage';
import { apiFetch, createManagedAgent, fetchManagedAgent, updateManagedAgent } from '../lib/api';
import { useAppStore } from '../lib/store';
import {
  builderMessages,
  CAPABILITIES,
  COLORS,
  emptyDraft,
  fromAgent,
  initial,
  KNOWLEDGE_TYPES,
  knowledgeChars,
  MAX_KNOWLEDGE_CHARS,
  MAX_STARTERS,
  parseBuilderReply,
  problems,
  systemPrompt,
  toConfig,
  type AgentDraft,
  type BuilderTurn,
  type Capability,
  type KnowledgeFile,
} from '../lib/agentBuilder';

async function complete(model: string, messages: Array<{ role: string; content: string }>): Promise<string> {
  const r = await apiFetch('/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages, stream: false, temperature: 0.4 }),
  });
  if (!r.ok) throw new Error(`Sergio no respondió (HTTP ${r.status}).`);
  const data = await r.json();
  return String(data?.choices?.[0]?.message?.content || '').trim();
}

function Avatar({ draft, size = 56 }: { draft: AgentDraft; size?: number }) {
  return (
    <span
      className="agent-avatar"
      data-empty={!draft.name.trim() && !draft.icon.trim()}
      style={{ width: size, height: size, fontSize: size * 0.42, backgroundColor: draft.color }}
      aria-hidden="true"
    >
      {!draft.name.trim() && !draft.icon.trim() ? <Plus size={size * 0.34} strokeWidth={1.2} /> : initial(draft)}
    </span>
  );
}

function Thread({ turns, busy }: { turns: BuilderTurn[]; busy: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: 'end' }), [turns.length, busy]);
  return (
    <div className="agent-thread">
      {turns.map((t, i) => (
        <p key={i} className={t.role === 'user' ? 'agent-msg mine' : 'agent-msg'}>
          {t.content}
        </p>
      ))}
      {busy && <p className="agent-msg agent-typing">Pensando…</p>}
      <div ref={end} />
    </div>
  );
}

function Composer({ placeholder, onSend, busy }: { placeholder: string; onSend: (t: string) => void; busy: boolean }) {
  const [text, setText] = useState('');
  const send = () => {
    const t = text.trim();
    if (!t || busy) return;
    setText('');
    onSend(t);
  };
  return (
    <div className="agent-composer">
      <textarea
        value={text}
        rows={1}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
          }
        }}
        aria-label={placeholder}
      />
      <button type="button" className="mac-icon-btn" onClick={send} disabled={busy || !text.trim()} aria-label="Enviar">
        <SendHorizontal size={16} strokeWidth={1.4} />
      </button>
    </div>
  );
}

// Crear agente: like making a custom GPT. On the left «Crear» (describe it
// in a conversation) or «Configurar» (every field); on the right a live
// preview to talk to it before saving.
export function AgentBuilderPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const selectedModel = useAppStore((s) => s.selectedModel);
  const models = useAppStore((s) => s.models);
  const [draft, setDraft] = useState<AgentDraft>(() => emptyDraft(selectedModel));
  const [mode, setMode] = useState<'create' | 'configure'>('create');
  const [builder, setBuilder] = useState<BuilderTurn[]>([
    { role: 'assistant', content: 'Hola. Cuénteme qué agente quiere: para qué sirve, cómo debe hablar y qué no debe hacer. Yo voy rellenando la configuración.' },
  ]);
  const [preview, setPreview] = useState<BuilderTurn[]>([]);
  const [busy, setBusy] = useState<'' | 'builder' | 'preview' | 'save'>('');
  const [loaded, setLoaded] = useState(!id);
  const fileInput = useRef<HTMLInputElement>(null);
  const stored = useRef<Record<string, unknown>>({}); // keep what the builder does not edit (schedule, budget…)

  useEffect(() => {
    if (!id) return;
    fetchManagedAgent(id)
      .then((a) => {
        stored.current = (a.config || {}) as Record<string, unknown>;
        setDraft(fromAgent(a));
        setMode('configure');
      })
      .catch(() => toast.error('No encuentro ese agente.'))
      .finally(() => setLoaded(true));
  }, [id]);

  const set = (patch: Partial<AgentDraft>) => setDraft((d) => ({ ...d, ...patch }));
  const model = draft.model || selectedModel;

  const askBuilder = async (text: string) => {
    const turns: BuilderTurn[] = [...builder, { role: 'user', content: text }];
    setBuilder(turns);
    setBusy('builder');
    try {
      const reply = await complete(model, builderMessages(turns.slice(1), draft));
      const { say, patch } = parseBuilderReply(reply);
      setDraft((d) => ({ ...d, ...patch }));
      setBuilder([...turns, { role: 'assistant', content: say || 'Actualizado.' }]);
    } catch (e) {
      setBuilder([...turns, { role: 'assistant', content: e instanceof Error ? e.message : 'No pude responder.' }]);
    } finally {
      setBusy('');
    }
  };

  const askPreview = async (text: string) => {
    const turns: BuilderTurn[] = [...preview, { role: 'user', content: text }];
    setPreview(turns);
    setBusy('preview');
    try {
      const reply = await complete(model, [{ role: 'system', content: systemPrompt(draft) }, ...turns]);
      setPreview([...turns, { role: 'assistant', content: reply || '…' }]);
    } catch (e) {
      setPreview([...turns, { role: 'assistant', content: e instanceof Error ? e.message : 'No pude responder.' }]);
    } finally {
      setBusy('');
    }
  };

  const addFiles = async (files: FileList | null) => {
    if (!files) return;
    const added: KnowledgeFile[] = [];
    for (const f of Array.from(files)) {
      const ok = KNOWLEDGE_TYPES.some((ext) => f.name.toLowerCase().endsWith(ext));
      if (!ok) {
        toast.error(`«${f.name}»: por ahora solo texto (${KNOWLEDGE_TYPES.join(' ')}).`);
        continue;
      }
      added.push({ name: f.name, text: await f.text() });
    }
    if (added.length) setDraft((d) => ({ ...d, knowledge: [...d.knowledge, ...added] }));
  };

  const save = async () => {
    const issues = problems(draft).filter((p) => !p.startsWith('El conocimiento'));
    if (issues.length) {
      toast.error(issues.join(' '));
      setMode('configure');
      return;
    }
    setBusy('save');
    try {
      const config = { ...stored.current, ...toConfig({ ...draft, model }) };
      const saved = id
        ? await updateManagedAgent(id, { name: draft.name.trim(), config })
        : await createManagedAgent({ name: draft.name.trim(), agent_type: 'orchestrator', config });
      toast.success(id ? 'Agente actualizado.' : 'Agente creado.');
      useAppStore.getState().setSelectedAgentId(saved.id);
      navigate('/agents');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude guardar.');
    } finally {
      setBusy('');
    }
  };

  const toggleCap = (key: Capability) =>
    set({ capabilities: draft.capabilities.includes(key) ? draft.capabilities.filter((c) => c !== key) : [...draft.capabilities, key] });

  const used = knowledgeChars(draft);

  return (
    <div className="paper-page">
      <div className="paper-page-inner" style={{ maxWidth: 1120 }}>
        <PaperHead
          title={id ? 'Editar agente' : 'Crear agente'}
          left={
            <button type="button" className="mac-icon-btn" aria-label="Volver a los agentes" onClick={() => navigate('/agents')}>
              <ArrowLeft size={17} strokeWidth={1.3} />
            </button>
          }
          right={
            <button type="button" className="paper-button" onClick={save} disabled={busy === 'save' || !loaded}>
              {busy === 'save' ? 'Guardando…' : id ? 'Actualizar' : 'Crear'}
            </button>
          }
        />

        <div className="agent-builder">
          <section className="agent-pane" aria-label="Definir el agente">
            <div className="paper-tabs agent-modes" role="tablist">
              {(['create', 'configure'] as const).map((m) => (
                <button key={m} type="button" role="tab" className="paper-tab" aria-selected={mode === m} onClick={() => setMode(m)}>
                  {m === 'create' ? 'Crear' : 'Configurar'}
                </button>
              ))}
            </div>

            {mode === 'create' ? (
              <div className="agent-chat">
                <Thread turns={builder} busy={busy === 'builder'} />
                <Composer placeholder="Describa su agente…" onSend={askBuilder} busy={!!busy} />
              </div>
            ) : (
              <div className="agent-form">
                <div className="agent-identity">
                  <Avatar draft={draft} size={64} />
                  <div className="agent-swatches" role="radiogroup" aria-label="Color">
                    {COLORS.map((c) => (
                      <button
                        key={c}
                        type="button"
                        role="radio"
                        aria-checked={draft.color === c}
                        aria-label={`Color ${c}`}
                        className="agent-swatch"
                        style={{ background: c }}
                        onClick={() => set({ color: c })}
                      />
                    ))}
                    <input
                      className="paper-input agent-emoji"
                      value={draft.icon}
                      maxLength={4}
                      placeholder="Emoji"
                      aria-label="Emoji o letra"
                      onChange={(e) => set({ icon: e.target.value })}
                    />
                  </div>
                </div>

                <label className="agent-field">
                  <span className="paper-label">Nombre</span>
                  <input className="paper-input" value={draft.name} placeholder="Ej. Chef de la nevera" onChange={(e) => set({ name: e.target.value })} />
                </label>
                <label className="agent-field">
                  <span className="paper-label">Descripción</span>
                  <input
                    className="paper-input"
                    value={draft.description}
                    placeholder="Una línea: qué hace"
                    onChange={(e) => set({ description: e.target.value })}
                  />
                </label>
                <label className="agent-field">
                  <span className="paper-label">Instrucciones</span>
                  <textarea
                    className="paper-input"
                    rows={7}
                    value={draft.instructions}
                    placeholder="Qué hace, cómo habla, qué evita. Ej.: «Propón tres recetas con lo que te diga, pregunta por alergias, nunca más de 30 minutos.»"
                    onChange={(e) => set({ instructions: e.target.value })}
                  />
                </label>

                <div className="agent-field">
                  <span className="paper-label">Frases de inicio</span>
                  {draft.starters.map((s, i) => (
                    <div key={i} className="agent-row">
                      <input
                        className="paper-input"
                        value={s}
                        aria-label={`Frase de inicio ${i + 1}`}
                        onChange={(e) => set({ starters: draft.starters.map((x, j) => (j === i ? e.target.value : x)) })}
                      />
                      <button
                        type="button"
                        className="mac-icon-btn"
                        aria-label="Quitar"
                        onClick={() => set({ starters: draft.starters.filter((_, j) => j !== i) })}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                  {draft.starters.length < MAX_STARTERS && (
                    <button type="button" className="agent-add" onClick={() => set({ starters: [...draft.starters, ''] })}>
                      <Plus size={13} /> Añadir frase
                    </button>
                  )}
                </div>

                <div className="agent-field">
                  <span className="paper-label">Conocimiento</span>
                  <p className="agent-hint">
                    Archivos de texto que el agente usa como fuente ({Math.round(used / 1000)} de {MAX_KNOWLEDGE_CHARS / 1000} mil caracteres).
                  </p>
                  {draft.knowledge.map((k, i) => (
                    <div key={`${k.name}-${i}`} className="agent-file">
                      <Paperclip size={13} strokeWidth={1.4} />
                      <span className="truncate">{k.name}</span>
                      <button
                        type="button"
                        className="mac-icon-btn"
                        aria-label={`Quitar ${k.name}`}
                        onClick={() => set({ knowledge: draft.knowledge.filter((_, j) => j !== i) })}
                      >
                        <Trash2 size={13} strokeWidth={1.4} />
                      </button>
                    </div>
                  ))}
                  <input
                    ref={fileInput}
                    type="file"
                    multiple
                    hidden
                    accept={KNOWLEDGE_TYPES.join(',')}
                    onChange={(e) => {
                      void addFiles(e.target.files);
                      e.target.value = '';
                    }}
                  />
                  <button type="button" className="agent-add" onClick={() => fileInput.current?.click()}>
                    <Plus size={13} /> Subir archivos
                  </button>
                </div>

                <div className="agent-field">
                  <span className="paper-label">Capacidades</span>
                  <div className="agent-caps">
                    {CAPABILITIES.map((c) => (
                      <label key={c.key} className="agent-cap">
                        <input type="checkbox" checked={draft.capabilities.includes(c.key)} onChange={() => toggleCap(c.key)} />
                        <span>
                          <span className="block">{c.label}</span>
                          <span className="agent-hint">{c.hint}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {models.length > 0 && (
                  <label className="agent-field">
                    <span className="paper-label">Modelo</span>
                    <select className="paper-input" value={model} onChange={(e) => set({ model: e.target.value })}>
                      {models.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.id}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            )}
          </section>

          <section className="agent-pane agent-preview" aria-label="Vista previa">
            <span className="paper-label">Vista previa</span>
            {preview.length === 0 ? (
              <div className="agent-cover">
                <Avatar draft={draft} size={72} />
                <h2 className="agent-name">{draft.name.trim() || 'Su agente'}</h2>
                <p className="agent-hint text-center">{draft.description.trim() || 'Aquí aparecerá la descripción.'}</p>
                <div className="agent-starters">
                  {draft.starters
                    .map((s) => s.trim())
                    .filter(Boolean)
                    .map((s) => (
                      <button key={s} type="button" onClick={() => void askPreview(s)} disabled={!!busy}>
                        {s}
                      </button>
                    ))}
                </div>
              </div>
            ) : (
              <Thread turns={preview} busy={busy === 'preview'} />
            )}
            <div className="agent-preview-foot">
              {preview.length > 0 && (
                <button type="button" className="agent-add" onClick={() => setPreview([])}>
                  Empezar de nuevo
                </button>
              )}
              <Composer placeholder={`Hable con ${draft.name.trim() || 'su agente'}…`} onSend={askPreview} busy={!!busy} />
              <p className="agent-hint">La vista previa no usa herramientas; el agente guardado sí.</p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default AgentBuilderPage;
