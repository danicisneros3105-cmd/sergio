// Reunión: record a meeting or a call from the phone or the computer and get
// the minutes — summary, key points, who said what, tasks. «Boca abajo» turns
// the screen black and keeps it awake so the phone can lie face down on the
// table and go on recording (a phone switched off cannot record: nothing can).

import { useEffect, useRef, useState } from 'react';
import { Copy, Download, Mic, Moon, Phone, Square, Users, MessagesSquare } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';
import { mediaProblem } from '../lib/compat';
import './meeting.css';

interface Person {
  quien: string;
  turnos: number;
  ideas: string[];
  tareas: string[];
}

interface Minutes {
  titulo: string;
  resumen: string;
  puntos_clave: string[];
  decisiones: string[];
  personas: Person[];
  transcripcion: Array<{ t: string; quien: string; texto: string }>;
  markdown: string;
}

type Kind = 'reunión' | 'llamada' | 'conversación';
const KINDS: Kind[] = ['reunión', 'llamada', 'conversación'];
const KIND_ICON = { reunión: Users, llamada: Phone, conversación: MessagesSquare };

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

/** Face down: the phone lying on its screen (beta near ±180°). */
export function faceDown(beta: number | null, gamma: number | null): boolean {
  if (beta === null || gamma === null) return false;
  return Math.abs(beta) > 150 && Math.abs(gamma) < 35;
}

export function MeetingPage() {
  const [kind, setKind] = useState<Kind>('reunión');
  const [state, setState] = useState<'listo' | 'grabando' | 'escribiendo'>('listo');
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [dark, setDark] = useState(false);
  const [minutes, setMinutes] = useState<Minutes | null>(null);
  const [error, setError] = useState('');
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const started = useRef(0);
  const lock = useRef<{ release: () => Promise<void> } | null>(null);
  const stopAll = useRef<() => void>(() => {});

  // While recording: the clock, and the phone turned face down goes dark.
  useEffect(() => {
    if (state !== 'grabando') return;
    const t = window.setInterval(() => setSeconds((Date.now() - started.current) / 1000), 500);
    const onTilt = (e: DeviceOrientationEvent) => setDark((d) => (faceDown(e.beta, e.gamma) ? true : d));
    window.addEventListener('deviceorientation', onTilt);
    return () => {
      window.clearInterval(t);
      window.removeEventListener('deviceorientation', onTilt);
    };
  }, [state]);

  useEffect(() => () => stopAll.current(), []);

  const start = async () => {
    setError('');
    const problem = mediaProblem('micrófono');
    if (problem) {
      setError(problem);
      return;
    }
    try {
      // iPhone asks once for the tilt, inside the tap.
      const ask = (DeviceOrientationEvent as unknown as { requestPermission?: () => Promise<string> }).requestPermission;
      if (ask) void ask().catch(() => undefined);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const type = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find((t) => MediaRecorder.isTypeSupported?.(t)) || '';
      const r = new MediaRecorder(stream, type ? { mimeType: type, audioBitsPerSecond: 32000 } : undefined);
      chunks.current = [];
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.start(5000); // a piece every 5 s: a crash keeps what was said
      rec.current = r;
      // the level, to see it hears
      const ctx = new AudioContext();
      const an = ctx.createAnalyser();
      ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.fftSize);
      let raf = 0;
      const tick = () => {
        an.getByteTimeDomainData(buf);
        let peak = 0;
        for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
        setLevel(peak / 128);
        raf = requestAnimationFrame(tick);
      };
      tick();
      try {
        lock.current = await (navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> } }).wakeLock?.request('screen') ?? null;
      } catch {
        lock.current = null; // the screen may sleep; recording goes on while it can
      }
      stopAll.current = () => {
        cancelAnimationFrame(raf);
        stream.getTracks().forEach((t) => t.stop());
        void ctx.close();
        void lock.current?.release().catch(() => undefined);
        lock.current = null;
      };
      started.current = Date.now();
      setSeconds(0);
      setMinutes(null);
      setState('grabando');
    } catch {
      setError('No pude usar el micrófono. Revise el permiso.');
    }
  };

  const stop = () => {
    const r = rec.current;
    if (!r) return;
    const took = (Date.now() - started.current) / 1000;
    r.onstop = async () => {
      stopAll.current();
      setDark(false);
      setState('escribiendo');
      const audio = new Blob(chunks.current, { type: r.mimeType || 'audio/webm' });
      const form = new FormData();
      form.append('audio', audio, `reunion.${audio.type.includes('mp4') ? 'm4a' : audio.type.includes('ogg') ? 'ogg' : 'webm'}`);
      form.append('kind', kind);
      form.append('seconds', String(Math.round(took)));
      form.append('when', new Date().toLocaleString('es'));
      try {
        const res = await apiFetch('/v1/meeting/summarize', { method: 'POST', body: form });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'No pude escribir el acta.');
        setMinutes(data as Minutes);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No pude escribir el acta.');
      } finally {
        setState('listo');
      }
    };
    r.stop();
  };

  const save = () => {
    if (!minutes) return;
    const url = URL.createObjectURL(new Blob([minutes.markdown], { type: 'text/markdown' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: `${minutes.titulo || 'acta'}.md` });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="paper-page">
      <div className="paper-page-inner meet">
        <h1 className="paper-title">Reunión</h1>

        <div className="meet-kinds" role="radiogroup" aria-label="Qué se graba">
          {KINDS.map((k) => (
            <button key={k} type="button" role="radio" aria-checked={kind === k} disabled={state !== 'listo'} onClick={() => setKind(k)}>
              {(() => {
                const Icon = KIND_ICON[k];
                return <Icon size={14} strokeWidth={1.8} aria-hidden />;
              })()}
              {k[0].toUpperCase() + k.slice(1)}
            </button>
          ))}
        </div>

        <section className="meet-stage" data-state={state}>
          <button
            type="button"
            className="meet-rec"
            onClick={state === 'grabando' ? stop : () => void start()}
            disabled={state === 'escribiendo'}
            aria-label={state === 'grabando' ? 'Terminar y escribir el acta' : 'Empezar a grabar'}
            style={{ ['--lvl' as string]: String(state === 'grabando' ? level : 0) }}
          >
            {state === 'grabando' ? <Square size={26} strokeWidth={2} /> : <Mic size={28} strokeWidth={1.8} />}
          </button>
          <strong className="meet-clock">{state === 'escribiendo' ? 'Escribiendo el acta…' : clock(seconds)}</strong>
          <span className="meet-consent">Avise a todos que está grabando.</span>
          {state === 'grabando' && (
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => setDark(true)} title="Deje el teléfono boca abajo: sigue grabando">
              <Moon size={15} /> Boca abajo
            </button>
          )}
        </section>

        {error && (
          <p className="meet-error" role="alert">
            {error}
          </p>
        )}

        {minutes && (
          <article className="meet-minutes">
            <header>
              <h2>{minutes.titulo}</h2>
              <span>
                <button type="button" className="mac-icon-btn" aria-label="Copiar" title="Copiar" onClick={() => void navigator.clipboard?.writeText(minutes.markdown).then(() => toast.success('Copiada.'))}>
                  <Copy size={15} />
                </button>
                <button type="button" className="mac-icon-btn" aria-label="Descargar" title="Descargar" onClick={save}>
                  <Download size={15} />
                </button>
              </span>
            </header>
            <p className="meet-summary">{minutes.resumen}</p>
            {minutes.puntos_clave?.length > 0 && (
              <ul className="meet-points">
                {minutes.puntos_clave.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            )}
            {minutes.personas?.length > 0 && (
              <div className="meet-people">
                {minutes.personas.map((p) => (
                  <section key={p.quien} className="meet-person">
                    <header>
                      <i aria-hidden>{p.quien.slice(0, 1)}</i>
                      <b>{p.quien}</b>
                      <small>{p.turnos}</small>
                    </header>
                    <ul>
                      {p.ideas.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                      {p.tareas.map((x, i) => (
                        <li key={`t${i}`} className="meet-task">
                          {x}
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )}
            {minutes.transcripcion?.length > 0 && (
              <details className="meet-transcript">
                <summary>Transcripción</summary>
                {minutes.transcripcion.map((r, i) => (
                  <p key={i}>
                    <time>{r.t}</time> <b>{r.quien}</b> {r.texto}
                  </p>
                ))}
              </details>
            )}
          </article>
        )}
      </div>

      {dark && (
        <button type="button" className="meet-dark" onClick={() => setDark(false)} aria-label="Volver a la pantalla">
          <span>{clock(seconds)}</span>
        </button>
      )}
    </div>
  );
}

export default MeetingPage;
