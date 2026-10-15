// Creator spaces built on the real programs: Diseño is OpenDesign (and
// Sergio can lay a design out inside it), Código is VSCodium. While a
// program is not installed yet, the quick editor that ships with Sergio
// stays available underneath.

import { lazy, Suspense } from 'react';
import { MonitorUp } from 'lucide-react';
import { toast } from 'sonner';
import { installProgram, openProgram, type Program } from '../../lib/creatorPrograms';
import { EmbeddedProgram } from './Programs';

const DesignStudio = lazy(() => import('./DesignStudio'));
const CodeStudio = lazy(() => import('./CodeStudio'));

const Quick = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<div className="creator-loading">Abriendo el editor rápido…</div>}>{children}</Suspense>
);

// Diseño is the Canva-like editor itself (owner, 2026-10: «igual a Canva»).
// OpenDesign stays installed and can still be opened from Extensiones.
export function DesignSpace(_props: { programs: Program[] | null; reload: () => void }) {
  return (
    <Quick>
      <DesignStudio mode="diseno" />
    </Quick>
  );
}

export function CodeSpace({ programs, reload }: { programs: Program[] | null; reload: () => void }) {
  const program = programs?.find((p) => p.id === 'vscodium');
  const desktop = program?.windows;
  const openDesktop = async () => {
    try {
      const out = desktop?.installed ? await openProgram('vscodium') : await installProgram('vscodium', 'windows');
      toast.success(out.message || 'Hecho.');
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <EmbeddedProgram
      program={program}
      reload={reload}
      fallback={
        <Quick>
          <CodeStudio />
        </Quick>
      }
      toolbar={
        desktop?.reachable && (
          <button type="button" className="paper-button" data-variant="quiet" onClick={() => void openDesktop()}>
            <MonitorUp size={15} /> {desktop.installed ? 'Abrir en Windows' : 'Instalar en Windows'}
          </button>
        )
      }
    />
  );
}
