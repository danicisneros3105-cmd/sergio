import { Suspense, useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router';
import { ApprovalBell } from './ApprovalBell';
import { SystemPulse } from './SystemPulse';
import { StatusBar } from './Shell/StatusBar';
import { Toolbar } from './Shell/Toolbar';
import { QuickCapture } from './Shell/QuickCapture';
import { checkHealth } from '../lib/api';

// The e-paper shell: the device's status bar on top, the page in the middle
// (title centred, content on a calm grid), the toolbar of thin icons at the
// bottom. A matte grain is painted into the paper (index.css .paper-app).
export function Layout() {
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);

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

  const navigate = useNavigate();

  return (
    <div className="paper-app flex flex-col h-full w-full overflow-hidden">
      <SystemPulse apiReachable={apiReachable} />
      <StatusBar apiReachable={apiReachable} />
      <ApprovalBell />

      {apiReachable === false && (
        <div
          className="flex items-center gap-3 px-4 py-2 text-[13px] shrink-0"
          style={{
            background: 'color-mix(in srgb, var(--color-error) 7%, transparent)',
            borderTop: '1px solid color-mix(in srgb, var(--color-error) 14%, transparent)',
            borderBottom: '1px solid color-mix(in srgb, var(--color-error) 14%, transparent)',
            color: 'var(--color-text)',
          }}
        >
          <span>No puedo conectar con Sergio. Lo que escriba en el Workspace se guarda en este equipo.</span>
          <button
            onClick={() => navigate('/settings')}
            className="underline cursor-pointer ml-auto shrink-0"
            style={{ color: 'var(--color-accent)' }}
          >
            Cambiar dirección
          </button>
        </div>
      )}

      <main className="flex-1 min-h-0 relative">
        <Suspense fallback={<div className="paper-page" aria-busy="true" />}>
          <Outlet />
        </Suspense>
      </main>
      <QuickCapture />
      <Toolbar />
    </div>
  );
}
