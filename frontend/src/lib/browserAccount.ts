// Authenticated app data has its own stable partition, independent of the
// session token. Freeze it for this page so in-flight work cannot change owner.
const SESSION_KEY = 'sergio-account-session-v1';

interface BrowserAccount {
  id: string;
  token: string;
  base: string;
}

function readAccount(): BrowserAccount | null {
  try {
    const data = JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null');
    if (data && /^[a-f0-9]{16}$/.test(data.id) &&
        typeof data.token === 'string' && data.token.startsWith('sg_') &&
        typeof data.base === 'string') return data;
  } catch {
    // A browser without writable session storage cannot keep a login.
  }
  return null;
}

const pageAccount = readAccount();
export const accountAtPageLoad = pageAccount?.id;

export function scopedDataKey(key: string, accountId = pageAccount?.id): string {
  return accountId ? `sergio-account:${accountId}:${key}` : key;
}

export function sessionToken(base: string): string {
  const account = readAccount();
  return account?.base === base ? account.token : '';
}

export function saveBrowserAccount(account: BrowserAccount): void {
  if (!/^[a-f0-9]{16}$/.test(account.id) || !account.token.startsWith('sg_')) {
    throw new Error('No se pudo verificar la cuenta de Sergio.');
  }
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(account));
}

export function clearBrowserAccount(): void {
  sessionStorage.removeItem(SESSION_KEY);
}

// A page restored from the browser's back/forward cache may still contain
// the old React tree. Rebuild it when the tab's account changed meanwhile.
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('pageshow', (event) => {
    if (event.persisted && readAccount()?.id !== accountAtPageLoad) window.location.reload();
  });
}
