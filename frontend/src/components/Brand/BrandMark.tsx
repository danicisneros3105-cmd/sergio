// A service's logo on its tile, in its own colour (lib/brands.ts); a monogram
// when Sergio has no logo for it.

import type { CSSProperties } from 'react';
import { brandFor, isLight, type Brand } from '../../lib/brands';

function monogram(name: string): string {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? '?').slice(0, 2)).toUpperCase();
}

export function BrandMark({ name, id, size = 36, brand }: { name: string; id?: string; size?: number; brand?: Brand | null }) {
  const b = brand === undefined ? brandFor(id, name) : brand;
  if (!b) {
    return (
      <span className="brand-mark" data-plain style={{ width: size, height: size, fontSize: size * 0.36 }} aria-hidden>
        {monogram(name)}
      </span>
    );
  }
  const dark = isLight(b.hex);
  return (
    <span className="brand-mark" data-dark={dark} style={{ width: size, height: size }} title={b.title} aria-hidden>
      <svg viewBox="0 0 24 24" width={size * 0.56} height={size * 0.56} fill={`#${b.hex}`} role="img">
        <path d={b.path} />
      </svg>
    </span>
  );
}

/** Style for a card or row that carries the brand's colour bar. */
export function brandStyle(...names: Array<string | undefined>): CSSProperties | undefined {
  const b = brandFor(...names);
  return b ? ({ ['--brand' as string]: `#${b.hex}` } as CSSProperties) : undefined;
}
