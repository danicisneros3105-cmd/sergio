// The lock over Sergio: after a while without use (or «Bloquear ahora»),
// everything is covered until the owner looks at the camera (Sergio's own
// Face ID) or types Sergio's code. Only on this computer, and only once Face
// ID is set up: a lock nobody can open would be worse than none.
import { useCallback, useEffect, useRef, useState } from 'react';
import { ScanFace } from 'lucide-react';
import { apiFetch } from '../../lib/api';
import { isThisComputer, lockPrefs, shouldLock, type LockPrefs } from '../../lib/appLock';
import { cameraReady, unlockWithCode, unlockWithSergioFace } from '../../lib/faceLogin';

export function AppLock() {
  const [ready, setReady] = useState(false);
  const [locked, setLocked] = useState(false);
  const [prefs, setPrefs] = useState<LockPrefs>(lockPrefs);
  const [said, setSaid] = useState('');
  const [busy, setBusy] = useState(false);
  const [useCode, setUseCode] = useState(false);
  const [code, setCode] = useState('');
  const last = useRef(Date.now());

  // Face ID set up on this computer? Otherwise the lock never closes.
  useEffect(() => {
    if (!isThisComputer()) return;
    apiFetch('/v1/faces/faceid')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setReady(!!d?.owner))
      .catch(() => setReady(false));
  }, []);

  useEffect(() => {
    const onPrefs = () => setPrefs(lockPrefs());
    const onLock = () => ready && setLocked(true);
    window.addEventListener('sergio:lock-prefs', onPrefs);
    window.addEventListener('sergio:lock', onLock);
    return () => {
      window.removeEventListener('sergio:lock-prefs', onPrefs);
      window.removeEventListener('sergio:lock', onLock);
    };
  }, [ready]);

  // Use = pointer, keys, touch. Checked every 15 s and when the window comes back.
  useEffect(() => {
    if (!ready) return;
    const seen = () => {
      if (!locked) last.current = Date.now();
    };
    const check = () => {
      if (!locked && shouldLock(prefs, Date.now() - last.current)) setLocked(true);
    };
    const events = ['pointerdown', 'keydown', 'wheel', 'touchstart'] as const;
    events.forEach((e) => window.addEventListener(e, seen, { passive: true }));
    document.addEventListener('visibilitychange', check);
    const t = window.setInterval(check, 15_000);
    return () => {
      events.forEach((e) => window.removeEventListener(e, seen));
      document.removeEventListener('visibilitychange', check);
      window.clearInterval(t);
    };
  }, [ready, locked, prefs]);

  const open = useCallback(() => {
    last.current = Date.now();
    setLocked(false);
    setSaid('');
    setCode('');
    setUseCode(false);
  }, []);

  const face = async () => {
    if (!cameraReady()) {
      setUseCode(true);
      setSaid('No hay cámara disponible: use su código.');
      return;
    }
    setBusy(true);
    try {
      const r = await unlockWithSergioFace(setSaid);
      if (r.ok) return open();
      if (r.passcode_required) {
        setUseCode(true);
        setSaid(r.reason || 'Use su código de Sergio.');
      } else {
        setSaid(r.message || 'No le reconocí. Inténtelo otra vez.');
      }
    } catch (e) {
      setSaid((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const withCode = async () => {
    setBusy(true);
    try {
      const r = await unlockWithCode(code.trim());
      if (r.ok) return open();
      setCode('');
      setSaid(r.wait ? `Espere ${r.wait} s y vuelva a intentarlo.` : 'Ese no es el código.');
    } catch (e) {
      setSaid((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!locked) return null;
  return (
    <div className="app-lock" role="dialog" aria-modal="true" aria-label="Sergio está bloqueado">
      <div className="app-lock-card">
        <span className="app-lock-icon" aria-hidden="true">
          <ScanFace size={34} strokeWidth={1.4} />
        </span>
        <h2>Sergio está bloqueado</h2>
        {!useCode ? (
          <>
            <button type="button" className="app-lock-go" disabled={busy} onClick={() => void face()}>
              {busy ? 'Mirando…' : 'Desbloquear con Face ID'}
            </button>
            <button type="button" className="app-lock-alt" onClick={() => setUseCode(true)}>
              Usar mi código
            </button>
          </>
        ) : (
          <form
            className="app-lock-code"
            onSubmit={(e) => {
              e.preventDefault();
              if (code.trim()) void withCode();
            }}
          >
            <input
              type="password"
              inputMode="numeric"
              autoComplete="off"
              autoFocus
              aria-label="Código de Sergio"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <button type="submit" className="app-lock-go" disabled={busy || !code.trim()}>
              Desbloquear
            </button>
            <button type="button" className="app-lock-alt" onClick={() => setUseCode(false)}>
              Volver a Face ID
            </button>
          </form>
        )}
        {said && (
          <p className="app-lock-said" role="status">
            {said}
          </p>
        )}
      </div>
    </div>
  );
}

export default AppLock;
