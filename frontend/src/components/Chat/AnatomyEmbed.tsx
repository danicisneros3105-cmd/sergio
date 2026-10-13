// One Anatomy figure inside a chat reply: Sergio's interactive drawing of a
// machine, in a sandboxed frame (scripts only).

import { useEffect, useRef, useState } from 'react';
import { Maximize2 } from 'lucide-react';
import { apiFetch } from '../../lib/api';
import { withMemoryStorage } from '../../lib/anatomy';

export function AnatomyEmbed({ name }: { name: string }) {
  const [html, setHtml] = useState('');
  const [error, setError] = useState('');
  const frame = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    let alive = true;
    apiFetch(`/v1/creator/anatomy/view/${encodeURIComponent(name)}`)
      .then(async (res) => {
        if (!res.ok) throw new Error('La lámina aún no está lista.');
        const text = await res.text();
        if (alive) setHtml(withMemoryStorage(text));
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [name]);

  if (error) return <p className="anatomy-embed-error">{error}</p>;
  return (
    <figure className="anatomy-embed">
      {html ? (
        <iframe ref={frame} title={`Lámina: ${name}`} sandbox="allow-scripts" srcDoc={html} />
      ) : (
        <div className="anatomy-embed-wait">Dibujando la lámina…</div>
      )}
      {html && (
        <button
          type="button"
          className="mac-icon-btn anatomy-embed-full"
          aria-label="Pantalla completa"
          title="Pantalla completa"
          onClick={() => void frame.current?.requestFullscreen?.()}
        >
          <Maximize2 size={15} />
        </button>
      )}
    </figure>
  );
}
