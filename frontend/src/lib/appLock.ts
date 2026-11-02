// Sergio locks itself and opens with his own Visage (owner, 2 Nov 2026:
// «debes poder desbloquear el dispositivo con Visage»). What an app can lock
// is the app: Windows, macOS or a phone unlock only through their own system
// (docs/FACEID-SISTEMA.md), so this never claims to unlock the computer.
// Only on this computer, where Sergio's Visage lives.

export interface LockPrefs {
  on: boolean;
  /** Minutes without use before it locks (0 = only «Bloquear ahora»). */
  minutes: number;
}

const KEY = 'sergio-bloqueo';
export const DEFAULT_LOCK: LockPrefs = { on: true, minutes: 15 };

export function lockPrefs(): LockPrefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_LOCK;
    const d = JSON.parse(raw) as Partial<LockPrefs>;
    return {
      on: typeof d.on === 'boolean' ? d.on : DEFAULT_LOCK.on,
      minutes: typeof d.minutes === 'number' && d.minutes >= 0 ? Math.min(240, d.minutes) : DEFAULT_LOCK.minutes,
    };
  } catch {
    return DEFAULT_LOCK;
  }
}

export function saveLockPrefs(p: LockPrefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* private window: the default applies */
  }
  window.dispatchEvent(new CustomEvent('sergio:lock-prefs'));
}

/** Whether *idleMs* without use should lock, with these prefs. */
export function shouldLock(p: LockPrefs, idleMs: number): boolean {
  return p.on && p.minutes > 0 && idleMs >= p.minutes * 60_000;
}

export function lockNow(): void {
  window.dispatchEvent(new CustomEvent('sergio:lock'));
}

export function isThisComputer(): boolean {
  const h = window.location.hostname;
  return h === 'localhost' || h === '127.0.0.1' || h === '[::1]';
}
