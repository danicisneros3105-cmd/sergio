import { useCallback, useEffect, useState } from 'react';
import { Loader2, Play, ExternalLink } from 'lucide-react';
import {
  fetchExtensions,
  globeFrameUrl,
  startExtension,
  type ExtensionName,
  type ExtensionsState,
} from '../lib/extensions-api';

const POLL_MS = 3000;

// Only Sergio's names in sight (the agent's own interface is patched to match:
// scripts/marca_agente.py). No subtext under the title.
export const EXTENSION_TITLE: Record<ExtensionName, string> = {
  globe: 'Globo',
  clacky: 'Agente de código',
};

// Embeds one bundled extension (the coding agent or the globe) as a full-page panel.
export function ExtensionPage({ name }: { name: ExtensionName }) {
  const [state, setState] = useState<ExtensionsState | null>(null);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);

  const refresh = useCallback(async () => {
    // Skip polls while the browser tab is in the background.
    if (document.hidden) return;
    try {
      setState(await fetchExtensions());
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const svc = state?.services.find((s) => s.name === name);
  const title = EXTENSION_TITLE[name];

  const handleStart = async () => {
    setStarting(true);
    try {
      await startExtension(name);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
      refresh();
    }
  };

  const src = svc
    ? name === 'globe'
      ? globeFrameUrl(svc.url, state?.globe_target ?? null)
      : svc.url
    : '';

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <header
        className="flex items-center justify-between gap-3 px-4 py-2 shrink-0 border-b"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <div className="min-w-0">
          <h1 className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
            {title}
            {name === 'globe' && state?.globe_target ? ` · ${state.globe_target.label}` : ''}
          </h1>
        </div>
        {svc?.running && (
          <a
            href={src}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-xs"
            style={{ color: 'var(--color-accent-text)' }}
          >
            <ExternalLink size={14} /> Abrir aparte
          </a>
        )}
      </header>

      {svc?.running ? (
        <iframe
          key={src}
          title={title}
          src={src}
          className="flex-1 w-full border-0"
          allow="microphone; clipboard-read; clipboard-write; fullscreen"
        />
      ) : (
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="max-w-md text-center space-y-3">
            {!state && !error && <Loader2 className="mx-auto animate-spin" size={20} />}
            {error && <p style={{ color: 'var(--color-error)' }}>{error}</p>}
            {svc && !svc.available && (
              <p style={{ color: 'var(--color-warning)' }}>{svc.problem}</p>
            )}
            {state && !svc && (
              <p style={{ color: 'var(--color-text-secondary)' }}>
                Está apagado en config.toml ([extensions.{name}] enabled = false).
              </p>
            )}
            {svc?.available && (
              <button
                onClick={handleStart}
                disabled={starting}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm"
                style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}
              >
                {starting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                {starting ? 'Abriendo…' : `Abrir ${title.toLowerCase()}`}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
