import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Library, Search, SquarePen, X } from 'lucide-react';
import { ConversationList } from '../Sidebar/ConversationList';
import { useAppStore } from '../../lib/store';

// The history beside the rail (ChatGPT's sidebar): new chat, a search, your
// conversations, and the library of everything you keep.
export function HistoryPanel({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  const createConversation = useAppStore((s) => s.createConversation);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const narrow = () => typeof window !== 'undefined' && window.innerWidth < 768;

  return (
    <aside className="history" aria-label="Historial">
      <div className="history-head">
        <span className="wordmark">Sergio</span>
        <button type="button" className="mac-icon-btn" aria-label="Cerrar historial" onClick={onClose}>
          <X size={16} strokeWidth={1.5} />
        </button>
      </div>
      <button
        type="button"
        className="history-action"
        onClick={() => {
          createConversation(selectedModel);
          navigate('/chat');
          if (narrow()) onClose();
        }}
      >
        <SquarePen size={16} strokeWidth={1.5} /> Nuevo chat
      </button>
      <button type="button" className="history-action" onClick={() => (navigate('/biblioteca'), narrow() && onClose())}>
        <Library size={16} strokeWidth={1.5} /> Biblioteca
      </button>
      <label className="history-search">
        <Search size={14} strokeWidth={1.5} />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar chats" aria-label="Buscar chats" />
      </label>
      <p className="history-label">Chats</p>
      <div className="history-list" onClick={() => narrow() && onClose()}>
        <ConversationList searchQuery={query} />
      </div>
    </aside>
  );
}
