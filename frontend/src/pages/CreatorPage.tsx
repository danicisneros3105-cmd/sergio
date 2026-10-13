// Creator: one place to make things, built on real programs instead of
// copies of them (owner, 2026-10). 3D in Sergio's modeller and Blender;
// architecture with FreeCAD, Blender + Bonsai and LibreCAD (the plan travels
// as IFC or DXF); design in OpenDesign; images and video in ArtCraft and
// Kdenlive; code in VSCodium; stocks with Kronos. Each space loads only when
// opened. The «Anatomy» figures are not a space: Sergio draws them in chat.

import { lazy, Suspense } from 'react';
import { Navigate, NavLink, useParams } from 'react-router';
import { Box, Building2, Code2, Image, LayoutTemplate, LineChart, PanelsTopLeft } from 'lucide-react';
import { ProgramShelf, usePrograms } from '../components/Creator/Programs';
import { CodeSpace, DesignSpace } from '../components/Creator/RealSpaces';

const Studio3D = lazy(() => import('../components/Creator/Studio3D'));
const DesignStudio = lazy(() => import('../components/Creator/DesignStudio'));
const BolsaStudio = lazy(() => import('../components/Creator/BolsaStudio'));

export const SPACES = [
  { id: 'modelado', label: 'Modelado 3D', hint: 'Modelado 3D', icon: Box },
  { id: 'arquitectura', label: 'Arquitectura', hint: 'Arquitectura', icon: Building2 },
  { id: 'diseno', label: 'Diseño', hint: 'Diseño', icon: LayoutTemplate },
  { id: 'imagen', label: 'Imagen y video', hint: 'Imagen y video', icon: Image },
  { id: 'codigo', label: 'Código', hint: 'Código', icon: Code2 },
  { id: 'bolsa', label: 'Bolsa', hint: 'Bolsa', icon: LineChart },
] as const;

type SpaceId = (typeof SPACES)[number]['id'];

function Space({ id }: { id: SpaceId }) {
  const { programs, reload } = usePrograms();
  switch (id) {
    case 'modelado':
    case 'arquitectura':
      return (
        <div className="creator-stack">
          <ProgramShelf space={id} programs={programs} reload={reload} />
          <Studio3D key={id} mode={id} />
        </div>
      );
    case 'diseno':
      return <DesignSpace programs={programs} reload={reload} />;
    case 'imagen':
      return (
        <div className="creator-stack">
          <ProgramShelf space="imagen" programs={programs} reload={reload} />
          <DesignStudio key={id} mode="imagen" />
        </div>
      );
    case 'codigo':
      return <CodeSpace programs={programs} reload={reload} />;
    case 'bolsa':
      return <BolsaStudio programs={programs} reload={reload} />;
  }
}

export default function CreatorPage() {
  const { space } = useParams();
  // The old Anatomía space is now a hidden skill used in the chat.
  if (space === 'anatomia') return <Navigate to="/creator" replace />;
  const current = (SPACES.find((s) => s.id === space)?.id ?? 'modelado') as SpaceId;

  return (
    <div className="creator-page">
      <header className="creator-head">
        <h1>Creator</h1>
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
        <NavLink to="/extensiones" className="creator-tab creator-all" title="Extensiones">
          <PanelsTopLeft size={16} strokeWidth={1.8} />
          <span>Extensiones</span>
        </NavLink>
      </header>
      <main className="creator-body">
        <Suspense fallback={<div className="creator-loading">Abriendo {SPACES.find((s) => s.id === current)?.label}…</div>}>
          <Space id={current} />
        </Suspense>
      </main>
    </div>
  );
}
