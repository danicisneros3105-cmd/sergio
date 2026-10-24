// The Face ID glyph, in Sergio's colours: still, scanning, the check, or a shake.

/** Apple-style Face ID glyph, Sergio's colours. */
export function FaceGlyph({ size = 72, state = 'idle' }: { size?: number; state?: 'idle' | 'scan' | 'ok' | 'fail' }) {
  return (
    <svg className="faceid-glyph" data-state={state} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <path d="M6 20V12a6 6 0 0 1 6-6h8M44 6h8a6 6 0 0 1 6 6v8M58 44v8a6 6 0 0 1-6 6h-8M20 58h-8a6 6 0 0 1-6-6v-8" />
      {state === 'ok' ? (
        <path className="faceid-check" d="M20 33l8 8 16-18" />
      ) : (
        <>
          <path d="M22 24v5M42 24v5M32 24v12h-3M24 44c5 4 11 4 16 0" />
        </>
      )}
    </svg>
  );
}
