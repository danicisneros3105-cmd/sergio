import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Brain, Loader2, Square, X } from 'lucide-react';
import { getBase } from '../../lib/api';
import { useAppStore } from '../../lib/store';
import { buildWsProtocols } from '../../lib/useAgentEvents';
import { lastUserQuestion, thinkingUrl } from '../../lib/thinking';
import { describeStep, type ThinkEvent } from '../../pages/ThinkPage';

// A collapsible side panel next to the chat: think the last question
// through, step by step, while the conversation stays where it is.
export function ReasoningPanel() {
  const messages = useAppStore((s) => s.messages);
  const toggle = useAppStore((s) => s.toggleReasoningPanel);
  const [question, setQuestion] = useState('');
  const [events, setEvents] = useState<ThinkEvent[]>([]);
  const [running, setRunning] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const lastQuestion = lastUserQuestion(messages);

  useEffect(() => {
    if (!running) setQuestion(lastQuestion);
  }, [lastQuestion, running]);

  useEffect(() => () => socketRef.current?.close(), []);

  const stop = () => {
    socketRef.current?.close();
    socketRef.current = null;
    setRunning(false);
  };

  const think = () => {
    if (!question.trim() || running) return;
    setEvents([]);
    setRunning(true);
    const ws = new WebSocket(thinkingUrl(getBase(), window.location.origin), buildWsProtocols());
    socketRef.current = ws;
    ws.onopen = () => ws.send(JSON.stringify({ question, strategy: 'auto' }));
    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(String(msg.data)) as ThinkEvent;
        setEvents((prev) => [...prev, event]);
        if (event.stage === 'answer' || event.stage === 'error') stop();
      } catch {
        // a malformed message is skipped
      }
    };
    ws.onerror = () => {
      setEvents((prev) => [...prev, { stage: 'error', message: 'No pude conectar con Sergio.' }]);
      stop();
    };
    ws.onclose = () => setRunning(false);
  };

  const answer = events.find((e) => e.stage === 'answer');
  const steps = events.filter((e) => e.stage !== 'answer');

  return (
    <aside
      className="flex flex-col h-full overflow-y-auto"
      style={{
        width: 300,
        minWidth: 300,
        borderLeft: '1px solid var(--color-border)',
        background: 'var(--color-bg-secondary)',
      }}
      aria-label="Razonamiento"
    >
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-sm font-medium flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
          <Brain size={15} /> Razonamiento
        </span>
        <button onClick={toggle} className="mac-icon-btn" aria-label="Cerrar el razonamiento">
          <X size={15} />
        </button>
      </div>
      <div className="px-4 space-y-3 pb-4">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          placeholder="La pregunta a pensar a fondo"
          className="w-full px-2 py-1.5 rounded-lg text-xs border resize-y"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)' }}
        />
        {running ? (
          <button
            onClick={stop}
            className="w-full inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg text-xs border"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
          >
            <Square size={12} /> Detener
          </button>
        ) : (
          <button
            onClick={think}
            disabled={!question.trim()}
            className="w-full inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg text-xs disabled:opacity-50"
            style={{ background: 'var(--color-ink)', color: 'var(--color-on-ink)' }}
          >
            <Brain size={13} /> Pensar a fondo
          </button>
        )}
        {steps.length > 0 && (
          <ol className="space-y-1" aria-live="polite">
            {steps.map((event, i) => (
              <li key={i} className="text-xs flex gap-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                {running && i === steps.length - 1 ? (
                  <Loader2 size={12} className="animate-spin mt-0.5 shrink-0" />
                ) : (
                  <span className="shrink-0">·</span>
                )}
                <span>{describeStep(event)}</span>
              </li>
            ))}
          </ol>
        )}
        {answer && (
          <div className="text-xs prose prose-sm max-w-none" style={{ color: 'var(--color-text)' }}>
            <ReactMarkdown>{String(answer.answer ?? '')}</ReactMarkdown>
            <p style={{ color: 'var(--color-text-secondary)' }}>
              Seguridad {Math.round(Number(answer.confidence) * 100)}%
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
