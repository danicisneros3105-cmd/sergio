// Phone pairing: `sergio movil` shows a QR code whose link ends in
// `#pair=<token>`. The fragment never reaches the server or the tunnel logs;
// here it is moved into the settings blob that getApiKey() reads, then wiped
// from the address bar so it is not bookmarked or shared by accident.

const SETTINGS_KEY = 'openjarvis-settings';

export function readPairToken(hash: string): string {
  const fragment = hash.startsWith('#') ? hash.slice(1) : hash;
  for (const part of fragment.split('&')) {
    const [key, ...rest] = part.split('=');
    if (key === 'pair') {
      const token = decodeURIComponent(rest.join('='));
      return /^[A-Za-z0-9_-]{16,200}$/.test(token) ? token : '';
    }
  }
  return '';
}

export function consumePairFragment(win: Window = window): boolean {
  const token = readPairToken(win.location.hash);
  if (!token) return false;
  try {
    const raw = win.localStorage.getItem(SETTINGS_KEY);
    const settings = raw ? JSON.parse(raw) : {};
    win.localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...settings, apiKey: token }));
  } catch {
    return false;
  }
  win.history.replaceState(null, '', win.location.pathname + win.location.search);
  return true;
}
