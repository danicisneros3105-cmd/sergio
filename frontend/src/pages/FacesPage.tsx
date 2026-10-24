// Recognition is approximate. Sensitive actions use Windows Hello in the companion.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Lock, ScanFace, Trash2, UserPlus, X } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { FaceGlyph } from '../components/Accounts/FaceGlyph';
import '../components/Studio/studio.css';
import { mediaProblem } from '../lib/compat';

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
  | { kind: 'passcode'; then: 'after' | 'unlock' }
  | { kind: 'scan'; who: string; consent: boolean; round: 1 | 2; fresh?: boolean }
  | { kind: 'unlock' }
  | { kind: 'done'; title: string; text: string; ok: boolean; retry?: 'scan' | 'unlock' };

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

export { FaceGlyph } from '../components/Accounts/FaceGlyph';

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

function PinPad({
  title,
  subtitle,
  onDone,
  error,
  onSkip,
}: {
  title: string;
  subtitle: string;
  onDone: (code: string) => void;
  error: string;
  onSkip?: () => void;
}) {
  const [code, setCode] = useState('');
  const press = (d: string) => setCode((c) => (c.length < 12 ? c + d : c));
  // The number keys of the keyboard work too: no need to click each digit.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (/^\d$/.test(e.key)) setCode((c) => (c.length < 12 ? c + e.key : c));
      else if (e.key === 'Backspace') setCode((c) => c.slice(0, -1));
      else if (e.key === 'Enter' && code.length >= 6) {
        onDone(code);
        setCode('');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [code, onDone]);
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
      {onSkip && (
        <button type="button" className="faceid-link" onClick={onSkip}>
          Ahora no
        </button>
      )}
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
  const [firstCode, setFirstCode] = useState('');
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
    const problem = mediaProblem('cámara');
    if (problem) {
      setError(problem);
      return false;
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

  // How lit the face area is (0-255): webcams fail mostly in the dark.
  const brightness = (): number => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return 255;
    const c = document.createElement('canvas');
    c.width = 32;
    c.height = 24;
    const g = c.getContext('2d');
    if (!g) return 255;
    g.drawImage(video, video.videoWidth * 0.25, video.videoHeight * 0.15, video.videoWidth * 0.5, video.videoHeight * 0.7, 0, 0, 32, 24);
    const d = g.getImageData(0, 0, 32, 24).data;
    let sum = 0;
    for (let i = 0; i < d.length; i += 4) sum += 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
    return sum / (d.length / 4);
  };

  // -- setting up: look at the camera, nothing else ---------------------------
  // The ring fills by itself while good frames arrive; turning the head slowly
  // only adds variety. No code is asked first: it comes after, and can wait.
  useEffect(() => {
    if (mode.kind !== 'scan') return;
    let stop = false;
    setLit(Array(TICKS).fill(false));
    setSay('Mire a la cámara');
    const started = Date.now();
    (async () => {
      if (!(await startCamera())) return;
      let good = 0;
      const WANT = 14;
      while (!stop) {
        const blob = await frame();
        if (blob) {
          const form = new FormData();
          form.append('image', blob, 'f.jpg');
          const res = await apiFetch('/v1/faces/pose', { method: 'POST', body: form }).catch(() => null);
          const pose = res && res.ok ? await res.json() : null;
          if (pose?.face && pose.faces > 1) setSay('Solo una persona frente a la cámara');
          else if (pose?.face) {
            shots.current.push(blob);
            good++;
            const progress = Math.round((Math.min(good, WANT) / WANT) * TICKS);
            setLit(Array.from({ length: TICKS }, (_, i) => i < progress));
            setSay(good < 5 ? 'Mire a la cámara' : good < WANT ? 'Gire la cabeza muy despacio' : 'Listo');
          } else setSay(brightness() < 60 ? 'Necesito más luz en su cara' : 'Coloque la cara dentro del círculo');
        }
        if (good >= WANT || Date.now() - started > 30000) break;
        await new Promise((r) => setTimeout(r, 120));
      }
      if (stop) return;
      if (good < 5) {
        stopCamera();
        shots.current = [];
        setMode({
          kind: 'done',
          ok: false,
          title: 'No le vi bien',
          text: brightness() < 60 ? 'Hay poca luz: encienda una lámpara frente a usted e inténtelo de nuevo.' : 'Mire de frente a la cámara, a un brazo de distancia, e inténtelo de nuevo.',
          retry: 'scan',
        });
        return;
      }
      const form = new FormData();
      form.append('name', mode.who);
      form.append('consent', String(mode.consent));
      // Setting up again starts clean: old, poor samples cannot make it fail.
      if (mode.fresh) form.append('replace', 'true');
      const pick = shots.current.filter((_, i) => i % Math.max(1, Math.ceil(shots.current.length / 40)) === 0).slice(0, 40);
      pick.forEach((b, i) => form.append('images', b, `s${i}.jpg`));
      shots.current = [];
      stopCamera();
      const res = await apiFetch('/v1/faces/scan', { method: 'POST', body: form });
      if (!res.ok) {
        setMode({ kind: 'done', ok: false, title: 'No se completó', text: await readError(res), retry: 'scan' });
        return;
      }
      await load();
      const mine = mode.who === (status?.owner || mode.who);
      // Face ID can only unlock with a backup code: ask for it now, once.
      if (mine && !status?.passcode_set) {
        setError('');
        setFirstCode('');
        setMode({ kind: 'passcode', then: 'after' });
        return;
      }
      setMode({
        kind: 'done',
        ok: true,
        title: mine ? 'Face ID está listo' : `${mode.who} guardado`,
        text: mine ? 'Ya puede desbloquear mirando a la pantalla.' : 'Sergio ya le reconoce.',
      });
    })();
    return () => {
      stop = true;
    };
  }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  // -- unlocking: look, do the gentle movement, done ------------------------
  const unlock = async (again = false) => {
    setError('');
    const cRes = await apiFetch('/v1/faces/faceid/challenge', { method: 'POST' });
    const challenge = cRes.ok ? await cRes.json() : null;
    if (!challenge) return setError(await readError(cRes));
    if (challenge.passcode_required) {
      setError('');
      return setMode({ kind: 'passcode', then: 'unlock' });
    }
    setMode({ kind: 'unlock' });
    setLit(Array(TICKS).fill(false));
    if (!(await startCamera())) return;
    setSay(`${challenge.say}…`);
    // Time to read the instruction before the camera starts counting.
    await new Promise((r) => setTimeout(r, 1100));
    const frames: Blob[] = [];
    const totalFrames = 16;
    for (let i = 0; i < totalFrames; i++) {
      const b = await frame();
      if (b) frames.push(b);
      const progress = Math.round(((i + 1) / totalFrames) * TICKS);
      setLit(Array.from({ length: TICKS }, (_, idx) => idx < progress));
      await new Promise((r) => setTimeout(r, 170));
    }
    const form = new FormData();
    form.append('nonce', challenge.nonce);
    frames.forEach((b, i) => form.append('images', b, `u${i}.jpg`));
    setSay('Verificando identidad…');
    const res = await apiFetch('/v1/faces/faceid/unlock', { method: 'POST', body: form });
    stopCamera();
    const out = res.ok ? await res.json() : { ok: false, message: await readError(res) };
    await load();
    // Light or a missed movement is not a wrong face: try once more by itself.
    if (!out.ok && out.retry && !again) return unlock(true);
    if (out.passcode_required && !out.message) {
      setError('');
      return setMode({ kind: 'passcode', then: 'unlock' });
    }
    setMode(
      out.ok
        ? { kind: 'done', ok: true, title: `Hola, ${out.name || 'señor'}`, text: `Reconocido en ${out.ms} ms.` }
        : {
            kind: 'done',
            ok: false,
            title: 'No se pudo',
            retry: 'unlock',
            text: `${out.message || 'Inténtelo de nuevo.'} ${
              out.retry
                ? 'Este intento no cuenta.'
                : out.attempts_left === 0
                ? 'Ahora le pediré su código.'
                : out.attempts_left === 1
                  ? 'Queda 1 intento antes de pedir el código.'
                  : `Quedan ${out.attempts_left ?? '—'} intentos antes de pedir el código.`
            }`,
          },
    );
  };

  const submitPasscode = async (code: string, then: 'after' | 'unlock') => {
    setError('');
    const form = new FormData();
    form.append('code', code);
    if (!status?.passcode_set) {
      // Creating the code: type it twice so a slip never locks the owner out.
      if (!firstCode) {
        setFirstCode(code);
        return;
      }
      if (firstCode !== code) {
        setFirstCode('');
        return setError('Los dos códigos no coinciden. Empiece de nuevo.');
      }
      const res = await apiFetch('/v1/faces/faceid/passcode', { method: 'POST', body: form });
      if (!res.ok) return setError(await readError(res));
      setFirstCode('');
      await load();
      return setMode({ kind: 'done', ok: true, title: 'Face ID está listo', text: 'Ya puede desbloquear mirando a la pantalla.' });
    }
    const res = await apiFetch('/v1/faces/faceid/passcode/check', { method: 'POST', body: form });
    const out = res.ok ? await res.json() : { ok: false };
    if (!out.ok) return setError(out.wait ? `Espere ${out.wait} s antes de volver a intentarlo.` : 'Código incorrecto.');
    await load();
    setMode(then === 'after' ? { kind: 'home' } : { kind: 'done', ok: true, title: 'Desbloqueado', text: 'Face ID vuelve a estar disponible.' });
  };

  // One tap: the camera opens and Sergio learns the face. The code comes afterwards.
  const setup = () => {
    setError('');
    shots.current = [];
    setMode({ kind: 'scan', who: status?.owner || 'Señor', consent: true, round: 1, fresh: !!status?.owner });
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
              <Ring lit={lit} size={300} />
            </div>
            <p className="faceid-say" aria-live="polite">
              {say}
            </p>
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => (stopCamera(), setMode({ kind: 'home' }))}>
              Cancelar
            </button>
          </>
        ) : mode.kind === 'passcode' ? (
          <PinPad
            key={status?.passcode_set ? 'check' : firstCode ? 'again' : 'new'}
            title={status?.passcode_set ? 'Introduzca su código' : firstCode ? 'Repita el código' : 'Cree un código de respaldo'}
            subtitle={
              status?.passcode_set
                ? REASON_ES[status.passcode_reason] || 'Código de Sergio para este reconocimiento.'
                : 'De 6 a 12 cifras. Lo pedirá tras reiniciar, tras 5 fallos y tras 48 horas.'
            }
            error={error}
            onDone={(c) => submitPasscode(c, mode.then)}
            onSkip={!status?.passcode_set ? () => (setFirstCode(''), setMode({ kind: 'home' })) : undefined}
          />
        ) : mode.kind === 'done' ? (
          <div className="faceid-done" data-ok={mode.ok ? '1' : '0'} role="status">
            <span className="faceid-badge">{mode.ok ? <Check size={44} strokeWidth={2.4} /> : <X size={44} strokeWidth={2.4} />}</span>
            <h1>{mode.title}</h1>
            <p>{mode.text}</p>
            {mode.retry ? (
              <div className="faceid-actions">
                <button type="button" className="paper-button" onClick={() => (mode.retry === 'scan' ? setup() : void unlock())}>
                  Intentar de nuevo
                </button>
                <button type="button" className="paper-button" data-variant="quiet" onClick={() => setMode({ kind: 'home' })}>
                  Ahora no
                </button>
              </div>
            ) : (
              <button type="button" className="paper-button" onClick={() => setMode({ kind: 'home' })}>
                Listo
              </button>
            )}
          </div>
        ) : (
          <div className="faceid-home">
            <span className="face-presence-mark"><FaceGlyph size={84} /></span>
            <h1>Reconocimiento facial</h1>
            <p>Un toque, mire a la cámara y listo. Una webcam no reemplaza la cámara de profundidad de un iPhone.</p>
            {error && <p className="faceid-error">{error}</p>}
            <div className="faceid-actions">
              {enrolled ? (
                <>
                  <button type="button" className="paper-button" onClick={() => void unlock()}>
                    <ScanFace size={16} /> Probar reconocimiento
                  </button>
                  {!status?.passcode_set && (
                    <button type="button" className="paper-button" onClick={() => (setError(''), setFirstCode(''), setMode({ kind: 'passcode', then: 'after' }))}>
                      <Lock size={15} /> Crear código de respaldo
                    </button>
                  )}
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
