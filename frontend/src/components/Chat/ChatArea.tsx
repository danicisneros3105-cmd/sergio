import { Fragment, useMemo, useRef, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { MessageBubble } from './MessageBubble';
import { InputArea } from './InputArea';
import { StreamingDots } from './StreamingDots';
import { useAppStore } from '../../lib/store';
import { shouldAutoplayFinishedReply, useTtsStore } from '../../lib/tts';
import { liveIsSpeaking } from '../../lib/liveSession';
import { stripThinkTags } from '../../lib/message-text';
import { bubbleFlags as flagsFor } from '../../lib/imessage';
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

// What people actually do with Sergio, as ChatGPT's pills under the
// composer: some open their section, the rest fill the composer with an
// editable start.
const MODES: Array<{
  icon: typeof Search;
  label: string;
  hint: string;
  to?: string;
  text?: string;
}> = [
  { icon: CalendarCheck, label: 'Mi semana', hint: 'Tareas, horarios y recordatorios', text: 'Ayúdame a organizar mi semana: ' },
  { icon: FileText, label: 'Resumir texto', hint: 'Adjunte un PDF o pegue el texto', text: 'Resume esto en cinco puntos: ' },
  { icon: Shapes, label: 'Crear algo', hint: 'Imagen, diseño o modelo 3D', text: 'Ayúdame a crear: ' },
  { icon: CircleDot, label: 'Vigilar algo', hint: 'Un Node que avisa cuando cambia', to: '/nodes?nuevo=1' },
  { icon: Network, label: 'Investigar', hint: 'Muchos agentes a la vez', to: '/swarm' },
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
      // His live voice is already talking: a second voice on top would be noise.
      if (liveIsSpeaking()) return;

      const text = stripThinkTags(currentLast.content);
      if (!text) return;
      currentTts.markAutoSpoken(completedMessageId);
      void currentTts.speak(completedMessageId, text);
    });
  }, [activeId, messages, streamState.isStreaming, isCurrentChatStreaming, voiceOutputEnabled, voiceAutoplay]);
  const currentStreamContent = isCurrentChatStreaming ? streamState.content : '';
  // iMessage: groups, tails, centred times and «Entregado» / «Leído».
  const bubbleFlags = useMemo(() => flagsFor(messages), [messages]);

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
      <header className="chat-top imsg-top">
        <span aria-hidden="true" />
        {/* Like iMessage: who you are talking to, in the middle. A click
            changes how he thinks (fast or thorough). */}
        <button
          type="button"
          className="imsg-contact"
          onClick={() => setCommandPaletteOpen(true)}
          title={`${title !== 'Chat' && messages.length ? title + ' · ' : ''}Modo: ${modelLabel} (cambiar con Ctrl+K)`}
        >
          <span className="imsg-avatar" aria-hidden="true">S</span>
          <span className="imsg-name">
            Sergio <ChevronDown size={11} strokeWidth={2.5} />
          </span>
        </button>
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
            <h1 className="chat-hello">¿En qué trabajamos hoy, señor?</h1>
          </div>
        ) : (
          <div className="imsg-thread max-w-[var(--chat-max-width)] mx-auto px-4 py-6">
            {messages.map((msg, i) => {
              const isLastAssistant =
                i === messages.length - 1 && msg.role === 'assistant';
              const flags = bubbleFlags[i];
              return (
                <Fragment key={msg.id}>
                  {flags?.stamp && <div className="imsg-stamp">{flags.stamp}</div>}
                  <MessageBubble
                    message={msg}
                    isLive={isLastAssistant && isCurrentChatStreaming}
                    tail={flags?.tail ?? true}
                    receipt={flags?.receipt ?? ''}
                  />
                </Fragment>
              );
            })}
            {(() => {
              if (!isCurrentChatStreaming || streamState.content !== '') return null;
              // For research messages the ResearchTimeline handles its own
              // pre-content loading state — suppress the generic dots.
              const last = messages[messages.length - 1];
              if (last?.role === 'assistant' && last.isResearch) return null;
              return (
                <div className="imsg-row them end">
                  <div className="imsg-bubble them tail imsg-typing" aria-label="Sergio está escribiendo">
                    <StreamingDots phase={streamState.phase} />
                  </div>
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
            className="mac-rise mx-auto starter-pills pt-1"
            style={{ maxWidth: 'var(--chat-max-width)', ['--i' as string]: 2 }}
          >
            {MODES.map(({ icon: Icon, label, hint, to, text }) => (
              <button
                key={label}
                type="button"
                className="starter-pill"
                title={hint}
                onClick={() => (to ? navigate(to) : prefill(text || ''))}
              >
                <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
                {label}
              </button>
            ))}
            {hasConnectedSources === false && (
              <button type="button" className="starter-pill" onClick={() => navigate('/data-sources')}>
                <Database size={16} strokeWidth={1.8} aria-hidden="true" />
                Conectar mis apps
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
