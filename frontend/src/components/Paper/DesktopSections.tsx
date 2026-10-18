import { useState } from 'react';
import { useNavigate } from 'react-router';
import type { LucideIcon } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';

export interface DesktopSection {
  key: string;
  label: string;
  meta: string;
  icon: LucideIcon;
  /** A page of the web app: opens here, no PC app needed. */
  to?: string;
}

// Asks Sergio Escritorio (through the server) to open one of its windows.
export async function openOnDesktop(key: string): Promise<string> {
  const res = await apiFetch('/v1/desktop/open', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section: key }),
  });
  try {
    const data = await res.json();
    if (!res.ok) return String(data.detail ?? `Error ${res.status}`);
    // The server answers ok even when the PC app is closed: say so, never claim it opened.
    if (data.companion === false) return 'Sergio Escritorio no está abierto en su PC. Ábralo e inténtelo de nuevo.';
    return '';
  } catch {
    return res.ok ? '' : `Error ${res.status}`;
  }
}

// Document cards, each opening a part of Sergio on the PC.
export function DesktopSections({ sections }: { sections: DesktopSection[] }) {
  const [busy, setBusy] = useState('');
  const navigate = useNavigate();
  const open = async (key: string, label: string, to?: string) => {
    if (to) return navigate(to);
    setBusy(key);
    const problem = await openOnDesktop(key);
    setBusy('');
    if (problem) toast.error(problem);
    else toast.success(`${label}: abierto en su PC`);
  };
  return (
    <div className="paper-grid desktop-sections">
      {sections.map((s) => (
        <button
          key={s.key}
          type="button"
          className="paper-card"
          onClick={() => open(s.key, s.label, s.to)}
          disabled={busy === s.key}
          aria-label={s.to ? `Abrir ${s.label}` : `Abrir ${s.label} en el PC`}
        >
          <span className="paper-thumb" style={{ aspectRatio: '1 / 1' }}>
            <s.icon size={34} strokeWidth={1.6} />
          </span>
          <span>
            <span className="paper-name block">{s.label}</span>
            {busy === s.key && <span className="paper-meta block">Abriendo…</span>}
          </span>
        </button>
      ))}
    </div>
  );
}
