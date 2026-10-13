// The web Sergio serves always wins over the copy the browser kept.
//
// Every build writes /version.json with its id and bakes the same id into the
// code. If the server answers with another id, this copy is old: the offline
// cache and the service worker are dropped and the page reloads once.

declare const __BUILD_ID__: string;

export const BUILD_ID: string = typeof __BUILD_ID__ === 'string' ? __BUILD_ID__ : 'dev';
const TRIED = 'sergio-reloaded-for';

export function isStale(serverId: string | undefined | null, mine = BUILD_ID): boolean {
  return !!serverId && mine !== 'dev' && serverId !== mine;
}

export async function dropOldCopy(): Promise<void> {
  try {
    const regs = (await navigator.serviceWorker?.getRegistrations?.()) || [];
    await Promise.all(regs.map((r) => r.unregister()));
  } catch {
    /* no service worker here */
  }
  try {
    const names = (await globalThis.caches?.keys?.()) || [];
    await Promise.all(names.map((n) => caches.delete(n)));
  } catch {
    /* no Cache Storage here */
  }
}

export async function checkFreshness(fetcher: typeof fetch = fetch): Promise<boolean> {
  let serverId = '';
  try {
    const r = await fetcher(`/version.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!r.ok) return false;
    serverId = String((await r.json())?.build || '');
  } catch {
    return false; // offline: keep working with this copy
  }
  if (!isStale(serverId)) return false;
  try {
    if (sessionStorage.getItem(TRIED) === serverId) return false; // reload once, never loop
    sessionStorage.setItem(TRIED, serverId);
  } catch {
    /* private mode: still reload */
  }
  await dropOldCopy();
  location.reload();
  return true;
}

export function watchFreshness(): void {
  if (BUILD_ID === 'dev') return;
  void checkFreshness();
  const again = () => {
    if (document.visibilityState === 'visible') void checkFreshness();
  };
  document.addEventListener('visibilitychange', again);
  window.setInterval(again, 5 * 60_000);
}
