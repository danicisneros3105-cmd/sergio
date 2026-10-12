// Creator: one place to make things. Six spaces that share the same layout
// (tools left, work in the middle, properties right, "ask Sergio" at the
// bottom): 3D modelling, architecture, design, photos, anatomy figures and
// code. Each space loads only when opened, so Creator starts fast.

import { lazy, Suspense } from 'react';
import { NavLink, useParams } from 'react-router';
import { Box, Building2, Code2, Image, LayoutTemplate, Cog } from 'lucide-react';

const Studio3D = lazy(() => import('../components/Creator/Studio3D'));
const DesignStudio = lazy(() => import('../components/Creator/DesignStudio'));
const AnatomyStudio = lazy(() => import('../components/Creator/AnatomyStudio'));
const CodeStudio = lazy(() => import('../components/Creator/CodeStudio'));

export const SPACES = [
  { id: 'modelado', label: 'Modelado 3D', hint: 'Objetos en 3D, como en Blender', icon: Box, color: '#4f7cff' },
  { id: 'arquitectura', label: 'Arquitectura', hint: 'Planos, muros, puertas y ventanas', icon: Building2, color: '#10b981' },
  { id: 'diseno', label: 'Diseño', hint: 'Posts, pósters y presentaciones', icon: LayoutTemplate, color: '#ec4899' },
  { id: 'imagen', label: 'Imagen', hint: 'Fotos: retoque, fondo e IA', icon: Image, color: '#f59e0b' },
  { id: 'anatomia', label: 'Anatomía', hint: 'Láminas que explican máquinas', icon: Cog, color: '#8b5cf6' },
  { id: 'codigo', label: 'Código', hint: 'Editor con IA, como Cursor', icon: Code2, color: '#0ea5e9' },
] as const;

type SpaceId = (typeof SPACES)[number]['id'];

function Space({ id }: { id: SpaceId }) {
  switch (id) {
    case 'modelado':
    case 'arquitectura':
      return <Studio3D key={id} mode={id} />;
    case 'diseno':
    case 'imagen':
      return <DesignStudio key={id} mode={id} />;
    case 'anatomia':
      return <AnatomyStudio />;
    case 'codigo':
      return <CodeStudio />;
  }
}

export default function CreatorPage() {
  const { space } = useParams();
  const current = (SPACES.find((s) => s.id === space)?.id ?? 'modelado') as SpaceId;

  return (
    <div className="creator-page">
      <header className="creator-head">
        <h1>Creator</h1>
        <nav className="creator-tabs" aria-label="Espacios de Creator">
          {SPACES.map(({ id, label, hint, icon: Icon, color }) => (
            <NavLink
              key={id}
              to={`/creator/${id}`}
              className="creator-tab"
              aria-current={current === id ? 'page' : undefined}
              title={hint}
              style={{ ['--sec' as string]: color }}
            >
              <Icon size={16} strokeWidth={2} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="creator-body">
        <Suspense fallback={<div className="creator-loading">Abriendo {SPACES.find((s) => s.id === current)?.label}…</div>}>
          <Space id={current} />
        </Suspense>
      </main>
    </div>
  );
}
