import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { Check } from 'lucide-react';
import { toast } from 'sonner';
import { useWorkspace } from '../lib/workspace/store';
import { FilePick, Recorder } from '../components/Workspace/MediaBlock';
import type { Block } from '../lib/workspace/model';

// Quick capture: one screen, ready in a moment (it loads nothing else):
// type, record a voice note or take a photo, and it lands in the Workspace
// inbox at once, with or without network.
export function CapturePage() {
  const navigate = useNavigate();
  const ready = useWorkspace((s) => s.ready);
  const load = useWorkspace((s) => s.load);
  const capture = useWorkspace((s) => s.capture);
  const [text, setText] = useState('');
  const [count, setCount] = useState(0);
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!ready) void load();
    area.current?.focus();
  }, [ready, load]);

  const saved = () => {
    setCount((c) => c + 1);
    toast.success('Guardado en la Bandeja de entrada.');
  };
  const save = () => {
    if (!text.trim()) return;
    capture({ text: text.trim() });
    setText('');
    saved();
    area.current?.focus();
  };
  const media = (kind: 'audio' | 'image') => (m: NonNullable<Block['media']>) => {
    capture({ kind, media: m, text: text.trim() || undefined });
    setText('');
    saved();
  };

  return (
    <div className="paper-page">
      <div className="paper-page-inner" style={{ maxWidth: 560 }}>
        <header className="paper-head">
          <span />
          <h1 className="paper-title">Captura</h1>
          <span />
        </header>
        <textarea
          ref={area}
          className="ws-capture"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save();
          }}
          placeholder="Una idea, una tarea, lo que sea…"
          aria-label="Nota rápida"
        />
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <button type="button" className="paper-button" onClick={save} disabled={!text.trim()}>
            <Check size={14} /> Guardar
          </button>
          <Recorder onSaved={media('audio')} />
          <FilePick accept="image/*" capture="environment" label="Foto" onSaved={media('image')} />
          <span className="ml-auto text-[12px]" style={{ color: 'var(--color-text-tertiary)' }}>
            {count ? `${count} guardadas` : 'Ctrl+Enter guarda'}
          </span>
        </div>
        <button type="button" className="paper-tab mt-8" onClick={() => navigate('/workspace')}>
          Ir al Workspace →
        </button>
      </div>
    </div>
  );
}

export default CapturePage;
