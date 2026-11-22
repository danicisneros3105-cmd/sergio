import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router';
import { sessionNeed } from '../lib/session';
import './VideoWorkspace.css';

const NAV = [
  { path: '/video', label: 'Video' },
  { path: '/galeria', label: 'Galería' },
  { path: '/planes', label: 'Planes' },
] as const;

export function VideoLayout() {
  const [ready, setReady] = useState(false);
  const { pathname } = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    let alive = true;
    void sessionNeed().then((need) => {
      if (!alive) return;
      if (need !== 'ok') {
        navigate(need === 'crear' ? '/entrar?crear=1' : '/entrar', { replace: true });
        return;
      }
      setReady(true);
    }).catch(() => {
      if (alive) navigate('/entrar', { replace: true });
    });
    return () => { alive = false; };
  }, [navigate]);

  if (!ready) return <main className="paper-page" aria-busy="true" />;

  return (
    <div className="video-only-shell">
      <header className="video-only-header">
        <Link className="video-only-brand" to="/video">Sergio</Link>
        <nav className="video-only-nav" aria-label="Navegación principal">
          {NAV.map((item) => {
            const active = pathname === item.path || pathname.startsWith(`${item.path}/`);
            return <Link key={item.path} to={item.path} aria-current={active ? 'page' : undefined}>{item.label}</Link>;
          })}
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}

export default VideoLayout;
