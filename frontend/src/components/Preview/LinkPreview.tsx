// A web link as a card: picture, title, a line of description and the site
// (owner, 3 Nov 2026: «búsqueda en la web con imágenes y preview»). The
// preview is read by Sergio's server (/v1/vista-previa) only when the card
// comes into view, and the picture is served by Sergio itself.
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../lib/api';
import './link-preview.css';

export interface Preview {
  url: string;
  title: string;
  description: string;
  site: string;
  host: string;
  picture?: string;
}

const seen = new Map<string, Promise<Preview | null>>();

function load(url: string): Promise<Preview | null> {
  let p = seen.get(url);
  if (!p) {
    p = apiFetch(`/v1/vista-previa?url=${encodeURIComponent(url)}`)
      .then((r) => (r.ok ? (r.json() as Promise<Preview>) : null))
      .catch(() => null);
    seen.set(url, p);
  }
  return p;
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export function LinkPreview({ url, compact = false }: { url: string; compact?: boolean }) {
  const [data, setData] = useState<Preview | null>(null);
  const box = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let live = true;
    const go = () => void load(url).then((d) => live && setData(d));
    if (typeof IntersectionObserver === 'undefined') {
      go();
      return () => void (live = false);
    }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        io.disconnect();
        go();
      }
    }, { rootMargin: '200px' });
    io.observe(el);
    return () => {
      live = false;
      io.disconnect();
    };
  }, [url]);
  const host = data?.host || hostOf(url);
  return (
    <a ref={box} className="lp" data-compact={compact || undefined} href={url} target="_blank" rel="noreferrer">
      <span className="lp-pic" aria-hidden="true">
        {data?.picture ? <img src={data.picture} alt="" loading="lazy" /> : <span>{host.slice(0, 1).toUpperCase()}</span>}
      </span>
      <span className="lp-text">
        <b>{data?.title || host}</b>
        {!compact && data?.description && <small>{data.description}</small>}
        <i>{data?.site || host}</i>
      </span>
    </a>
  );
}

export default LinkPreview;
