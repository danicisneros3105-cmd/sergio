import { AudioLines, MessageSquareText, Trash2, Zap, type LucideIcon } from 'lucide-react';
import { useNavigate } from 'react-router';
import { chatKindOf, useAppStore } from '../../lib/store';
import type { ChatKind } from '../../types';

export const CHAT_SECTIONS: Array<{ kind: ChatKind; label: string; icon: LucideIcon }> = [
  { kind: 'texto', label: 'Texto', icon: MessageSquareText },
  { kind: 'voz', label: 'Voz', icon: AudioLines },
  { kind: 'rapido', label: 'Quick', icon: Zap },
];

/** The three chat sections: written, spoken and quick questions. */
export function ChatSections() {
  const kind = useAppStore((s) => s.chatKind);
  const setKind = useAppStore((s) => s.setChatKind);
  return (
    <div className="sb-tabs" role="tablist" aria-label="Chats">
      {CHAT_SECTIONS.map((t) => (
        <button
          key={t.kind}
          type="button"
          role="tab"
          aria-selected={kind === t.kind}
          className="sb-tab"
          onClick={() => setKind(t.kind)}
          title={t.kind === 'rapido' ? 'Quick Chat (Ctrl J)' : t.label}
        >
          <t.icon size={13} strokeWidth={1.8} aria-hidden />
          {t.label}
        </button>
      ))}
    </div>
  );
}

interface Props {
  searchQuery: string;
}

function formatRelativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'Ahora';
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'Ayer';
  if (days < 7) return `hace ${days} días`;
  return new Date(timestamp).toLocaleDateString('es');
}

export function ConversationList({ searchQuery }: Props) {
  const navigate = useNavigate();
  const conversations = useAppStore((s) => s.conversations);
  const activeId = useAppStore((s) => s.activeId);
  const streamingConversationId = useAppStore((s) =>
    s.streamState.isStreaming ? s.streamState.conversationId : null,
  );
  const selectConversation = useAppStore((s) => s.selectConversation);
  const deleteConversation = useAppStore((s) => s.deleteConversation);
  const kind = useAppStore((s) => s.chatKind);

  // Searching looks in every section; otherwise only the chosen one.
  const filtered = searchQuery
    ? conversations.filter((c) =>
        c.title.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : conversations.filter((c) => chatKindOf(c) === kind);

  if (filtered.length === 0) {
    return (
      <div className="px-3 py-8 text-center text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
        {searchQuery
          ? 'Ninguna conversación coincide'
          : kind === 'voz'
            ? 'Lo que hable con Sergio aparece aquí'
            : kind === 'rapido'
              ? 'Preguntas rápidas: Ctrl J'
              : 'Aquí aparecerán tus conversaciones'}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-px py-1">
      {filtered.map((conv) => {
        const isActive = conv.id === activeId;
        const isStreaming = conv.id === streamingConversationId;
        return (
          <div
            key={conv.id}
            className="mac-row group !p-0 !gap-0"
            data-active={isActive}
          >
            <button
              onClick={() => {
                selectConversation(conv.id);
                navigate('/chat');
              }}
              className="flex-1 text-left pl-2.5 pr-1 py-2 min-w-0 cursor-pointer"
              aria-current={isActive ? 'true' : undefined}
              title={`${conv.title} · ${formatRelativeTime(conv.updatedAt)}`}
            >
              <div className="text-[14px] truncate">{conv.title}</div>
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                deleteConversation(conv.id);
              }}
              disabled={isStreaming}
              className="p-1.5 mr-1 rounded-md opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity cursor-pointer disabled:cursor-not-allowed disabled:opacity-30 hover:text-[var(--color-error)]"
              style={{ color: 'var(--color-text-tertiary)' }}
              title={
                isStreaming
                  ? 'Detén la respuesta antes de borrar esta conversación'
                  : 'Borrar conversación'
              }
              aria-label="Borrar conversación"
            >
              <Trash2 size={14} strokeWidth={1.75} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
