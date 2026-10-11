import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Mic, MicOff, Monitor, X } from 'lucide-react';
import { VoiceCall, type VoiceState } from '../../lib/liveVoice';

const STATE_ES: Record<VoiceState, string> = {
  connecting: 'Conectando…',
  listening: 'Le escucho',
  thinking: 'Trabajando en su pedido',
  speaking: 'Hablando',
  ended: 'Llamada terminada',
  error: 'No se pudo',
};

/** Full-screen voice mode, like ChatGPT's: an orb that breathes with the voice. */
export function VoiceMode({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<VoiceState>('connecting');
  const [heard, setHeard] = useState('');
  const [said, setSaid] = useState('');
  const [error, setError] = useState('');
  const [muted, setMuted] = useState(false);
  const [sharing, setSharing] = useState(false);
  const orb = useRef<HTMLDivElement>(null);
  const call = useRef<VoiceCall | null>(null);
  // The call starts once; a parent re-render must not hang up and redial.
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const language = (navigator.language || 'es').slice(0, 2).toLowerCase();
    const c = new VoiceCall(
      {
        onState: setState,
        onHeard: setHeard,
        onSaid: setSaid,
        onError: setError,
        onScreen: setSharing,
        // The level moves the orb directly (no React render per audio buffer).
        onLevel: (level) => orb.current?.style.setProperty('--level', level.toFixed(3)),
      },
      language,
    );
    call.current = c;
    void c.start();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close.current();
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      c.stop(false);
    };
  }, []);

  const toggleMute = () => {
    call.current?.setMuted(!muted);
    setMuted(!muted);
  };

  // On <body>: a transformed ancestor (the composer) would trap a fixed overlay.
  return createPortal(
    <div className="voice-mode" role="dialog" aria-modal="true" aria-label="Modo de voz">
      <div className="voice-orb" ref={orb} data-state={state} aria-hidden="true">
        <i />
      </div>
      <p className="voice-state" aria-live="polite">
        {muted && state === 'listening' ? 'Micrófono en silencio' : STATE_ES[state]}
      </p>
      <div className="voice-captions" aria-live="polite">
        {error ? <p className="voice-error">{error}</p> : null}
        {!error && heard && <p className="voice-heard">{heard}</p>}
        {!error && said && <p className="voice-said">{said}</p>}
      </div>
      <div className="voice-controls">
        <button type="button" className="voice-btn" aria-pressed={sharing}
          aria-label={sharing ? 'Dejar de compartir pantalla' : 'Compartir pantalla con Gemini'}
          disabled={state === 'error' || state === 'ended' || state === 'connecting'}
          onClick={() => void call.current?.shareScreen().catch(() => setError('No se compartió la pantalla.'))}>
          <Monitor size={22} strokeWidth={1.6} />
        </button>
        <button
          type="button"
          className="voice-btn"
          aria-pressed={muted}
          aria-label={muted ? 'Activar el micrófono' : 'Silenciar el micrófono'}
          onClick={toggleMute}
          disabled={state === 'error' || state === 'ended'}
        >
          {muted ? <MicOff size={22} strokeWidth={1.6} /> : <Mic size={22} strokeWidth={1.6} />}
        </button>
        <button type="button" className="voice-btn voice-end" aria-label="Terminar" onClick={onClose}>
          <X size={22} strokeWidth={1.8} />
        </button>
      </div>
      {sharing && <p role="status">Pantalla compartida con Gemini · puede pausarla aquí</p>}
    </div>,
    document.body,
  );
}

export default VoiceMode;
