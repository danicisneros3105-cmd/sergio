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
  PanelRightOpen,
  PanelRightClose,
  Database,
  Phone,
  MonitorSmartphone,
  CloudSun,
  MessageCircle,
  History,
  Plus,
  Search,
  X,
} from 'lucide-react';
import { listConnectors } from '../../lib/connectors-api';
import { PaperHead } from '../Paper/PaperPage';
import { ConversationList } from '../Sidebar/ConversationList';

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Buenos días';
  if (hour < 19) return 'Buenas tardes';
  return 'Buenas noches';
}

// Each suggestion fills the composer with an editable request.
const SUGGESTIONS = [
  { icon: Phone, label: 'Reservar por teléfono', text: 'Llama al restaurante y reserva una mesa para dos a las 8 de la noche. El número es ' },
  { icon: MonitorSmartphone, label: 'Usar mi pantalla', text: 'Abre Spotify y pon música tranquila' },
  { icon: CloudSun, label: 'El clima en Quito', text: '¿Cómo está el clima ahora en Quito y a qué hora anochece?' },
  { icon: MessageCircle, label: 'Enviar un WhatsApp', text: 'Mándale un WhatsApp a  diciendo que llego en 10 minutos' },
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
  const createConversation = useAppStore((s) => s.createConversation);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyQuery, setHistoryQuery] = useState('');
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

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 pt-6 shrink-0">
        <div className="mx-auto" style={{ maxWidth: 1040 }}>
          <PaperHead
            title={messages.length ? title.slice(0, 48) : 'Chat'}
            left={
              <>
                <button
                  type="button"
                  className="mac-icon-btn"
                  onClick={() => setHistoryOpen(!historyOpen)}
                  aria-label="Conversaciones"
                  aria-pressed={historyOpen}
                  title="Conversaciones"
                >
                  <History size={17} strokeWidth={1.4} />
                </button>
                <button
                  type="button"
                  className="mac-icon-btn"
                  onClick={() => {
                    if (messages.length) createConversation(selectedModel);
                  }}
                  aria-label="Nueva conversación"
                  title="Nueva conversación"
                >
                  <Plus size={17} strokeWidth={1.4} />
                </button>
              </>
            }
            right={
              <>
                <button
                  onClick={toggleReasoningPanel}
                  className="mac-icon-btn"
                  title={`${reasoningPanelOpen ? 'Ocultar' : 'Mostrar'} el razonamiento paso a paso`}
                  aria-label="Razonamiento"
                  aria-pressed={reasoningPanelOpen}
                >
                  <Brain size={17} strokeWidth={1.4} />
                </button>
                <button
                  onClick={toggleSystemPanel}
                  className="mac-icon-btn hidden lg:inline-grid"
                  title={`${systemPanelOpen ? 'Ocultar' : 'Mostrar'} el panel del sistema (${navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'}+I)`}
                  aria-label="Panel del sistema"
                >
                  <PanelIcon size={17} strokeWidth={1.4} />
                </button>
              </>
            }
          />
        </div>
      </div>

      {historyOpen && (
        <aside className="ws-drawer" aria-label="Conversaciones">
          <div className="flex items-center gap-2 mb-3">
            <span className="paper-label flex-1">Conversaciones</span>
            <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={() => setHistoryOpen(false)}>
              <X size={15} />
            </button>
          </div>
          <label className="mac-field text-[13px] mb-2">
            <Search size={13} />
            <input
              value={historyQuery}
              onChange={(e) => setHistoryQuery(e.target.value)}
              placeholder="Buscar"
              className="flex-1 bg-transparent outline-none"
              aria-label="Buscar conversaciones"
            />
          </label>
          <div onClick={() => setHistoryOpen(false)}>
            <ConversationList searchQuery={historyQuery} />
          </div>
        </aside>
      )}

      <div
        ref={listRef}
        onScroll={handleScroll}
        className={isEmpty ? 'flex-[1] flex flex-col justify-end px-4 pb-7' : 'flex-1 overflow-y-auto'}
      >
        {isEmpty ? (
          <div className="mac-rise text-center" style={{ ['--i' as string]: 0 }}>
            <h2 className="paper-title" style={{ fontSize: 26 }}>
              {getGreeting()}
            </h2>
            <p className="mt-1.5 text-[14px]" style={{ color: 'var(--color-text-secondary)' }}>
              ¿En qué le ayudo?
            </p>
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
        <div className="flex-[1.6] px-4 overflow-y-auto">
          <div
            className="mac-rise mx-auto flex flex-wrap justify-center gap-2 pt-2"
            style={{ maxWidth: 'var(--chat-max-width)', ['--i' as string]: 2 }}
          >
            {SUGGESTIONS.map(({ icon: Icon, label, text }) => (
              <button key={label} className="mac-chip" onClick={() => prefill(text)}>
                <Icon size={14} strokeWidth={1.75} />
                {label}
              </button>
            ))}
            {hasConnectedSources === false && (
              <button className="mac-chip" onClick={() => navigate('/data-sources')}>
                <Database size={14} strokeWidth={1.75} />
                Conectar mis datos
              </button>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
