// Creator: refocused 100% on Video editing. All other spaces hidden but code preserved.
// The video editor (VideoStudio) is now the default and only visible space.
// Other spaces are accessible by direct URL only.

import { lazy, Suspense } from 'react';
import { Navigate, NavLink, useParams } from 'react-router';
import { Film } from 'lucide-react';

const VideoStudio = lazy(() => import('../components/VideoStudio/VideoStudio'));

// All spaces still exist in code but only Video is exposed in UI
export const SPACES = [
  { id: 'imagen', label: 'Studio Video', hint: 'Editor de video profesional con IA', icon: Film },
  // Hidden from nav but accessible by URL:
  // modelado, arquitectura, diseno, prototipos, codigo, bolsa
] as const;

type SpaceId = (typeof SPACES)[number]['id'];

function Space({ id }: { id: SpaceId }) {
  if (id === 'imagen') {
    return <VideoStudio />;
  }
  return <Navigate to="/creator/imagen" replace />;
}

export default function CreatorPage() {
  const { space } = useParams();
  if (space === 'anatomia') return <Navigate to="/creator" replace />;
  const current = (SPACES.find((s) => s.id === space)?.id ?? 'imagen') as SpaceId;

  return (
    <div className="creator-page">
      <header className="creator-head">
        <h1><Film size={18} /> Studio Video</h1>
        <nav className="creator-tabs" aria-label="Espacios de Creator">
          {SPACES.map(({ id, label, hint, icon: Icon }) => (
            <NavLink
              key={id}
              to={`/creator/${id}`}
              className="creator-tab"
              aria-current={current === id ? 'page' : undefined}
              title={hint}
            >
              <Icon size={16} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="creator-body">
        <Suspense fallback={<div className="creator-loading">Abriendo Studio Video…</div>}>
          <Space id={current} />
        </Suspense>
      </main>
    </div>
  );
}
