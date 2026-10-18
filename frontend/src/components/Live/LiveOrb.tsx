// The always-on conversation, visible on every page. Small, it is ChatGPT's
// voice button (a black circle whose bars move with the voice); large, the
// light-blue sphere of voice mode. Click to mute or unmute (it never hangs
// up); if the microphone was refused, clicking asks again.

import { useEffect, useRef, useState } from 'react';
import { MicOff } from 'lucide-react';
import { onLiveLevel, useLive, type LiveStatus } from '../../lib/liveSession';

export const LIVE_ES: Record<LiveStatus, string> = {
  off: 'Conversación apagada (Ajustes)',
  waiting: 'Haga clic en cualquier parte y hable: Sergio le escucha',
  connecting: 'Conectando…',
  reconnecting: 'Reconectando…',
  listening: 'Le escucho',
  thinking: 'Pensando…',
  speaking: 'Hablando',
  ended: 'Reconectando…',
  error: 'Reconectando…',
  blocked: 'Necesito permiso para el micrófono: haga clic para concederlo',
  replaced: 'Otra ventana tiene la conversación: haga clic para hablar aquí',
};

export function LiveOrb({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const status = useLive((s) => s.status);
  const muted = useLive((s) => s.muted);
  const enabled = useLive((s) => s.enabled);
  const toggleMute = useLive((s) => s.toggleMute);
  const ensure = useLive((s) => s.ensure);
  const takeBack = useLive((s) => s.takeBack);
  const orb = useRef<HTMLButtonElement>(null);

  useEffect(
    () => onLiveLevel((level) => orb.current?.style.setProperty('--level', level.toFixed(3))),
    [],
  );

  if (!enabled) return null;
  const label = muted ? 'Micrófono en silencio: haga clic para hablar' : LIVE_ES[status];
  const live = status === 'listening' || status === 'speaking' || status === 'thinking';
  return (
    <button
      ref={orb}
      type="button"
      className={`live-orb live-orb-${size}`}
      data-state={muted ? 'muted' : status}
      aria-pressed={live ? muted : undefined}
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        if (live) toggleMute();
        else if (status === 'replaced') takeBack();
        else ensure();
      }}
    >
      <i aria-hidden="true">
        {size !== 'lg' && !muted && (
          <>
            <b />
            <b />
            <b />
            <b />
          </>
        )}
      </i>
      {muted && <MicOff size={size === 'sm' ? 12 : 15} strokeWidth={2} aria-hidden="true" />}
    </button>
  );
}

/** What is being said right now, as subtitles; the chat keeps the full turns. */
export function LiveCaptions() {
  const heard = useLive((s) => s.heard);
  const said = useLive((s) => s.said);
  const status = useLive((s) => s.status);
  const error = useLive((s) => s.error);
  const text = said || heard;
  // A refused microphone is said once, for a few seconds (the orb in the rail
  // keeps showing it); it never sits on top of what the owner is doing.
  const [showError, setShowError] = useState(false);
  useEffect(() => {
    if (!(status === 'blocked' && error)) return setShowError(false);
    setShowError(true);
    const t = window.setTimeout(() => setShowError(false), 7000);
    return () => window.clearTimeout(t);
  }, [status, error]);
  if (!text && !showError) return null;
  return (
    <div className="live-captions" role="status" aria-live="polite">
      {!text && showError ? (
        <p className="live-captions-error">{error}</p>
      ) : (
        <p data-who={said ? 'sergio' : 'you'}>
          <b>{said ? 'Sergio' : 'Usted'}</b>
          {text}
        </p>
      )}
    </div>
  );
}

/** Starts the conversation on the first click or key press (browser rule). */
export function LiveStarter() {
  const ensure = useLive((s) => s.ensure);
  useEffect(() => {
    const wake = () => ensure();
    window.addEventListener('pointerdown', wake, true);
    window.addEventListener('keydown', wake, true);
    return () => {
      window.removeEventListener('pointerdown', wake, true);
      window.removeEventListener('keydown', wake, true);
    };
  }, [ensure]);
  return null;
}
