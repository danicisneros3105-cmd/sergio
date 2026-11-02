// Signing in with Sergio's own Face ID (owner, 29 Oct 2026: «en Windows Hello
// aparecen símbolos raros y pide PIN siempre»). No Windows Hello, no PIN: the
// camera of this computer takes a short burst while the person makes the
// one-time movement Sergio asks for, and the server decides (live face,
// looking at the screen, the owner and nobody else). Only on this computer.

import { apiFetch } from './api';

export interface FaceAnswer {
  status: 'dentro' | 'pendiente' | 'bloqueada' | 'no' | 'codigo';
  token?: string;
  message?: string;
  reason?: string;
}

interface Reto {
  ready?: boolean;
  passcode_required?: boolean;
  reason?: string;
  nonce?: string;
  say?: string;
}

const FRAMES = 14;
const EVERY_MS = 150;
const READ_FIRST_MS = 900;

const wait = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

/** True when this page can use a camera at all. */
export function cameraReady(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
}

async function burst(video: HTMLVideoElement, n: number): Promise<Blob[]> {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext('2d');
  const out: Blob[] = [];
  for (let i = 0; i < n; i++) {
    ctx?.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/jpeg', 0.85));
    if (blob) out.push(blob);
    await wait(EVERY_MS);
  }
  return out;
}

/** One sign-in attempt; *say* shows what to do («Gire la cabeza…»). */
export async function signInWithSergioFace(device: string, say: (text: string) => void): Promise<FaceAnswer> {
  const r = await apiFetch('/v1/cuentas/cara/reto', { method: 'POST' });
  const reto = (await r.json().catch(() => ({}))) as Reto;
  if (!r.ok) throw new Error((reto as { detail?: string }).detail || 'Face ID solo funciona en este equipo.');
  if (reto.passcode_required) return { status: 'codigo', message: reto.reason || 'Use su código de Sergio.' };
  if (!reto.ready || !reto.nonce) return { status: 'no', message: reto.reason || 'Primero configure el Face ID de Sergio.' };

  const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false });
  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;
  video.srcObject = stream;
  try {
    await video.play();
    say(`Mire a la pantalla. ${reto.say ?? ''}…`);
    await wait(READ_FIRST_MS);
    const frames = await burst(video, FRAMES);
    say('Verificando…');
    const form = new FormData();
    form.append('nonce', reto.nonce);
    form.append('device', device);
    frames.forEach((b, i) => form.append('images', b, `f${i}.jpg`));
    const res = await apiFetch('/v1/cuentas/cara/entrar', { method: 'POST', body: form });
    const data = (await res.json().catch(() => ({}))) as FaceAnswer & { detail?: string };
    if (!res.ok) throw new Error(data.detail || 'No se pudo verificar.');
    return data;
  } finally {
    stream.getTracks().forEach((t) => t.stop());
  }
}

export interface UnlockAnswer {
  ok: boolean;
  retry?: boolean;
  message?: string;
  passcode_required?: boolean;
  reason?: string;
}

/** Unlock Sergio (the app lock) with his own Face ID, on this computer: the
 * same one-time movement and burst, but no new session is opened. */
export async function unlockWithSergioFace(say: (text: string) => void): Promise<UnlockAnswer> {
  const r = await apiFetch('/v1/faces/faceid/challenge', { method: 'POST' });
  const reto = (await r.json().catch(() => ({}))) as Reto & { detail?: string; action?: string };
  if (!r.ok) throw new Error(reto.detail || 'Face ID solo funciona en este equipo.');
  if (reto.passcode_required) return { ok: false, passcode_required: true, reason: reto.reason };
  if (!reto.nonce) return { ok: false, message: 'Primero configure el Face ID de Sergio.' };
  const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false });
  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;
  video.srcObject = stream;
  try {
    await video.play();
    say(`Mire a la pantalla. ${reto.say ?? ''}…`);
    await wait(READ_FIRST_MS);
    const frames = await burst(video, FRAMES);
    say('Verificando…');
    const form = new FormData();
    form.append('nonce', reto.nonce);
    frames.forEach((b, i) => form.append('images', b, `f${i}.jpg`));
    const res = await apiFetch('/v1/faces/faceid/unlock', { method: 'POST', body: form });
    const data = (await res.json().catch(() => ({}))) as UnlockAnswer & { detail?: string };
    if (!res.ok) throw new Error(data.detail || 'No se pudo verificar.');
    return data;
  } finally {
    stream.getTracks().forEach((t) => t.stop());
  }
}

/** Unlock with Sergio's code instead (always possible). */
export async function unlockWithCode(code: string): Promise<{ ok: boolean; wait?: number }> {
  const form = new FormData();
  form.append('code', code);
  const r = await apiFetch('/v1/faces/faceid/passcode/check', { method: 'POST', body: form });
  const d = (await r.json().catch(() => ({}))) as { ok?: boolean; wait?: number; detail?: string };
  if (!r.ok) throw new Error(d.detail || 'No se pudo comprobar el código.');
  return { ok: !!d.ok, wait: d.wait };
}
