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
  replaced: 'Le escucho (haga clic para hablar aquí)',
};

export function LiveOrb({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const status = useLive((s) => s.status);
  const muted = useLive((s) => s.muted);
  const enabled = useLive((s) => s.enabled);
  const toggleMute = useLive((s) => s.toggleMute);
  const ensure = useLive((s) => s.ensure);
  const takeBack = useLive((s) => s.takeBack);
  const elsewhere = useLive((s) => s.elsewhere);
  const orb = useRef<HTMLButtonElement>(null);

  useEffect(
    () => onLiveLevel((level) => orb.current?.style.setProperty('--level', level.toFixed(3))),
    [],
  );

  if (!enabled) return null;
  const label = muted
    ? 'Micrófono en silencio: haga clic para hablar'
    : elsewhere
      ? 'Le escucho (haga clic para usar esta ventana)'
      : LIVE_ES[status];
  const live = status === 'listening' || status === 'speaking' || status === 'thinking';
  return (
    <button
      ref={orb}
      type="button"
      className={`live-orb live-orb-${size}`}
      data-state={muted ? 'muted' : elsewhere ? 'elsewhere' : status}
      aria-pressed={live ? muted : undefined}
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        if (live) toggleMute();
        else if (status === 'replaced' || elsewhere) takeBack();
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

/** Starts the conversation on the first click or key press (browser rule) and keeps the multi-device bridge active. */
export function LiveStarter() {
  const ensure = useLive((s) => s.ensure);
  useEffect(() => {
    const wake = () => ensure();
    window.addEventListener('pointerdown', wake, true);
    window.addEventListener('keydown', wake, true);

    const isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '');
    let devId = 'dev-web';
    try {
      devId = localStorage.getItem('sergio.device_id') || `${isMobile ? 'phone' : 'pc'}-${Math.random().toString(36).slice(2, 8)}`;
      localStorage.setItem('sergio.device_id', devId);
    } catch {
      // ignore private mode
    }
    const pollDeviceBridge = async () => {
      try {
        const res = await fetch('/v1/devices/heartbeat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            device_id: devId,
            kind: isMobile ? 'phone' : 'pc',
            name: isMobile ? 'Teléfono móvil (Sergio Web)' : 'Computadora (Sergio Web)',
          }),
        });
        if (!res.ok) return;
        const data = await res.json();
        const cmds: Array<{ action: string; params?: Record<string, unknown> }> = data.commands || [];
        for (const cmd of cmds) {
          if (cmd.action === 'record_video' || cmd.action === 'stop_video' || cmd.action === 'take_photo') {
            if (!window.location.pathname.startsWith('/capture')) {
              window.history.pushState({}, '', '/capture');
              window.dispatchEvent(new PopStateEvent('popstate'));
            }
            setTimeout(() => window.dispatchEvent(new CustomEvent('sergio:device-command', { detail: cmd })), 250);
          } else if (cmd.action === 'record_meeting' || cmd.action === 'stop_meeting') {
            if (!window.location.pathname.startsWith('/meeting')) {
              window.history.pushState({}, '', '/meeting');
              window.dispatchEvent(new PopStateEvent('popstate'));
            }
            setTimeout(() => window.dispatchEvent(new CustomEvent('sergio:device-command', { detail: cmd })), 250);
          } else if (cmd.action === 'open_url' && typeof cmd.params?.url === 'string') {
            window.open(cmd.params.url, '_blank');
          }
        }
      } catch {
        // offline or unit test
      }
    };
    const timer = window.setInterval(() => void pollDeviceBridge(), 4000);
    return () => {
      window.removeEventListener('pointerdown', wake, true);
      window.removeEventListener('keydown', wake, true);
      window.clearInterval(timer);
    };
  }, [ensure]);
  return null;
}
