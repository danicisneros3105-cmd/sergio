// The Visage mark, Sergio's own (owner, 3 Nov 2026: «cambiar logo de
// reconocimiento facial» and then «mejora el icono»): a faint ring with one
// accent arc and its dot — the scan — around a simple face (two eyes and a
// smile). No corner brackets and no nose, so it is not Apple's Face ID.
// States: still, scanning (the arc sweeps the ring), the check, or a shake.

export function FaceGlyph({ size = 72, state = 'idle' }: { size?: number; state?: 'idle' | 'scan' | 'ok' | 'fail' }) {
  return (
    <svg className="faceid-glyph visage-mark" data-state={state} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <circle className="visage-ring" cx="32" cy="32" r="26" />
      <g className="visage-sweep">
        <path className="visage-arc" d="M32 6a26 26 0 0 1 26 26" />
        <circle className="visage-dot" cx="58" cy="32" r="2.6" />
      </g>
      {state === 'ok' ? (
        <path className="faceid-check" d="M22 33l7 7 14-16" />
      ) : (
        <>
          <path className="visage-eye" d="M24 26.5v4.5M40 26.5v4.5" />
          <path className="visage-smile" d="M23.5 39.5c5 4.6 12 4.6 17 0" />
        </>
      )}
    </svg>
  );
}
