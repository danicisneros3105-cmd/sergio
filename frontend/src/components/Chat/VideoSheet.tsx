// «Video» in the chat's «+» menu: what the video is about, its shape, how much
// effort (a bar with the four modes, from a quick test to Absolut Cinema) and,
// if wanted, «repetir cada 3 horas». A one-off video is asked in the chat (the
// director and editor answer there); a repeating one is saved as a schedule
// (/v1/personal/videos). Finished scheduled videos wait here for the person's
// OK: nothing is posted without them, and «Publicar» hands over the file,
// title and description to upload.

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';

const EFFORT = [
  { id: 'test', nombre: 'Prueba', tarda: 'unos minutos' },
  { id: 'basic', nombre: 'Básico', tarda: 'un rato' },
  { id: 'post', nombre: 'Para publicar', tarda: 'horas' },
  { id: 'cinema', nombre: 'Absolut Cinema', tarda: 'muchas horas' },
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
  const [format, setFormat] = useState('9:16');
  const [length, setLength] = useState(60);
  const [every, setEvery] = useState(0);
  const [ready, setReady] = useState<Ready[]>([]);
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

  const go = async () => {
    const mode = EFFORT[effort];
    const shape = FORMATS.find((f) => f.id === format)?.nombre.toLowerCase();
    if (!every) {
      onAsk(
        `Haz un video sobre: ${idea.trim()}. Formato ${shape} (${format}). Duración: ${length} segundos. Esfuerzo: ${mode.nombre} (modo ${mode.id}).`,
      );
      onClose();
      return;
    }
    try {
      await call('/v1/personal/videos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea, cada_horas: every, modo: mode.id, formato: format, segundos: length }),
      });
      toast.success('Programado. Le aviso cuando cada video esté listo; nada se publica sin usted.');
      setIdea('');
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude programarlo.');
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
      <div className="msheet vsheet" role="dialog" aria-label="Video" onClick={(e) => e.stopPropagation()}>
        <header className="msheet-head">
          <h2>Video</h2>
          <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={onClose}><X size={18} /></button>
        </header>
        <textarea
          className="vsheet-idea"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="De qué trata: «la historia del primer auto eléctrico», «3 recetas en 30 segundos»…"
          rows={3}
        />
        <div className="msheet-effort" role="radiogroup" aria-label="Formato" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          {FORMATS.map((f) => (
            <button key={f.id} type="button" role="radio" aria-checked={format === f.id} onClick={() => setFormat(f.id)}>{f.nombre}</button>
          ))}
        </div>
        <div className="msheet-effort" role="radiogroup" aria-label="Duración" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
          {LENGTHS.map((x) => (
            <button key={x.s} type="button" role="radio" aria-checked={length === x.s} onClick={() => setLength(x.s)}>{x.label}</button>
          ))}
        </div>
        <label className="vsheet-effort">
          <span>Esfuerzo: <b>{EFFORT[effort].nombre}</b> · tarda {EFFORT[effort].tarda}</span>
          <input type="range" min={0} max={3} step={1} value={effort} onChange={(e) => setEffort(Number(e.target.value))} aria-label="Esfuerzo" />
          <span className="vsheet-ticks">{EFFORT.map((x) => <i key={x.id}>{x.nombre}</i>)}</span>
        </label>
        <div className="vsheet-every" role="radiogroup" aria-label="Repetir">
          {EVERY.map((x) => (
            <button key={x.h} type="button" role="radio" aria-checked={every === x.h} onClick={() => setEvery(x.h)}>{x.label}</button>
          ))}
        </div>
        <p className="msheet-for">
          Sergio escribe el guion, elige los clips, corta, pone subtítulos y música. Nada se publica sin que usted lo apruebe.
        </p>
        <button type="button" className="msheet-primary vsheet-go" disabled={idea.trim().length < 3} onClick={() => void go()}>
          {every ? 'Programar' : 'Hacer el video'}
        </button>

        {ready.length > 0 && (
          <section className="vsheet-list">
            <h3>Listos para publicar</h3>
            {ready.map((r) => (
              <div key={r.job} className="vsheet-row">
                <span>{r.titulo || 'Video'}</span>
                <button type="button" className="msheet-primary" onClick={() => void post(r)}>Publicar</button>
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
