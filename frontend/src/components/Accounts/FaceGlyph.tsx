// The Visage mark, Sergio's own (owner, 3 Nov 2026: «cambiar logo de
// reconocimiento facial»; the old one copied Apple's Face ID corners): an
// oval face drawn as contour lines, like a depth scan, with the two eyes.
// States: still, scanning (the lines light in turn), the check, or a shake.

export function FaceGlyph({ size = 72, state = 'idle' }: { size?: number; state?: 'idle' | 'scan' | 'ok' | 'fail' }) {
  return (
    <svg className="faceid-glyph visage-mark" data-state={state} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <ellipse cx="32" cy="32" rx="20" ry="25" />
      {state === 'ok' ? (
        <path className="faceid-check" d="M22 33l7 7 14-16" />
      ) : (
        <>
          <path className="visage-line" d="M17 24c10-4 20-4 30 0" />
          <path className="visage-line" d="M13 33c12-3 26-3 38 0" />
          <path className="visage-line" d="M16 42c10 3 22 3 32 0" />
          <circle className="visage-eye" cx="25" cy="29" r="1.6" />
          <circle className="visage-eye" cx="39" cy="29" r="1.6" />
        </>
      )}
    </svg>
  );
}
