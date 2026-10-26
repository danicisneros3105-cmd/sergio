// The moment itself (lib/celebrate.ts): a small card in the middle of the
// screen for under two seconds, then gone. Sergio's disc is the hero; for a
// connector, the service's logo flies into it.

import { useEffect, useState } from 'react';
import { CELEBRATE_EVENT, type Celebration } from '../../lib/celebrate';
import { BrandMark } from '../Brand/BrandMark';
import './celebration.css';

const SHOW_MS = 1900;

function Disc() {
  return (
    <svg className="cel-disc" viewBox="0 0 100 100" aria-hidden>
      <circle cx="50" cy="50" r="47" fill="#0a6cfe" />
      <circle className="cel-ring" cx="50" cy="50" r="13.7" fill="none" stroke="#ffffff" strokeWidth="10.2" />
    </svg>
  );
}

export function CelebrationLayer() {
  const [now, setNow] = useState<(Celebration & { key: number }) | null>(null);
  useEffect(() => {
    let timer = 0;
    const on = (e: Event) => {
      const detail = (e as CustomEvent<Celebration>).detail;
      if (!detail) return;
      window.clearTimeout(timer);
      setNow({ ...detail, key: Date.now() });
      timer = window.setTimeout(() => setNow(null), SHOW_MS);
    };
    window.addEventListener(CELEBRATE_EVENT, on);
    return () => {
      window.removeEventListener(CELEBRATE_EVENT, on);
      window.clearTimeout(timer);
    };
  }, []);
  if (!now) return null;
  return (
    <div className="cel-layer" role="status" aria-live="polite" onClick={() => setNow(null)}>
      <div key={now.key} className="cel-card" data-kind={now.kind}>
        <div className="cel-stage">
          {now.kind === 'plan' && <span className="cel-waves" aria-hidden><i /><i /><i /></span>}
          {now.kind === 'connector' && now.brand && (
            <span className="cel-brand"><BrandMark name={now.brand.name} id={now.brand.id} size={44} /></span>
          )}
          <Disc />
        </div>
        <p className="cel-title">{now.title}</p>
        {now.detail && <p className="cel-detail">{now.detail}</p>}
      </div>
    </div>
  );
}
