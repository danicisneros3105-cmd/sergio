// Salud, in the quietest form: what the owner entered, a way to add more, one question for
// the coach and the mental gym when asked for. No invented numbers: a value appears only
// after the owner (or a synced source) put it there.

import { useCallback, useEffect, useState } from 'react';
import { Brain, ChevronDown, ChevronUp } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';
import { PaperPage, PaperSection } from '../components/Paper/PaperPage';
import { HealthGym } from './health/HealthGym';
import './health/health.css';

type Hub = {
  entered?: Record<string, number>;
  heart: { resting_hr: number; hrv_ms: number };
  sleep: { total_hours: number };
  mental: { mood_today: string };
  nutrition: { kcal_consumed: number; protein_g: number; meals: Array<{ id: string; time: string; name: string; kcal: number; protein_g: number }> };
  gym: { cognitive_index: number; sessions_completed: number };
  // the rest of the hub exists for the gym and older clients
  [key: string]: any; // eslint-disable-line @typescript-eslint/no-explicit-any
};

const post = (path: string, body: unknown) =>
  apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function Metric({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="health-metric" data-empty={value === null ? '1' : undefined}>
      <b>{value ?? '—'}</b>
      <span>{label}</span>
    </div>
  );
}

export function HealthPage() {
  const [hub, setHub] = useState<Hub | null>(null);
  const [problem, setProblem] = useState('');
  const [sleep, setSleep] = useState('');
  const [pulse, setPulse] = useState('');
  const [hrv, setHrv] = useState('');
  const [mood, setMood] = useState('');
  const [meal, setMeal] = useState('');
  const [ask, setAsk] = useState('');
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState('');
  const [gymOpen, setGymOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await apiFetch('/v1/desktop/health');
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      if (data.hub) setHub(data.hub);
      setProblem('');
    } catch {
      setProblem('No pude leer sus datos de salud. Compruebe que Sergio está en marcha.');
    }
  }, []);

  useEffect(() => {
    void load();
    const refresh = () => void load();
    window.addEventListener('sergio:health-refresh', refresh);
    return () => window.removeEventListener('sergio:health-refresh', refresh);
  }, [load]);

  const entered = hub?.entered ?? {};
  const has = (...keys: string[]) => keys.some((k) => entered[k]);

  const save = async () => {
    const jobs: Array<Promise<Response>> = [];
    if (sleep.trim() && Number(sleep) > 0) jobs.push(post('/v1/desktop/health/log', { category: 'sleep', payload: { total_hours: Number(sleep) } }));
    if ((pulse.trim() && Number(pulse) > 0) || (hrv.trim() && Number(hrv) > 0)) {
      const payload: Record<string, number> = {};
      if (Number(pulse) > 0) payload.resting_hr = Number(pulse);
      if (Number(hrv) > 0) payload.hrv_ms = Number(hrv);
      jobs.push(post('/v1/desktop/health/log', { category: 'vitals', payload }));
    }
    if (mood.trim()) jobs.push(post('/v1/desktop/health/log', { category: 'mental', payload: { mood: mood.trim() } }));
    if (!jobs.length) return toast('Escriba al menos un dato.');
    setBusy('save');
    try {
      const results = await Promise.all(jobs);
      const last = results[results.length - 1];
      const body = last.ok ? await last.json() : null;
      if (body?.hub) setHub(body.hub);
      else await load();
      setSleep('');
      setPulse('');
      setHrv('');
      setMood('');
      toast.success('Anotado.');
    } catch {
      toast.error('No se pudo guardar.');
    } finally {
      setBusy('');
    }
  };

  const logMeal = async () => {
    if (!meal.trim()) return;
    setBusy('meal');
    try {
      const res = await post('/v1/desktop/health/nutrition-ai', { description: meal.trim() });
      if (!res.ok) throw new Error();
      const data = await res.json();
      if (data.hub) setHub(data.hub);
      setMeal('');
      toast.success(`Anotada: unas ${data.meal?.kcal} kcal (estimación).`);
    } catch {
      toast.error('No pude anotar la comida.');
    } finally {
      setBusy('');
    }
  };

  const question = async () => {
    const text = ask.trim();
    if (!text) return;
    setBusy('ask');
    try {
      const res = await post('/v1/desktop/health/coach-ai', { message: text });
      if (!res.ok) throw new Error();
      const data = await res.json();
      if (data.hub) setHub(data.hub);
      setReply(String(data.reply ?? ''));
      setAsk('');
    } catch {
      toast.error('No pude responder ahora.');
    } finally {
      setBusy('');
    }
  };

  const meals = (hub?.nutrition.meals ?? []).filter((m) => m.id.startsWith('m-')).slice(0, 5);

  return (
    <PaperPage title="Salud" wide>
      {problem && <p className="paper-meta">{problem}</p>}

      <PaperSection label="Hoy">
        <div className="health-metrics">
          <Metric label="Sueño" value={has('sleep') && hub ? `${hub.sleep.total_hours} h` : null} />
          <Metric label="Pulso en reposo" value={has('vitals', 'heart') && hub ? `${hub.heart.resting_hr} lpm` : null} />
          <Metric label="Variabilidad" value={has('vitals', 'heart') && hub ? `${hub.heart.hrv_ms} ms` : null} />
          <Metric label="Ánimo" value={has('mental') && hub ? hub.mental.mood_today : null} />
          <Metric label="Comida" value={has('nutrition') && hub ? `${hub.nutrition.kcal_consumed} kcal` : null} />
        </div>
      </PaperSection>

      <PaperSection label="Anotar">
        <div className="health-form">
          <input className="paper-input" inputMode="decimal" value={sleep} onChange={(e) => setSleep(e.target.value)} placeholder="Horas de sueño" aria-label="Horas de sueño" />
          <input className="paper-input" inputMode="numeric" value={pulse} onChange={(e) => setPulse(e.target.value)} placeholder="Pulso en reposo" aria-label="Pulso en reposo" />
          <input className="paper-input" inputMode="numeric" value={hrv} onChange={(e) => setHrv(e.target.value)} placeholder="Variabilidad (ms)" aria-label="Variabilidad cardiaca" />
          <input className="paper-input" value={mood} onChange={(e) => setMood(e.target.value)} placeholder="Cómo se siente" aria-label="Estado de ánimo" maxLength={80} />
          <button type="button" className="paper-button" onClick={save} disabled={busy === 'save'}>
            Guardar
          </button>
        </div>
        <form
          className="health-line"
          onSubmit={(e) => {
            e.preventDefault();
            void logMeal();
          }}
        >
          <input className="paper-input" value={meal} onChange={(e) => setMeal(e.target.value)} placeholder="Qué comió" aria-label="Qué comió" />
          <button type="submit" className="paper-button" data-variant="quiet" disabled={!meal.trim() || busy === 'meal'}>
            Anotar comida
          </button>
        </form>
        {meals.length > 0 && (
          <ul className="health-meals">
            {meals.map((m) => (
              <li key={m.id}>
                <span>{m.time}</span> {m.name} <em>≈ {m.kcal} kcal</em>
              </li>
            ))}
          </ul>
        )}
      </PaperSection>

      <PaperSection label="Preguntar">
        <form
          className="health-line"
          onSubmit={(e) => {
            e.preventDefault();
            void question();
          }}
        >
          <input className="paper-input" value={ask} onChange={(e) => setAsk(e.target.value)} placeholder="Una duda sobre su salud o su entrenamiento" aria-label="Pregunta" />
          <button type="submit" className="paper-button" disabled={!ask.trim() || busy === 'ask'}>
            Preguntar
          </button>
        </form>
        {reply && <p className="health-reply">{reply}</p>}
        <p className="paper-meta">Es un consejo general, no un diagnóstico. Ante un dolor o un síntoma, vea a un médico.</p>
      </PaperSection>

      <PaperSection
        label="Mente"
        aside={
          <button type="button" className="paper-button" data-variant="quiet" onClick={() => setGymOpen((v) => !v)} aria-expanded={gymOpen}>
            <Brain size={14} /> Gimnasio mental {gymOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        }
      >
        {has('gym') && hub ? (
          <p className="paper-meta">
            Índice {hub.gym.cognitive_index} · {hub.gym.sessions_completed} sesiones
          </p>
        ) : (
          <p className="paper-meta">Aún sin sesiones.</p>
        )}
        {gymOpen && hub && <HealthGym hub={hub} setHub={(h: Hub) => setHub(h)} />}
      </PaperSection>
    </PaperPage>
  );
}

export default HealthPage;
