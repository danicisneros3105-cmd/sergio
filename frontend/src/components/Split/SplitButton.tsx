// «Dividir pantalla»: the visible way into the fold (it used to hide behind
// Ctrl \ and the palette — owner, 28 Oct 2026: «no encuentro cómo hacer split
// screen»). It opens the second screen with the iPhone-Duo animation and
// closes it again; the label says what a tap will do.

import { Columns2 } from 'lucide-react';
import { useSplit } from '../../lib/split';

export function SplitButton({ className = 'mac-icon-btn' }: { className?: string }) {
  const open = useSplit((s) => s.open);
  const label = open ? 'Unir la pantalla' : 'Dividir la pantalla';
  return (
    <button
      type="button"
      className={className}
      aria-label={label}
      aria-pressed={open}
      title={`${label} (${typeof navigator !== 'undefined' && navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'} \\)`}
      onClick={() => window.dispatchEvent(new CustomEvent('sergio:split'))}
    >
      <Columns2 size={18} strokeWidth={1.5} />
    </button>
  );
}
