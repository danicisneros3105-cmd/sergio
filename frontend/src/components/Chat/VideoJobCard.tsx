// A video being made, live in the chat where it was asked: its step and
// progress, then the video itself, or why it stopped in plain words (owner,
// 2 Nov 2026: «dice que ya se está ejecutando… pero no me lo manda»).
import { useEffect, useState } from 'react';
import { apiFetch } from '../../lib/api';

interface Job {
  id: string;
  titulo: string;
  estado: string;
  etapa: string;
  paso: number;
  pasos: number;
  avance: number;
  error: string;
  video: string;
  portada: string;
}

export function VideoJobCard({ id }: { id: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const r = await apiFetch(`/v1/personal/videos/trabajos/${encodeURIComponent(id)}`);
        if (r.status === 404) {
          if (alive) setGone(true);
          return;
        }
        const d = (await r.json()) as Job;
        if (!alive) return;
        setJob(d);
        if (d.estado === 'en curso') timer = window.setTimeout(tick, 4000);
      } catch {
        if (alive) timer = window.setTimeout(tick, 8000);
      }
    };
    void tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [id]);

  if (gone) return null;
  if (!job) return <div className="vjob" aria-busy="true" />;
  const pct = Math.round(((Math.max(0, job.paso - 1) + job.avance) / Math.max(1, job.pasos)) * 100);
  return (
    <div className="vjob" data-state={job.estado}>
      <div className="vjob-head">
        <b>{job.titulo}</b>
        <span>
          {job.estado === 'listo'
            ? 'Listo'
            : job.estado === 'en curso'
              ? `${job.etapa} · ${pct} %`
              : job.estado === 'cancelado'
                ? 'Cancelado'
                : 'Se detuvo'}
        </span>
      </div>
      {job.estado === 'en curso' && (
        <div className="vjob-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <i style={{ width: `${pct}%` }} />
        </div>
      )}
      {job.estado === 'listo' && job.video && (
        <video className="vjob-video" src={job.video} poster={job.portada || undefined} controls playsInline preload="metadata" />
      )}
      {(job.estado === 'error' || job.estado === 'detenido') && (
        <p className="vjob-why">
          {job.error ? `Se detuvo en «${job.etapa}»: ${job.error}` : 'Se detuvo antes de terminar.'} Pídame «reintenta el video» y sigo desde ahí.
        </p>
      )}
    </div>
  );
}

export default VideoJobCard;
