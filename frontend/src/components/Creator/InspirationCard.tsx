// Three trending videos found for a brief: the person picks one as the style
// and inspiration, and Sergio plans the video with it (owner, 3 Nov 2026).
import { useEffect, useState } from 'react';
import { apiFetch } from '../../lib/api';
import './creator.css';

interface Option {
  plataforma: string;
  url: string;
  titulo: string;
  canal: string;
  vistas: number;
  me_gusta: number;
  segundos: number;
  por_que: string;
  mini: string;
}

interface Found {
  id: string;
  encargo: string;
  opciones: Option[];
  notas: string[];
  tiktok: string[];
  elegida: number | null;
}

export function InspirationCard({ id }: { id: string }) {
  const [data, setData] = useState<Found | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let dead = false;
    apiFetch(`/v1/creator/inspiracion/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => !dead && setData(d))
      .catch(() => !dead && setFailed(true));
    return () => {
      dead = true;
    };
  }, [id]);

  const choose = async (i: number) => {
    setBusy(true);
    try {
      const r = await apiFetch(`/v1/creator/inspiracion/${id}/elegir`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ opcion: i }),
      });
      const d = await r.json();
      setData(d);
      if (d.mensaje) window.dispatchEvent(new CustomEvent('sergio:send', { detail: d.mensaje }));
    } finally {
      setBusy(false);
    }
  };

  if (failed) return <p className="cr-note">No pude abrir las opciones de inspiración.</p>;
  if (!data) return <div className="cr-insp" aria-busy="true" />;
  return (
    <section className="cr-insp" aria-label="Videos de inspiración">
      <header>
        <b>Elija un estilo</b>
        <span>Tres videos reales que van bien con su idea</span>
      </header>
      <div className="cr-insp-grid">
        {data.opciones.map((o, i) => {
          const chosen = data.elegida === i;
          return (
            <article key={o.url} className="cr-insp-card" data-chosen={chosen || undefined}>
              <a href={o.url} target="_blank" rel="noreferrer" className="cr-insp-thumb" data-empty={o.mini ? undefined : true} aria-label={`Ver «${o.titulo}»`}>
                {o.mini ? <img src={o.mini} alt="" loading="lazy" /> : <span>{o.segundos ? `${Math.round(o.segundos)} s` : 'Ver video'}</span>}
                <i>{o.plataforma}</i>
              </a>
              <div className="cr-insp-body">
                <b title={o.titulo}>{o.titulo || 'Sin título'}</b>
                {o.canal && <small>{o.canal}</small>}
                {o.por_que && <p>{o.por_que}</p>}
                <button type="button" disabled={busy || data.elegida !== null} onClick={() => choose(i)}>
                  {chosen ? 'Elegido' : 'Usar este estilo'}
                </button>
              </div>
            </article>
          );
        })}
      </div>
      {data.tiktok.length > 0 && (
        <p className="cr-note">En TikTok suben ahora: {data.tiktok.slice(0, 6).map((t) => `#${t}`).join(' ')}</p>
      )}
    </section>
  );
}

export default InspirationCard;
