// Start a video from the composer. One-off jobs go through the chat;
// recurring jobs are saved in /v1/personal/videos for review before publishing.

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';

const EFFORT = [
  { id: 'test', nombre: 'Prueba' },
  { id: 'basic', nombre: 'Básico' },
  { id: 'post', nombre: 'Para publicar' },
  { id: 'cinema', nombre: 'Absolut Cinema' },
];
const FORMATS = [
  { id: '9:16', nombre: 'Vertical' },
  { id: '16:9', nombre: 'Horizontal' },
  { id: '1:1', nombre: 'Cuadrado' },
];
// From scratch up to 8 minutes (owner, 2 Nov 2026); a long one is made in
// the background, in chapters, and says when it is ready.
const LENGTHS = [
  { s: 30, label: '30 s' },
  { s: 60, label: '1 min' },
  { s: 180, label: '3 min' },
  { s: 300, label: '5 min' },
  { s: 480, label: '8 min' },
];
const EVERY: { h: number; label: string }[] = [
  { h: 0, label: 'Una vez' },
  { h: 3, label: 'Cada 3 h' },
  { h: 6, label: 'Cada 6 h' },
  { h: 12, label: 'Cada 12 h' },
  { h: 24, label: 'Cada día' },
  { h: 168, label: 'Cada semana' },
];

interface Ready {
  job: string;
  titulo: string;
  descripcion: string;
  video: string;
}

interface Scheduled {
  id: string;
  idea: string;
  cada_horas: number;
  modo: string;
  activo: boolean;
  nota: string;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(String((body as { detail?: string }).detail || 'No pude completar eso.'));
  return body as T;
}

export function VideoSheet({ onClose, onAsk }: { onClose: () => void; onAsk: (text: string) => void }) {
  const [idea, setIdea] = useState('');
  const [effort, setEffort] = useState(1);
  const [animation, setAnimation] = useState(false);
  const [format, setFormat] = useState('9:16');
  const [length, setLength] = useState(60);
  const [every, setEvery] = useState(0);
  const [ready, setReady] = useState<Ready[]>([]);
  const [clips, setClips] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [liveTrends, setLiveTrends] = useState(false);
  const [scheduled, setScheduled] = useState<Scheduled[]>([]);

  const load = () =>
    call<{ listos: Ready[]; programados: Scheduled[] }>('/v1/personal/videos')
      .then((d) => {
        setReady(d.listos ?? []);
        setScheduled(d.programados ?? []);
      })
      .catch(() => {});
  useEffect(() => {
    void load();
  }, []);

  const repeat = animation ? 0 : every;
  const selectedClips = animation ? [] : clips;

  const go = async () => {
    const mode = EFFORT[animation ? Math.max(effort, 2) : effort];
    const shape = FORMATS.find((f) => f.id === format)?.nombre.toLowerCase();
    if (!repeat) {
      let gallery = '';
      if (selectedClips.length) {
        if (selectedClips.length > 6 || selectedClips.reduce((size, file) => size + file.size, 0) > 64 * 1024 * 1024) {
          toast.error('Elige hasta seis videos que sumen menos de 64 MB.');
          return;
        }
        setSending(true);
        try {
          const body = new FormData();
          selectedClips.forEach((file) => body.append('files', file));
          const batch = await call<{ id: string; videos: number }>('/v1/personal/videos/galeria', { method: 'POST', body });
          gallery = ` Usa exactamente mis ${batch.videos} clips en el orden seleccionado: galeria_id=${batch.id} en video_essay. Activa equipo_creativo y crea una miniatura en modo post.`;
        } catch (e) {
          toast.error(e instanceof Error ? e.message : 'No pude importar los clips.');
          return;
        } finally {
          setSending(false);
        }
      }
      onAsk(
        `Haz un video sobre: ${idea.trim()}. Formato ${shape} (${format}). Duración: ${length} segundos. Modo ${selectedClips.length ? 'post' : mode.id}. Activa equipo_creativo.${animation ? ' Usa video_essay con verificar_animacion=true y narración en español. No sustituyas tomas por imágenes fijas.' : ''}${liveTrends ? ' Consulta YouTube e Instagram ahora con tendencias_en_vivo=true.' : ''}${gallery}`,
      );
      onClose();
      return;
    }
    setSending(true);
    try {
      await call('/v1/personal/videos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea, cada_horas: repeat, modo: mode.id, formato: format, segundos: length }),
      });
      toast.success('Programado. Le aviso cuando cada video esté listo; nada se publica sin usted.');
      setIdea('');
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude programarlo.');
    } finally {
      setSending(false);
    }
  };

  const post = async (r: Ready) => {
    try {
      const out = await call<{ video: string; titulo: string; descripcion: string }>(
        `/v1/personal/videos/listos/${r.job}/publicar`,
        { method: 'POST' },
      );
      try {
        await navigator.clipboard.writeText(`${out.titulo}\n\n${out.descripcion}`);
      } catch {
        /* the text is on screen anyway */
      }
      if (out.video) window.open(out.video, '_blank', 'noopener');
      toast.success('Título y descripción copiados. Súbalo en su red: el video se abrió para descargarlo.');
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude prepararlo.');
    }
  };

  const stop = async (s: Scheduled) => {
    await call(`/v1/personal/videos/${s.id}`, { method: 'DELETE' }).catch(() => {});
    void load();
  };

  // On the page itself: the composer around it would trap a fixed layer.
  return createPortal(
    <div className="msheet-layer" onClick={onClose}>
      <div className="msheet vsheet" role="dialog" aria-label="Crear video" onClick={(e) => e.stopPropagation()}>
        <header className="msheet-head">
          <h2>Crear video</h2>
          <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={onClose}><X size={18} /></button>
        </header>
        <textarea
          className="vsheet-idea"
          aria-label="Idea del video"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="¿Qué quiere contar?"
          rows={3}
        />
        <label className="vsheet-effort">
          <span>Tipo de video</span>
          <select className="paper-input" value={animation ? 'animation' : 'edit'} disabled={sending} onChange={(e) => setAnimation(e.target.value === 'animation')}>
            <option value="edit">Montaje narrado</option>
            <option value="animation">Animación con voz</option>
          </select>
        </label>
        <details className="vjob-why">
          <summary>Ajustes del video</summary>
          <label className="vsheet-effort">
            <span>Formato</span>
            <select className="paper-input" value={format} onChange={(e) => setFormat(e.target.value)} disabled={sending}>
              {FORMATS.map((f) => <option key={f.id} value={f.id}>{f.nombre}</option>)}
            </select>
          </label>
          <label className="vsheet-effort">
            <span>Duración</span>
            <select className="paper-input" value={length} onChange={(e) => setLength(Number(e.target.value))} disabled={sending}>
              {LENGTHS.map((x) => <option key={x.s} value={x.s}>{x.label}</option>)}
            </select>
          </label>
          <label className="vsheet-effort">
            <span>Producción</span>
            <select className="paper-input" value={selectedClips.length ? 2 : animation ? Math.max(2, effort) : effort}
              onChange={(e) => setEffort(Number(e.target.value))} disabled={sending || selectedClips.length > 0}>
              {EFFORT.map((x, i) => (!animation || i >= 2) && <option key={x.id} value={i}>{x.nombre}</option>)}
            </select>
          </label>
          {!animation && <label className="vsheet-effort">
            <span>Repetir</span>
            <select className="paper-input" value={every} onChange={(e) => setEvery(Number(e.target.value))}
              disabled={sending || selectedClips.length > 0}>
              {EVERY.map((x) => <option key={x.h} value={x.h}>{x.label}</option>)}
            </select>
          </label>}
          {!animation && !every && <label className="vsheet-effort">
            <span>Usar mis clips</span>
            <input type="file" accept="video/*,.mov,.mp4,.webm,.mkv,.m4v" multiple
              onChange={(e) => setClips(Array.from(e.target.files ?? []))} disabled={sending} />
            {clips.length > 0 && <small>{clips.length} clips · se usan en orden, en modo Para publicar.</small>}
          </label>}
          {!repeat && <label className="msheet-for">
            <input type="checkbox" checked={liveTrends} onChange={(e) => setLiveTrends(e.target.checked)} disabled={sending} />
            {' '}Consultar tendencias actuales
          </label>}
        </details>
        <p className="msheet-for">
          {animation
            ? 'Requiere un proveedor de voz y un generador de video o Blender. Puede tardar horas.'
            : `${FORMATS.find((f) => f.id === format)?.nombre} · ${LENGTHS.find((x) => x.s === length)?.label}`}
          {' '}No se publica automáticamente desde aquí.
        </p>
        <button type="button" className="msheet-primary vsheet-go" disabled={idea.trim().length < 3 || sending} onClick={() => void go()}>
          {sending ? 'Preparando…' : repeat ? 'Programar video' : 'Crear video'}
        </button>

        {ready.length > 0 && (
          <section className="vsheet-list">
            <h3>Listos para publicar</h3>
            {ready.map((r) => (
              <div key={r.job} className="vsheet-row">
                <span>{r.titulo || 'Video'}</span>
                <button type="button" className="msheet-primary" onClick={() => void post(r)}>Abrir para subir</button>
              </div>
            ))}
          </section>
        )}
        {scheduled.length > 0 && (
          <section className="vsheet-list">
            <h3>Programados</h3>
            {scheduled.map((s) => (
              <div key={s.id} className="vsheet-row">
                <span>
                  {s.idea}
                  <em>
                    {EVERY.find((x) => x.h === s.cada_horas)?.label ?? `Cada ${s.cada_horas} h`} · {EFFORT.find((x) => x.id === s.modo)?.nombre}
                    {s.nota ? ` · ${s.nota}` : ''}
                  </em>
                </span>
                <button type="button" className="msheet-advanced" onClick={() => void stop(s)}>Quitar</button>
              </div>
            ))}
          </section>
        )}
      </div>
    </div>,
    document.body,
  );
}
