// Multitasking on the computer, not inside the app (owner, 3 Nov 2026: «lo de
// dividir pantalla NO es para la app sino de la computadora o dispositivo,
// para que el usuario pueda hacer multitasking»). On the PC, Sergio places
// two programs side by side (desktop_action «split», the same as saying «pon
// Chrome y Word lado a lado»). Elsewhere it shows how the device itself does it.
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { askSergio } from '../../pages/OrganizerPage';

function device(): 'windows' | 'mac' | 'ipad' | 'android' | 'other' {
  const ua = typeof navigator === 'undefined' ? '' : navigator.userAgent;
  if (/Android/i.test(ua)) return 'android';
  if (/iPad|iPhone/i.test(ua) || (/Macintosh/.test(ua) && typeof document !== 'undefined' && 'ontouchend' in document)) return 'ipad';
  if (/Mac/i.test(ua)) return 'mac';
  if (/Windows/i.test(ua)) return 'windows';
  return 'other';
}

const HOW: Record<string, string> = {
  windows: 'En Windows también: arrastre una ventana al borde o pulse Windows + ← o →.',
  mac: 'En el Mac: mantenga el botón verde de la ventana y elija «Mosaico a la izquierda».',
  ipad: 'En el iPad: toque los tres puntos arriba de la app y elija Split View. El iPhone no tiene pantalla dividida.',
  android: 'En Android: abra las apps recientes, toque el icono de la app y elija «Pantalla dividida».',
  other: 'Use la pantalla dividida de su sistema.',
};

export function SplitButton({
  className = 'mac-icon-btn',
  showLabel = false,
}: {
  className?: string;
  showLabel?: boolean;
}) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [left, setLeft] = useState('');
  const [right, setRight] = useState('');
  const box = useRef<HTMLDivElement>(null);
  const where = device();
  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener('sergio:multitarea', show);
    return () => window.removeEventListener('sergio:multitarea', show);
  }, []);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [open]);
  const go = () => {
    if (!left.trim()) return;
    setOpen(false);
    askSergio(navigate, `Pon ${left.trim()}${right.trim() ? ` y ${right.trim()}` : ''} lado a lado en la pantalla.`);
  };
  return (
    <div className="split-wrap" ref={box}>
      <button
        type="button"
        className={`${className} split-duo-btn`}
        aria-label="Multitarea: dos apps lado a lado"
        aria-expanded={open}
        title="Multitarea: dos apps lado a lado"
        onClick={() => setOpen((o) => !o)}
      >
        <svg className="split-duo-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect className="split-pane-left" x="3" y="4" width="8" height="16" rx="2" />
          <line className="split-pane-hinge" x1="12" y1="5" x2="12" y2="19" />
          <rect className="split-pane-right" x="13" y="4" width="8" height="16" rx="2" />
        </svg>
        {showLabel && <span className="split-btn-label">Multitarea</span>}
      </button>
      {open && (
        <div className="split-pop" role="dialog" aria-label="Multitarea">
          {(where === 'windows' || where === 'other') && (
            <form onSubmit={(e) => (e.preventDefault(), go())}>
              <b>Dos apps lado a lado</b>
              <input value={left} onChange={(e) => setLeft(e.target.value)} placeholder="A la izquierda (p. ej. Chrome)" aria-label="App de la izquierda" autoFocus />
              <input value={right} onChange={(e) => setRight(e.target.value)} placeholder="A la derecha (p. ej. Word)" aria-label="App de la derecha" />
              <button type="submit" disabled={!left.trim()}>Ponerlas lado a lado</button>
              <small>Lo hace Sergio en su PC con la app de escritorio. Si una no está abierta, la abre.</small>
            </form>
          )}
          <small>{HOW[where]}</small>
        </div>
      )}
    </div>
  );
}
