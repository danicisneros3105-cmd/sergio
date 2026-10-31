// «Dividir pantalla»: the visible way into the fold (it used to hide behind
// Ctrl \ and the palette — owner, 28 Oct 2026: «no encuentro cómo hacer split
// screen»). It opens the second screen with the iPhone-Duo animation and
// closes it again; the label says what a tap will do.

import { useSplit } from '../../lib/split';

export function SplitButton({
  className = 'mac-icon-btn',
  showLabel = false,
}: {
  className?: string;
  showLabel?: boolean;
}) {
  const open = useSplit((s) => s.open);
  const label = open ? 'Unir pantalla' : 'Dividir pantalla';
  const shortLabel = open ? 'Unir' : 'Split';
  const shortcut = `${typeof navigator !== 'undefined' && navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'} \\`;
  return (
    <button
      type="button"
      className={`${className} split-duo-btn`}
      data-split-open={open || undefined}
      aria-label={label}
      aria-pressed={open}
      title={`${label} (${shortcut})`}
      onClick={() => window.dispatchEvent(new CustomEvent('sergio:split'))}
    >
      <svg
        className="split-duo-svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect className="split-pane-left" x="3" y="4" width="8" height="16" rx="2" />
        <line className="split-pane-hinge" x1="12" y1="5" x2="12" y2="19" />
        <rect className="split-pane-right" x="13" y="4" width="8" height="16" rx="2" />
      </svg>
      {showLabel && <span className="split-btn-label">{shortLabel}</span>}
    </button>
  );
}
