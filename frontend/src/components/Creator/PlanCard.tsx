// A video plan in the chat: the animatic (storyboard timed to the cut), the
// shot list to film, an upload per shot, and «Editar con mis tomas» once the
// creator has filmed (owner, 3 Nov 2026: «Sergio creará una animación y un
// guion… el usuario lo convierte a videos reales y Sergio lo edita»).
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../lib/api';
import { WebVideo } from '../Gallery/WebVideo';
import './creator.css';

interface Shot {
  n: number;
  segundos: number;
  tipo: string;
  encuadre: string;
  movimiento: string;
  que_se_ve: string;
  dice: string;
  texto: string;
  sonido: string;
  consejo: string;
  archivo: string;
}

interface Plan {
  id: string;
  titulo: string;
  gancho: string;
  musica: string;
  notas: string[];
  tomas: Shot[];
  animatic?: string;
  animatic_error?: string;
  montaje?: { url: string; faltan: number[]; segundos: number; sonido: { lufs: number } } | null;
  montaje_error?: string;
  montando?: boolean;
}

const KIND: Record<string, string> = {
  cara: 'A cámara',
  broll: 'Recurso',
  producto: 'Producto',
  pantalla: 'Pantalla',
  texto: 'Texto',
};

export function PlanCard({ id }: { id: string }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [failed, setFailed] = useState(false);
  const [uploading, setUploading] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const pick = useRef<HTMLInputElement>(null);
  const target = useRef<number>(0);

  const load = useCallback(async () => {
    try {
      const r = await apiFetch(`/v1/creator/plan/${id}`);
      if (!r.ok) throw new Error(String(r.status));
      setPlan(await r.json());
    } catch {
      setFailed(true);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  // While the edit runs, look again every few seconds.
  useEffect(() => {
    if (!plan?.montando) return;
    const t = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(t);
  }, [plan?.montando, load]);

  const upload = async (n: number, file: File) => {
    setUploading(n);
    setNote('');
    try {
      const body = new FormData();
      body.append('file', file);
      const r = await apiFetch(`/v1/creator/plan/${id}/toma/${n}`, { method: 'POST', body });
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail || 'No se pudo subir.');
      await load();
    } catch (e) {
      setNote(e instanceof Error ? e.message : 'No se pudo subir.');
    } finally {
      setUploading(null);
    }
  };

  const edit = async () => {
    setNote('');
    await apiFetch(`/v1/creator/plan/${id}/montar`, { method: 'POST' });
    await load();
  };

  if (failed) return <p className="cr-note">No pude abrir el plan.</p>;
  if (!plan) return <div className="cr-plan" aria-busy="true" />;
  const filmed = plan.tomas.filter((s) => s.archivo).length;
  const total = plan.tomas.reduce((a, s) => a + s.segundos, 0);
  return (
    <section className="cr-plan" aria-label={`Plan: ${plan.titulo}`}>
      <header>
        <b>{plan.titulo}</b>
        <span>
          {plan.tomas.length} tomas · {Math.round(total)} s{plan.musica ? ` · Música: ${plan.musica}` : ''}
        </span>
      </header>
      {plan.gancho && <p className="cr-plan-hook">Gancho: {plan.gancho}</p>}
      {plan.animatic ? (
        <div className="cr-plan-animatic">
          <WebVideo src={plan.animatic} preload="metadata" />
        </div>
      ) : plan.animatic_error ? (
        <p className="cr-note">La animación no salió ({plan.animatic_error}); la lista de tomas sí.</p>
      ) : null}
      <ol className="cr-shots">
        {plan.tomas.map((s) => (
          <li key={s.n} data-done={s.archivo ? true : undefined}>
            <div className="cr-shot-head">
              <b>{s.n}</b>
              <span>
                {s.segundos.toFixed(1)} s · {KIND[s.tipo] || s.tipo}
                {s.encuadre ? ` · ${s.encuadre}` : ''}
                {s.movimiento ? ` · ${s.movimiento}` : ''}
              </span>
              <button
                type="button"
                className="cr-shot-up"
                disabled={uploading !== null}
                onClick={() => {
                  target.current = s.n;
                  pick.current?.click();
                }}
              >
                {uploading === s.n ? 'Subiendo…' : s.archivo ? 'Cambiar toma' : 'Subir toma'}
              </button>
            </div>
            <p>{s.que_se_ve}</p>
            {s.dice && <p className="cr-shot-line">«{s.dice}»</p>}
            {(s.texto || s.sonido || s.consejo) && (
              <small>
                {[s.texto && `En pantalla: ${s.texto}`, s.sonido && `Sonido: ${s.sonido}`, s.consejo]
                  .filter(Boolean)
                  .join(' · ')}
              </small>
            )}
          </li>
        ))}
      </ol>
      <input
        ref={pick}
        type="file"
        accept="video/*"
        hidden
        onChange={(e) => {
          const f = e.currentTarget.files?.[0];
          e.currentTarget.value = '';
          if (f) void upload(target.current, f);
        }}
      />
      <div className="cr-plan-actions">
        <span>
          {filmed} de {plan.tomas.length} tomas grabadas
        </span>
        <button type="button" disabled={!filmed || plan.montando} onClick={() => void edit()}>
          {plan.montando ? 'Editando…' : plan.montaje ? 'Volver a editar' : 'Editar con mis tomas'}
        </button>
      </div>
      {note && <p className="cr-note" role="alert">{note}</p>}
      {plan.montaje_error && <p className="cr-note" role="alert">El montaje falló: {plan.montaje_error}</p>}
      {plan.montaje && (
        <div className="cr-plan-result">
          <WebVideo src={plan.montaje.url} preload="metadata" />
          <p className="cr-note">
            {plan.montaje.segundos} s · sonido a {plan.montaje.sonido.lufs} LUFS
            {plan.montaje.faltan.length ? ` · faltan las tomas ${plan.montaje.faltan.join(', ')} (va su cuadro)` : ''}
          </p>
        </div>
      )}
    </section>
  );
}

export default PlanCard;
