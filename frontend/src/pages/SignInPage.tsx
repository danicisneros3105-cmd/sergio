// Entrar / Crear cuenta: the device's own face first (a passkey), then Google,
// Microsoft or Apple; email with a code, or the phone with an SMS. The token
// Sergio gives back works like the key.

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';
import { newUuid } from '../lib/compat';
import { useAppStore } from '../lib/store';
import { BrandMark } from '../components/Brand/BrandMark';
import { BRANDS } from '../lib/brands';
import { passkeyProblem, passkeyReady, signInWithFace } from '../lib/passkey';
import { FaceGlyph } from '../components/Accounts/FaceGlyph';

interface State {
  accounts: number;
  providers: Record<string, boolean>;
  sms: boolean;
  email_codes: boolean;
  local: boolean;
  me: { email?: string; phone?: string; role: string } | null;
}

interface Answer {
  status: 'dentro' | 'codigo' | 'pendiente' | 'bloqueada';
  token?: string;
  message?: string;
}

function device(): string {
  try {
    let id = localStorage.getItem('sergio-device');
    if (!id) {
      id = newUuid();
      localStorage.setItem('sergio-device', id);
    }
    return id;
  } catch {
    return '';
  }
}

async function post(path: string, body: unknown): Promise<Answer> {
  const res = await apiFetch(`/v1/cuentas/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'No se pudo.');
  return data as Answer;
}

const LABEL: Record<string, string> = { google: 'Google', microsoft: 'Microsoft', apple: 'Apple' };

export function SignInPage() {
  const navigate = useNavigate();
  const updateSettings = useAppStore((s) => s.updateSettings);
  const [info, setInfo] = useState<State | null>(null);
  const [way, setWay] = useState<'correo' | 'telefono'>('correo');
  const [mode, setMode] = useState<'entrar' | 'crear'>('entrar');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'datos' | 'codigo'>('datos');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const dev = useMemo(device, []);
  // The device's face: only offered where the device can check the person.
  const [faceOk, setFaceOk] = useState(false);
  const [face, setFace] = useState<'idle' | 'scan' | 'ok' | 'fail'>('idle');
  useEffect(() => {
    void passkeyReady().then(setFaceOk);
  }, []);

  const done = (a: Answer) => {
    if (a.status === 'dentro' && a.token) {
      updateSettings({ apiKey: a.token });
      toast.success('Bienvenido, señor.');
      navigate('/');
      return;
    }
    if (a.status === 'codigo') setStep('codigo');
    setNote(a.message || '');
  };

  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.slice(1));
    if (hash.get('token')) {
      window.history.replaceState(null, '', '/entrar');
      done({ status: 'dentro', token: hash.get('token')! });
      return;
    }
    if (hash.get('error')) setNote(hash.get('error')!);
    if (hash.get('estado') === 'pendiente') setNote('Su cuenta espera la aprobación del dueño de este Sergio.');
    void apiFetch('/v1/cuentas/estado')
      .then((r) => r.json())
      .then((d: State) => {
        setInfo(d);
        if (d.accounts === 0) setMode('crear');
      })
      .catch(() => setNote('No puedo hablar con Sergio. ¿Está en marcha?'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async (fn: () => Promise<Answer>) => {
    setBusy(true);
    setNote('');
    try {
      done(await fn());
    } catch (e) {
      setNote(e instanceof Error ? e.message : 'No se pudo.');
    } finally {
      setBusy(false);
    }
  };

  const providers = Object.entries(info?.providers ?? {}).filter(([, ok]) => ok);

  const withFace = async () => {
    setFace('scan');
    setNote('Mirándole, señor…');
    try {
      const a = await signInWithFace(dev);
      if (a.status === 'dentro') {
        setFace('ok');
        setNote('Es usted. Adelante.');
        window.setTimeout(() => done(a), 650);
      } else {
        setFace('fail');
        done(a);
      }
    } catch (e) {
      setFace('fail');
      setNote(passkeyProblem(e));
    }
  };

  return (
    <div className="signin">
      <div className="signin-card">
        <img className="signin-mark" src="/sergio.svg" alt="" width={56} height={56} />
        <h1 className="signin-title">Sergio</h1>
        {faceOk && info && info.accounts > 0 && (
          <button type="button" className="signin-face" data-state={face} disabled={face === 'scan'} onClick={() => void withFace()}>
            <FaceGlyph size={44} state={face} />
            <span>Entrar con la cara</span>
          </button>
        )}
        {providers.length > 0 && (
          <div className="signin-providers">
            {providers.map(([key]) => (
              <button
                key={key}
                type="button"
                className="signin-provider"
                disabled={busy}
                onClick={async () => {
                  const r = await apiFetch(`/v1/cuentas/oauth/${key}/inicio?device=${encodeURIComponent(dev)}`);
                  const d = await r.json().catch(() => ({}));
                  if (r.ok && d.url) window.location.href = d.url;
                  else setNote(d.detail || 'No se pudo abrir.');
                }}
              >
                <BrandMark name={LABEL[key]} brand={BRANDS[key] ?? null} size={22} />
                <span>Continuar con {LABEL[key]}</span>
              </button>
            ))}
            <div className="signin-or">
              <span>o</span>
            </div>
          </div>
        )}

        <div className="signin-ways" role="tablist" aria-label="Cómo entrar">
          {(['correo', 'telefono'] as const).map((w) => (
            <button key={w} type="button" role="tab" aria-selected={way === w} onClick={() => (setWay(w), setStep('datos'), setNote(''))}>
              {w === 'correo' ? 'Correo' : 'Teléfono'}
            </button>
          ))}
        </div>

        {way === 'correo' && step === 'datos' && (
          <form
            className="signin-form"
            onSubmit={(e) => {
              e.preventDefault();
              void run(() => post(mode === 'crear' ? 'registro' : 'entrar', { email, password, device: dev }));
            }}
          >
            <input type="email" autoComplete="email" placeholder="Correo" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <input
              type="password"
              autoComplete={mode === 'crear' ? 'new-password' : 'current-password'}
              placeholder={mode === 'crear' ? 'Contraseña (10 o más caracteres)' : 'Contraseña'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button type="submit" className="signin-go" disabled={busy}>
              {mode === 'crear' ? 'Crear cuenta' : 'Entrar'}
            </button>
            <button type="button" className="signin-switch" onClick={() => setMode(mode === 'crear' ? 'entrar' : 'crear')}>
              {mode === 'crear' ? 'Ya tengo cuenta' : 'Crear una cuenta'}
            </button>
          </form>
        )}

        {way === 'telefono' && step === 'datos' && (
          <form
            className="signin-form"
            onSubmit={(e) => {
              e.preventDefault();
              void run(() => post('telefono/codigo', { phone, device: dev }));
            }}
          >
            <input type="tel" autoComplete="tel" placeholder="+593 99 123 4567" value={phone} onChange={(e) => setPhone(e.target.value)} required />
            <button type="submit" className="signin-go" disabled={busy || info?.sms === false}>
              Enviar código
            </button>
            {info?.sms === false && <p className="signin-note">Los SMS no están configurados en este Sergio.</p>}
          </form>
        )}

        {step === 'codigo' && (
          <form
            className="signin-form"
            onSubmit={(e) => {
              e.preventDefault();
              void run(() =>
                way === 'telefono'
                  ? post('telefono/entrar', { phone, code, device: dev })
                  : post('verificar', { email, code, device: dev }),
              );
            }}
          >
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="Código de 6 cifras"
              value={code}
              maxLength={6}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              required
            />
            <button type="submit" className="signin-go" disabled={busy || code.length !== 6}>
              Confirmar
            </button>
          </form>
        )}

        {note && (
          <p className="signin-note" role="status">
            {note}
          </p>
        )}
      </div>
    </div>
  );
}

export default SignInPage;
