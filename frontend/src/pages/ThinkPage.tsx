import { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Brain, CheckCircle2, Loader2, RotateCcw, ShieldCheck, Square, TriangleAlert } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { readSSE } from '../lib/sse';

// One event of POST /v1/evolve/think/stream (see server/evolution_routes.py).
export interface ThinkEvent {
  stage: 'plan' | 'call' | 'draft' | 'constitution' | 'confidence' | 'retry' | 'answer' | 'error';
  [key: string]: unknown;
}

const STRATEGIES: Record<string, string> = {
  auto: 'Automática (la que mejor le ha funcionado)',
  reflection: 'Reflexión: borrador, crítica y mejora',
  tot: 'Árbol de ideas',
  consistency: 'Votación entre varias soluciones',
  causal: 'Análisis de causas / qué pasaría si',
  direct: 'Respuesta directa',
};

// The server names each model call in English; the page speaks Spanish.
const STEP_ES: Record<string, string> = {
  'Critiquing the draft': 'Criticando el borrador',
  'Improving the draft': 'Mejorando el borrador',
  'Checking the principles': 'Revisando los principios',
  'Fixing a principle': 'Corrigiendo un principio',
  'Estimating confidence': 'Midiendo la seguridad',
  'Exploring possible next steps': 'Explorando siguientes pasos',
  'Scoring a line of reasoning': 'Puntuando una línea de razonamiento',
  'Writing up the best line': 'Redactando la mejor línea',
  'Solving it one more independent way': 'Resolviéndolo otra vez por separado',
  'Mapping causes and effects': 'Trazando causas y efectos',
  'Explaining with the causal facts': 'Explicando con los hechos causales',
  'Framing the what-if': 'Planteando el qué pasaría si',
  'Describing the alternative world': 'Describiendo el mundo alternativo',
};

export function describeStep(event: ThinkEvent): string {
  switch (event.stage) {
    case 'plan':
      return `Tipo de pregunta: ${String(event.kind)} · estrategia: ${STRATEGIES[String(event.strategy)] ?? String(event.strategy)}`;
    case 'call': {
      const step = String(event.step ?? '');
      return `${String(event.n)}. ${STEP_ES[step] ?? step} (${String(event.seconds)} s)`;
    }
    case 'draft':
      return 'Borrador listo';
    case 'constitution':
      return event.revised
        ? `Corregido por principios: ${((event.fixed as string[]) ?? []).join(', ')}`
        : 'Cumple los principios';
    case 'confidence':
      return `Seguridad: ${Math.round(Number(event.confidence) * 100)}%`;
    case 'retry':
      return 'Poca seguridad: una ronda más de reflexión';
    case 'answer':
      return 'Respuesta lista';
    case 'error':
      return String(event.message ?? 'Algo falló');
  }
}

function StepIcon({ stage, last, running }: { stage: ThinkEvent['stage']; last: boolean; running: boolean }) {
  if (stage === 'error') return <TriangleAlert size={15} style={{ color: 'var(--color-error, #e5484d)' }} />;
  if (stage === 'retry') return <RotateCcw size={15} style={{ color: 'var(--color-warning)' }} />;
  if (stage === 'constitution') return <ShieldCheck size={15} style={{ color: 'var(--color-accent-text)' }} />;
  if (last && running) return <Loader2 size={15} className="animate-spin" style={{ color: 'var(--color-accent-text)' }} />;
  return <CheckCircle2 size={15} style={{ color: 'var(--color-text-secondary)' }} />;
}

// Deep thinking with every step visible as it happens.
export function ThinkPage() {
  const [question, setQuestion] = useState('');
  const [strategy, setStrategy] = useState('auto');
  const [events, setEvents] = useState<ThinkEvent[]>([]);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const answer = events.find((e) => e.stage === 'answer');
  const error = events.find((e) => e.stage === 'error');
  const steps = events.filter((e) => e.stage !== 'answer');

  const think = async () => {
    if (!question.trim() || running) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setEvents([]);
    setRunning(true);
    try {
      const res = await apiFetch('/v1/evolve/think/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, strategy }),
        signal: controller.signal,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: `Error ${res.status}` }));
        setEvents([{ stage: 'error', message: detail.detail ?? `Error ${res.status}` }]);
      } else {
        await readSSE<ThinkEvent>(res, (event) => setEvents((prev) => [...prev, event]));
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setEvents((prev) => [...prev, { stage: 'error', message: 'No pude conectar con Sergio.' }]);
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  };

  const confidence = answer ? Number(answer.confidence) : null;

  return (
    <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 sm:py-8">
      <div className="max-w-3xl mx-auto space-y-5">
        <header className="space-y-1">
          <h1 className="text-lg font-semibold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Brain size={18} /> Pensar a fondo
          </h1>
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            Sergio elige cómo razonar, se critica, revisa sus principios y dice qué tan seguro está. Aquí ve cada paso
            mientras ocurre.
          </p>
        </header>

        <div className="space-y-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) think();
            }}
            rows={3}
            placeholder="Escriba su pregunta…"
            className="w-full px-3 py-2 rounded-lg text-sm border resize-y"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)' }}
          />
          <div className="flex flex-wrap gap-3 items-center">
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm border"
              style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)' }}
              aria-label="Estrategia"
            >
              {Object.entries(STRATEGIES).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            {running ? (
              <button
                onClick={() => abortRef.current?.abort()}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm border"
                style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
              >
                <Square size={14} /> Detener
              </button>
            ) : (
              <button
                onClick={think}
                disabled={!question.trim()}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-white disabled:opacity-50"
                style={{ background: 'var(--color-accent)' }}
              >
                <Brain size={16} /> Pensar
              </button>
            )}
          </div>
        </div>

        {steps.length > 0 && (
          <ol className="space-y-1.5" aria-live="polite">
            {steps.map((event, i) => (
              <li key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                <span className="mt-0.5 shrink-0">
                  <StepIcon stage={event.stage} last={i === steps.length - 1} running={running} />
                </span>
                <span className={event.stage === 'call' ? 'pl-2' : 'font-medium'}>{describeStep(event)}</span>
              </li>
            ))}
          </ol>
        )}

        {error && (
          <p className="text-sm" style={{ color: 'var(--color-warning)' }}>
            {String(error.fix ?? '')}
          </p>
        )}

        {answer && (
          <section className="rounded-xl p-4 space-y-3" style={{ background: 'var(--color-bg-secondary)' }}>
            <div className="prose prose-sm max-w-none" style={{ color: 'var(--color-text)' }}>
              <ReactMarkdown>{String(answer.answer ?? '')}</ReactMarkdown>
            </div>
            {confidence !== null && (
              <div className="space-y-1">
                <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-border)' }}>
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${Math.round(confidence * 100)}%`, background: 'var(--color-accent)' }}
                  />
                </div>
                <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  Seguridad {Math.round(confidence * 100)}% · {String(answer.calls)} consultas · {String(answer.seconds)} s
                </p>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
