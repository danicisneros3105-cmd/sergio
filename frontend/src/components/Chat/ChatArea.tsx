import { useRef, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { MessageBubble } from './MessageBubble';
import { InputArea } from './InputArea';
import { StreamingDots } from './StreamingDots';
import { useAppStore } from '../../lib/store';
import { shouldAutoplayFinishedReply, useTtsStore } from '../../lib/tts';
import { stripThinkTags } from '../../lib/message-text';
import {
  Brain,
  CalendarCheck,
  ChevronDown,
  CircleDot,
  PanelRightOpen,
  PanelRightClose,
  Database,
  FileText,
  Network,
  NotebookPen,
  Shapes,
  Search,
} from 'lucide-react';
import { listConnectors } from '../../lib/connectors-api';

/** What a person needs to know about the model: fast, thorough or on this PC. */
export function friendlyModel(id: string): string {
  const name = (id.split('/').pop() || id).split('@')[0].toLowerCase();
  if (/(^|-)pro($|-)|opus|deep-research|thinking/.test(name)) return 'A fondo';
  if (/flash|lite|mini|haiku|sonnet|gpt|claude|gemini/.test(name)) return 'Rápido';
  return 'En su PC';
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Buenos días';
  if (hour < 19) return 'Buenas tardes';
  return 'Buenas noches';
}

// What people actually do with Sergio, as cards under the composer: some
// open their section, the rest fill the composer with an editable start.
// Each card wears its section's colour.
const MODES: Array<{
  icon: typeof Search;
  label: string;
  hint: string;
  color: string;
  to?: string;
  text?: string;
}> = [
  { icon: CalendarCheck, label: 'Organiza mi semana', hint: 'Tareas, horarios y recordatorios', color: 'var(--sec-chat)', text: 'Ayúdame a organizar mi semana: ' },
  { icon: FileText, label: 'Resume un documento', hint: 'Adjunte un PDF o pegue el texto', color: 'var(--sec-cowork)', text: 'Resume esto en cinco puntos: ' },
  { icon: Shapes, label: 'Crea algo', hint: 'Imagen, diseño o modelo 3D', color: 'var(--sec-creator)', to: '/creator' },
  { icon: CircleDot, label: 'Vigila algo por mí', hint: 'Un Node que avisa cuando cambia', color: 'var(--sec-nodes)', to: '/nodes?nuevo=1' },
  { icon: Network, label: 'Investiga a fondo', hint: 'Muchos agentes a la vez', color: 'var(--sec-swarm)', to: '/swarm' },
  { icon: NotebookPen, label: 'Toma notas', hint: 'Páginas, tablas y tareas', color: 'var(--sec-workspace)', to: '/workspace' },
];

function prefill(text: string) {
  window.dispatchEvent(new CustomEvent('sergio:prefill', { detail: text }));
}

export function ChatArea() {
  const activeId = useAppStore((s) => s.activeId);
  const messages = useAppStore((s) => s.messages);
  const streamState = useAppStore((s) => s.streamState);
  const systemPanelOpen = useAppStore((s) => s.systemPanelOpen);
  const toggleSystemPanel = useAppStore((s) => s.toggleSystemPanel);
  const reasoningPanelOpen = useAppStore((s) => s.reasoningPanelOpen);
  const toggleReasoningPanel = useAppStore((s) => s.toggleReasoningPanel);
  const navigate = useNavigate();
  const conversations = useAppStore((s) => s.conversations);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const title = conversations.find((c) => c.id === activeId)?.title || 'Chat';
  const listRef = useRef<HTMLDivElement>(null);
  const shouldAutoScroll = useRef(true);
  const wasStreaming = useRef(false);
  const lastScrollTop = useRef(0);
  const isCurrentChatStreaming = streamState.isStreaming && streamState.conversationId === activeId;

  // Autoplay: speak a reply once it is finished, never while it streams -- a
  // partial sentence would be synthesized and then cut off by the next chunk.
  // autoSpokenId fences the message so re-renders cannot repeat it.
  const voiceOutputEnabled = useAppStore((s) => s.settings.voiceOutputEnabled);
  const voiceAutoplay = useAppStore((s) => s.settings.voiceAutoplay);
  // Probe the backend as soon as voice output is switched on. Without this the
  // first reply could never autoplay: `available` is only set by ensureHealth,
  // which until now ran solely from the per-message read-aloud button -- and
  // that button does not exist until a reply is already on screen.
  useEffect(() => {
    if (!voiceOutputEnabled) return;
    useTtsStore.getState().ensureHealth();
  }, [voiceOutputEnabled]);

  // Speak on the falling edge of a stream -- the moment a reply finishes -- and
  // never merely because a finished reply happens to be on screen. Opening the
  // app or switching conversations would otherwise read stale history aloud,
  // and browsers block that anyway: playback with no preceding user gesture is
  // rejected outright, so the failure would be silent in both senses.
  const streamingConversationRef = useRef<string | null>(null);
  useEffect(() => {
    const last = messages[messages.length - 1];
    const tts = useTtsStore.getState();
    const justFinished = shouldAutoplayFinishedReply(
      streamingConversationRef.current,
      activeId,
      streamState.isStreaming,
      last,
      tts.autoSpokenId,
    );
    streamingConversationRef.current = isCurrentChatStreaming ? activeId : null;

    if (!justFinished) return;
    if (!voiceOutputEnabled || !voiceAutoplay) return;

    if (!last || last.role !== 'assistant' || activeId === null) return;

    // Model loading may still be in flight when a fast reply completes. Wait
    // for the probe, then confirm that this is still the active finished reply.
    const completedConversationId = activeId;
    const completedMessageId = last.id;
    void tts.ensureHealth().then(() => {
      const app = useAppStore.getState();
      const currentTts = useTtsStore.getState();
      const currentLast = app.messages[app.messages.length - 1];
      if (app.activeId !== completedConversationId || app.streamState.isStreaming) return;
      if (!app.settings.voiceOutputEnabled || !app.settings.voiceAutoplay) return;
      if (currentLast?.id !== completedMessageId || currentTts.available !== true) return;
      if (currentTts.autoSpokenId === completedMessageId) return;

      const text = stripThinkTags(currentLast.content);
      if (!text) return;
      currentTts.markAutoSpoken(completedMessageId);
      void currentTts.speak(completedMessageId, text);
    });
  }, [activeId, messages, streamState.isStreaming, isCurrentChatStreaming, voiceOutputEnabled, voiceAutoplay]);
  const currentStreamContent = isCurrentChatStreaming ? streamState.content : '';

  // Check if any data sources are connected
  const [hasConnectedSources, setHasConnectedSources] = useState<boolean | null>(null);

  useEffect(() => {
    listConnectors()
      .then((list) => setHasConnectedSources(list.some((c) => c.connected)))
      .catch(() => setHasConnectedSources(null));
  }, []);

  useEffect(() => {
    // Sending a message always pins the view to the bottom, even if the
    // user had scrolled up to read earlier messages.
    if (isCurrentChatStreaming && !wasStreaming.current) {
      shouldAutoScroll.current = true;
    }
    wasStreaming.current = isCurrentChatStreaming;
    if (shouldAutoScroll.current && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, currentStreamContent, isCurrentChatStreaming]);

  const handleScroll = () => {
    if (!listRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = listRef.current;
    const distance = scrollHeight - scrollTop - clientHeight;
    const scrolledUp = scrollTop < lastScrollTop.current;
    lastScrollTop.current = scrollTop;
    if (scrolledUp && distance >= 1) {
      // Any upward scroll away from the bottom stops autoscroll immediately,
      // so streaming content never fights the user (no jitter). Sub-1px
      // upward movement (elastic bounce settling at the bottom) is ignored.
      shouldAutoScroll.current = false;
    } else if (!scrolledUp) {
      // Re-engage when scrolled back to the bottom. < 2 rather than < 1:
      // at fractional zoom levels the at-bottom residual can reach 1px,
      // which would otherwise leave autoscroll permanently disengaged.
      shouldAutoScroll.current = distance < 2;
    }
  };

  const isEmpty = messages.length === 0 && !isCurrentChatStreaming;

  const PanelIcon = systemPanelOpen ? PanelRightClose : PanelRightOpen;
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const modelLabel = selectedModel ? friendlyModel(selectedModel) : 'Elegir modelo';

  return (
    <div className="flex flex-col h-full">
      <header className="chat-top">
        <button
          type="button"
          className="chat-model"
          onClick={() => setCommandPaletteOpen(true)}
          title={`Modelo: ${selectedModel || "ninguno"} (cambiar con Ctrl+K)`}
        >
          <span className="wordmark">Sergio</span>
          <span className="chat-model-name">{modelLabel}</span>
          <ChevronDown size={14} strokeWidth={1.75} />
        </button>
        <span className="chat-top-title" title={title}>
          {messages.length ? title : ''}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={toggleReasoningPanel}
            className="mac-icon-btn"
            title={`${reasoningPanelOpen ? 'Ocultar' : 'Mostrar'} el razonamiento paso a paso`}
            aria-label="Razonamiento"
            aria-pressed={reasoningPanelOpen}
          >
            <Brain size={18} strokeWidth={1.5} />
          </button>
          <button
            onClick={toggleSystemPanel}
            className="mac-icon-btn hidden lg:inline-grid"
            title={`${systemPanelOpen ? 'Ocultar' : 'Mostrar'} el panel del sistema (${navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'}+I)`}
            aria-label="Panel del sistema"
          >
            <PanelIcon size={18} strokeWidth={1.5} />
          </button>
        </div>
      </header>

      <div
        ref={listRef}
        onScroll={handleScroll}
        className={isEmpty ? 'flex-[1] flex flex-col justify-end px-4 pb-8' : 'flex-1 overflow-y-auto'}
      >
        {isEmpty ? (
          <div className="mac-rise text-center" style={{ ['--i' as string]: 0 }}>
            <h2 className="chat-hello">
              <span className="chat-hello-name">{getGreeting()}, señor</span>
              <span className="chat-hello-ask">¿En qué trabajamos hoy?</span>
            </h2>
          </div>
        ) : (
          <div className="max-w-[var(--chat-max-width)] mx-auto px-4 py-6">
            {messages.map((msg, i) => {
              const isLastAssistant =
                i === messages.length - 1 && msg.role === 'assistant';
              return (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  isLive={isLastAssistant && isCurrentChatStreaming}
                />
              );
            })}
            {(() => {
              if (!isCurrentChatStreaming || streamState.content !== '') return null;
              // For research messages the ResearchTimeline handles its own
              // pre-content loading state — suppress the generic dots.
              const last = messages[messages.length - 1];
              if (last?.role === 'assistant' && last.isResearch) return null;
              return (
                <div className="flex justify-start mb-4">
                  <StreamingDots phase={streamState.phase} />
                </div>
              );
            })()}
          </div>
        )}
      </div>

      <div className={isEmpty ? 'mac-rise' : undefined} style={{ ['--i' as string]: 1 }}>
        <InputArea />
      </div>

      {isEmpty && (
        <div className="flex-[1.4] px-4 overflow-y-auto">
          <div
            className="mac-rise mx-auto starter-grid pt-1"
            style={{ maxWidth: 'var(--chat-max-width)', ['--i' as string]: 2 }}
          >
            {MODES.map(({ icon: Icon, label, hint, color, to, text }) => (
              <button
                key={label}
                className="starter-card"
                style={{ '--sec': color } as React.CSSProperties}
                onClick={() => (to ? navigate(to) : prefill(text || ''))}
              >
                <span className="starter-icon" aria-hidden="true">
                  <Icon size={18} strokeWidth={1.8} />
                </span>
                <b>{label}</b>
                <small>{hint}</small>
              </button>
            ))}
            {hasConnectedSources === false && (
              <button className="mac-chip" onClick={() => navigate('/data-sources')}>
                <Database size={15} strokeWidth={1.6} />
                Conectar mis apps
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
