// «Instalar Sergio»: the web app as an app (own window, icon, start menu /
// home screen). Shown only when the browser can install it and it is not
// installed yet; on iPhone and iPad (no install event) it says the two taps.
// Closing it hides it for 30 days. Nothing is added to the sidebar.

import { useEffect, useState } from 'react';
import { Download, X } from 'lucide-react';

interface InstallEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: string }>;
}

const KEY = 'sergio.install.hidden';
const DAYS = 30;
// The browser can fire this while the sign-in check still hides the app.
let deferredInstall: InstallEvent | null = null;
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstall = e as InstallEvent;
  });
  window.addEventListener('appinstalled', () => { deferredInstall = null; });
}

function standalone(): boolean {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function hiddenRecently(): boolean {
  try {
    const at = Number(localStorage.getItem(KEY) || 0);
    return Date.now() - at < DAYS * 86400000;
  } catch {
    return false;
  }
}

export function isAppleMobile(ua: string = navigator.userAgent): boolean {
  return /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
}

export function InstallPrompt() {
  const [event, setEvent] = useState<InstallEvent | null>(() => deferredInstall);
  const [apple, setApple] = useState(false);
  const [gone, setGone] = useState(() => standalone() || hiddenRecently());

  useEffect(() => {
    if (gone) return;
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setEvent(e as InstallEvent);
    };
    const onInstalled = () => setGone(true);
    window.addEventListener('beforeinstallprompt', onPrompt);
    window.addEventListener('appinstalled', onInstalled);
    if (isAppleMobile()) setApple(true);
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt);
      window.removeEventListener('appinstalled', onInstalled);
    };
  }, [gone]);

  if (gone || (!event && !apple)) return null;

  const close = () => {
    try {
      localStorage.setItem(KEY, String(Date.now()));
    } catch {
      /* private mode: it just shows again next time */
    }
    setGone(true);
  };
  const install = async () => {
    if (!event) return;
    try {
      await event.prompt();
      const choice = await event.userChoice;
      if (choice.outcome === 'accepted') setGone(true);
    } catch {
      // An expired prompt cannot be reused. Wait for a new browser event.
    } finally {
      deferredInstall = null;
      setEvent(null);
    }
  };

  return (
    <div className="install-chip" role="dialog" aria-label="Instalar Sergio">
      <Download size={16} aria-hidden="true" />
      {event ? (
        <button type="button" className="install-go" onClick={() => void install()}>
          Instalar Sergio como app
        </button>
      ) : (
        <span>Para instalarlo: Compartir, luego «Añadir a pantalla de inicio».</span>
      )}
      <button type="button" className="install-close" aria-label="Ahora no" onClick={close}>
        <X size={14} />
      </button>
    </div>
  );
}
