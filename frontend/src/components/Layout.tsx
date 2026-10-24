import { Suspense, useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router';
import { Menu } from 'lucide-react';
import { ApprovalBell } from './ApprovalBell';
import { SystemPulse } from './SystemPulse';
import { Toolbar } from './Shell/Toolbar';
import { checkHealth } from '../lib/api';
import { LiveCaptions, LiveStarter } from './Live/LiveOrb';
import { ReminderWatcher } from './Reminders/ReminderWatcher';
import { startAppWindow } from '../lib/appWindow';
import { inPane } from '../lib/split';
import { SplitView } from './Split/SplitView';

// Read once: inside the second pane of a split screen (the app in «pane»
// mode), navigation later drops the ?pane=1 but the window stays a pane.
const PANE = inPane() || (typeof window !== 'undefined' && window.name === 'sergio-pane');

const HISTORY_KEY = 'sergio-history-open';

// The shell, like ChatGPT's: one sidebar on the left (open with names and
// chats, or folded into a rail of icons; a drawer on a phone), the page in
// the middle, and the always-on conversation underneath it all.
export function Layout() {
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);
  const [historyOpen, setHistoryOpen] = useState(() => {
    try {
      // Like ChatGPT: open on a computer until you close it; a rail on a tablet, closed on a phone.
      const saved = localStorage.getItem(HISTORY_KEY);
      return window.innerWidth >= 1100 && saved !== '0';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    const check = () => checkHealth().then(setApiReachable);
    check();
    const interval = setInterval(check, 30000);
    const onFocus = () => check();
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const toggleHistory = () => {
    setHistoryOpen((open) => {
      try {
        localStorage.setItem(HISTORY_KEY, open ? '0' : '1');
      } catch {
        // a per-viewer convenience only
      }
      return !open;
    });
  };

  const navigate = useNavigate();

  useEffect(() => {
    // A new user lands on «Primeros pasos» once (GetStartedPage marks it
    // seen). Only from the start page: a window opened on Nodes, Salud or a
    // chat stays there. (It never marked itself seen and sent every new
    // window back here: «no puedo abrir nada».)
    try {
      const home = window.location.pathname === '/' || window.location.pathname === '';
      if (home && !localStorage.getItem('sergio-onboarded')) {
        navigate('/get-started', { replace: true });
      }
    } catch {
      // storage blocked: no first-run guide, nothing else changes
    }
  }, [navigate]);

  // One window: the desktop shows its pages here instead of opening another.
  useEffect(() => {
    if (!PANE) startAppWindow();
  }, []);

  // In the pane: the window around it says what to show; Ctrl \ closes it.
  useEffect(() => {
    if (!PANE) return;
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin || e.source !== window.parent) return;
      const data = e.data as { type?: string; path?: string } | null;
      if (data?.type === 'sergio:navigate' && typeof data.path === 'string' && data.path.startsWith('/')) {
        navigate(data.path);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
        e.preventDefault();
        window.parent.postMessage({ type: 'sergio:split-close' }, window.location.origin);
      }
    };
    window.addEventListener('message', onMessage);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('message', onMessage);
      window.removeEventListener('keydown', onKey);
    };
  }, [navigate]);

  useEffect(() => {
    const onNav = (e: Event) => {
      const route = (e as CustomEvent<string>).detail;
      if (typeof route === 'string' && route.startsWith('/')) {
        navigate(route);
      }
    };
    window.addEventListener('sergio:navigate', onNav);
    return () => window.removeEventListener('sergio:navigate', onNav);
  }, [navigate]);
  // A device without access (another computer, the phone) goes to sign in.
  useEffect(() => {
    let sent = false;
    const onLogin = () => {
      if (sent || window.location.pathname === '/entrar') return;
      sent = true;
      navigate('/entrar');
    };
    window.addEventListener('sergio:needs-login', onLogin);
    return () => window.removeEventListener('sergio:needs-login', onLogin);
  }, [navigate]);

  if (PANE) {
    // The second screen of a split: the page alone, no sidebar, no voice.
    return (
      <div className="app-shell pane-shell">
        <div className="app-main">
          <main className="flex-1 min-h-0 relative">
            <Suspense fallback={<div className="paper-page" aria-busy="true" />}>
              <Outlet />
            </Suspense>
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <SystemPulse apiReachable={apiReachable} />
      <LiveStarter />
      <ReminderWatcher />
      <Toolbar historyOpen={historyOpen} onToggleHistory={toggleHistory} />
      <div className="app-main">
        {!historyOpen && (
          <button type="button" className="sb-open-mobile" aria-label="Abrir la barra lateral" onClick={toggleHistory}>
            <Menu size={20} strokeWidth={1.8} />
          </button>
        )}
        <ApprovalBell />
        {apiReachable === false && (
          <div className="app-banner" role="status">
            <span>No puedo conectar con Sergio. Lo que escriba en el Workspace se guarda en este equipo.</span>
            <button onClick={() => navigate('/settings')} className="app-banner-action">
              Cambiar dirección
            </button>
          </div>
        )}
        <main className="flex-1 min-h-0 relative">
          <SplitView>
            <Suspense fallback={<div className="paper-page" aria-busy="true" />}>
              <Outlet />
            </Suspense>
          </SplitView>
          <LiveCaptions />
        </main>
      </div>
    </div>
  );
}
