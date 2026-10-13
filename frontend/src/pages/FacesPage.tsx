// Recognition is approximate. Sensitive actions use Windows Hello in the companion.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Lock, ScanFace, Trash2, UserPlus, X } from 'lucide-react';
import { apiFetch } from '../lib/api';
import '../components/Studio/studio.css';

interface Person {
  name: string;
  samples: number;
  angles?: number;
}

interface Status {
  passcode_set: boolean;
  face_allowed: boolean;
  passcode_reason: string;
  attempts_left: number;
  owner: string;
}

type Mode =
  | { kind: 'home' }
  | { kind: 'passcode'; then: 'setup' | 'unlock' }
  | { kind: 'scan'; who: string; consent: boolean; round: 1 | 2 }
  | { kind: 'unlock' }
  | { kind: 'done'; title: string; text: string; ok: boolean };

const TICKS = 60;
const REASON_ES: Record<string, string> = {
  sin_codigo: 'Face ID necesita un código de respaldo.',
  reinicio: 'Sergio se reinició: introduzca su código una vez.',
  intentos: 'Cinco intentos fallidos: introduzca su código.',
  inactivo: 'Hace más de 48 horas que no desbloquea: introduzca su código.',
  codigo_antiguo: 'Hace más de 6 días y medio que no usa su código: introdúzcalo.',
  bloqueado: 'Lo bloqueó usted: introduzca su código.',
};

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body.detail ?? `Error ${res.status}`;
  } catch {
    return `Error ${res.status}`;
  }
}

/** Apple-style Face ID glyph, Sergio's colours. */
export function FaceGlyph({ size = 72, state = 'idle' }: { size?: number; state?: 'idle' | 'scan' | 'ok' | 'fail' }) {
  return (
    <svg className="faceid-glyph" data-state={state} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <path d="M6 20V12a6 6 0 0 1 6-6h8M44 6h8a6 6 0 0 1 6 6v8M58 44v8a6 6 0 0 1-6 6h-8M20 58h-8a6 6 0 0 1-6-6v-8" />
      {state === 'ok' ? (
        <path className="faceid-check" d="M20 33l8 8 16-18" />
      ) : (
        <>
          <path d="M22 24v5M42 24v5M32 24v12h-3M24 44c5 4 11 4 16 0" />
        </>
      )}
    </svg>
  );
}

function Ring({ lit, size }: { lit: boolean[]; size: number }) {
  const r1 = size / 2 - 4;
  const r0 = r1 - 14;
  return (
    <svg className="faceid-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      {lit.map((on, i) => {
        const a = (i / TICKS) * Math.PI * 2;
        const c = size / 2;
        return (
          <line
            key={i}
            x1={c + Math.cos(a) * r0}
            y1={c - Math.sin(a) * r0}
            x2={c + Math.cos(a) * r1}
            y2={c - Math.sin(a) * r1}
            data-on={on ? '1' : undefined}
          />
        );
      })}
    </svg>
  );
}

function PinPad({ title, subtitle, onDone, error }: { title: string; subtitle: string; onDone: (code: string) => void; error: string }) {
  const [code, setCode] = useState('');
  const press = (d: string) => setCode((c) => (c.length < 12 ? c + d : c));
  return (
    <div className="faceid-pin">
      <Lock size={22} />
      <h2>{title}</h2>
      <p>{subtitle}</p>
      <div className="faceid-dots" aria-label={`${code.length} cifras`}>
        {Array.from({ length: Math.max(6, code.length) }, (_, i) => (
          <i key={i} data-on={i < code.length ? '1' : undefined} />
        ))}
      </div>
      {error && <p className="faceid-error" role="alert">{error}</p>}
      <div className="faceid-keys">
        {['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', '⌫'].map((k, i) =>
          k ? (
            <button
              key={i}
              type="button"
              onClick={() => (k === '⌫' ? setCode((c) => c.slice(0, -1)) : press(k))}
              aria-label={k === '⌫' ? 'Borrar' : k}
            >
              {k}
            </button>
          ) : (
            <span key={i} />
          ),
        )}
      </div>
      <button type="button" className="paper-button" disabled={code.length < 6} onClick={() => (onDone(code), setCode(''))}>
        Continuar
      </button>
    </div>
  );
}

export function FacesPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [mode, setMode] = useState<Mode>({ kind: 'home' });
  const [status, setStatus] = useState<Status | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [lit, setLit] = useState<boolean[]>(() => Array(TICKS).fill(false));
  const [say, setSay] = useState('');
  const [error, setError] = useState('');
  const [other, setOther] = useState({ name: '', consent: false });
  const shots = useRef<Blob[]>([]);

  const load = useCallback(async () => {
    const [s, p] = await Promise.all([apiFetch('/v1/faces/faceid'), apiFetch('/v1/faces')]);
    if (s.ok) setStatus(await s.json());
    if (p.ok) setPeople((await p.json()).people);
  }, []);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };
  useEffect(() => stopCamera, []);

  const startCamera = async (): Promise<boolean> => {
    // The <video> appears with the camera view: wait for it to be on screen.
    for (let i = 0; i < 20 && !videoRef.current; i++) await new Promise((r) => requestAnimationFrame(r));
    if (streamRef.current) {
      if (videoRef.current && videoRef.current.srcObject !== streamRef.current) {
        videoRef.current.srcObject = streamRef.current;
        await videoRef.current.play().catch(() => {});
      }
      return true;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' } });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      return true;
    } catch {
      setError('No pude abrir la cámara. Permita el acceso a la cámara en el navegador.');
      return false;
    }
  };

  const frame = (): Promise<Blob | null> =>
    new Promise((resolve) => {
      const video = videoRef.current;
      if (!video || !video.videoWidth) return resolve(null);
      const canvas = document.createElement('canvas');
      canvas.width = 640;
      canvas.height = Math.round((video.videoHeight / video.videoWidth) * 640);
      canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.85);
    });

  // -- setting up: two slow circles with the head ---------------------------
  useEffect(() => {
    if (mode.kind !== 'scan') return;
    let stop = false;
    const ring: boolean[] = Array(TICKS).fill(false);
    setLit(ring.slice());
    setSay('Coloque la cara dentro del círculo');
    const started = Date.now();
    (async () => {
      if (!(await startCamera())) return;
      while (!stop) {
        const blob = await frame();
        if (blob) {
          const form = new FormData();
          form.append('image', blob, 'f.jpg');
          const res = await apiFetch('/v1/faces/pose', { method: 'POST', body: form }).catch(() => null);
          const pose = res && res.ok ? await res.json() : null;
          if (pose?.face) {
            if (pose.faces > 1) setSay('Solo una persona frente a la cámara');
            else {
              shots.current.push(blob);
              const tilt = Math.hypot(pose.yaw, pose.pitch);
              if (tilt < 8) setSay('Mueva la cabeza despacio para completar el círculo');
              else {
                // Shown mirrored: turning to your left lights the left side.
                const a = (Math.atan2(pose.pitch, -pose.yaw) + Math.PI * 2) % (Math.PI * 2);
                const k = Math.round((a / (Math.PI * 2)) * TICKS) % TICKS;
                for (let d = -2; d <= 2; d++) ring[(k + d + TICKS) % TICKS] = true;
                setLit(ring.slice());
              }
            }
          } else setSay('Coloque la cara dentro del círculo');
        }
        const done = ring.filter(Boolean).length / TICKS >= 0.8 && Date.now() - started > 2500;
        if (done || Date.now() - started > 30000) break;
        await new Promise((r) => setTimeout(r, 120));
      }
      if (stop) return;
      if (mode.round === 1) {
        setMode({ ...mode, round: 2 });
        return;
      }
      // Save: the sharpest shots of each angle, both rounds.
      const form = new FormData();
      form.append('name', mode.who);
      form.append('consent', String(mode.consent));
      const pick = shots.current.filter((_, i) => i % Math.max(1, Math.ceil(shots.current.length / 60)) === 0).slice(0, 60);
      pick.forEach((b, i) => form.append('images', b, `s${i}.jpg`));
      shots.current = [];
      stopCamera();
      const res = await apiFetch('/v1/faces/scan', { method: 'POST', body: form });
      if (!res.ok) {
        setMode({ kind: 'done', ok: false, title: 'No se completó', text: await readError(res) });
        return;
      }
      await load();
      setMode({
        kind: 'done',
        ok: true,
        title: mode.who === (status?.owner || mode.who) ? 'Face ID está listo' : `${mode.who} guardado`,
        text: 'Ahora puede desbloquear mirando a la pantalla.',
      });
    })();
    return () => {
      stop = true;
    };
  }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  // -- unlocking: look, do the random movement, done ------------------------
  const unlock = async () => {
    setError('');
    const cRes = await apiFetch('/v1/faces/faceid/challenge', { method: 'POST' });
    const challenge = cRes.ok ? await cRes.json() : null;
    if (!challenge) return setError(await readError(cRes));
    if (challenge.passcode_required) {
      setError('');
      return setMode({ kind: 'passcode', then: 'unlock' });
    }
    setMode({ kind: 'unlock' });
    if (!(await startCamera())) return;
    setSay(challenge.say);
    await new Promise((r) => setTimeout(r, 350));
    const frames: Blob[] = [];
    for (let i = 0; i < 12; i++) {
      const b = await frame();
      if (b) frames.push(b);
      await new Promise((r) => setTimeout(r, 140));
    }
    const form = new FormData();
    form.append('nonce', challenge.nonce);
    frames.forEach((b, i) => form.append('images', b, `u${i}.jpg`));
    setSay('Comprobando…');
    const res = await apiFetch('/v1/faces/faceid/unlock', { method: 'POST', body: form });
    stopCamera();
    const out = res.ok ? await res.json() : { ok: false, message: await readError(res) };
    await load();
    if (out.passcode_required && !out.message) {
      setError('');
      return setMode({ kind: 'passcode', then: 'unlock' });
    }
    setMode(
      out.ok
        ? { kind: 'done', ok: true, title: `Hola, ${out.name || 'señor'}`, text: `Desbloqueado en ${out.ms} ms.` }
        : {
            kind: 'done',
            ok: false,
            title: 'No se pudo',
            text: `${out.message || 'Inténtelo de nuevo.'} ${
              out.attempts_left === 0
                ? 'Ahora le pediré su código.'
                : out.attempts_left === 1
                  ? 'Queda 1 intento antes de pedir el código.'
                  : `Quedan ${out.attempts_left ?? '—'} intentos antes de pedir el código.`
            }`,
          },
    );
  };

  const submitPasscode = async (code: string, then: 'setup' | 'unlock') => {
    setError('');
    const form = new FormData();
    form.append('code', code);
    if (!status?.passcode_set) {
      const res = await apiFetch('/v1/faces/faceid/passcode', { method: 'POST', body: form });
      if (!res.ok) return setError(await readError(res));
      await load();
      return setMode(then === 'setup' ? { kind: 'scan', who: status?.owner || 'Señor', consent: true, round: 1 } : { kind: 'home' });
    }
    const res = await apiFetch('/v1/faces/faceid/passcode/check', { method: 'POST', body: form });
    const out = res.ok ? await res.json() : { ok: false };
    if (!out.ok) return setError(out.wait ? `Espere ${out.wait} s antes de volver a intentarlo.` : 'Código incorrecto.');
    await load();
    setMode(then === 'setup' ? { kind: 'scan', who: status?.owner || 'Señor', consent: true, round: 1 } : { kind: 'done', ok: true, title: 'Desbloqueado', text: 'Face ID vuelve a estar disponible.' });
  };

  const setup = () => {
    setError('');
    shots.current = [];
    if (!status?.passcode_set) return setMode({ kind: 'passcode', then: 'setup' });
    setMode({ kind: 'scan', who: status.owner || 'Señor', consent: true, round: 1 });
  };

  const forget = async (person: string) => {
    if (!window.confirm(`¿Olvidar la cara de ${person}?`)) return;
    const res = await apiFetch(`/v1/faces/${encodeURIComponent(person)}`, { method: 'DELETE' });
    if (res.ok) load();
  };

  const enrolled = !!status?.owner;
  const camera = mode.kind === 'scan' || mode.kind === 'unlock';

  return (
    <div className="faceid-page">
      <div className="faceid-stage" data-mode={mode.kind}>
        {camera ? (
          <>
            <div className="faceid-view">
              <video ref={videoRef} muted playsInline />
              <Ring lit={mode.kind === 'scan' ? lit : Array(TICKS).fill(true)} size={300} />
            </div>
            <p className="faceid-say" aria-live="polite">
              {mode.kind === 'scan' && mode.round === 2 && lit.filter(Boolean).length === 0
                ? 'Primera exploración completada. Haga otra vuelta.'
                : say}
            </p>
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => (stopCamera(), setMode({ kind: 'home' }))}>
              Cancelar
            </button>
          </>
        ) : mode.kind === 'passcode' ? (
          <PinPad
            title={status?.passcode_set ? 'Introduzca su código' : 'Cree un código'}
            subtitle={
              status?.passcode_set
                ? REASON_ES[status.passcode_reason] || 'Código de Sergio para este reconocimiento.'
                : 'De 6 a 12 cifras. Se pide tras reiniciar, tras 5 fallos y tras 48 horas.'
            }
            error={error}
            onDone={(c) => submitPasscode(c, mode.then)}
          />
        ) : mode.kind === 'done' ? (
          <div className="faceid-done" data-ok={mode.ok ? '1' : '0'} role="status">
            <span className="faceid-badge">{mode.ok ? <Check size={44} strokeWidth={2.4} /> : <X size={44} strokeWidth={2.4} />}</span>
            <h1>{mode.title}</h1>
            <p>{mode.text}</p>
            <button type="button" className="paper-button" onClick={() => setMode({ kind: 'home' })}>
              Listo
            </button>
          </div>
        ) : (
          <div className="faceid-home">
            <span className="face-presence-mark"><FaceGlyph size={84} /></span>
            <h1>Reconocimiento facial</h1>
            <p>
              Sergio aprende sus rasgos y le reconoce para conversar. Un reto de movimiento reduce errores, pero una webcam no reemplaza la cámara de profundidad de Face ID.
            </p>
            {error && <p className="faceid-error">{error}</p>}
            <div className="faceid-actions">
              {enrolled ? (
                <>
                  <button type="button" className="paper-button" onClick={unlock}>
                    <ScanFace size={16} /> Probar reconocimiento
                  </button>
                  <button type="button" className="paper-button" data-variant="quiet" onClick={setup}>
                    Volver a configurar
                  </button>
                </>
              ) : (
                <button type="button" className="paper-button" onClick={setup}>
                  <ScanFace size={16} /> Configurar mi rostro
                </button>
              )}
            </div>
            {status && (
              <ul className="faceid-facts">
                <li data-on={status.passcode_set ? '1' : undefined}>
                  {status.passcode_set ? 'Código de respaldo activo' : 'Sin código de respaldo todavía'}
                </li>
                <li data-on={status.face_allowed ? '1' : undefined}>
                  {status.face_allowed
                    ? `Reconocimiento disponible · ${status.attempts_left} intentos`
                    : REASON_ES[status.passcode_reason] || 'Face ID no disponible'}
                </li>
                <li data-on="1">Su cara se guarda cifrada, nunca como foto</li>
              </ul>
            )}
            {status?.passcode_set && (
              <button
                type="button"
                className="faceid-link"
                onClick={async () => (await apiFetch('/v1/faces/faceid/lock', { method: 'POST' }), load())}
              >
                <Lock size={13} /> Bloquear ahora
              </button>
            )}
          </div>
        )}
      </div>

      <aside className="face-system-proof"><Lock size={20} /><div><strong>Usted confirma. El sistema verifica.</strong><p>Las acciones sensibles requieren consentimiento y Windows Hello: rostro con cámara compatible, huella o PIN. Las muestras de la webcam no autorizan acciones.</p><a href="ms-settings:signinoptions">Configurar Windows Hello ↗</a></div></aside>

      {mode.kind === 'home' && (
        <section className="faceid-people">
          <h2>Personas que Sergio reconoce</h2>
          <p>Solo con su permiso. Útil para saber quién habla o quién está en una foto.</p>
          {people.map((p) => (
            <div key={p.name} className="faceid-person">
              <span className="faceid-avatar">{p.name.slice(0, 1).toUpperCase()}</span>
              <span className="flex-1 min-w-0">
                <b>{p.name}</b>
                {p.name === status?.owner && <em> · usted</em>}
                <small>
                  {p.samples} muestras · {p.angles ?? 1} ángulos
                </small>
              </span>
              <button type="button" className="mac-icon-btn" aria-label={`Olvidar a ${p.name}`} onClick={() => forget(p.name)}>
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          <div className="faceid-add">
            <input
              className="paper-input"
              value={other.name}
              onChange={(e) => setOther({ ...other, name: e.target.value })}
              placeholder="Nombre de otra persona"
              maxLength={60}
            />
            <label>
              <input type="checkbox" checked={other.consent} onChange={(e) => setOther({ ...other, consent: e.target.checked })} />
              Esta persona está de acuerdo
            </label>
            <button
              type="button"
              className="paper-button"
              data-variant="quiet"
              disabled={!other.name.trim() || !other.consent}
              onClick={() => {
                shots.current = [];
                setMode({ kind: 'scan', who: other.name.trim(), consent: true, round: 1 });
              }}
            >
              <UserPlus size={15} /> Añadir
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

export default FacesPage;
