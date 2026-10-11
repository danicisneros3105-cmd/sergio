import { useId, type CSSProperties } from 'react';
import './nodes.css';

/** Actual running goals only; the liquid filter never touches text or controls. */
export function LiquidNotch({ running }: { running: number }) {
  const id = `node-liquid-${useId().replace(/:/g, '')}`;
  if (!Number.isFinite(running) || running < 1) return null;
  const count = Math.floor(running);
  return <a href="/agents" className="node-liquid-notch" aria-label={`${count} objetivos en ejecución. Abrir Agent Swarm`}>
    <svg className="node-liquid-background" width="180" height="64" viewBox="0 0 180 64" aria-hidden="true">
      <defs><filter id={id} filterUnits="userSpaceOnUse" x="0" y="0" width="180" height="64" colorInterpolationFilters="sRGB">
        <feGaussianBlur in="SourceGraphic" stdDeviation="12" result="blur" />
        <feColorMatrix in="blur" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 25 -12" result="goo" />
        <feComposite in="SourceGraphic" in2="goo" operator="atop" />
      </filter></defs>
      <g className={count > 1 ? 'node-liquid-shapes node-liquid-split' : 'node-liquid-shapes'} style={{ '--liquid-filter': `url(#${id})` } as CSSProperties} fill="#09090b">
        <rect x="12" y="14" width="112" height="36" rx="18" />
        {count > 1 && <circle className="node-liquid-bubble" cx="150" cy="32" r="18" />}
      </g>
    </svg>
    <span className="node-liquid-label">{count} {count === 1 ? 'objetivo' : 'objetivos'}</span>
    {count > 1 && <span className="node-liquid-count" aria-hidden="true">+{count - 1}</span>}
  </a>;
}
