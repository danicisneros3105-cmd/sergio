import { useEffect, useRef, useState } from 'react';
import { Pause, Play, RotateCcw } from 'lucide-react';

// A focus timer inside a page: work, then rest, a hairline ring for the
// time left. It keeps time from the clock (not from ticks), so a sleeping
// tab never drifts; a notification says when the round ends.
export function PomodoroBlock({
  work,
  rest,
  onChange,
}: {
  work: number;
  rest: number;
  onChange: (next: { work: number; rest: number }) => void;
}) {
  const [phase, setPhase] = useState<'work' | 'rest'>('work');
  const [endsAt, setEndsAt] = useState<number | null>(null);
  const [left, setLeft] = useState(work * 60);
  const [rounds, setRounds] = useState(0);
  const tick = useRef<number | null>(null);
  const total = (phase === 'work' ? work : rest) * 60;

  useEffect(() => {
    if (endsAt === null) return;
    const step = () => {
      const remaining = Math.max(0, Math.round((endsAt - Date.now()) / 1000));
      setLeft(remaining);
      if (remaining === 0) {
        const next = phase === 'work' ? 'rest' : 'work';
        if (phase === 'work') setRounds((r) => r + 1);
        try {
          if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(next === 'rest' ? 'Descanso' : 'A trabajar', {
              body: next === 'rest' ? `${rest} minutos para despejarse.` : `${work} minutos de enfoque.`,
            });
          }
        } catch {
          // notifications blocked: the ring still shows it
        }
        setPhase(next);
        setEndsAt(Date.now() + (next === 'work' ? work : rest) * 60_000);
      }
    };
    step();
    tick.current = window.setInterval(step, 500);
    return () => {
      if (tick.current) window.clearInterval(tick.current);
    };
  }, [endsAt, phase, work, rest]);

  const start = () => {
    try {
      if ('Notification' in window && Notification.permission === 'default') void Notification.requestPermission();
    } catch {
      // ignore
    }
    setEndsAt(Date.now() + left * 1000);
  };
  const pause = () => setEndsAt(null);
  const reset = () => {
    setEndsAt(null);
    setPhase('work');
    setLeft(work * 60);
  };

  const r = 34;
  const c = 2 * Math.PI * r;
  const done = total ? 1 - left / total : 0;
  const mm = String(Math.floor(left / 60)).padStart(2, '0');
  const ss = String(left % 60).padStart(2, '0');

  return (
    <div className="ws-card flex items-center gap-6" role="timer" aria-label="Pomodoro">
      <svg width="84" height="84" viewBox="0 0 84 84" aria-hidden="true">
        <circle cx="42" cy="42" r={r} fill="none" stroke="var(--color-border)" strokeWidth="1" />
        <circle
          cx="42"
          cy="42"
          r={r}
          fill="none"
          stroke="var(--color-ink)"
          strokeWidth="2"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - done)}
          transform="rotate(-90 42 42)"
          style={{ transition: 'stroke-dashoffset 480ms linear' }}
        />
      </svg>
      <div className="flex-1 min-w-0">
        <div className="paper-label">{phase === 'work' ? 'Enfoque' : 'Descanso'} · ronda {rounds + 1}</div>
        <div className="text-[34px] font-light tabular-nums leading-tight">
          {mm}:{ss}
        </div>
        <div className="flex items-center gap-3 mt-1 text-[12px]" style={{ color: 'var(--color-text-secondary)' }}>
          <label className="flex items-center gap-1">
            Trabajo
            <input
              type="number"
              min={5}
              max={90}
              value={work}
              onChange={(e) => onChange({ work: Math.max(5, Math.min(90, Number(e.target.value) || 25)), rest })}
              className="ws-mini-input"
              aria-label="Minutos de trabajo"
            />
          </label>
          <label className="flex items-center gap-1">
            Descanso
            <input
              type="number"
              min={1}
              max={30}
              value={rest}
              onChange={(e) => onChange({ work, rest: Math.max(1, Math.min(30, Number(e.target.value) || 5)) })}
              className="ws-mini-input"
              aria-label="Minutos de descanso"
            />
          </label>
        </div>
      </div>
      <div className="flex gap-1">
        {endsAt === null ? (
          <button type="button" className="mac-icon-btn" onClick={start} aria-label="Empezar">
            <Play size={16} strokeWidth={1.5} />
          </button>
        ) : (
          <button type="button" className="mac-icon-btn" onClick={pause} aria-label="Pausa">
            <Pause size={16} strokeWidth={1.5} />
          </button>
        )}
        <button type="button" className="mac-icon-btn" onClick={reset} aria-label="Reiniciar">
          <RotateCcw size={16} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}
