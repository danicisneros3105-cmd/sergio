import { useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router';
import { Toaster } from 'sonner';
import './App.css';

import ChatPage from './pages/ChatPage';
const SetupPage = lazy(() => import('./pages/SetupPage'));
const EditorPage = lazy(() => import('./pages/EditorPage'));
const PlansPage = lazy(() => import('./pages/PlansPage'));
const UsagePage = lazy(() => import('./pages/UsagePage'));
const HelpPage = lazy(() => import('./pages/HelpPage'));
const LicensePage = lazy(() => import('./pages/LicensePage'));
const AboutPage = lazy(() => import('./pages/AboutPage'));
const CreatorPage = lazy(() => import('./pages/CreatorPage'));
const GalleryPage = lazy(() => import('./pages/GalleryPage'));
const PayPage = lazy(() => import('./pages/PayPage'));
const OrgPage = lazy(() => import('./pages/OrgPage'));
const ReportPage = lazy(() => import('./pages/ReportPage'));

import { Toolbar } from './components/Shell/Toolbar';
import { apiFetch } from './lib/api';
import { lazy, Suspense } from 'react';

const RELOAD_KEY = 'sergio-reload';
const RELOAD_GRACE_MS = 5000;

function reloadIfVersionMismatch() {
  try {
    const remoteBuild = (import.meta as any).env.VITE_BUILD_ID ?? '';
    const localBuild = sessionStorage.getItem('sergio.build');
    if (!localBuild) {
      sessionStorage.setItem('sergio.build', remoteBuild);
      return;
    }
    if (remoteBuild && localBuild !== remoteBuild) {
      sessionStorage.setItem('sergio.build', remoteBuild);
      if (!sessionStorage.getItem(RELOAD_KEY)) {
        sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
        location.reload();
      }
    }
  } catch {}
}

function clearStaleReload() {
  try {
    const ts = Number(sessionStorage.getItem(RELOAD_KEY) || '0');
    if (Date.now() - ts > RELOAD_GRACE_MS) sessionStorage.removeItem(RELOAD_KEY);
  } catch {}
}

function AppRoutes() {
  const location = useLocation();
  const navigate = useNavigate();
  const licenseDismissed = useRef(false);
  const [licenseNeeded, setLicenseNeeded] = useState(false);
  const [alive, setAlive] = useState(true);
  const [checking, setChecking] = useState(true);

  const showShell = useMemo(() => {
    const noShell = ['/setup', '/about', '/license'];
    return !noShell.includes(location.pathname) && !location.pathname.startsWith('/pagar');
  }, [location.pathname]);

  useEffect(() => {
    reloadIfVersionMismatch();
  }, []);

  useEffect(() => {
    const t = setInterval(clearStaleReload, 2000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiFetch('/v1/health')
      .then((r) => {
        if (cancelled) return;
        setAlive(r.ok);
        setChecking(false);
        if (r.status === 403) {
          try { localStorage.setItem('sergio.license_needed', '1'); } catch {}
          setLicenseNeeded(true);
        } else {
          setLicenseNeeded(false);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setAlive(false);
        setChecking(false);
      });
    return () => { cancelled = true; };
  }, [location.pathname]);

  useEffect(() => {
    try {
      if (localStorage.getItem('sergio.license_needed') === '1' && !licenseDismissed.current) {
        setLicenseNeeded(true);
      }
    } catch {}
  }, []);

  return (
    <div className="app-shell">
      {showShell && <Toolbar />}
      <main className="app-main">
        <Suspense fallback={<div className="app-loading">Cargando…</div>}>
          <Routes>
            <Route path="setup" element={<SetupPage />} />
            <Route path="editor" element={<CreatorPage />} />
            <Route path="creator/*" element={<CreatorPage />} />
            <Route path="planes" element={<PlansPage />} />
            <Route path="uso" element={<UsagePage />} />
            <Route path="ayuda" element={<HelpPage />} />
            <Route path="about" element={<AboutPage />} />
            <Route path="license" element={<LicensePage />} />
            <Route path="galeria" element={<GalleryPage />} />
            <Route path="pagar" element={<PayPage />} />
            <Route path="org/*" element={<OrgPage />} />
            <Route path="reporte" element={<ReportPage />} />
            <Route index element={<Navigate to="/editor" replace />} />
            <Route path="*" element={<div className="page-center"><h2>Pagina no encontrada</h2><p>Volviendo al inicio…</p></div>} />
          </Routes>
        </Suspense>
      </main>

      {licenseNeeded && !licenseDismissed.current && (
        <div className="license-toast">
          <span>Es posible que necesites una licencia para usar Sergio en este servidor.</span>
          <button onClick={() => navigate('/license')}>Ver licencia</button>
          <button onClick={() => { licenseDismissed.current = true; setLicenseNeeded(false); }}>Descartar</button>
        </div>
      )}

      {!checking && !alive && (
        <div className="offline-banner">
          <span>Sergio parece estar fuera de linea. Algunas funciones no estaran disponibles.</span>
          <button onClick={() => location.reload()}>Reintentar</button>
        </div>
      )}

      <Toaster
        position="bottom-right"
        toastOptions={{
          style: { background: '#1e1e2e', color: '#e4e4e7', border: '1px solid #27273a' },
        }}
      />
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="chat/*" element={<ChatPage />} />
      <Route path="*" element={<AppRoutes />} />
    </Routes>
  );
}

export default App;
