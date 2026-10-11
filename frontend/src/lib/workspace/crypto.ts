// End-to-end encryption for Workspace pages, in the browser (WebCrypto).
// The key is derived from a passphrase only you know (PBKDF2-SHA-256,
// 600 000 iterations, a random salt per page) and the page's blocks are
// sealed with AES-256-GCM. The server and any backup only ever hold the
// ciphertext; without the passphrase nobody, Sergio included, can read it.
// Lose the passphrase and the page is gone: there is no back door.

import type { Block, Sealed } from './model';

const ITERATIONS = 600_000;

function b64(bytes: Uint8Array): string {
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

function unb64(text: string): Uint8Array<ArrayBuffer> {
  const s = atob(text);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

async function keyFor(passphrase: string, salt: Uint8Array<ArrayBuffer>, iterations = ITERATIONS): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(passphrase), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', hash: 'SHA-256', salt, iterations },
    base,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
}

export class WrongPassphrase extends Error {
  constructor() {
    super('La frase no es correcta.');
  }
}

export async function seal(blocks: Block[], passphrase: string, iterations = ITERATIONS): Promise<Sealed> {
  if (passphrase.length < 8) throw new Error('Use una frase de al menos 8 caracteres.');
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await keyFor(passphrase, salt, iterations);
  const plain = new TextEncoder().encode(JSON.stringify(blocks));
  const data = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plain));
  return { v: 1, salt: b64(salt), iv: b64(iv), data: b64(data), ...(iterations !== ITERATIONS ? { n: iterations } : {}) } as Sealed;
}

export async function unseal(sealed: Sealed, passphrase: string): Promise<Block[]> {
  const iterations = (sealed as Sealed & { n?: number }).n ?? ITERATIONS;
  const key = await keyFor(passphrase, unb64(sealed.salt), iterations);
  try {
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(sealed.iv) }, key, unb64(sealed.data));
    return JSON.parse(new TextDecoder().decode(plain)) as Block[];
  } catch {
    throw new WrongPassphrase();
  }
}
