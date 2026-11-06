import { WeekLine } from './WeekLine';
import { IaSetupCard } from './IaSetupCard';
import { Fragment, useMemo, useRef, useEffect } from 'react';
import { MessageBubble } from './MessageBubble';
import { SplitButton } from '../Split/SplitButton';
import { InputArea } from './InputArea';
import { ActivityFilm } from './ActivityFilm';
import { StreamingDots } from './StreamingDots';
import { useAppStore } from '../../lib/store';
import { shouldAutoplayFinishedReply, useTtsStore } from '../../lib/tts';
import { liveIsSpeaking } from '../../lib/liveSession';
import { stripThinkTags } from '../../lib/message-text';
import { bubbleFlags as flagsFor } from '../../lib/imessage';
import {
  ChevronDown,
  PanelRightOpen,
  PanelRightClose,
} from 'lucide-react';
import { usePersonal } from '../../lib/personal';
import { greetingLine } from '../../lib/greetings';

/** What a person needs to know about the model: fast, thorough or on this PC. */
export function friendlyModel(id: string): string {
  const name = (id.split('/').pop() || id).split('@')[0].toLowerCase();
  if (/(^|-)pro($|-)|opus|deep-research|thinking/.test(name)) return 'A fondo';
  if (/flash|lite|mini|haiku|sonnet|gpt|claude|gemini/.test(name)) return 'Rápido';
  return 'En su PC';
}

export function ChatArea() {
  const activeId = useAppStore((s) => s.activeId);
  const messages = useAppStore((s) => s.messages);
  const streamState = useAppStore((s) => s.streamState);
  const systemPanelOpen = useAppStore((s) => s.systemPanelOpen);
  const toggleSystemPanel = useAppStore((s) => s.toggleSystemPanel);
  const conversations = useAppStore((s) => s.conversations);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const chatKind = useAppStore((s) => s.chatKind);
  const personal = usePersonal();
  const hello = useMemo(
    () => greetingLine(personal, { kind: chatKind === 'voz' ? 'voice' : 'chat' }),
    [personal, chatKind],
  );
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
          <img className="sg-chat-mark" src="/sergio.svg" width={32} height={32} alt="" />
          <span className="imsg-name">
            Sergio <ChevronDown size={11} strokeWidth={2.5} />
          </span>
        </button>
        <div className="flex items-center gap-1.5">
          <SplitButton className="split-pill-btn" />
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

      <div className={isEmpty ? 'sg-chat-body sg-chat-body-home' : 'sg-chat-body'}>
        <div
          ref={listRef}
          onScroll={handleScroll}
          className={isEmpty ? 'sg-chat-intro' : 'flex-1 min-h-0 overflow-y-auto'}
        >
          {isEmpty ? (
            <div>
              <header className="sg-chat-heading sg-editorial-cover">
                <span className="sg-kicker">Espacio personal</span>
                <h1>{hello}</h1>
              </header>
              <IaSetupCard />
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

        {!isEmpty && (
          <div className="activity-film-wrap">
            <ActivityFilm active={isCurrentChatStreaming} />
          </div>
        )}
        <div className={isEmpty ? 'sg-chat-composer' : undefined}>
          <InputArea />
        </div>

        {isEmpty && <div className="sg-chat-context"><WeekLine /></div>}
      </div>
    </div>
  );
}
