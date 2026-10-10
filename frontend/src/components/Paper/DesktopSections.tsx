import { useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';

export interface DesktopSection {
  key: string;
  label: string;
  meta: string;
  icon: LucideIcon;
}

// Asks Sergio Escritorio (through the server) to open one of its windows.
export async function openOnDesktop(key: string): Promise<string> {
  const res = await apiFetch('/v1/desktop/open', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section: key }),
  });
  if (res.ok) return '';
  try {
    const data = await res.json();
    return String(data.detail ?? `Error ${res.status}`);
  } catch {
    return `Error ${res.status}`;
  }
}

// Document cards, each opening a part of Sergio on the PC.
export function DesktopSections({ sections }: { sections: DesktopSection[] }) {
  const [busy, setBusy] = useState('');
  const open = async (key: string, label: string) => {
    setBusy(key);
    const problem = await openOnDesktop(key);
    setBusy('');
    if (problem) toast.error(problem);
    else toast.success(`${label}: abierto en su PC`);
  };
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-x-5 gap-y-6">
      {sections.map((s) => (
        <button
          key={s.key}
          type="button"
          className="paper-card"
          onClick={() => open(s.key, s.label)}
          disabled={busy === s.key}
          aria-label={`Abrir ${s.label} en el PC`}
        >
          <span className="paper-thumb" style={{ aspectRatio: '1 / 1' }}>
            <s.icon size={34} strokeWidth={1.1} style={{ color: 'var(--color-text)' }} />
          </span>
          <span>
            <span className="paper-name block">{s.label}</span>
            <span className="paper-meta block">{busy === s.key ? 'Abriendo…' : s.meta}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
