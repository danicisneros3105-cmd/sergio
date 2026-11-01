// Split screen with the fold of a book-style phone (the iPhone Duo look):
// the second screen opens from the hinge — the first one stretches a little,
// both go out of focus while they move, a soft shade marks the crease — and
// settles. On a foldable with two screens the hinge is the real one.

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router';
import { Briefcase, Gauge, HeartPulse, MessageSquare, NotebookPen, Users, X, type LucideIcon } from 'lucide-react';

const PAGE_ICON: Record<string, LucideIcon> = {
  '/chat': MessageSquare,
  '/nodes': Users,
  '/salud': HeartPulse,
  '/workspace': NotebookPen,
  '/cowork': Briefcase,
  '/uso': Gauge,
};
import { SPLIT_PAGES, foldOf, paneUrl, useSplit, type Fold } from '../../lib/split';
import './split.css';

const STEP = 0.05;

export function SplitView({ children }: { children: ReactNode }) {
  const { open, path, ratio, phase, show, hide, toggle, setPath, setRatio, settle } = useSplit();
  const { pathname } = useLocation();
  const box = useRef<HTMLDivElement>(null);
  const [fold, setFold] = useState<Fold>(() => foldOf());
  const [narrow, setNarrow] = useState(() => typeof window !== 'undefined' && window.innerWidth < 700);
  const [dragging, setDragging] = useState(false);
  const opened = useRef(false); // opened because the phone unfolded
  const frame = useRef<HTMLIFrameElement>(null);
  // The pane loads once per opening; changing what it shows navigates inside
  // it (fast) instead of loading the app again.
  const [wasOpen, setWasOpen] = useState(open);
  const [first, setFirst] = useState(path);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setFirst(path);
  }
  const shown = useRef(path);
  useEffect(() => {
    if (open) shown.current = first;
  }, [open, first]);
  useEffect(() => {
    if (!open || path === shown.current) return;
    shown.current = path;
    frame.current?.contentWindow?.postMessage({ type: 'sergio:navigate', path }, window.location.origin);
  }, [open, path]);
  // If the fold's end never reports (an animation turned off), settle anyway.
  useEffect(() => {
    if (phase === 'still') return;
    const t = window.setTimeout(settle, 1700); // a little longer than --duo-in
    return () => window.clearTimeout(t);
  }, [phase, settle]);

  // Screens, hinge and width change when the phone folds or turns.
  useEffect(() => {
    const update = () => {
      setFold(foldOf());
      setNarrow(window.innerWidth < 700);
      if (box.current) box.current.style.setProperty('--split-left', `${box.current.getBoundingClientRect().left}px`);
    };
    update();
    window.addEventListener('resize', update);
    const posture = (navigator as Navigator & { devicePosture?: EventTarget }).devicePosture;
    posture?.addEventListener?.('change', update);
    return () => {
      window.removeEventListener('resize', update);
      posture?.removeEventListener?.('change', update);
    };
  }, []);

  // Two screens: one part of Sergio on each, instead of a page cut by the hinge.
  useEffect(() => {
    const st = useSplit.getState();
    if (fold !== 'none' && !st.open) {
      opened.current = true;
      st.show(pathname.startsWith('/chat') || pathname === '/' ? '/nodes' : '/chat');
    } else if (fold === 'none' && opened.current) {
      opened.current = false;
      st.hide();
    }
  }, [fold, pathname]);

  // Ctrl/⌘ \ splits and joins; the pane, the palette and the voice ask with events.
  useEffect(() => {
    const other = () => (pathname.startsWith('/chat') || pathname === '/' ? '/nodes' : '/chat');
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
        e.preventDefault();
        toggle(useSplit.getState().open ? undefined : other());
      }
    };
    const onEvent = (e: Event) => {
      const want = (e as CustomEvent<string | undefined>).detail;
      if (want === 'off') hide();
      else if (want === 'on') {
        if (!useSplit.getState().open) show(other());
      } else if (typeof want === 'string' && want.startsWith('/')) show(want);
      else toggle(useSplit.getState().open ? undefined : other());
    };
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
      const data = e.data as { type?: string } | null;
      if (data?.type === 'sergio:split-close') hide();
      if (data?.type === 'sergio:split-toggle') toggle();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('sergio:split', onEvent);
    window.addEventListener('message', onMessage);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('sergio:split', onEvent);
      window.removeEventListener('message', onMessage);
    };
  }, [pathname, toggle, show, hide]);

  const stacked = fold === 'stacked' || (fold === 'none' && narrow);
  const onHingeMove = (clientX: number, clientY: number) => {
    const rect = box.current?.getBoundingClientRect();
    if (!rect) return;
    setRatio(stacked ? (clientY - rect.top) / rect.height : (clientX - rect.left) / rect.width);
  };

  const share = `${Math.round(ratio * 1000) / 10}%`;
  return (
    <div
      ref={box}
      className="split"
      data-open={open || undefined}
      data-phase={open ? phase : undefined}
      data-fold={open && fold !== 'none' ? fold : undefined}
      data-stacked={open && stacked ? '' : undefined}
      data-dragging={dragging || undefined}
      style={{ ['--split-a' as string]: share }}
    >
      <div className="split-a">{children}</div>
      {open && (
        <>
          <div
            className="split-hinge"
            role="separator"
            aria-orientation={stacked ? 'horizontal' : 'vertical'}
            aria-label="Mover la división"
            aria-valuemin={25}
            aria-valuemax={75}
            aria-valuenow={Math.round(ratio * 100)}
            tabIndex={fold === 'none' ? 0 : -1}
            onKeyDown={(e) => {
              const back = stacked ? 'ArrowUp' : 'ArrowLeft';
              const fwd = stacked ? 'ArrowDown' : 'ArrowRight';
              if (e.key === back) setRatio(ratio - STEP);
              else if (e.key === fwd) setRatio(ratio + STEP);
              else if (e.key === 'Home') setRatio(0.25);
              else if (e.key === 'End') setRatio(0.75);
              else return;
              e.preventDefault();
            }}
            onDoubleClick={() => setRatio(0.5)}
            onPointerDown={(e) => {
              if (fold !== 'none') return; // a real hinge does not move
              (e.target as HTMLElement).setPointerCapture(e.pointerId);
              setDragging(true);
            }}
            onPointerMove={(e) => dragging && onHingeMove(e.clientX, e.clientY)}
            onPointerUp={() => setDragging(false)}
            onPointerCancel={() => setDragging(false)}
          >
            <i aria-hidden />
          </div>
          <section
            className="split-b"
            aria-label="Segunda pantalla"
            onAnimationEnd={(e) => {
              if (e.target === e.currentTarget) settle();
            }}
          >
            <header className="split-bar">
              <nav className="split-pages" aria-label="Qué ver al lado">
                {SPLIT_PAGES.map((p) => (
                  <button
                    key={p.path}
                    type="button"
                    aria-pressed={path === p.path || path.startsWith(`${p.path}/`)}
                    onClick={() => setPath(p.path)}
                  >
                    {(() => {
                      const Icon = PAGE_ICON[p.path];
                      return Icon ? <Icon size={14} strokeWidth={1.8} aria-hidden /> : null;
                    })()}
                    {p.label}
                  </button>
                ))}
              </nav>
              <button type="button" className="split-close" onClick={hide} aria-label="Cerrar la segunda pantalla" title="Cerrar (Ctrl \)">
                <X size={16} strokeWidth={1.8} />
              </button>
            </header>
            <iframe ref={frame} name="sergio-pane" title="Segunda pantalla" src={paneUrl(first)} />
          </section>
        </>
      )}
    </div>
  );
}
