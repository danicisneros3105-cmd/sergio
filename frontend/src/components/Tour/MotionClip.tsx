// Mini motion-graphics clips for the tour, silent, one per step (owner, 4 Nov
// 2026: «crea mini videos de motion graphics sin sonido, solo que muestren
// cómo funciona todo, agrégalos al tutorial»). Each clip is a short loop
// (5-7 s) drawn with the app's own colours, so it is crisp at any size, light
// or dark, and weighs nothing: a cursor moves, text types, cards appear, the
// way the real screen does it. A thin bar shows the clip's progress; a tap
// pauses it. With «reduce motion» the clip shows its last frame, still.
import { useEffect, useId, useMemo, useState, type CSSProperties, type ReactNode } from 'react';
import { Pause, Play } from 'lucide-react';
import './motion-clips.css';

type Point = { x: number; y: number; t: number; click?: boolean };

function d(ms: number, extra: CSSProperties = {}): CSSProperties {
  return { ['--d' as string]: `${ms}ms`, ...extra };
}

/** A pointer that follows *path* (x, y in % of the clip; t in ms). */
function Cursor({ path, length }: { path: Point[]; length: number }) {
  const raw = useId();
  const name = `mc-cur-${raw.replace(/[^a-zA-Z0-9]/g, '')}`;
  const frames = useMemo(() => {
    const at = (p: Point) => Math.min(100, (p.t / length) * 100).toFixed(2);
    const rows = path.map((p) => `${at(p)}% { left: ${p.x}%; top: ${p.y}%; }`);
    const clicks = path
      .filter((p) => p.click)
      .map((p) => {
        const a = (p.t / length) * 100;
        return `${a.toFixed(2)}% { transform: scale(1); } ${(a + 1.5).toFixed(2)}% { transform: scale(0.82); } ${(a + 3).toFixed(2)}% { transform: scale(1); }`;
      });
    return `@keyframes ${name} { 0% { left: ${path[0].x}%; top: ${path[0].y}%; } ${rows.join(' ')} 100% { left: ${path[path.length - 1].x}%; top: ${path[path.length - 1].y}%; } }
@keyframes ${name}-press { ${clicks.join(' ')} }`;
  }, [path, length, name]);
  return (
    <>
      <style>{frames}</style>
      <span
        className="mc-cursor"
        style={{ animation: `${name} ${length}ms cubic-bezier(.45,.05,.3,1) both` }}
      >
        <svg viewBox="0 0 16 20" width="14" height="18" style={{ animation: `${name}-press ${length}ms linear both` }}>
          <path d="M1 1l13 9.5-6 1.2 3.2 6.8-2.6 1.2-3.2-6.9L1 17z" />
        </svg>
      </span>
      {path
        .filter((p) => p.click)
        .map((p) => (
          <span key={p.t} className="mc-ripple" style={d(p.t, { left: `${p.x}%`, top: `${p.y}%` })} />
        ))}
    </>
  );
}

/** Text that types itself, a letter at a time. */
function Type({ text, at, ms = 1200 }: { text: string; at: number; ms?: number }) {
  return (
    <span className="mc-type" style={d(at, { ['--n' as string]: text.length, ['--t' as string]: `${ms}ms` })}>
      {text}
    </span>
  );
}

// -- the clips ---------------------------------------------------------------

const Hello = () => (
  <div className="mc-scene mc-center">
    <span className="mc-logo mc-pop" style={d(100)} />
    <div className="mc-row" style={{ marginTop: 14 }}>
      {['Chat', 'Voz', 'Nodes', 'Video', 'Cowork'].map((w, i) => (
        <span key={w} className="mc-chip mc-in" style={d(700 + i * 220)}>
          {w}
        </span>
      ))}
    </div>
  </div>
);

const Chat = ({ length }: { length: number }) => (
  <div className="mc-scene mc-col">
    <div className="mc-thread">
      <span className="mc-bubble me mc-pop" style={d(2300)}>
        Resume mis correos de hoy
      </span>
      <span className="mc-bubble mc-typing mc-transient mc-in" style={d(2600, { ['--out' as string]: '3500ms' })}>
        <i />
        <i />
        <i />
      </span>
      <span className="mc-bubble them mc-pop" style={d(3600)}>
        Tiene 3 importantes, señor.
        <b className="mc-line mc-grow" style={d(4000)} />
        <b className="mc-line short mc-grow" style={d(4300)} />
      </span>
    </div>
    <div className="mc-input">
      <span className="mc-sent" style={{ ['--out' as string]: '2250ms' }}>
        <Type text="Resume mis correos de hoy" at={400} ms={1300} />
      </span>
      <span className="mc-send mc-flash" style={d(2150)} />
    </div>
    <Cursor length={length} path={[{ x: 60, y: 120, t: 0 }, { x: 60, y: 120, t: 1600 }, { x: 92, y: 88, t: 2100, click: true }, { x: 80, y: 120, t: 3200 }]} />
  </div>
);

const Voice = () => (
  <div className="mc-scene mc-center">
    <span className="mc-orb" />
    <span className="mc-wave">
      {Array.from({ length: 11 }, (_, i) => (
        <i key={i} style={{ animationDelay: `${(i % 6) * 90}ms` }} />
      ))}
    </span>
    <p className="mc-caption">
      {'Sergio, ¿qué tengo hoy?'.split(' ').map((w, i) => (
        <span key={i} className="mc-in mc-word" style={d(300 + i * 260)}>
          {w}
        </span>
      ))}
    </p>
    <span className="mc-card mc-pop" style={d(2300)}>
      2 reuniones · 1 pendiente · lluvia a las 5
    </span>
  </div>
);

const Models = ({ length }: { length: number }) => (
  <div className="mc-scene mc-col">
    <div className="mc-list">
      {['Gemini 4 Argon', 'GPT-5.6 Sol', 'Claude Opus 5.5', 'DeepSeek V4'].map((m, i) => (
        <span key={m} className={`mc-item mc-in${i === 2 ? ' mc-pick' : ''}`} style={d(150 + i * 140, i === 2 ? { ['--pick' as string]: '2050ms' } : {})}>
          {m}
          {i === 2 && <b className="mc-check mc-pop" style={d(2150)} />}
        </span>
      ))}
      <span className="mc-item mc-dim mc-in" style={d(750)}>
        + cientos por OpenRouter
      </span>
    </div>
    <Cursor length={length} path={[{ x: 85, y: 110, t: 0 }, { x: 85, y: 110, t: 900 }, { x: 45, y: 54, t: 1900, click: true }, { x: 60, y: 110, t: 3200 }]} />
  </div>
);

const NODES: [string, string][] = [
  ['R', 'Rihno'],
  ['M', 'Manchas'],
  ['H', 'Hous'],
  ['T', 'Tennessee'],
];
const Nodes = () => (
  <div className="mc-scene mc-col">
    <div className="mc-row" style={{ gap: 18 }}>
      {NODES.map(([k, n], i) => (
        <span key={n} className={`mc-node mc-pop${i === 1 ? ' mc-busy' : ''}`} style={d(150 + i * 160)}>
          <b>{k}</b>
          <small>{n}</small>
        </span>
      ))}
    </div>
    <span className="mc-task mc-fly" style={d(1100)}>
      Investiga a 3 competidores
    </span>
    <span className="mc-bar">
      <i className="mc-fill" style={d(1900, { ['--t' as string]: '2200ms' })} />
    </span>
    <span className="mc-done mc-pop" style={d(4200)}>
      Listo · informe en su chat
    </span>
  </div>
);

const Video = ({ length }: { length: number }) => (
  <div className="mc-scene mc-col">
    <div className="mc-row" style={{ gap: 8 }}>
      {['Datos raros', 'Historia con giro', 'Ranking'].map((t, i) => (
        <span key={t} className={`mc-thumb mc-pop${i === 1 ? ' mc-pick' : ''}`} style={d(150 + i * 180, i === 1 ? { ['--pick' as string]: '1500ms' } : {})}>
          <i />
          <small>{t}</small>
        </span>
      ))}
    </div>
    <div className="mc-row mc-board" style={{ gap: 5 }}>
      {[0, 1, 2, 3, 4].map((i) => (
        <span key={i} className="mc-frame mc-slide" style={d(2000 + i * 160)} />
      ))}
    </div>
    <span className="mc-bar">
      <i className="mc-fill" style={d(2900, { ['--t' as string]: '1800ms' })} />
    </span>
    <span className="mc-done mc-pop" style={d(4800)}>
      Video listo: cortes, subtítulos y música
    </span>
    <Cursor length={length} path={[{ x: 50, y: 110, t: 0 }, { x: 50, y: 110, t: 700 }, { x: 50, y: 30, t: 1400, click: true }, { x: 70, y: 110, t: 2400 }]} />
  </div>
);

const Cowork = () => (
  <div className="mc-scene mc-col">
    <div className="mc-input">
      <Type text="Prepara el informe de gastos del mes" at={200} ms={1300} />
    </div>
    <ol className="mc-steps">
      {['Leer sus facturas', 'Sumar por categoría', 'Hacer el informe'].map((s, i) => (
        <li key={s} className="mc-in" style={d(1700 + i * 300)}>
          <b className="mc-tick" style={d(2600 + i * 450)} />
          {s}
        </li>
      ))}
    </ol>
    <div className="mc-rowcard mc-in" style={d(4100)}>
      <span>Organizador</span>
      <small className="mc-in" style={d(4500)}>
        Hoy · 9:00 dentista · 2 pendientes
      </small>
    </div>
  </div>
);

const Health = () => (
  <div className="mc-scene mc-center">
    <svg className="mc-ring" viewBox="0 0 64 64" width="84" height="84">
      <circle cx="32" cy="32" r="26" />
      <circle className="mc-ring-on" cx="32" cy="32" r="26" style={d(300)} />
    </svg>
    <span className="mc-pill mc-pop" style={d(1800)}>
      Vitamina D · 9:00 <b className="mc-check mc-pop" style={d(2300)} /> Tomada
    </span>
    <span className="mc-row" style={{ gap: 6, marginTop: 10 }}>
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <i key={i} className={`mc-dot mc-pop${i < 5 ? ' on' : ''}`} style={d(2600 + i * 120)} />
      ))}
    </span>
  </div>
);

const Usage = () => (
  <div className="mc-scene mc-col" style={{ gap: 12 }}>
    {[
      ['Hoy', '64%'],
      ['Esta semana', '38%'],
    ].map(([k, w], i) => (
      <span key={k} className="mc-meter">
        <small>{k}</small>
        <span className="mc-bar">
          <i className="mc-fill" style={d(300 + i * 500, { ['--t' as string]: '1400ms', ['--w' as string]: w })} />
        </span>
      </span>
    ))}
    <span className="mc-done mc-pop" style={d(2400)}>
      Plan Free · Configuración → Cuenta
    </span>
  </div>
);

const Split = () => (
  <div className="mc-scene mc-desk">
    <span className="mc-win left">
      <b>Chrome</b>
      <i />
      <i />
    </span>
    <span className="mc-win right">
      <b>Word</b>
      <i />
      <i />
    </span>
    <span className="mc-say mc-in" style={d(200)}>
      «Pon Chrome y Word lado a lado»
    </span>
  </div>
);

const Palette = () => (
  <div className="mc-scene mc-col">
    <div className="mc-row" style={{ gap: 6 }}>
      <kbd className="mc-key" style={d(200)}>
        Ctrl
      </kbd>
      <kbd className="mc-key" style={d(380)}>
        K
      </kbd>
    </div>
    <div className="mc-palette mc-drop" style={d(800)}>
      <div className="mc-input small">
        <Type text="vid" at={1300} ms={500} />
      </div>
      {['Hacer un video', 'Videos programados', 'Galería'].map((r, i) => (
        <span key={r} className={`mc-item mc-in${i === 0 ? ' mc-pick' : ''}`} style={d(1900 + i * 120, i === 0 ? { ['--pick' as string]: '2400ms' } : {})}>
          {r}
        </span>
      ))}
    </div>
  </div>
);

export const CLIPS: Record<string, { length: number; scene: (p: { length: number }) => ReactNode }> = {
  hola: { length: 4200, scene: Hello },
  chat: { length: 6200, scene: Chat },
  voz: { length: 5200, scene: Voice },
  modelos: { length: 5000, scene: Models },
  nodes: { length: 6200, scene: Nodes },
  video: { length: 6800, scene: Video },
  auto: { length: 6400, scene: Cowork },
  salud: { length: 5200, scene: Health },
  uso: { length: 4400, scene: Usage },
  dividir: { length: 4400, scene: Split },
  atajos: { length: 4600, scene: Palette },
};

function reduced(): boolean {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
}

/** One clip, looping, with a progress bar and a pause button. */
export function MotionClip({ clip, label }: { clip: string; label: string }) {
  const found = CLIPS[clip];
  const [run, setRun] = useState(0);
  const [paused, setPaused] = useState(false);
  const still = useMemo(reduced, []);
  useEffect(() => {
    if (!found || paused || still) return;
    const id = window.setTimeout(() => setRun((n) => n + 1), found.length + 700);
    return () => window.clearTimeout(id);
  }, [found, run, paused, still]);
  if (!found) return null;
  const Scene = found.scene;
  return (
    <figure
      className={`mc${paused ? ' mc-paused' : ''}${still ? ' mc-static' : ''}`}
      style={{ ['--len' as string]: `${found.length}ms` }}
      aria-label={`Animación: ${label}`}
    >
      <div className="mc-stage" key={run} aria-hidden="true">
        <Scene length={found.length} />
        <span className="mc-progress" />
      </div>
      {!still && (
        <button
          type="button"
          className="mc-toggle"
          aria-label={paused ? 'Reproducir la animación' : 'Pausar la animación'}
          onClick={() => {
            if (paused) setRun((n) => n + 1);
            setPaused(!paused);
          }}
        >
          {paused ? <Play size={12} /> : <Pause size={12} />}
        </button>
      )}
    </figure>
  );
}

export default MotionClip;
