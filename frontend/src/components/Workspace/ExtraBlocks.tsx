// Notion-like blocks that are drawn, not typed into: an equation (KaTeX,
// from the LaTeX in the block), a table of contents (the page's headings,
// live) and a bookmark card for a link (no request is made to the site:
// the card shows what the link itself says).

import { useMemo } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import { Globe } from 'lucide-react';
import type { Block } from '../../lib/workspace/model';

export function EquationView({ tex }: { tex: string }) {
  const html = useMemo(() => {
    if (!tex.trim()) return '';
    try {
      return katex.renderToString(tex, { displayMode: true, throwOnError: true, output: 'html' });
    } catch (e) {
      return `<span class="ws-eq-error">${(e instanceof Error ? e.message : 'Fórmula no válida').replace(/[<>&]/g, '')}</span>`;
    }
  }, [tex]);
  if (!html) return null;
  // KaTeX escapes the user's text itself; nothing else is injected.
  return <div className="ws-equation" dangerouslySetInnerHTML={{ __html: html }} />;
}

export function TocView({ blocks, onJump }: { blocks: Block[]; onJump: (id: string) => void }) {
  const heads = blocks.filter((b) => (b.type === 'h1' || b.type === 'h2' || b.type === 'h3') && b.text.trim() && !b.archived);
  if (!heads.length) return <p className="ws-empty">El índice aparece en cuanto la página tenga títulos.</p>;
  return (
    <nav className="ws-toc" aria-label="Índice de la página">
      {heads.map((h) => (
        <button key={h.id} type="button" data-level={h.type} onClick={() => onJump(h.id)}>
          {h.text}
        </button>
      ))}
    </nav>
  );
}

export function bookmarkParts(raw: string): { href: string; host: string; path: string } | null {
  const v = raw.trim();
  if (!v) return null;
  try {
    const url = new URL(/^https?:\/\//i.test(v) ? v : `https://${v}`);
    if (!url.hostname.includes('.')) return null;
    const path = decodeURIComponent(url.pathname + url.search).replace(/\/$/, '');
    return { href: url.toString(), host: url.hostname.replace(/^www\./, ''), path };
  } catch {
    return null;
  }
}

export function BookmarkView({ url }: { url: string }) {
  const parts = bookmarkParts(url);
  if (!parts) return null;
  const words = parts.path
    .split(/[/?=&_-]+/)
    .filter((w) => w && !/^\d+$/.test(w))
    .slice(-4)
    .join(' ');
  return (
    <a className="ws-bookmark" href={parts.href} target="_blank" rel="noreferrer">
      <span className="ws-bookmark-icon">
        <Globe size={18} />
      </span>
      <span>
        <b>{words ? words.charAt(0).toUpperCase() + words.slice(1) : parts.host}</b>
        <small>{parts.host}</small>
      </span>
    </a>
  );
}
