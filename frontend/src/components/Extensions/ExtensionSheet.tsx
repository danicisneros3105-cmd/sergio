import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

export function ExtensionSheet({ label, onClose, wide, children }: { label: string; onClose: () => void; wide?: boolean; children: React.ReactNode }) {
  const card = useRef<HTMLDivElement>(null);
  const [previousFocus] = useState(() => typeof document === 'undefined' ? null : document.activeElement as HTMLElement | null);
  useEffect(() => {
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    card.current?.focus();
    const keys = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
      if (e.key !== 'Tab') return;
      const nodes = Array.from(card.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href]') ?? []).filter(node => node.getClientRects().length > 0);
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (!first) { e.preventDefault(); return; }
      if (e.shiftKey && (document.activeElement === first || document.activeElement === card.current)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (document.activeElement === last || document.activeElement === card.current)) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', keys);
    return () => { document.removeEventListener('keydown', keys); document.body.style.overflow = overflow; previousFocus?.focus(); };
  }, [onClose, previousFocus]);
  return (
    <div className="cx-sheet" role="dialog" aria-modal="true" aria-label={label} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={card} tabIndex={-1} className={`cx-card${wide ? ' cx-card-wide' : ''}`}>
        <button type="button" className="cx-x" aria-label="Cerrar" onClick={onClose}>
          <X size={18} />
        </button>
        {children}
      </div>
    </div>
  );
}

