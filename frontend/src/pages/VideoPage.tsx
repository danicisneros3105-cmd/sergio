import { useState } from 'react';
import { apiFetch } from '../lib/api';
import { PlanCard } from '../components/Creator/PlanCard';
import { VideoJobCard } from '../components/Chat/VideoJobCard';
import './VideoWorkspace.css';

type Mode = 'basic' | 'post' | 'cinema';
type Tab = 'crear' | 'planear';

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(String((body as { detail?: string }).detail || 'No pude completar la solicitud.'));
  }
  return body as T;
}

export function VideoPage() {
  const [tab, setTab] = useState<Tab>('crear');
  const [idea, setIdea] = useState('');
  const [seconds, setSeconds] = useState(60);
  const [aspect, setAspect] = useState('9:16');
  const [mode, setMode] = useState<Mode>('basic');
  const [reference, setReference] = useState('');
  const [jobs, setJobs] = useState<string[]>([]);
  const [planId, setPlanId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const createVideo = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!idea.trim()) return;
    setBusy(true);
    setError('');
    try {
      const result = await call<{ job_id: string }>('/v1/video/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea: idea.trim(), seconds, aspect, mode, reference: reference.trim() }),
      });
      setJobs((current) => [result.job_id, ...current.filter((id) => id !== result.job_id)].slice(0, 5));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No pude iniciar el video.');
    } finally {
      setBusy(false);
    }
  };

  const createPlan = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!idea.trim()) return;
    setBusy(true);
    setError('');
    try {
      const result = await call<{ plan_id: string }>('/v1/video/plans', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea: idea.trim(), seconds, aspect, reference: reference.trim() }),
      });
      setPlanId(result.plan_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No pude crear el plan de tomas.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="video-page">
      <h1>Video</h1>
      <div className="video-tabs" role="tablist" aria-label="Herramientas de video">
        <button type="button" role="tab" aria-selected={tab === 'crear'} onClick={() => { setTab('crear'); setError(''); }}>Crear video</button>
        <button type="button" role="tab" aria-selected={tab === 'planear'} onClick={() => { setTab('planear'); setError(''); }}>Planear tomas</button>
      </div>

      <form className="video-form" onSubmit={tab === 'crear' ? createVideo : createPlan}>
        <label>
          Idea del video
          <textarea value={idea} onChange={(event) => setIdea(event.target.value)} maxLength={2000} required placeholder="¿Qué quieres contar o mostrar?" />
        </label>
        <label>
          Referencia opcional
          <input value={reference} onChange={(event) => setReference(event.target.value)} maxLength={2000} placeholder="Enlace de inspiración" />
        </label>
        <div className="video-form-grid">
          <label>
            Duración aproximada
            <select value={seconds} onChange={(event) => setSeconds(Number(event.target.value))}>
              <option value={30}>30 segundos</option>
              <option value={60}>1 minuto</option>
              <option value={90}>1 minuto y medio</option>
              <option value={120}>2 minutos</option>
              <option value={180}>3 minutos</option>
            </select>
          </label>
          <label>
            Formato
            <select value={aspect} onChange={(event) => setAspect(event.target.value)}>
              <option value="9:16">Vertical</option>
              <option value="16:9">Horizontal</option>
              <option value="1:1">Cuadrado</option>
            </select>
          </label>
          {tab === 'crear' && (
            <label>
              Nivel de producción
              <select value={mode} onChange={(event) => setMode(event.target.value as Mode)}>
                <option value="basic">Básico</option>
                <option value="post">Alta calidad</option>
                <option value="cinema">Cinemático</option>
              </select>
            </label>
          )}
        </div>
        {error && <p className="video-error" role="alert">{error}</p>}
        <button className="video-submit" type="submit" disabled={busy || !idea.trim()}>
          {busy ? 'Preparando…' : tab === 'crear' ? 'Crear video' : 'Crear plan de tomas'}
        </button>
      </form>

      <section className="video-results" aria-live="polite">
        {tab === 'crear' ? (
          <>
            <h2>Trabajos de video</h2>
            {jobs.length ? jobs.map((id) => <VideoJobCard key={id} id={id} />) : <p className="video-empty">Los videos que inicies aparecerán aquí.</p>}
          </>
        ) : (
          <>
            <h2>Plan de tomas</h2>
            {planId ? <PlanCard id={planId} /> : <p className="video-empty">Crea un plan para ver la animática y la lista de tomas.</p>}
          </>
        )}
      </section>
    </div>
  );
}

export default VideoPage;
