import { useRef, useEffect } from 'react';
import { Copy, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAppStore } from '../lib/store';

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('es', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function LogsPage() {
  const logEntries = useAppStore((s) => s.logEntries);
  const clearLogs = useAppStore((s) => s.clearLogs);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logEntries.length]);

  const handleCopy = async () => {
    const text = logEntries
      .map((e) => `${formatTime(e.timestamp)} [${e.level}] [${e.category}] ${e.message}`)
      .join('\n');
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Copiado.');
    } catch {
      toast.error('No pude copiar. Seleccione el texto y cópielo a mano.');
    }
  };

  return (
    <div className="paper-page">
      <div className="paper-head paper-head-wrap">
        <span />
        <h1 className="paper-title">Registro</h1>
        <div>
          <span className="paper-meta">{logEntries.length} {logEntries.length === 1 ? 'entrada' : 'entradas'}</span>
          <button type="button" className="paper-button" data-variant="quiet" onClick={() => void handleCopy()}>
            <Copy size={14} aria-hidden="true" /> Copiar todo
          </button>
          <button type="button" className="paper-button" data-variant="quiet" onClick={clearLogs}>
            <Trash2 size={14} aria-hidden="true" /> Vaciar
          </button>
        </div>
      </div>
      <div className="paper-log" role="log" aria-live="polite">
        {logEntries.length === 0 ? (
          <p className="paper-meta">Aún no hay nada. Aquí aparece lo que pasa mientras usa Sergio.</p>
        ) : (
          logEntries.map((entry, i) => (
            <div key={i} className={`paper-log-row${entry.level === 'error' ? ' is-error' : ''}`}>
              <span className="paper-meta">{formatTime(entry.timestamp)}</span> <b>[{entry.category}]</b> {entry.message}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
