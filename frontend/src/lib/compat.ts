// Runs before anything else (first import in main.tsx) so Sergio opens on
// any device: a phone on the home network (plain http, where browsers hide
// crypto.randomUUID, the microphone and the camera), older iPhones and iPads
// (Safari 14-15 have no structuredClone) and browsers that block storage.

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key) => (data.has(key) ? (data.get(key) as string) : null),
    key: (index) => Array.from(data.keys())[index] ?? null,
    removeItem: (key) => {
      data.delete(key);
    },
    setItem: (key, value) => {
      data.set(key, String(value));
    },
  };
}

function uuid(): string {
  const bytes = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(bytes);
  else for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function installCompat(): void {
  if (typeof window === 'undefined') return;
  // Storage blocked (private mode, cookies off): reading it throws and the
  // whole app would stay blank. A memory copy keeps it working this visit.
  for (const name of ['localStorage', 'sessionStorage'] as const) {
    try {
      const s = window[name];
      const probe = '__sergio__';
      s.setItem(probe, '1');
      s.removeItem(probe);
    } catch {
      try {
        Object.defineProperty(window, name, { value: memoryStorage(), configurable: true });
      } catch {
        // nothing more can be done
      }
    }
  }
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID !== 'function') {
    try {
      Object.defineProperty(crypto, 'randomUUID', { value: uuid, configurable: true });
    } catch {
      // read-only crypto: callers use newId() below
    }
  }
  if (typeof globalThis.structuredClone !== 'function') {
    (globalThis as { structuredClone?: (v: unknown) => unknown }).structuredClone = (v: unknown) =>
      v === undefined ? undefined : JSON.parse(JSON.stringify(v));
  }
}

/** A random id on any device. */
export function newUuid(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  } catch {
    // insecure context in an old browser
  }
  return uuid();
}

/**
 * Why the microphone or the camera cannot open here, in words for the owner,
 * or '' when the browser can ask for it. Browsers only allow them on https
 * or on the computer itself (localhost), never on http://192.168…
 */
export function mediaProblem(what: 'micrófono' | 'cámara'): string {
  if (typeof navigator === 'undefined') return '';
  if (typeof navigator.mediaDevices?.getUserMedia === 'function') return '';
  if (typeof window !== 'undefined' && window.isSecureContext === false) {
    return `Este navegador solo permite el ${what} con conexión segura. Abra Sergio en este mismo equipo o con el enlace https de «Sergio móvil».`;
  }
  return `Este navegador no permite usar el ${what}. Pruebe con Chrome, Edge o Safari actualizados.`;
}

installCompat();
