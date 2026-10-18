import { Suspense, useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router';
import { Menu } from 'lucide-react';
import { ApprovalBell } from './ApprovalBell';
import { SystemPulse } from './SystemPulse';
import { Toolbar } from './Shell/Toolbar';
import { checkHealth } from '../lib/api';
import { LiveCaptions, LiveStarter } from './Live/LiveOrb';
import { StickyNotesLayer } from './StickyNotes/StickyNotesLayer';

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
    const onNav = (e: Event) => {
      const route = (e as CustomEvent<string>).detail;
      if (typeof route === 'string' && route.startsWith('/')) {
        navigate(route);
      }
    };
    window.addEventListener('sergio:navigate', onNav);
    return () => window.removeEventListener('sergio:navigate', onNav);
  }, [navigate]);

  return (
    <div className="app-shell">
      <SystemPulse apiReachable={apiReachable} />
      <LiveStarter />
      <StickyNotesLayer />
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
          <Suspense fallback={<div className="paper-page" aria-busy="true" />}>
            <Outlet />
          </Suspense>
          <LiveCaptions />
        </main>
      </div>
    </div>
  );
}
