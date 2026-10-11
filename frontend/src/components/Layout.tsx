import { Suspense, useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router';
import { ApprovalBell } from './ApprovalBell';
import { SystemPulse } from './SystemPulse';
import { Toolbar } from './Shell/Toolbar';
import { HistoryPanel } from './Shell/HistoryPanel';
import { checkHealth } from '../lib/api';

const HISTORY_KEY = 'sergio-history-open';

// The shell, like ChatGPT and Kimi: a rail of icons on the left (names on
// hover), the history beside it when you want it, the page in the middle.
// Black, white and one light blue; nothing else.
export function Layout() {
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);
  const [historyOpen, setHistoryOpen] = useState(() => {
    try {
      // Like ChatGPT: open on a wide screen until you close it.
      const saved = localStorage.getItem(HISTORY_KEY);
      return window.innerWidth >= 1280 ? saved !== '0' : saved === '1' && window.innerWidth >= 1024;
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

  return (
    <div className="app-shell">
      <SystemPulse apiReachable={apiReachable} />
      <Toolbar historyOpen={historyOpen} onToggleHistory={toggleHistory} />
      {historyOpen && (
        <>
          <div className="history-scrim" onClick={toggleHistory} aria-hidden="true" />
          <HistoryPanel onClose={toggleHistory} />
        </>
      )}
      <div className="app-main">
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
        </main>
      </div>
    </div>
  );
}
