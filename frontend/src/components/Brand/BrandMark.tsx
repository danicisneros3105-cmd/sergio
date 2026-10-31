// A service's logo on its tile, in its own colour (lib/brands.ts); a monogram
// when Sergio has no logo for it.

import { useEffect, useState, type CSSProperties } from 'react';
import { apiFetch } from '../../lib/api';
import { brandFor, isLight, type Brand } from '../../lib/brands';

/** The words of a server address that can name a brand: «mcp.notion.com» → notion. */
function urlWords(url?: string): string[] {
  if (!url) return [];
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host.split('.').filter((w) => w.length > 2 && !['mcp', 'api', 'www', 'com', 'net', 'org', 'app', 'run', 'dev', 'ai', 'io'].includes(w));
  } catch {
    return [];
  }
}

interface SiteLogo { hex: string; icon: string }
const siteLogos = new Map<string, Promise<SiteLogo | null>>();

/** The service's own icon and colour, from its website (server: /v1/mcp/marca). */
function siteLogo(url: string): Promise<SiteLogo | null> {
  let got = siteLogos.get(url);
  if (!got) {
    got = apiFetch(`/v1/mcp/marca?url=${encodeURIComponent(url)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => (d && d.icon ? (d as SiteLogo) : null))
      .catch(() => null);
    siteLogos.set(url, got);
  }
  return got;
}

function monogram(name: string): string {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? '?').slice(0, 2)).toUpperCase();
}

export function BrandMark({ name, id, size = 36, brand, url }: { name: string; id?: string; size?: number; brand?: Brand | null; url?: string }) {
  const b = brand === undefined ? brandFor(id, name, ...urlWords(url)) : brand;
  // Owner, 29 Oct 2026: «el MCP que tengo conectado aún está sin logo y color»:
  // a service Sergio has no logo for shows the one its own site publishes.
  const [site, setSite] = useState<SiteLogo | null>(null);
  useEffect(() => {
    if (b || !url || !/^https:\/\//.test(url)) return;
    let live = true;
    void siteLogo(url).then((s) => live && setSite(s));
    return () => {
      live = false;
    };
  }, [b, url]);
  if (!b && site) {
    return (
      <span className="brand-mark" data-site style={{ width: size, height: size, ['--brand' as string]: `#${site.hex}` } as CSSProperties} title={name} aria-hidden>
        <img src={site.icon} alt="" width={size * 0.62} height={size * 0.62} />
      </span>
    );
  }
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
