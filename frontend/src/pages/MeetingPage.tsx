// Reunión: record a meeting or a call from the phone or the computer and get
// the minutes — summary, key points, who said what, tasks. «Boca abajo» turns
// the screen black and keeps it awake so the phone can lie face down on the
// table and go on recording (a phone switched off cannot record: nothing can).

import { useEffect, useRef, useState } from 'react';
import { BookmarkPlus, CheckCircle2, Copy, Download, History, Laptop, Mic, Moon, Phone, Smartphone, Square, Users, MessagesSquare } from 'lucide-react';
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
  id?: string;
  titulo: string;
  resumen: string;
  puntos_clave: string[];
  decisiones: string[];
  tareas?: Array<{ quien: string; que: string; cuando?: string }>;
  recordatorios_creados?: string[];
  personas: Person[];
  transcripcion: Array<{ t: string; quien: string; texto: string }>;
  markdown: string;
  when?: string;
  seconds?: number;
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
  const [systemAudio, setSystemAudio] = useState(false);
  const [liveNoteInput, setLiveNoteInput] = useState('');
  const [liveNotes, setLiveNotes] = useState<string[]>([]);
  const [minutes, setMinutes] = useState<Minutes | null>(null);
  const [history, setHistory] = useState<Minutes[]>([]);
  const [error, setError] = useState('');
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const started = useRef(0);
  const lock = useRef<{ release: () => Promise<void> } | null>(null);
  const stopAll = useRef<() => void>(() => {});

  const loadHistory = async () => {
    try {
      const res = await apiFetch('/v1/meeting/history?limit=12');
      if (res.ok) {
        const d = await res.json();
        if (Array.isArray(d.meetings)) setHistory(d.meetings);
      }
    } catch {
      // ignore offline
    }
  };

  useEffect(() => {
    void loadHistory();
  }, []);

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

  const addLiveBookmark = () => {
    const clean = liveNoteInput.trim() || 'Momento importante marcado';
    const stamp = clock(seconds);
    setLiveNotes((prev) => [...prev, `[${stamp}] ${clean}`]);
    setLiveNoteInput('');
    toast.success(`Marcador guardado en ${stamp}`);
  };

  const triggerPhoneMeeting = async () => {
    try {
      const res = await apiFetch('/v1/meeting/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: state === 'grabando' ? 'stop' : 'start', kind, device: 'phone' }),
      });
      if (res.ok) {
        toast.success(state === 'grabando' ? 'Orden enviada para detener en el teléfono.' : 'Orden enviada: grabando reunión en su teléfono.');
      }
    } catch {
      toast.error('No se pudo contactar con el teléfono.');
    }
  };

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
      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const allTracks: MediaStreamTrack[] = [...micStream.getTracks()];
      const ctx = new AudioContext();
      const dest = ctx.createMediaStreamDestination();
      ctx.createMediaStreamSource(micStream).connect(dest);

      if (systemAudio && navigator.mediaDevices.getDisplayMedia) {
        try {
          const sysStream = await navigator.mediaDevices.getDisplayMedia({ audio: true, video: true });
          sysStream.getVideoTracks().forEach((vt) => vt.stop());
          allTracks.push(...sysStream.getTracks());
          if (sysStream.getAudioTracks().length > 0) {
            ctx.createMediaStreamSource(new MediaStream(sysStream.getAudioTracks())).connect(dest);
          }
        } catch {
          toast.info('Grabando con micrófono (no se compartió audio del sistema).');
        }
      }

      const mixedStream = dest.stream.getAudioTracks().length > 0 ? dest.stream : micStream;
      const type = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find((t) => MediaRecorder.isTypeSupported?.(t)) || '';
      const r = new MediaRecorder(mixedStream, type ? { mimeType: type, audioBitsPerSecond: 48000 } : undefined);
      chunks.current = [];
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.start(3000); // a piece every 3 s: a crash keeps what was said
      rec.current = r;
      // the level, to see it hears
      const an = ctx.createAnalyser();
      ctx.createMediaStreamSource(mixedStream).connect(an);
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
        allTracks.forEach((t) => t.stop());
        void ctx.close();
        void lock.current?.release().catch(() => undefined);
        lock.current = null;
      };
      started.current = Date.now();
      setSeconds(0);
      setLiveNotes([]);
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
    const notesSnapshot = liveNotes.join('\n');
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
      if (notesSnapshot) form.append('live_notes', notesSnapshot);
      form.append('auto_remind', 'true');
      try {
        const res = await apiFetch('/v1/meeting/summarize', { method: 'POST', body: form });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'No pude escribir el acta.');
        setMinutes(data as Minutes);
        void loadHistory();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No pude escribir el acta.');
      } finally {
        setState('listo');
      }
    };
    r.stop();
  };

  // Multi-device remote trigger listener (PC -> Phone or Phone -> PC)
  useEffect(() => {
    const onCmd = (ev: Event) => {
      const detail = (ev as CustomEvent<{ action?: string; params?: { kind?: Kind } }>).detail;
      if (!detail) return;
      if (detail.action === 'record_meeting' && state === 'listo') {
        if (detail.params?.kind) setKind(detail.params.kind);
        void start();
      } else if (detail.action === 'stop_meeting' && state === 'grabando') {
        stop();
      }
    };
    window.addEventListener('sergio:device-command', onCmd);
    return () => window.removeEventListener('sergio:device-command', onCmd);
  });

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

        <div className="flex flex-wrap items-center justify-center gap-2 my-2">
          <button
            type="button"
            className="paper-button"
            data-variant={systemAudio ? undefined : 'quiet'}
            disabled={state !== 'listo'}
            onClick={() => setSystemAudio((v) => !v)}
            title="Captura tanto su micrófono como el audio de Zoom, Meet, Teams o WhatsApp"
          >
            <Laptop size={14} /> {systemAudio ? 'Micrófono + Audio de llamada (Zoom/Meet)' : 'Solo micrófono'}
          </button>
          <button
            type="button"
            className="paper-button"
            data-variant="quiet"
            onClick={() => void triggerPhoneMeeting()}
            title="Ordenar a su teléfono que empiece o termine de grabar la reunión"
          >
            <Smartphone size={14} /> Grabar desde mi teléfono
          </button>
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
          <strong className="meet-clock">{state === 'escribiendo' ? 'Escribiendo el acta ejecutiva…' : clock(seconds)}</strong>
          <span className="meet-consent">Avise a todos que está grabando · Tareas y recordatorios se agendan automáticamente.</span>
          {state === 'grabando' && (
            <div className="flex flex-col items-center gap-2 w-full max-w-md mt-2">
              <div className="flex gap-2 w-full">
                <input
                  type="text"
                  className="ws-capture flex-1 px-3 py-1.5 text-sm"
                  placeholder="Anotar acuerdo o momento clave en vivo…"
                  value={liveNoteInput}
                  onChange={(e) => setLiveNoteInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addLiveBookmark()}
                />
                <button type="button" className="paper-button" onClick={addLiveBookmark}>
                  <BookmarkPlus size={14} /> Marcar
                </button>
              </div>
              {liveNotes.length > 0 && (
                <div className="text-xs opacity-75 w-full text-left">
                  {liveNotes.map((n, idx) => (
                    <div key={idx}>{n}</div>
                  ))}
                </div>
              )}
              <button type="button" className="paper-button" data-variant="quiet" onClick={() => setDark(true)} title="Deje el teléfono boca abajo: sigue grabando">
                <Moon size={15} /> Boca abajo
              </button>
            </div>
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
            {minutes.decisiones?.length > 0 && (
              <div className="my-2">
                <strong className="text-xs uppercase tracking-wider opacity-70">Decisiones cerradas</strong>
                <ul className="meet-points">
                  {minutes.decisiones.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              </div>
            )}
            {minutes.puntos_clave?.length > 0 && (
              <ul className="meet-points">
                {minutes.puntos_clave.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            )}
            {minutes.recordatorios_creados && minutes.recordatorios_creados.length > 0 && (
              <div className="my-2 p-2.5 rounded-lg border border-black/10 text-xs flex items-start gap-2">
                <CheckCircle2 size={15} className="shrink-0 mt-0.5" />
                <div>
                  <b>Recordatorios proactivos agendados ({minutes.recordatorios_creados.length}):</b>
                  <ul className="mt-1 space-y-0.5">
                    {minutes.recordatorios_creados.map((r, i) => (
                      <li key={i}>• {r}</li>
                    ))}
                  </ul>
                </div>
              </div>
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

        {history.length > 0 && (
          <section className="mt-6 pt-4 border-t border-black/10">
            <h3 className="text-xs font-semibold uppercase tracking-wider opacity-70 flex items-center gap-1.5 mb-2">
              <History size={13} /> Actas recientes ({history.length})
            </h3>
            <div className="space-y-1.5">
              {history.slice(0, 6).map((item, idx) => (
                <button
                  key={item.id || idx}
                  type="button"
                  onClick={() => setMinutes(item)}
                  className="w-full text-left px-3 py-2 rounded-lg border border-black/10 hover:bg-black/5 transition flex items-center justify-between text-sm"
                >
                  <span className="font-medium truncate">{item.titulo || 'Reunión'}</span>
                  <span className="text-xs opacity-60 shrink-0 ml-2">{item.when || ''}</span>
                </button>
              ))}
            </div>
          </section>
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
