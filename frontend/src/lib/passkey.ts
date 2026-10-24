// The device's own face, finger or PIN (a passkey): Face ID on the iPhone,
// Touch ID on the Mac, Windows Hello, the Android fingerprint. The browser
// asks the device; Sergio only ever sees a signature and a public key.

import { apiFetch } from './api';

export const b64u = (buf: ArrayBuffer | Uint8Array): string => {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

export const unb64u = (text: string): Uint8Array<ArrayBuffer> => {
  const s = atob(text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (text.length % 4)) % 4));
  const out = new Uint8Array(new ArrayBuffer(s.length));
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
};

/** True when this device can check the person itself (face, finger or PIN). */
export async function passkeyReady(): Promise<boolean> {
  try {
    if (typeof window === 'undefined' || !window.isSecureContext || !window.PublicKeyCredential) return false;
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

async function ask<T>(path: string, body?: unknown): Promise<T> {
  const res = await apiFetch(`/v1/cuentas/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'No se pudo.');
  return data as T;
}

/** Why the device said no, in plain words. */
export function passkeyProblem(e: unknown): string {
  const name = e instanceof DOMException ? e.name : '';
  if (name === 'NotAllowedError') return 'Cancelado, o el dispositivo no le reconoció.';
  if (name === 'InvalidStateError') return 'Este dispositivo ya está guardado.';
  if (name === 'SecurityError') return 'Solo funciona en https o en este equipo.';
  return e instanceof Error ? e.message : 'No se pudo.';
}

interface CreateOptions {
  challenge: string;
  rp: { id: string; name: string };
  user: { id: string; name: string; displayName: string };
  pubKeyCredParams: Array<{ type: 'public-key'; alg: number }>;
  authenticatorSelection: AuthenticatorSelectionCriteria;
  excludeCredentials: Array<{ type: 'public-key'; id: string }>;
  attestation: AttestationConveyancePreference;
  timeout: number;
}

/** Save this device's face/finger/PIN for the signed-in account. */
export async function addThisDevice(name: string): Promise<void> {
  const o = await ask<CreateOptions>('llave/opciones-registro');
  const cred = (await navigator.credentials.create({
    publicKey: {
      ...o,
      challenge: unb64u(o.challenge),
      user: { ...o.user, id: unb64u(o.user.id) },
      excludeCredentials: o.excludeCredentials.map((c) => ({ type: c.type, id: unb64u(c.id) })),
    },
  })) as PublicKeyCredential | null;
  if (!cred) throw new Error('Cancelado.');
  const r = cred.response as AuthenticatorAttestationResponse;
  await ask('llave/registrar', {
    clientDataJSON: b64u(r.clientDataJSON),
    attestationObject: b64u(r.attestationObject),
    name,
  });
}

interface GetOptions {
  challenge: string;
  rpId: string;
  userVerification: UserVerificationRequirement;
  timeout: number;
}

export interface SignedIn {
  status: 'dentro' | 'pendiente' | 'bloqueada';
  token?: string;
  message?: string;
}

/** Sign in with the device's face/finger/PIN. */
export async function signInWithFace(device: string): Promise<SignedIn> {
  const o = await ask<GetOptions>('llave/opciones');
  const cred = (await navigator.credentials.get({
    publicKey: { challenge: unb64u(o.challenge), rpId: o.rpId, userVerification: o.userVerification, timeout: o.timeout, allowCredentials: [] },
  })) as PublicKeyCredential | null;
  if (!cred) throw new Error('Cancelado.');
  const r = cred.response as AuthenticatorAssertionResponse;
  return ask<SignedIn>('llave/entrar', {
    id: cred.id,
    clientDataJSON: b64u(r.clientDataJSON),
    authenticatorData: b64u(r.authenticatorData),
    signature: b64u(r.signature),
    device,
  });
}

/** A name for this device, from what the browser says it runs on. */
export function deviceName(ua: string = typeof navigator !== 'undefined' ? navigator.userAgent : ''): string {
  if (/iPhone/.test(ua)) return 'iPhone';
  if (/iPad/.test(ua)) return 'iPad';
  if (/Android/.test(ua)) return /Mobile/.test(ua) ? 'Teléfono Android' : 'Tablet Android';
  if (/Macintosh|Mac OS X/.test(ua)) return 'Mac';
  if (/Windows/.test(ua)) return 'PC con Windows';
  return 'Este dispositivo';
}
