// A video that plays in any browser. The server says whether the file is one a
// browser can play (the 10-bit HEVC «máster» of the highest mode is not): if
// not, a copy it can play is made and this waits for it. If the browser still
// refuses, it says so and offers the file instead of showing nothing.
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../lib/api';
import './gallery-stage.css';

/** Only what Sergio made (the creator's media folder) can be checked. */
const MINE = /^\/v1\/creator\/media\/([\w-]+\.mp4)$/;

type State = { kind: 'wait' | 'play' | 'fail'; src?: string; why?: string };

export function WebVideo({
  src,
  poster,
  className,
  autoPlay = false,
  preload = 'auto',
}: {
  src: string;
  poster?: string;
  className?: string;
  autoPlay?: boolean;
  preload?: 'auto' | 'metadata';
}) {
  const name = MINE.exec(src)?.[1];
  const [state, setState] = useState<State>(name ? { kind: 'wait' } : { kind: 'play', src });
  const forced = useRef(false);

  const ask = useCallback(
    (force: boolean) => {
      let dead = false;
      let timer = 0;
      const once = async () => {
        try {
          const r = await apiFetch(`/v1/creator/video-listo/${name}${force ? '?forzar=true' : ''}`);
          if (!r.ok) throw new Error(String(r.status));
          const d = await r.json();
          if (dead) return;
          if (d.estado === 'listo') setState({ kind: 'play', src: d.url });
          else if (d.estado === 'preparando') {
            setState({ kind: 'wait' });
            timer = window.setTimeout(once, 2000);
          } else setState({ kind: 'fail', why: d.motivo || 'No pude preparar este video.' });
        } catch {
          // the check itself failed: try the file as it is
          if (!dead) setState({ kind: 'play', src });
        }
      };
      void once();
      return () => {
        dead = true;
        window.clearTimeout(timer);
      };
    },
    [name, src],
  );

  useEffect(() => {
    forced.current = false;
    if (!name) {
      setState({ kind: 'play', src });
      return;
    }
    setState({ kind: 'wait' });
    return ask(false);
  }, [ask, name, src]);

  const failed = () => {
    if (name && !forced.current && state.src === src) {
      // the browser refused the original: make a copy it can play
      forced.current = true;
      setState({ kind: 'wait' });
      ask(true);
    } else {
      setState({ kind: 'fail', why: 'Su navegador no pudo reproducir este video.' });
    }
  };

  if (state.kind === 'fail') {
    return (
      <div className="wv-note" role="alert">
        {poster && <img src={poster} alt="" />}
        <p>{state.why}</p>
        <div>
          <a href={src} download>
            Descargar el video
          </a>
          <a href={src} target="_blank" rel="noreferrer">
            Abrirlo aparte
          </a>
        </div>
      </div>
    );
  }
  if (state.kind === 'wait') {
    return (
      <div className="wv-note" role="status" aria-busy="true">
        {poster && <img src={poster} alt="" />}
        <p>Preparando el video para que se vea en su navegador…</p>
      </div>
    );
  }
  return (
    <video
      key={state.src}
      className={className}
      src={state.src}
      poster={poster}
      controls
      autoPlay={autoPlay}
      playsInline
      preload={preload}
      onError={failed}
      onLoadedData={autoPlay ? (e) => void e.currentTarget.play().catch(() => undefined) : undefined}
    />
  );
}

export default WebVideo;
