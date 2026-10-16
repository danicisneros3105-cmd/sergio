// Presentation mode: the page as full-screen slides, arrows to move, Esc to leave.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { EquationView, BookmarkView } from './ExtraBlocks';
import { NxIcon } from './NxIcon';
import { RichText } from './NxParts';
import { mediaUrl } from '../../lib/workspace/store';
import { slidesOf } from '../../lib/workspace/notion';
import type { Block, Page } from '../../lib/workspace/model';

function SlideImage({ media }: { media: NonNullable<Block['media']> }) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    let url = '';
    void mediaUrl(media).then((u) => setSrc((url = u)));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [media]);
  return src ? <img className="nx-slide-image" src={src} alt={media.caption || media.name} /> : null;
}

function SlideBlock({ b, n }: { b: Block; n: number }) {
  const rich = <RichText text={b.text} onPage={() => undefined} onClick={() => undefined} />;
  switch (b.type) {
    case 'h1':
      return <h1>{rich}</h1>;
    case 'h2':
      return <h2>{rich}</h2>;
    case 'h3':
      return <h3>{rich}</h3>;
    case 'bullet':
      return <div className="nx-slide-li">{rich}</div>;
    case 'number':
      return (
        <div className="nx-slide-li" data-n={`${n}.`}>
          {rich}
        </div>
      );
    case 'todo':
      return (
        <div className="nx-slide-todo" data-done={b.checked || undefined}>
          <span aria-hidden="true">{b.checked ? '■' : '□'}</span>
          {rich}
        </div>
      );
    case 'quote':
      return <blockquote>{rich}</blockquote>;
    case 'callout':
      return <div className="nx-slide-callout">{rich}</div>;
    case 'code':
      return <pre>{b.text}</pre>;
    case 'toggle':
      return <div className="nx-slide-li">{b.text.split('\n')[0]}</div>;
    case 'equation':
      return <EquationView tex={b.text} />;
    case 'bookmark':
      return <BookmarkView url={b.text} />;
    case 'image':
      return b.media ? <SlideImage media={b.media} /> : null;
    case 'tabs':
      return (
        <div>
          {(b.tabs || []).map((t) => (
            <div key={t.id} className="nx-slide-tab">
              <strong>{t.name}</strong>
              <RichText text={t.text} onPage={() => undefined} onClick={() => undefined} />
            </div>
          ))}
        </div>
      );
    case 'text':
      return b.text.trim() ? <p>{rich}</p> : null;
    default:
      return b.text.trim() ? <p>{rich}</p> : null;
  }
}

export function Presentation({ page, blocks, onClose }: { page: Page; blocks: Block[]; onClose: () => void }) {
  const slides = slidesOf(blocks);
  const total = slides.length + 1; // the title slide first
  const [at, setAt] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const go = useCallback((d: number) => setAt((i) => Math.min(total - 1, Math.max(0, i + d))), [total]);

  useEffect(() => {
    const el = root.current;
    el?.focus();
    void el?.requestFullscreen?.().catch(() => undefined);
    const onFull = () => {
      if (!document.fullscreenElement) onClose();
    };
    document.addEventListener('fullscreenchange', onFull);
    return () => {
      document.removeEventListener('fullscreenchange', onFull);
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    };
  }, [onClose]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === ' ') go(1);
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp' || e.key === 'PageUp') go(-1);
    else if (e.key === 'Home') setAt(0);
    else if (e.key === 'End') setAt(total - 1);
    else if (e.key === 'Escape') onClose();
    else return;
    e.preventDefault();
  };

  let n = 0;
  return (
    <div ref={root} className="nx nx-present" role="dialog" aria-modal="true" aria-label="Presentación" tabIndex={-1} onKeyDown={onKey}>
      <div className="nx-slide" onClick={(e) => (e.target === e.currentTarget ? go(1) : undefined)}>
        {at === 0 ? (
          <div className="nx-slide-cover">
            <span className="nx-slide-icon">
              <NxIcon icon={page.icon} size={56} />
            </span>
            <h1>{page.title || 'Sin título'}</h1>
          </div>
        ) : (
          <div className="nx-slide-body">
            {slides[at - 1].map((b) => {
              n = b.type === 'number' ? n + 1 : 0;
              return <SlideBlock key={b.id} b={b} n={n} />;
            })}
          </div>
        )}
      </div>
      <div className="nx-present-bar">
        <button type="button" className="nx-icon" aria-label="Anterior" disabled={at === 0} onClick={() => go(-1)}>
          <ChevronLeft size={18} />
        </button>
        <span className="nx-present-count">
          {at + 1} / {total}
        </span>
        <button type="button" className="nx-icon" aria-label="Siguiente" disabled={at === total - 1} onClick={() => go(1)}>
          <ChevronRight size={18} />
        </button>
        <button type="button" className="nx-icon" aria-label="Salir de la presentación" onClick={onClose}>
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
