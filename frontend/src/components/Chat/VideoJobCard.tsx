// A video being made, live in the chat where it was asked: its step and
// progress, then the video itself, or why it stopped in plain words (owner,
// 2 Nov 2026: «dice que ya se está ejecutando… pero no me lo manda»).
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { WebVideo } from '../Gallery/WebVideo';

interface Job {
  referencia_estado?: 'medida' | 'analizada' | 'sin_medicion';
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
  verificacion?: { tomas_animadas: number; fps: number; alineacion: string } | null;
  sin_voz?: boolean;
  checklist?: Array<{ tarea: string; estado: string }>;
  subida_youtube?: { estado: string; url?: string; miniatura?: string } | null;
}

export function VideoJobCard({ id }: { id: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [gone, setGone] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [requesting, setRequesting] = useState(false);

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
        if (d.estado === 'en curso' || ['esperando_aprobacion', 'subiendo', 'miniatura'].includes(d.subida_youtube?.estado ?? '')) {
          timer = window.setTimeout(tick, 4000);
        }
      } catch {
        if (alive) timer = window.setTimeout(tick, 8000);
      }
    };
    void tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [id, refresh]);

  if (gone) return null;
  if (!job) return <div className="vjob" aria-busy="true" />;
  const upload = job.subida_youtube;
  const uploading = ['esperando_aprobacion', 'subiendo', 'miniatura'].includes(upload?.estado ?? '');
  const requestUpload = async () => {
    setRequesting(true);
    try {
      const r = await apiFetch(`/v1/personal/videos/listos/${encodeURIComponent(id)}/youtube`, { method: 'POST' });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || 'No pude iniciar la subida.');
      if (!upload?.url) toast.info('Aprueba en la campana o con Visage para subir como privado.');
      setRefresh((n) => n + 1);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude iniciar la subida.');
    } finally {
      setRequesting(false);
    }
  };
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
        <>
          <WebVideo className="vjob-video" src={job.video} poster={job.portada || undefined} preload="metadata" />
          {upload?.url && <a href={upload.url} target="_blank" rel="noopener noreferrer">Ver video privado en YouTube</a>}
          {upload?.estado === 'revisar_canal' && <p className="vjob-why">YouTube no confirmó la subida. Revisa el canal antes de volver a intentarlo.</p>}
          {upload?.miniatura === 'aplicada' && <p className="vjob-why">Miniatura aplicada.</p>}
          {upload?.miniatura === 'procesando' && <p className="vjob-why">YouTube está procesando el video; vuelve a intentar la miniatura después.</p>}
          {upload?.miniatura === 'no_aplicada' && <p className="vjob-why">El video se subió. YouTube no confirmó la miniatura.</p>}
          {upload?.miniatura === 'sin_archivo' && <p className="vjob-why">El video se subió sin miniatura personalizada.</p>}
          {upload?.estado === 'no_aprobado' && <p className="vjob-why">La subida no se aprobó.</p>}
          {upload?.estado !== 'revisar_canal' && (!upload?.url || ['pendiente', 'procesando', 'no_aplicada'].includes(upload.miniatura ?? '')) && (
            <button type="button" className="vjob-why" disabled={requesting || uploading} onClick={() => void requestUpload()}>
              {uploading ? 'Subida en curso…' : upload?.url ? 'Aplicar miniatura' : 'Subir en privado a YouTube'}
            </button>
          )}
        </>
      )}
      {!!job.checklist?.length && (
        <details className="vjob-why">
          <summary>Checklist de producción</summary>
          <ul>{job.checklist.map((row) => <li key={row.tarea}>{row.tarea}: {row.estado}</li>)}</ul>
        </details>
      )}
      {job.estado === 'listo' && job.verificacion && (
        <p className="vjob-why">
          Verificación técnica: guion, voz audible, {job.verificacion.tomas_animadas} tomas animadas,
          subtítulos y video a {job.verificacion.fps} FPS.
          {job.verificacion.alineacion !== 'reconocedor' && ' La sincronía de subtítulos es estimada.'}
        </p>
      )}
      {job.estado === 'listo' && job.sin_voz && (
        <p className="vjob-why">La narración falló. Este montaje se entregó sin voz.</p>
      )}
      {job.referencia_estado === 'sin_medicion' && (
        <p className="vjob-why">Referencia sin medir. El video usa el tema y el estilo pedidos.</p>
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
