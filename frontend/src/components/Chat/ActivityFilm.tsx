// What Sergio is doing on the computer, in pictures (owner, 1 Nov 2026:
// «debe darte imágenes de lo que está haciendo, como Claude Code app»). While
// the operator works on the real screen, each step leaves a small picture and
// one line; this strip shows them under the conversation as they arrive.

import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../lib/api';

export interface FilmFrame {
  n: number;
  at: number;
  caption: string;
  jpeg_b64: string;
}

export interface Film {
  task: number;
  state: 'idle' | 'working' | 'done' | 'failed' | 'asking';
  goal: string;
  result: string;
  frames: FilmFrame[];
}

const STATE_WORDS: Record<Film['state'], string> = {
  idle: '',
  working: 'Trabajando en su pantalla',
  done: 'Hecho',
  failed: 'No pude terminar',
  asking: 'Espera su respuesta',
};

/** Fold new frames into the strip (a new task starts a new strip). */
export function mergeFilm(prev: Film | null, next: Film): Film {
  if (!prev || prev.task !== next.task) return next;
  const known = new Set(prev.frames.map((f) => f.n));
  return { ...next, frames: [...prev.frames, ...next.frames.filter((f) => !known.has(f.n))] };
}

export function ActivityFilm({ active }: { active: boolean }) {
  const [film, setFilm] = useState<Film | null>(null);
  const last = useRef(0);
  const task = useRef(0);

  useEffect(() => {
    let stop = false;
    let timer = 0;
    const tick = async () => {
      try {
        const r = await apiFetch(`/v1/actividad?since=${last.current}`);
        if (r.ok) {
          const data = (await r.json()) as Film;
          if (data.task !== task.current) last.current = 0;
          task.current = data.task;
          if (data.frames.length) last.current = data.frames[data.frames.length - 1].n;
          if (data.task) setFilm((prev) => mergeFilm(prev, data));
        }
      } catch {
        // no desktop on this device: nothing to show
      }
      if (!stop && document.visibilityState === 'visible') {
        timer = window.setTimeout(tick, active ? 1500 : 6000);
      }
    };
    void tick();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [active]);

  if (!film || !film.frames.length || film.state === 'idle') return null;
  const shown = film.frames.slice(-6);
  return (
    <section className="activity-film" aria-label="Lo que Sergio está haciendo" data-state={film.state}>
      <header>
        <span className="activity-dot" aria-hidden />
        <b>{STATE_WORDS[film.state]}</b>
        <span className="activity-goal">{film.goal}</span>
      </header>
      <ol>
        {shown.map((f) => (
          <li key={f.n}>
            {f.jpeg_b64 && <img src={`data:image/jpeg;base64,${f.jpeg_b64}`} alt={f.caption} loading="lazy" />}
            <span>
              {f.n}. {f.caption}
            </span>
          </li>
        ))}
      </ol>
      {film.state !== 'working' && film.result && <p className="activity-result">{film.result}</p>}
    </section>
  );
}
