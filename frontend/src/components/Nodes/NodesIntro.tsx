// The first time the Nodes open: the four fall into the page (real physics,
// you can throw them), and Sergio's pointer introduces each one in a mini
// tour. Once, then never again (owner, 2 Nov 2026).
import { useEffect, useMemo, useState } from 'react';
import { ShapePhysics } from '../Fx/ShapePhysics';
import { NodeCritter } from './NodeCritter';
import { pointAt } from '../../lib/pointer';
import type { Catalog, SergioNode } from '../../lib/nodes';
import { look } from '../../pages/nodes/shared';
import './intro.css';

export const NODES_INTRO = 'sergio-nodes-intro-v1';

const ROLES: Record<string, string> = {
  rihno: 'Organiza todo: su agenda, sus pendientes y lo que hacen los demás.',
  manchas: 'Investiga a fondo y mueve su marketing.',
  hous: 'Diseña: imágenes, videos, páginas y marca.',
  tennessee: 'Le dice la verdad con datos, aunque no guste. Estrategia y negocio.',
};

export function introSeen(): boolean {
  try {
    return localStorage.getItem(NODES_INTRO) === '1';
  } catch {
    return true;
  }
}

function markSeen() {
  try {
    localStorage.setItem(NODES_INTRO, '1');
  } catch {
    /* no storage */
  }
}

export function NodesIntro({ nodes, catalog, onClose }: { nodes: SergioNode[]; catalog: Catalog | null; onClose: () => void }) {
  const team = useMemo(() => nodes.filter((n) => n.team).slice(0, 4), [nodes]);
  const [step, setStep] = useState(0);
  const [landed, setLanded] = useState(false);
  const steps = useMemo(
    () => [
      { title: 'Su equipo: cuatro Nodes', text: 'Trabajan para usted todo el día. Puede lanzarlos con el ratón o el dedo.' },
      ...team.map((n) => {
        const member = catalog?.team?.find((m) => m.key === n.team);
        return {
          title: n.name,
          text: member?.does || ROLES[n.team || ''] || member?.role || '',
          target: `[data-intro-node="${n.team}"]`,
        };
      }),
      {
        title: 'Cómo se usan',
        text: 'Escríbale a cualquiera en su chat. «Cancelar acción» suelta lo que hace; «Detener» lo pausa. Nada se envía, compra ni publica sin su sí.',
      },
    ],
    [team, catalog],
  );
  const cur = steps[step];

  useEffect(() => {
    if (!landed) return;
    const t = (cur as { target?: string }).target;
    if (t) pointAt({ target: t, text: cur.title, ms: 2600 });
  }, [step, landed, cur]);

  const close = () => {
    markSeen();
    onClose();
  };

  return (
    <div className="ni-scrim" role="dialog" aria-modal="true" aria-label="Conozca a los Nodes">
      <div className="ni-card">
        <ShapePhysics
          height={260}
          onSettle={() => setLanded(true)}
          shapes={team.map((n) => ({
            key: n.id,
            size: 104,
            node: (
              <span className="ni-node" data-intro-node={n.team} data-on={(cur as { target?: string }).target?.includes(`"${n.team}"`) || undefined}>
                <NodeCritter look={look(n)} size={72} label={n.name} />
                <b>{n.name}</b>
              </span>
            ),
          }))}
        />
        <div className="ni-text" aria-live="polite">
          <h2>{cur.title}</h2>
          <p>{cur.text}</p>
        </div>
        <div className="ni-foot">
          <span className="ni-dots" aria-hidden="true">
            {steps.map((s, i) => (
              <i key={s.title + i} data-on={i === step || undefined} />
            ))}
          </span>
          <button type="button" className="ni-ghost" onClick={close}>
            Saltar
          </button>
          {step < steps.length - 1 ? (
            <button type="button" className="ni-primary" onClick={() => setStep(step + 1)}>
              Siguiente
            </button>
          ) : (
            <button type="button" className="ni-primary" onClick={close}>
              Empezar
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default NodesIntro;
