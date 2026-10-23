// One Sergio window on the computer. The desktop (notch, tray, «abre Nodes»)
// used to open a new window for every page, and each one opened its own
// conversation. This window keeps one request waiting at the server
// (/v1/app/wait); when the desktop asks for a page, it arrives here and the
// window goes there instead of a new one opening. A long poll keeps working
// while the window is in the background (timers are throttled, requests are
// not).

import { authHeaders, getBase } from './api';
import { newUuid } from './compat';

let started = false;

function local(): boolean {
  if (typeof window === 'undefined') return false;
  return ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
}

const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Go to *path* in this window, like a click in the sidebar. */
export function showPage(path: string): void {
  window.dispatchEvent(new CustomEvent('sergio:navigate', { detail: path }));
  try {
    window.focus();
  } catch {
    // the desktop brings the window to the front anyway
  }
}

export function startAppWindow(): void {
  if (started || !local() || typeof fetch !== 'function') return;
  started = true;
  const id = newUuid();
  let current: AbortController | null = null;

  const loop = async () => {
    for (;;) {
      current = new AbortController();
      try {
        const resp = await fetch(`${getBase()}/v1/app/wait`, {
          method: 'POST',
          headers: authHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ id, focused: document.hasFocus() }),
          signal: current.signal,
        });
        if (!resp.ok) {
          await pause(10_000); // an older server without this route
          continue;
        }
        const data = (await resp.json()) as { navigate?: string | null; local?: boolean };
        if (data.local === false) return;
        if (typeof data.navigate === 'string' && data.navigate.startsWith('/')) showPage(data.navigate);
      } catch {
        if (current.signal.aborted) continue; // focus changed: ask again at once
        await pause(5_000); // the server is restarting
      }
    }
  };
  // The window the owner looks at is the one the desktop should use.
  window.addEventListener('focus', () => current?.abort());
  void loop();
}
