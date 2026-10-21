import { useEffect, useRef, useState } from 'react';
import { Mic, Square, Upload } from 'lucide-react';
import { mediaUrl, saveMedia } from '../../lib/workspace/store';
import type { Block } from '../../lib/workspace/model';
import { mediaProblem } from '../../lib/compat';

// Shows a stored voice note or photo (fetched with the server key, kept in
// memory) and records or picks a new one.
export function useMedia(media: Block['media']): string {
  const [url, setUrl] = useState('');
  useEffect(() => {
    let alive = true;
    let made = '';
    if (media?.file) {
      void mediaUrl(media).then((u) => {
        made = u;
        if (alive) setUrl(u);
        else if (u) URL.revokeObjectURL(u);
      });
    }
    return () => {
      alive = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [media?.file]); // eslint-disable-line react-hooks/exhaustive-deps
  return url;
}

export function Recorder({ onSaved }: { onSaved: (media: NonNullable<Block['media']>) => void }) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState('');
  const rec = useRef<MediaRecorder | null>(null);

  const start = async () => {
    setError('');
    const problem = mediaProblem('micrófono');
    if (problem) {
      setError(problem);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const r = new MediaRecorder(stream);
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: r.mimeType || 'audio/webm' });
        const ext = (r.mimeType || 'audio/webm').includes('ogg') ? 'ogg' : 'webm';
        onSaved(await saveMedia(blob, `nota-de-voz-${new Date().toISOString().slice(0, 16).replace(':', '')}.${ext}`));
      };
      r.start();
      rec.current = r;
      setRecording(true);
    } catch {
      setError('No tengo permiso para el micrófono.');
    }
  };
  const stop = () => {
    rec.current?.stop();
    rec.current = null;
    setRecording(false);
  };

  return (
    <span className="inline-flex items-center gap-2">
      {recording ? (
        <button type="button" className="paper-button" onClick={stop}>
          <Square size={14} strokeWidth={1.5} /> Parar
        </button>
      ) : (
        <button type="button" className="paper-button" data-variant="quiet" onClick={() => void start()}>
          <Mic size={14} strokeWidth={1.5} /> Grabar
        </button>
      )}
      {error && <span className="text-[12px]" style={{ color: 'var(--color-error)' }}>{error}</span>}
    </span>
  );
}

export function FilePick({
  accept,
  capture,
  label,
  onSaved,
}: {
  accept: string;
  capture?: 'environment' | 'user';
  label: string;
  onSaved: (media: NonNullable<Block['media']>) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className="paper-button" data-variant="quiet" onClick={() => input.current?.click()}>
        <Upload size={14} strokeWidth={1.5} /> {label}
      </button>
      <input
        ref={input}
        type="file"
        accept={accept}
        capture={capture}
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (file) onSaved(await saveMedia(file, file.name));
          e.target.value = '';
        }}
      />
    </>
  );
}

export function MediaBlock({ block, onMedia }: { block: Block; onMedia: (media: NonNullable<Block['media']>) => void }) {
  const url = useMedia(block.media);
  if (block.type === 'image') {
    return block.media ? (
      url ? <img src={url} alt={block.text || block.media.name} className="ws-image" /> : <div className="ws-card">Cargando imagen…</div>
    ) : (
      <div className="ws-card flex gap-2">
        <FilePick accept="image/*" capture="environment" label="Foto o imagen" onSaved={onMedia} />
      </div>
    );
  }
  return block.media ? (
    <div className="ws-card">
      <div className="text-[12px] mb-1" style={{ color: 'var(--color-text-secondary)' }}>{block.media.name}</div>
      {url ? <audio controls src={url} className="w-full" /> : <span>Cargando audio…</span>}
    </div>
  ) : (
    <div className="ws-card flex gap-2 flex-wrap">
      <Recorder onSaved={onMedia} />
      <FilePick accept="audio/*" label="Archivo de audio" onSaved={onMedia} />
    </div>
  );
}
