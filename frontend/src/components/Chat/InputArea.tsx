import { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { ArrowUp, CircleDot, MonitorSmartphone, Network, Plus, Search, Square, X } from 'lucide-react';
import { toast } from 'sonner';
import { useAppStore, generateId } from '../../lib/store';
import { streamChat, streamResearch } from '../../lib/sse';
import { fetchSavings, getBase } from '../../lib/api';
import { listConnectors, getSyncStatus } from '../../lib/connectors-api';
import { serializeToolCallArguments } from '../../lib/tool-call';
import {
  findAnswer,
  isNetworkError,
  isOffline,
  offlineReply,
  rememberAnswer,
} from '../../lib/offline';
import {
  engineFromCompletionChunk,
  resolveChatEngine,
} from '../../lib/chat-telemetry';

import { LiveOrb } from '../Live/LiveOrb';
import { useLive } from '../../lib/liveSession';
import { useOnline } from '../../hooks/useOnline';
import type {
  ChatMessage,
  MessageTelemetry,
  ResearchSearchTrace,
  ResearchSource,
  TokenUsage,
  ToolCallInfo,
} from '../../types';

// While Deep Research is toggled on, poll connected sources for sync
// progress so we can surface "Searching over N items — sync in progress"
// next to the toggle. Polling is gated on `enabled` so toggling DR off
// stops the network chatter immediately.
function useResearchCorpusSync(enabled: boolean): {
  syncing: boolean;
  itemsSynced: number;
} {
  const [state, setState] = useState({ syncing: false, itemsSynced: 0 });

  useEffect(() => {
    if (!enabled) {
      setState({ syncing: false, itemsSynced: 0 });
      return;
    }
    let cancelled = false;

    const poll = async () => {
      try {
        const list = await listConnectors();
        const connected = list.filter((c) => c.connected);
        if (connected.length === 0) {
          if (!cancelled) setState({ syncing: false, itemsSynced: 0 });
          return;
        }
        const results = await Promise.all(
          connected.map(async (c) => {
            try {
              return await getSyncStatus(c.connector_id);
            } catch {
              return null;
            }
          }),
        );
        let syncing = false;
        let itemsSynced = 0;
        for (const r of results) {
          if (!r) continue;
          if (r.state === 'syncing') syncing = true;
          itemsSynced += r.items_synced ?? 0;
        }
        if (!cancelled) setState({ syncing, itemsSynced });
      } catch {
        // Network blip — leave previous state intact.
      }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled]);

  return state;
}

export function InputArea() {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const activeId = useAppStore((s) => s.activeId);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const streamState = useAppStore((s) => s.streamState);
  const messages = useAppStore((s) => s.messages);
  const maxTokens = useAppStore((s) => s.settings.maxTokens);
  const temperature = useAppStore((s) => s.settings.temperature);
  const createConversation = useAppStore((s) => s.createConversation);
  const addMessage = useAppStore((s) => s.addMessage);
  const updateLastAssistant = useAppStore((s) => s.updateLastAssistant);
  const setStreamState = useAppStore((s) => s.setStreamState);
  const resetStream = useAppStore((s) => s.resetStream);
  const modelLoading = useAppStore((s) => s.modelLoading);
  const deepResearch = useAppStore((s) => s.deepResearch);
  const setDeepResearch = useAppStore((s) => s.setDeepResearch);
  const corpusSync = useResearchCorpusSync(deepResearch);
  const isCurrentChatStreaming = streamState.isStreaming && streamState.conversationId === activeId;

  // Abort in-flight stream when the user switches models mid-generation.
  // This prevents errors from trying to continue a stream with a stale model.
  const prevModelRef = useRef(selectedModel);
  useEffect(() => {
    if (prevModelRef.current !== selectedModel && streamState.isStreaming) {
      abortRef.current?.abort();
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      resetStream();
      abortRef.current = null;
    }
    prevModelRef.current = selectedModel;
  }, [selectedModel, streamState.isStreaming, resetStream]);

  // Welcome-screen suggestions fill the composer (see ChatArea).
  useEffect(() => {
    const onPrefill = (e: Event) => {
      const text = (e as CustomEvent<string>).detail;
      if (typeof text !== 'string') return;
      setInput(text);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.focus();
        el.setSelectionRange(text.length, text.length);
      });
    };
    window.addEventListener('sergio:prefill', onPrefill);
    return () => window.removeEventListener('sergio:prefill', onPrefill);
  }, []);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, [input]);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    resetStream();
  }, [resetStream]);

  const sendMessage = useCallback(async () => {
    const content = input.trim();
    if (!content || streamState.isStreaming) return;
    if (!selectedModel) {
      toast.error('Elija un modelo en Ajustes (Ctrl K) y vuelva a enviar.');
      return;
    }

    // The answer this question follows: part of the offline cache key.
    const previousAnswer = activeId
      ? [...useAppStore.getState().messages].reverse().find((m) => m.role === 'assistant')?.content ?? ''
      : '';
    const saved = isOffline() ? await findAnswer(content, { previousAnswer }) : null;
    if (isOffline() && !saved) {
      toast.error('Sin conexión. Su mensaje sigue en la caja: envíelo cuando vuelva la red.');
      return;
    }

    setInput('');

    let convId = activeId;
    if (!convId) {
      convId = createConversation(selectedModel);
    }

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: Date.now(),
    };
    addMessage(convId, userMsg);

    if (saved) {
      addMessage(convId, {
        id: generateId(),
        role: 'assistant',
        content: offlineReply(saved),
        timestamp: Date.now(),
      });
      return;
    }

    // Build API messages before adding assistant placeholder
    const currentMessages = useAppStore.getState().messages;
    const apiMessages = currentMessages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const assistantMsg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      isResearch: deepResearch || undefined,
    };
    addMessage(convId, assistantMsg);

    // Start streaming
    const startTime = Date.now();
    const timer = setInterval(() => {
      setStreamState({ elapsedMs: Date.now() - startTime });
    }, 100);
    timerRef.current = timer;

    const controller = new AbortController();
    abortRef.current = controller;

    let accumulatedContent = '';
    let usage: TokenUsage | undefined;
    let complexity: { score: number; tier: string; suggested_max_tokens: number } | undefined;
    let routedEngine: string | undefined;
    const toolCalls: ToolCallInfo[] = [];
    const researchTraces: ResearchSearchTrace[] = [];
    const researchSourcesByRef = new Map<number, ResearchSource>();
    const flushSources = () =>
      Array.from(researchSourcesByRef.values()).sort((a, b) => a.ref - b.ref);
    let lastFlush = 0;
    let ttftMs: number | undefined;
    let answeredOk = false;

    setStreamState({
      conversationId: convId,
      isStreaming: true,
      phase: deepResearch ? 'Investigando…' : 'Escribiendo…',
      elapsedMs: 0,
      activeToolCalls: [],
      content: '',
    });
    useAppStore.getState().addLogEntry({
      timestamp: Date.now(),
      level: 'info',
      category: 'chat',
      message: deepResearch
        ? `Research: "${content.slice(0, 80)}${content.length > 80 ? '...' : ''}"`
        : `Request: "${content.slice(0, 80)}${content.length > 80 ? '...' : ''}" → ${selectedModel}`,
    });

    try {
      if (deepResearch) {
        for await (const ev of streamResearch(
          content,
          selectedModel,
          controller.signal,
        )) {
          if (ev.type === 'search_call') {
            const trace: ResearchSearchTrace = {
              id: generateId(),
              query: ev.arguments?.query ?? '',
              person: ev.arguments?.person,
              timeRange: ev.arguments?.time_range,
              status: 'pending',
            };
            researchTraces.push(trace);
            setStreamState({ phase: `Searching: ${trace.query}` });
            updateLastAssistant(
              convId,
              accumulatedContent,
              undefined,
              undefined,
              undefined,
              undefined,
              [...researchTraces],
              flushSources(),
            );
            useAppStore.getState().addLogEntry({
              timestamp: Date.now(),
              level: 'info',
              category: 'tool',
              message: `Search: "${trace.query}"${trace.person ? ` (person: ${trace.person})` : ''}`,
            });
          } else if (ev.type === 'search_result') {
            const pending = [...researchTraces].reverse().find((t) => t.status === 'pending');
            if (pending) {
              pending.status = 'complete';
              pending.numHits = ev.num_hits;
              pending.topTitles = ev.top_titles;
            }
            if (ev.sources) {
              for (const src of ev.sources) {
                if (src && typeof src.ref === 'number' && !researchSourcesByRef.has(src.ref)) {
                  researchSourcesByRef.set(src.ref, src);
                }
              }
            }
            updateLastAssistant(
              convId,
              accumulatedContent,
              undefined,
              undefined,
              undefined,
              undefined,
              [...researchTraces],
              flushSources(),
            );
          } else if (ev.type === 'synthesis') {
            if (!ttftMs) ttftMs = Date.now() - startTime;
            accumulatedContent += ev.text;
            setStreamState({ content: accumulatedContent, phase: '' });
            const now = Date.now();
            if (now - lastFlush >= 80) {
              updateLastAssistant(
                convId,
                accumulatedContent,
                undefined,
                undefined,
                undefined,
                undefined,
                [...researchTraces],
                flushSources(),
              );
              lastFlush = now;
            }
          } else if (ev.type === 'system_metrics') {
            // Live GPU sample — feed straight to the System panel so Power
            // (W) and Energy (kJ) tick up in real time as the agent runs.
            useAppStore.getState().setLiveEnergy({
              power_w: ev.power_w,
              energy_j: ev.energy_j,
              duration_s: ev.duration_s,
            });
          } else if (ev.type === 'error') {
            // Backend setup/worker failure (Ollama down, planner model
            // missing, KnowledgeStore locked, etc.). Without surfacing the
            // message, the user sees only the generic "No response was
            // generated" fallback and has no way to self-diagnose.
            const msg = ev.message || 'Research failed (no detail provided)';
            accumulatedContent = accumulatedContent
              ? `${accumulatedContent}\n\n**Research stopped:** ${msg}`
              : `**Research failed:** ${msg}`;
            setStreamState({ content: accumulatedContent, phase: '' });
            useAppStore.getState().addLogEntry({
              timestamp: Date.now(),
              level: 'error',
              category: 'chat',
              message: `Deep Research error: ${msg}`,
            });
            toast.error(msg, { duration: 8000 });
          } else if (ev.type === 'done') {
            if (ev.usage) {
              usage = {
                prompt_tokens: ev.usage.prompt_tokens ?? 0,
                completion_tokens: ev.usage.completion_tokens ?? 0,
                total_tokens:
                  ev.usage.total_tokens ??
                  (ev.usage.prompt_tokens ?? 0) +
                    (ev.usage.completion_tokens ?? 0),
              };
              // Optimistically roll this research turn into the session
              // counters so the Session panel updates the moment the
              // stream finishes, regardless of how /v1/savings aggregates
              // research telemetry server-side.
              useAppStore.getState().incrementSavings(usage);
            }
            // Hold the final live numbers visible for a beat so the panel
            // doesn't flash to 0 between the SSE close and the next
            // /v1/telemetry/energy poll picking up the persisted record.
            window.setTimeout(() => {
              useAppStore.getState().setLiveEnergy(null);
            }, 1500);
            break;
          }
        }
      } else {
      for await (const sseEvent of streamChat(
        { model: selectedModel, messages: apiMessages, stream: true, temperature, max_tokens: maxTokens },
        controller.signal,
      )) {
        const eventName = sseEvent.event;

        if (eventName === 'agent_turn_start') {
          setStreamState({ phase: 'Pensando…' });
        } else if (eventName === 'inference_start') {
          setStreamState({ phase: 'Escribiendo…' });
          useAppStore.getState().addLogEntry({
            timestamp: Date.now(), level: 'info', category: 'chat',
            message: `Generating with ${selectedModel}...`,
          });
        } else if (eventName === 'tool_call_start') {
          try {
            const data = JSON.parse(sseEvent.data);
            const tc: ToolCallInfo = {
              id: generateId(),
              tool: data.tool,
              arguments: serializeToolCallArguments(data.arguments),
              status: 'running',
            };
            toolCalls.push(tc);
            setStreamState({
              phase: `Usando ${data.tool}…`,
              activeToolCalls: [...toolCalls],
            });
            updateLastAssistant(convId, accumulatedContent, [...toolCalls]);
            useAppStore.getState().addLogEntry({
              timestamp: Date.now(), level: 'info', category: 'tool',
              message: `Calling ${data.tool}(${serializeToolCallArguments(data.arguments)})`,
            });
          } catch {}
        } else if (eventName === 'tool_call_end') {
          try {
            const data = JSON.parse(sseEvent.data);
            const tc = toolCalls.find(
              (t) => t.tool === data.tool && t.status === 'running',
            );
            if (tc) {
              tc.status = data.success ? 'success' : 'error';
              tc.latency = data.latency;
              tc.result = data.result;
            }
            const rawRes = typeof data.result === 'string' ? data.result : '';
            // Execute live UI actions emitted by sergio_app
            const uiMatch = rawRes.match(/<!--SERGIO_UI:(\{.*?\})-->/);
            if (uiMatch?.[1]) {
              try {
                const uiAction = JSON.parse(uiMatch[1]);
                if (uiAction.type === 'navigate' && typeof uiAction.route === 'string') {
                  window.dispatchEvent(new CustomEvent('sergio:navigate', { detail: uiAction.route }));
                } else if (uiAction.type === 'sticky_notes_refresh') {
                  window.dispatchEvent(new CustomEvent('sergio:sticky-notes'));
                } else if (uiAction.type === 'health_refresh') {
                  window.dispatchEvent(new CustomEvent('sergio:health-refresh'));
                }
              } catch {}
            }
            // If a tool generated an inline Creator image ![...](/v1/creator/media/...), ensure it shows in chat
            const imgMatch = rawRes.match(/!\[[^\]]*\]\(\/v1\/creator\/media\/[^)]+\)/);
            if (imgMatch?.[0] && !accumulatedContent.includes(imgMatch[0])) {
              accumulatedContent += (accumulatedContent ? '\n\n' : '') + imgMatch[0] + '\n\n';
            }
            setStreamState({
              phase: 'Escribiendo…',
              activeToolCalls: [...toolCalls],
            });
            updateLastAssistant(convId, accumulatedContent, [...toolCalls]);
          } catch {}
        } else {
          try {
            const data = JSON.parse(sseEvent.data);
            const delta = data.choices?.[0]?.delta;
            if (data.usage) usage = data.usage;
            if (data.complexity) complexity = data.complexity;
            routedEngine = engineFromCompletionChunk(data) ?? routedEngine;
            if (delta?.content) {
              if (!ttftMs) ttftMs = Date.now() - startTime;
              accumulatedContent += delta.content;
              setStreamState({ content: accumulatedContent, phase: '' });

              const now = Date.now();
              if (now - lastFlush >= 80) {
                updateLastAssistant(
                  convId,
                  accumulatedContent,
                  toolCalls.length > 0 ? [...toolCalls] : undefined,
                );
                lastFlush = now;
              }
            }
            if (data.choices?.[0]?.finish_reason === 'stop') break;
          } catch {}
        }
      }
      answeredOk = !!accumulatedContent;
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // User cancelled or model switch — keep whatever was accumulated
        if (!accumulatedContent) accumulatedContent = '(Respuesta detenida)';
      } else if (isNetworkError(err) && !accumulatedContent) {
        const cached = await findAnswer(content, { previousAnswer });
        if (cached) {
          accumulatedContent = offlineReply(cached);
        } else {
          accumulatedContent = 'Sin conexión con Sergio. Revise la red y vuelva a enviar el mensaje.';
          setInput(content);
        }
      } else {
        const errMsg = err?.message || String(err);
        accumulatedContent =
          accumulatedContent || `Error: ${errMsg}`;
        useAppStore.getState().addLogEntry({
          timestamp: Date.now(), level: 'error', category: 'chat',
          message: `Stream error: ${errMsg}`,
        });
      }
      // If we tore out mid-research, make sure the live System panel
      // numbers don't get stuck on the last sample.
      useAppStore.getState().setLiveEnergy(null);
    } finally {
      if (!accumulatedContent) {
        accumulatedContent = 'No llegó ninguna respuesta. Inténtalo otra vez.';
      }
      const totalMs = Date.now() - startTime;
      const appState = useAppStore.getState();
      const selectedOwner = appState.models.find((m) => m.id === selectedModel)?.owned_by;
      const engineLabel = resolveChatEngine({
        routedEngine,
        serverEngine: appState.serverInfo?.engine,
        selectedModel,
        selectedOwner,
      });
      const telemetry: MessageTelemetry = {
        engine: engineLabel,
        model_id: selectedModel,
        total_ms: totalMs,
        ttft_ms: ttftMs,
        tokens_per_sec: usage?.completion_tokens
          ? usage.completion_tokens / (totalMs / 1000)
          : undefined,
        complexity_score: complexity?.score,
        complexity_tier: complexity?.tier,
        suggested_max_tokens: complexity?.suggested_max_tokens,
      };
      // Check if the response has digest audio available
      let audioMeta: { url: string } | undefined;
      // Only a morning-digest answer can carry audio; asking on every reply 404s.
      if (toolCalls.some((t) => /digest/i.test(t.tool))) {
        try {
          const digestRes = await fetch(`${getBase()}/api/digest`);
          if (digestRes.ok) {
            const digest = await digestRes.json();
            if (digest.audio_available) {
              audioMeta = { url: `${getBase()}/api/digest/audio` };
            }
          }
        } catch {
          // Server unavailable — skip the audio
        }
      }

      // The voice shares this context: what was written is known out loud too.
      useLive.getState().note(
        `(En el chat escrito el señor dijo: «${content.slice(0, 600)}». Respondiste: «${accumulatedContent.slice(0, 900)}».)`,
      );

      updateLastAssistant(
        convId,
        accumulatedContent,
        toolCalls.length > 0 ? toolCalls : undefined,
        usage,
        telemetry,
        audioMeta,
        researchTraces.length > 0 ? researchTraces : undefined,
        researchSourcesByRef.size > 0 ? flushSources() : undefined,
      );
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      resetStream();
      useAppStore.getState().addLogEntry({
        timestamp: Date.now(), level: 'info', category: 'chat',
        message: `Response: ${accumulatedContent.length} chars`,
      });
      abortRef.current = null;
      if (answeredOk) {
        void rememberAnswer(content, accumulatedContent, { previousAnswer, model: selectedModel });
      }

      // Research path updates session counters optimistically from the
      // `done` event's usage payload — re-fetching here would overwrite
      // it with a potentially stale snapshot if the server's research
      // telemetry hasn't been merged into /v1/savings yet.
      if (!deepResearch) {
        fetchSavings()
          .then((data) => useAppStore.getState().setSavings(data))
          .catch(() => {});
      }
    }
  }, [
    input,
    activeId,
    selectedModel,
    streamState.isStreaming,
    createConversation,
    addMessage,
    updateLastAssistant,
    setStreamState,
    resetStream,
    deepResearch,
    temperature,
    maxTokens,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const isWelcome = messages.length === 0 && !isCurrentChatStreaming;
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [menuOpen]);
  const TOOLS = [
    {
      icon: Search,
      label: 'Investigación a fondo',
      hint: 'Varias fuentes, con citas',
      run: () => setDeepResearch(!deepResearch),
      on: deepResearch,
    },
    {
      icon: Network,
      label: 'Agent Swarm',
      hint: 'Muchos agentes a la vez para algo enorme',
      run: () => navigate(input.trim() ? `/swarm?tarea=${encodeURIComponent(input.trim())}` : '/swarm'),
    },
    {
      icon: CircleDot,
      label: 'Encargárselo a un Node',
      hint: 'Un empleado digital que sigue trabajando',
      run: () => navigate('/nodes?nuevo=1'),
    },
    {
      icon: MonitorSmartphone,
      label: 'Usar mi pantalla',
      hint: 'Lo hace en su PC, a la vista',
      run: () => setInput(input.startsWith('En mi pantalla, ') ? input : `En mi pantalla, ${input}`),
    },
  ];
  const online = useOnline();
  const canSend = !streamState.isStreaming && !!input.trim() && !modelLoading && !!selectedModel;

  return (
    <div className="px-4 pb-3 pt-2 w-full mx-auto" style={{ maxWidth: 'var(--chat-max-width)' }}>
      {!online && (
        <p
          role="status"
          className="mb-2 px-2 text-[11.5px] leading-snug"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Sin conexión. Puede leer sus conversaciones, y lo que ya me preguntó tiene su respuesta
          guardada.
        </p>
      )}
      {/* iMessage: a round «+» on the left, then the rounded field with the
          blue send arrow inside it (the voice orb when there is nothing to send). */}
      <div className="imsg-composer">
        <div className="composer-tools" ref={menuRef}>
          <button
            type="button"
            className="composer-plus imsg-plus"
            aria-label="Herramientas"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(!menuOpen)}
          >
            <Plus size={18} strokeWidth={2} />
          </button>
          {menuOpen && (
            <div className="composer-menu" role="menu">
              {TOOLS.map(({ icon: Icon, label, hint, run, on }) => (
                <button
                  key={label}
                  type="button"
                  role="menuitemcheckbox"
                  aria-checked={!!on}
                  onClick={() => {
                    setMenuOpen(false);
                    run();
                  }}
                >
                  <Icon size={16} strokeWidth={1.6} />
                  <span>
                    <b>{label}</b>
                    <em>{hint}</em>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="imsg-field">
          {deepResearch && (
            <button
              type="button"
              className="composer-pill"
              onClick={() => setDeepResearch(false)}
              disabled={streamState.isStreaming}
              aria-label="Quitar investigación a fondo"
              title="Busca en varias fuentes y responde con citas"
            >
              <Search size={13} strokeWidth={1.75} />
              Investigación
              <X size={12} strokeWidth={2} />
            </button>
          )}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedModel ? 'Mensaje' : 'Elige un modelo primero'}
            aria-label="Mensaje para Sergio"
            rows={1}
            className="imsg-input"
            disabled={streamState.isStreaming || modelLoading}
          />
          {isCurrentChatStreaming ? (
            <button
              onClick={stopStreaming}
              className="imsg-send"
              title="Detener"
              aria-label="Detener la respuesta"
            >
              <Square size={10} fill="currentColor" strokeWidth={0} />
            </button>
          ) : input.trim() ? (
            <button
              onClick={sendMessage}
              disabled={!canSend}
              title={selectedModel ? 'Enviar' : 'Elige un modelo primero'}
              aria-label="Enviar mensaje"
              className="imsg-send"
            >
              <ArrowUp size={17} strokeWidth={2.75} />
            </button>
          ) : (
            <LiveOrb size="sm" />
          )}
        </div>
      </div>
      {deepResearch && corpusSync.syncing && corpusSync.itemsSynced > 0 && (
        <p className="mt-2 px-2 text-[11.5px] leading-snug" style={{ color: 'var(--color-text-tertiary)' }}>
          Buscando en{' '}
          <span key={corpusSync.itemsSynced} className="sync-bump" style={{ color: 'var(--color-text-secondary)' }}>
            {corpusSync.itemsSynced.toLocaleString('es')}
          </span>{' '}
          elementos. La sincronización sigue, así que los resultados irán mejorando.
        </p>
      )}
    </div>
  );
}
