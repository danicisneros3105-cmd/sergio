// What went wrong, kept on this device only (nothing is sent anywhere).
//
// «La app se bugea… no sé qué onda»: a fault that does not blank the screen is
// easy to miss and hard to describe. The last few errors are kept here, with
// when and where, so Ayuda can show them and the person can copy them for
// whoever is helping. No messages, keys or page contents: only the error text,
// the first lines of its trace and the address (without parameters).

const KEY = 'sergio-crashes';
const MAX = 20;

export interface Crash {
  t: number;
  where: string;
  what: string;
  trace?: string;
}

export function readCrashes(): Crash[] {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) || '[]');
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function noteCrash(error: unknown, now: number = Date.now()): void {
  try {
    const e = error as { message?: unknown; stack?: unknown } | null;
    const what = String((e && e.message) || error || 'Error').slice(0, 300);
    // browser noise that is not a fault of Sergio
    if (/ResizeObserver loop|Script error\.?$|AbortError|The play\(\) request was interrupted/i.test(what)) return;
    const trace = e && typeof e.stack === 'string' ? e.stack.split('\n').slice(1, 4).join('\n').slice(0, 400) : undefined;
    const list = readCrashes();
    const last = list[list.length - 1];
    if (last && last.what === what && now - last.t < 5000) return; // the same one in a burst
    list.push({ t: now, where: location.pathname, what, trace });
    localStorage.setItem(KEY, JSON.stringify(list.slice(-MAX)));
  } catch {
    /* no storage: nothing to keep */
  }
}

export function clearCrashes(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* nothing */
  }
}

export function crashReport(list: Crash[] = readCrashes()): string {
  if (!list.length) return 'Sin errores guardados en este equipo.';
  return list
    .map((c) => `${new Date(c.t).toISOString()} ${c.where}\n${c.what}${c.trace ? `\n${c.trace}` : ''}`)
    .join('\n\n');
}

let started = false;
export function watchCrashes(): void {
  if (started || typeof window === 'undefined') return;
  started = true;
  window.addEventListener('error', (e) => noteCrash(e.error || e.message));
  window.addEventListener('unhandledrejection', (e) => noteCrash(e.reason));
}
