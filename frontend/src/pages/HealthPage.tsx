import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  Award,
  Brain,
  Check,
  Droplets,
  Ear,
  FileText,
  Flame,
  HeartPulse,
  Moon,
  Play,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Trophy,
  Users,
  Utensils,
  Zap,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';

type TabId = 'overview' | 'vitals' | 'nutrition' | 'gym' | 'clinical';
type GymGame = 'none' | 'dual_nback' | 'raven_matrices' | 'ufov_speed' | 'stroop_switch' | 'dsst_control';

const LETTERS = ['C', 'H', 'K', 'L', 'Q', 'R', 'S', 'T'];

interface MatrixPuzzle {
  q: string;
  rule: string;
  grid: string[][];
  options: string[];
  answer: number;
}

const RAVEN_PUZZLES: MatrixPuzzle[] = [
  {
    q: 'Matriz Relacional 1 (Progresión + Rotación simultánea · Nivel Klauer Gf)',
    rule: 'Cada fila incrementa +1 elemento y rota el símbolo 90° en sentido horario.',
    grid: [
      ['▲ · 1', '▶ · 2', '▼ · 3'],
      ['◆ · 2', '◈ · 3', '◆ · 4'],
      ['● · 3', '◐ · 4', '?'],
    ],
    options: ['◑ · 5', '● · 4', '▲ · 5', '◐ · 6'],
    answer: 0,
  },
  {
    q: 'Matriz Relacional 2 (Operador XOR conjuntivo · Red Fronto-Parietal P-FIT)',
    rule: 'La tercera celda de cada fila conserva los rasgos presentes en la 1.ª o 2.ª celda, pero NO en ambas (diferencia simétrica XOR).',
    grid: [
      ['[A, B]', '[B, C]', '[A, C]'],
      ['[X, Y, Z]', '[Y]', '[X, Z]'],
      ['[Δ, Ω, Ψ]', '[Ω, Φ]', '?'],
    ],
    options: ['[Δ, Ψ, Φ]', '[Δ, Ω]', '[Ψ, Φ]', '[Δ, Ω, Ψ, Φ]'],
    answer: 0,
  },
  {
    q: 'Matriz Relacional 3 (Doble progresión cuantitativa y paridad · Nivel Raven Avanzado)',
    rule: 'Por columnas se multiplica ×2; por filas se suma +3 al segundo término.',
    grid: [
      ['4', '7', '14'],
      ['8', '11', '22'],
      ['16', '19', '?'],
    ],
    options: ['38', '32', '29', '42'],
    answer: 0,
  },
];

const STROOP_COLORS = [
  { name: 'ROJO', hex: '#C94A38' },
  { name: 'VERDE', hex: '#2E6F40' },
  { name: 'AZUL', hex: '#2B5B84' },
  { name: 'ÁMBAR', hex: '#B47626' },
];

const DSST_MAP = [
  { digit: 1, sym: '⊕' },
  { digit: 2, sym: '⊗' },
  { digit: 3, sym: '⊥' },
  { digit: 4, sym: '∆' },
  { digit: 5, sym: '◊' },
  { digit: 6, sym: '≡' },
  { digit: 7, sym: '∩' },
  { digit: 8, sym: '∨' },
  { digit: 9, sym: '⊂' },
];

export function HealthPage() {
  const [tab, setTab] = useState<TabId>('overview');
  const [hub, setHub] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Coach AI state
  const [coachInput, setCoachInput] = useState('');
  const [coachBusy, setCoachBusy] = useState(false);

  // Nutrition AI state
  const [mealInput, setMealInput] = useState('');
  const [mealBusy, setMealBusy] = useState(false);

  // Vitals / Clinical quick log state
  const [hrInput, setHrInput] = useState('53');
  const [hrvInput, setHrvInput] = useState('68');
  const [sleepInput, setSleepInput] = useState('7.8');
  const [moodInput, setMoodInput] = useState('Enfocado y con energía');
  const [phqScore, setPhqScore] = useState(2);
  const [gadScore, setGadScore] = useState(2);
  const [labMarker, setLabMarker] = useState('');
  const [labValue, setLabValue] = useState('');

  // Harvard / PNAS Cognitive Gym state
  const [game, setGame] = useState<GymGame>('none');

  // 1) Dual N-Back state
  const [nLevel, setNLevel] = useState(2);
  const [nBackStep, setNBackStep] = useState(0);
  const [nBackHistory, setNBackHistory] = useState<{ pos: number; let: string }[]>([]);
  const [nBackCurrent, setNBackCurrent] = useState<{ pos: number; let: string } | null>(null);
  const [nBackHits, setNBackHits] = useState(0);
  const [nBackTotal, setNBackTotal] = useState(0);
  const [nBackPressed, setNBackPressed] = useState<{ pos: boolean; let: boolean }>({ pos: false, let: false });
  const nBackTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // 2) Raven Matrices state
  const [ravenIdx, setRavenIdx] = useState(0);
  const [ravenCorrect, setRavenCorrect] = useState(0);

  // 3) UFOV Double Decision state
  const [ufovRound, setUfovRound] = useState(0);
  const [ufovPhase, setUfovPhase] = useState<'flash' | 'ask'>('flash');
  const [ufovTarget, setUfovTarget] = useState<{ center: string; sector: number }>({ center: '▲', sector: 2 });
  const [ufovScore, setUfovScore] = useState(0);

  // 4) Stroop & Task Switching state
  const [stroopRound, setStroopRound] = useState(0);
  const [stroopScore, setStroopScore] = useState(0);
  const [stroopTrial, setStroopTrial] = useState<{ rule: 'COLOR' | 'PALABRA'; wordIdx: number; inkIdx: number }>({
    rule: 'COLOR',
    wordIdx: 0,
    inkIdx: 1,
  });

  // 5) DSST Control Test state
  const [dsstTarget, setDsstTarget] = useState<number>(3);
  const [dsstCount, setDsstCount] = useState(0);
  const [dsstRound, setDsstRound] = useState(0);

  const loadHub = useCallback(async () => {
    try {
      const res = await apiFetch('/v1/desktop/health');
      if (res.ok) {
        const data = await res.json();
        if (data.hub) {
          setHub(data.hub);
          setNLevel(data.hub.gym?.n_back_level || 2);
        }
      }
    } catch {
      // Offline resilient
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHub();
    const onRefresh = () => void loadHub();
    window.addEventListener('sergio:health-refresh', onRefresh);
    return () => window.removeEventListener('sergio:health-refresh', onRefresh);
  }, [loadHub]);

  const askCoach = async (customMsg?: string) => {
    const msg = (customMsg ?? coachInput).trim();
    if (!msg || coachBusy) return;
    setCoachBusy(true);
    if (!customMsg) setCoachInput('');
    try {
      const res = await apiFetch('/v1/desktop/health/coach-ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.hub) setHub(data.hub);
        toast.success('Coach IA actualizó su plan y recomendación.');
      }
    } finally {
      setCoachBusy(false);
    }
  };

  const logNutritionAI = async () => {
    if (!mealInput.trim() || mealBusy) return;
    setMealBusy(true);
    try {
      const res = await apiFetch('/v1/desktop/health/nutrition-ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: mealInput.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.hub) setHub(data.hub);
        setMealInput('');
        toast.success(`Comida registrada: +${data.meal?.kcal} kcal (${data.meal?.protein_g}g proteína)`);
      }
    } finally {
      setMealBusy(false);
    }
  };

  const logCategory = async (category: string, payload: Record<string, any>, successMsg = 'Datos actualizados') => {
    const res = await apiFetch('/v1/desktop/health/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category, payload }),
    });
    if (res.ok) {
      const data = await res.json();
      if (data.hub) setHub(data.hub);
      toast.success(successMsg);
    }
  };

  const syncConnector = async (connector_id: string) => {
    const res = await apiFetch('/v1/desktop/health/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ connector_id }),
    });
    if (res.ok) {
      const data = await res.json();
      if (data.hub) setHub(data.hub);
      toast.success(`Conector ${connector_id} sincronizado (+20 XP).`);
    }
  };

  const finishGymSession = useCallback(
    async (exercise: string, score: number, level = 2) => {
      if (nBackTimer.current) {
        clearInterval(nBackTimer.current);
        nBackTimer.current = null;
      }
      setGame('none');
      const res = await apiFetch('/v1/desktop/health/gym-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exercise, score: Math.max(10, Math.min(100, Math.round(score))), level, duration_sec: 120 }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.hub) setHub(data.hub);
        toast.success(`Sesión completada (${Math.round(score)}%). Índice Cognitivo Gf: ${data.gym?.cognitive_index}`);
      }
    },
    [],
  );

  // -- Dual N-Back Engine (Jaeggi et al., PNAS) --
  const startDualNBack = () => {
    setGame('dual_nback');
    setNBackStep(0);
    setNBackHits(0);
    setNBackTotal(0);
    const seq: { pos: number; let: string }[] = [];
    for (let i = 0; i < 14; i++) {
      let pos = Math.floor(Math.random() * 9);
      let ch = LETTERS[Math.floor(Math.random() * LETTERS.length)];
      if (i >= nLevel && Math.random() < 0.38) pos = seq[i - nLevel].pos;
      if (i >= nLevel && Math.random() < 0.38) ch = seq[i - nLevel].let;
      seq.push({ pos, let: ch });
    }
    setNBackHistory(seq);
    setNBackCurrent(seq[0]);
    setNBackPressed({ pos: false, let: false });
    try {
      window.speechSynthesis?.speak(new SpeechSynthesisUtterance(seq[0].let));
    } catch {}
    let idx = 0;
    if (nBackTimer.current) clearInterval(nBackTimer.current);
    nBackTimer.current = setInterval(() => {
      idx += 1;
      if (idx >= seq.length) {
        if (nBackTimer.current) clearInterval(nBackTimer.current);
        nBackTimer.current = null;
        return;
      }
      setNBackStep(idx);
      setNBackCurrent(seq[idx]);
      setNBackPressed({ pos: false, let: false });
      try {
        window.speechSynthesis?.speak(new SpeechSynthesisUtterance(seq[idx].let));
      } catch {}
    }, 2400);
  };

  useEffect(() => {
    return () => {
      if (nBackTimer.current) clearInterval(nBackTimer.current);
    };
  }, []);

  const checkNBackMatch = (kind: 'pos' | 'let') => {
    if (nBackStep < nLevel || nBackPressed[kind]) return;
    setNBackPressed((p) => ({ ...p, [kind]: true }));
    const prev = nBackHistory[nBackStep - nLevel];
    const curr = nBackHistory[nBackStep];
    const isMatch = kind === 'pos' ? prev.pos === curr.pos : prev.let === curr.let;
    setNBackTotal((t) => t + 1);
    if (isMatch) {
      setNBackHits((h) => h + 1);
      toast.success(kind === 'pos' ? '¡Coincidencia espacial N-Back correcta!' : '¡Coincidencia auditiva/letra N-Back correcta!');
    } else {
      toast.error('No coincidía con hace N pasos.');
    }
  };

  // -- UFOV Double Decision Engine (Harvard / ACTIVE Trial) --
  const startUfov = () => {
    setGame('ufov_speed');
    setUfovRound(1);
    setUfovScore(0);
    triggerUfovFlash();
  };

  const triggerUfovFlash = () => {
    const center = Math.random() < 0.5 ? '▲' : '◆';
    const sector = Math.floor(Math.random() * 8);
    setUfovTarget({ center, sector });
    setUfovPhase('flash');
    setTimeout(() => {
      setUfovPhase('ask');
    }, 420);
  };

  const answerUfov = (sectorGuess: number) => {
    const hit = sectorGuess === ufovTarget.sector;
    const nextScore = ufovScore + (hit ? 20 : 5);
    setUfovScore(nextScore);
    if (ufovRound >= 5) {
      void finishGymSession('ufov_speed', nextScore, 3);
    } else {
      setUfovRound((r) => r + 1);
      triggerUfovFlash();
    }
  };

  // -- Stroop & Executive Task-Switching Engine --
  const nextStroopTrial = () => {
    const rule = Math.random() < 0.5 ? 'COLOR' : 'PALABRA';
    const wordIdx = Math.floor(Math.random() * STROOP_COLORS.length);
    let inkIdx = Math.floor(Math.random() * STROOP_COLORS.length);
    if (inkIdx === wordIdx) inkIdx = (inkIdx + 1) % STROOP_COLORS.length;
    setStroopTrial({ rule, wordIdx, inkIdx });
  };

  const startStroop = () => {
    setGame('stroop_switch');
    setStroopRound(1);
    setStroopScore(0);
    nextStroopTrial();
  };

  const answerStroop = (choiceIdx: number) => {
    const expected = stroopTrial.rule === 'COLOR' ? stroopTrial.inkIdx : stroopTrial.wordIdx;
    const next = stroopScore + (choiceIdx === expected ? 20 : 0);
    setStroopScore(next);
    if (stroopRound >= 5) {
      void finishGymSession('stroop_switch', Math.max(20, next), 3);
    } else {
      setStroopRound((r) => r + 1);
      nextStroopTrial();
    }
  };

  // -- DSST Digit-Symbol Control Test --
  const startDsst = () => {
    setGame('dsst_control');
    setDsstCount(0);
    setDsstRound(1);
    setDsstTarget(1 + Math.floor(Math.random() * 9));
  };

  const answerDsst = (sym: string) => {
    const expected = DSST_MAP.find((m) => m.digit === dsstTarget)?.sym;
    const nextCount = dsstCount + (sym === expected ? 1 : 0);
    setDsstCount(nextCount);
    if (dsstRound >= 10) {
      void finishGymSession('dsst_control', nextCount * 10, 3);
    } else {
      setDsstRound((r) => r + 1);
      setDsstTarget(1 + Math.floor(Math.random() * 9));
    }
  };

  if (loading || !hub) {
    return (
      <div className="paper-page">
        <div className="paper-page-inner">
          <p className="paper-sub">Cargando Salud & Gimnasio Mental…</p>
        </div>
      </div>
    );
  }

  const r = hub.readiness;
  const heart = hub.heart;
  const sleep = hub.sleep;
  const act = hub.activity;
  const nut = hub.nutrition;
  const gym = hub.gym;
  const gam = hub.gamification;

  const cardStyle: React.CSSProperties = {
    background: '#FAF8F5',
    border: '1px solid #E5E0D8',
    borderRadius: 18,
    padding: 18,
    boxShadow: '0 4px 16px rgba(20, 20, 19, 0.03)',
  };

  const subCardStyle: React.CSSProperties = {
    background: '#F3F0EA',
    border: '1px solid #E5E0D8',
    borderRadius: 14,
    padding: 14,
  };

  return (
    <div className="paper-page">
      <div className="paper-page-inner" style={{ maxWidth: 1080 }}>
        {/* Header with Gamification XP, Streak & Privacy Badge */}
        <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 20 }}>
          <div>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '4px 10px',
                  borderRadius: 999,
                  background: '#F3F0EA',
                  border: '1px solid #E5E0D8',
                  fontSize: 12,
                  fontWeight: 600,
                  color: '#C96442',
                }}
              >
                <HeartPulse size={13} /> Apple Health + Garmin + IA Activa
              </span>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '4px 10px',
                  borderRadius: 999,
                  background: '#E8F3EC',
                  border: '1px solid #B7DEC4',
                  fontSize: 12,
                  fontWeight: 600,
                  color: '#2E6F40',
                }}
              >
                <ShieldCheck size={13} /> Cifrado local E2E
              </span>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '4px 10px',
                  borderRadius: 999,
                  background: '#F3F0EA',
                  border: '1px solid #E5E0D8',
                  fontSize: 12,
                  fontWeight: 700,
                  color: '#141413',
                }}
              >
                <Trophy size={13} style={{ color: '#C96442' }} /> Nivel {gam.level} · {gam.xp} XP · 🔥 {gam.streak_days} días
              </span>
            </div>
            <h1 className="paper-title" style={{ marginBottom: 4 }}>
              Salud & Gimnasio Mental
            </h1>
            <p className="paper-sub" style={{ margin: 0 }}>
              Biometría clínica completa (Apple Health + Garmin Connect), Puntuación de Recuperación por IA, Nutrición Inteligente y Entrenamiento de Inteligencia Fluida (Harvard / PNAS).
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="paper-button"
              data-variant="quiet"
              onClick={() => window.dispatchEvent(new CustomEvent('sergio:sticky-notes-toggle'))}
            >
              Notas Post-it
            </button>
            <button type="button" className="paper-button" onClick={() => setTab('gym')}>
              <Brain size={15} /> Entrenar IQ ({gym.cognitive_index})
            </button>
          </div>
        </header>

        {/* Navigation Tabs */}
        <nav
          aria-label="Secciones de Salud"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 8,
            paddingBottom: 14,
            marginBottom: 20,
            borderBottom: '1px solid #E5E0D8',
          }}
        >
          {(
            [
              { id: 'overview', label: 'Recuperación & Coach IA', icon: Zap },
              { id: 'vitals', label: 'Corazón, Sueño & Vitals', icon: HeartPulse },
              { id: 'nutrition', label: 'Actividad, VO2 & Nutrición IA', icon: Utensils },
              { id: 'gym', label: `Gimnasio Mental Harvard (IQ ${gym.cognitive_index})`, icon: Brain },
              { id: 'clinical', label: 'Mente, Audición, Ciclo & EHR', icon: FileText },
            ] as const
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 7,
                padding: '8px 14px',
                borderRadius: 999,
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                background: tab === id ? '#141413' : '#F3F0EA',
                color: tab === id ? '#FAF8F5' : '#141413',
                border: `1px solid ${tab === id ? '#141413' : '#E5E0D8'}`,
              }}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </nav>

        {/* TAB 1: OVERVIEW, READINESS SCORE, DYNAMIC AI PLAN & LIVE COACH */}
        {tab === 'overview' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
            {/* Readiness Score Card */}
            <section style={cardStyle}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <span style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#C96442' }}>
                  Puntuación de Recuperación IA
                </span>
                <span style={{ fontSize: 12, fontWeight: 600, color: '#2E6F40' }}>Body Battery {r.body_battery}%</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 10 }}>
                <span style={{ fontSize: 52, fontWeight: 800, lineHeight: 1, color: '#141413', fontFamily: 'var(--font-serif, Georgia, serif)' }}>
                  {r.score}%
                </span>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#141413' }}>{r.status}</div>
                  <div style={{ fontSize: 12.5, color: '#6E6B64' }}>
                    VFC {r.hrv_ms} ms (base {r.hrv_baseline_ms} ms) · FC reposo {r.rhr_bpm} lpm · Sueño {r.sleep_score}/100
                  </div>
                </div>
              </div>
              <p style={{ fontSize: 13.5, lineHeight: 1.55, color: '#2C2B28', background: '#F3F0EA', padding: 12, borderRadius: 12, margin: '0 0 14px' }}>
                {r.recommendation}
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Sueño</small>
                  <div style={{ fontSize: 16, fontWeight: 700 }}>{sleep.total_hours} h</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>VO2 máx</small>
                  <div style={{ fontSize: 16, fontWeight: 700 }}>{act.vo2_max}</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Pasos</small>
                  <div style={{ fontSize: 16, fontWeight: 700 }}>{act.steps.toLocaleString('es')}</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>IQ / Gf</small>
                  <div style={{ fontSize: 16, fontWeight: 700, color: '#C96442' }}>{gym.cognitive_index}</div>
                </div>
              </div>
            </section>

            {/* Dynamic AI Workout Plan */}
            <section style={cardStyle}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#2E6F40' }}>
                  Plan Dinámico con IA (Hoy)
                </span>
                <span style={{ fontSize: 12, color: '#6E6B64' }}>
                  {hub.training_plan.today.duration_min} min · {hub.training_plan.today.intensity}
                </span>
              </div>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: '#141413', marginBottom: 4 }}>
                {hub.training_plan.today.title}
              </h2>
              <p style={{ fontSize: 12.5, color: '#6E6B64', marginBottom: 12 }}>{hub.training_plan.adapted_reason}</p>
              <ul style={{ margin: '0 0 14px', paddingLeft: 18, fontSize: 13.5, lineHeight: 1.6, color: '#141413' }}>
                {hub.training_plan.today.blocks.map((b: string, i: number) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                <button
                  type="button"
                  className="paper-button"
                  onClick={() =>
                    logCategory(
                      'activity',
                      {
                        workout_name: hub.training_plan.today.title,
                        duration_min: hub.training_plan.today.duration_min,
                        kcal: 380,
                      },
                      '¡Entrenamiento de hoy completado (+25 XP)!',
                    )
                  }
                >
                  <Check size={14} /> Marcar como completado
                </button>
                <button
                  type="button"
                  className="paper-button"
                  data-variant="quiet"
                  onClick={() => askCoach('Hoy dormí mal y me siento cansado, adapta mi entrenamiento de hoy a recuperación suave.')}
                >
                  <RefreshCw size={14} /> Hoy estoy cansado · Adaptar plan
                </button>
              </div>
            </section>

            {/* Proactive Live AI Health Coach */}
            <section style={{ ...cardStyle, gridColumn: '1 / -1' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Sparkles size={16} style={{ color: '#C96442' }} />
                  <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Coach Biomédico y Deportivo con IA en Tiempo Real</h2>
                </div>
                <span style={{ fontSize: 12, color: '#6E6B64' }}>Conectado a tus métricas de corazón, sueño, nutrición y laboratorio</span>
              </div>
              <div
                style={{
                  maxHeight: 210,
                  overflowY: 'auto',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                  padding: 12,
                  background: '#F3F0EA',
                  borderRadius: 14,
                  marginBottom: 10,
                }}
              >
                {(hub.coach_messages || []).map((m: any, i: number) => (
                  <div
                    key={i}
                    style={{
                      alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                      maxWidth: '85%',
                      padding: '8px 12px',
                      borderRadius: 12,
                      background: m.role === 'user' ? '#141413' : '#FAF8F5',
                      color: m.role === 'user' ? '#FAF8F5' : '#141413',
                      border: '1px solid #E5E0D8',
                      fontSize: 13.5,
                      lineHeight: 1.5,
                    }}
                  >
                    <div>{m.text}</div>
                    <small style={{ fontSize: 10.5, opacity: 0.65 }}>{m.at}</small>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="paper-input"
                  style={{ flex: 1 }}
                  value={coachInput}
                  onChange={(e) => setCoachInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && askCoach()}
                  placeholder="Pregúntale a tu Coach IA: «¿Cómo subo mi VFC?», «¿Qué ceno hoy para recuperar?», «Interpreta mi Vitamina D»…"
                />
                <button type="button" className="paper-button" disabled={coachBusy || !coachInput.trim()} onClick={() => askCoach()}>
                  <Send size={14} /> {coachBusy ? 'Analizando…' : 'Preguntar'}
                </button>
              </div>
            </section>

            {/* Multi-Platform Connectors & Social Gamification */}
            <section style={cardStyle}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 7 }}>
                <Activity size={16} style={{ color: '#C96442' }} /> Conectores Multi-Plataforma (PC · iOS · Android · Garmin)
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {hub.connectors.map((c: any) => (
                  <div
                    key={c.id}
                    style={{
                      ...subCardStyle,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 10,
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 13.5, fontWeight: 700 }}>{c.name}</div>
                      <div style={{ fontSize: 11.5, color: '#6E6B64' }}>{c.metrics}</div>
                      <small style={{ fontSize: 11, color: '#2E6F40', fontWeight: 600 }}>{c.last_sync}</small>
                    </div>
                    <button type="button" className="paper-button" data-variant="quiet" onClick={() => syncConnector(c.id)}>
                      <RefreshCw size={13} /> Sincronizar
                    </button>
                  </div>
                ))}
              </div>
            </section>

            {/* Social Challenges & Unlockable Medals */}
            <section style={cardStyle}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 7 }}>
                <Users size={16} style={{ color: '#C96442' }} /> Retos Comunitarios & Medallas Desbloqueables
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
                {gam.challenges.map((ch: any) => (
                  <div key={ch.id} style={subCardStyle}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 700 }}>
                      <span>{ch.name}</span>
                      <span style={{ color: '#C96442' }}>Puesto #{ch.your_rank} de {ch.participants}</span>
                    </div>
                    <div style={{ height: 6, background: '#E5E0D8', borderRadius: 999, margin: '6px 0', overflow: 'hidden' }}>
                      <div style={{ width: `${ch.progress_pct}%`, height: '100%', background: '#2E6F40' }} />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11.5, color: '#6E6B64' }}>
                      <span>Progreso grupal: {ch.progress_pct}%</span>
                      <button
                        type="button"
                        onClick={() => logCategory('challenge', { id: ch.id }, 'Progreso de reto compartido actualizado')}
                        style={{ background: 'transparent', border: 'none', color: '#C96442', fontWeight: 700, cursor: 'pointer' }}
                      >
                        + Impulsar reto
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
                {gam.medals.map((m: any) => (
                  <div
                    key={m.id}
                    style={{
                      ...subCardStyle,
                      opacity: m.unlocked ? 1 : 0.55,
                      borderColor: m.unlocked ? '#C96442' : '#E5E0D8',
                    }}
                  >
                    <div style={{ fontSize: 12.5, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}>
                      <Award size={14} style={{ color: m.unlocked ? '#C96442' : '#6E6B64' }} /> {m.name}
                    </div>
                    <div style={{ fontSize: 11, color: '#6E6B64', marginTop: 2 }}>{m.desc}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {/* TAB 2: HEART, SLEEP & VITALS (APPLE HEALTH PILLARS 1 & 2) */}
        {tab === 'vitals' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
            <section style={cardStyle}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                <HeartPulse size={17} style={{ color: '#C96442' }} /> Salud del Corazón (ECG · AFib · Presión · VFC)
              </h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginBottom: 12 }}>
                <div style={subCardStyle}>
                  <small style={{ color: '#6E6B64', fontSize: 11.5 }}>FC en Reposo / Actual</small>
                  <div style={{ fontSize: 22, fontWeight: 800 }}>{heart.resting_hr} lpm <span style={{ fontSize: 13, fontWeight: 500 }}>({heart.current_hr} actual)</span></div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ color: '#6E6B64', fontSize: 11.5 }}>Variabilidad (VFC / HRV)</small>
                  <div style={{ fontSize: 22, fontWeight: 800, color: '#2E6F40' }}>{heart.hrv_ms} ms</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ color: '#6E6B64', fontSize: 11.5 }}>Presión Arterial</small>
                  <div style={{ fontSize: 20, fontWeight: 800 }}>{heart.bp_systolic}/{heart.bp_diastolic} mmHg</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ color: '#6E6B64', fontSize: 11.5 }}>Historial AFib / Ritmo</small>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#2E6F40' }}>0% Carga FA · Normal</div>
                </div>
              </div>
              <div style={{ ...subCardStyle, marginBottom: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#141413' }}>Último Electrocardiograma (ECG Derivación I)</div>
                <div style={{ fontSize: 13, color: '#2E6F40', fontWeight: 600 }}>{heart.ecg_last}</div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  className="paper-input"
                  style={{ width: 95 }}
                  value={hrInput}
                  onChange={(e) => setHrInput(e.target.value)}
                  placeholder="FC rep"
                  title="Frecuencia cardíaca en reposo"
                />
                <input
                  className="paper-input"
                  style={{ width: 95 }}
                  value={hrvInput}
                  onChange={(e) => setHrvInput(e.target.value)}
                  placeholder="VFC ms"
                  title="VFC en milisegundos"
                />
                <button
                  type="button"
                  className="paper-button"
                  onClick={() =>
                    logCategory(
                      'vitals',
                      { resting_hr: Number(hrInput) || 53, hrv_ms: Number(hrvInput) || 68 },
                      'Métricas cardíacas y Recuperación recalculadas.',
                    )
                  }
                >
                  Actualizar Corazón
                </button>
              </div>
            </section>

            <section style={cardStyle}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Moon size={17} style={{ color: '#C96442' }} /> Sueño & Vitals Nocturnos (REM · Profundo · Apnea)
              </h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 12 }}>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Sueño Total</small>
                  <div style={{ fontSize: 20, fontWeight: 800 }}>{sleep.total_hours} h</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Profundo (SWS)</small>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#2E6F40' }}>{sleep.deep_hours} h</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Fase REM</small>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#C96442' }}>{sleep.rem_hours} h</div>
                </div>
              </div>
              <div style={{ ...subCardStyle, marginBottom: 12, fontSize: 13, lineHeight: 1.6 }}>
                <div><b>Riesgo de Apnea del Sueño:</b> {sleep.apnea_risk}</div>
                <div><b>Frecuencia Respiratoria Nocturna:</b> {sleep.respiratory_rate_rpm} rpm · <b>SpO2:</b> {sleep.spo2_pct}%</div>
                <div><b>Variación de Temperatura en Muñeca:</b> {sleep.wrist_temp_delta_c > 0 ? `+${sleep.wrist_temp_delta_c}` : sleep.wrist_temp_delta_c} °C</div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  className="paper-input"
                  style={{ width: 110 }}
                  value={sleepInput}
                  onChange={(e) => setSleepInput(e.target.value)}
                  placeholder="Horas sueño"
                />
                <button
                  type="button"
                  className="paper-button"
                  onClick={() =>
                    logCategory(
                      'sleep',
                      { total_hours: Number(sleepInput) || 7.8 },
                      'Sueño registrado y Puntuación de Recuperación actualizada.',
                    )
                  }
                >
                  Registrar Noche
                </button>
              </div>
            </section>
          </div>
        )}

        {/* TAB 3: PHYSICAL ACTIVITY, VO2 MAX & AI NUTRITION TRACKER */}
        {tab === 'nutrition' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
            <section style={cardStyle}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Utensils size={17} style={{ color: '#C96442' }} /> Escáner Nutricional con IA & Macros
              </h2>
              <p style={{ fontSize: 12.5, color: '#6E6B64', marginBottom: 10 }}>
                Describe tu comida y Sergio calcula al instante calorías, proteínas, carbohidratos, grasas y su impacto neuro-metabólico.
              </p>
              <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
                <input
                  className="paper-input"
                  style={{ flex: 1 }}
                  value={mealInput}
                  onChange={(e) => setMealInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && logNutritionAI()}
                  placeholder="Ej: Pechuga de pollo a la plancha con arroz, aguacate y dos huevos…"
                />
                <button type="button" className="paper-button" disabled={mealBusy || !mealInput.trim()} onClick={logNutritionAI}>
                  {mealBusy ? 'Calculando…' : '+ Analizar IA'}
                </button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 14 }}>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Calorías</small>
                  <div style={{ fontSize: 15, fontWeight: 800 }}>{nut.kcal_consumed} / {nut.kcal_target}</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Proteína</small>
                  <div style={{ fontSize: 15, fontWeight: 800, color: '#2E6F40' }}>{nut.protein_g}g / {nut.protein_target_g}g</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Carbos</small>
                  <div style={{ fontSize: 15, fontWeight: 800 }}>{nut.carbs_g}g / {nut.carbs_target_g}g</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Grasas</small>
                  <div style={{ fontSize: 15, fontWeight: 800 }}>{nut.fat_g}g / {nut.fat_target_g}g</div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', ...subCardStyle, marginBottom: 12 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13.5, fontWeight: 700 }}>
                  <Droplets size={16} style={{ color: '#2B5B84' }} /> Hidratación: {nut.water_ml} / {nut.water_target_ml} mL
                </span>
                <button
                  type="button"
                  className="paper-button"
                  data-variant="quiet"
                  onClick={() => logCategory('water', { add_ml: 250 }, '+250 mL de agua registrados')}
                >
                  + 250 mL Agua
                </button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {nut.meals.slice(0, 4).map((m: any) => (
                  <div key={m.id} style={subCardStyle}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 700 }}>
                      <span>{m.name}</span>
                      <span style={{ color: '#C96442' }}>{m.kcal} kcal</span>
                    </div>
                    <div style={{ fontSize: 11.5, color: '#6E6B64' }}>
                      Proteína {m.protein_g}g · Carbos {m.carbs_g}g · Grasas {m.fat_g}g · {m.time}
                    </div>
                    {m.ai_insight && <div style={{ fontSize: 11.5, color: '#2E6F40', marginTop: 3 }}>IA: {m.ai_insight}</div>}
                  </div>
                ))}
              </div>
            </section>

            <section style={cardStyle}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Flame size={17} style={{ color: '#C96442' }} /> Actividad Física & Condición VO2 Máx (HealthKit)
              </h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginBottom: 12 }}>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Pasos Hoy</small>
                  <div style={{ fontSize: 22, fontWeight: 800 }}>{act.steps.toLocaleString('es')} <span style={{ fontSize: 12, fontWeight: 500 }}>/ {act.steps_goal.toLocaleString('es')}</span></div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>VO2 Máx (Cardio Fitness)</small>
                  <div style={{ fontSize: 22, fontWeight: 800, color: '#2E6F40' }}>{act.vo2_max} <span style={{ fontSize: 11 }}>mL/kg/min</span></div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Distancia & Pisos</small>
                  <div style={{ fontSize: 17, fontWeight: 700 }}>{act.distance_km} km · {act.flights_climbed} pisos</div>
                </div>
                <div style={subCardStyle}>
                  <small style={{ fontSize: 11, color: '#6E6B64' }}>Calorías Activas</small>
                  <div style={{ fontSize: 17, fontWeight: 700, color: '#C96442' }}>{act.active_kcal} kcal</div>
                </div>
              </div>
              <h3 style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 8 }}>Entrenamientos Sincronizados</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {act.workouts.map((w: any) => (
                  <div key={w.id} style={subCardStyle}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 700 }}>
                      <span>{w.name}</span>
                      <span>{w.duration_min} min · {w.kcal} kcal</span>
                    </div>
                    <small style={{ fontSize: 11.5, color: '#6E6B64' }}>
                      FC media {w.avg_hr} lpm · {w.source} · {w.when}
                    </small>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {/* TAB 4: HARVARD / PNAS COGNITIVE GYM (REAL FLUID INTELLIGENCE Gf & IQ TRAINING) */}
        {tab === 'gym' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <section style={cardStyle}>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
                <div>
                  <span style={{ fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#C96442' }}>
                    Neurociencia Cognitiva Aplicada · Harvard / PNAS / Estudio ACTIVE
                  </span>
                  <h2 style={{ fontSize: 20, fontWeight: 800, margin: '2px 0' }}>
                    Gimnasio Mental de Transferencia a Inteligencia Fluida (Gf)
                  </h2>
                  <p style={{ fontSize: 13, color: '#6E6B64', margin: 0 }}>
                    Diseñado sobre los 4 paradigmas con evidencia revisada por pares para incrementar la capacidad de la memoria de trabajo dorsolateral, inducción relacional y velocidad de procesamiento.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', background: '#F3F0EA', padding: '10px 16px', borderRadius: 16, border: '1px solid #E5E0D8' }}>
                  <div>
                    <small style={{ fontSize: 11, color: '#6E6B64', display: 'block' }}>Índice Cognitivo Gf</small>
                    <b style={{ fontSize: 26, color: '#141413', fontFamily: 'var(--font-serif, Georgia, serif)' }}>{gym.cognitive_index}</b>
                  </div>
                  <div style={{ borderLeft: '1px solid #D8D2C7', paddingLeft: 12 }}>
                    <small style={{ fontSize: 11, color: '#6E6B64', display: 'block' }}>Percentil</small>
                    <b style={{ fontSize: 18, color: '#2E6F40' }}>{gym.gf_percentile}º</b>
                  </div>
                  <div style={{ borderLeft: '1px solid #D8D2C7', paddingLeft: 12 }}>
                    <small style={{ fontSize: 11, color: '#6E6B64', display: 'block' }}>Nivel N-Back</small>
                    <b style={{ fontSize: 18, color: '#C96442' }}>{nLevel}-Back</b>
                  </div>
                </div>
              </div>

              {/* Active Game Stage */}
              {game === 'dual_nback' && (
                <div style={{ ...subCardStyle, padding: 20, marginBottom: 16, textAlign: 'center' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <b style={{ fontSize: 15 }}>Dual {nLevel}-Back Adaptativo (Jaeggi et al., PNAS) — Paso {nBackStep + 1}/14</b>
                    <button
                      type="button"
                      className="paper-button"
                      data-variant="quiet"
                      onClick={() => finishGymSession('dual_nback', Math.min(100, 65 + nBackHits * 15), nLevel)}
                    >
                      Terminar y guardar
                    </button>
                  </div>
                  <p style={{ fontSize: 12.5, color: '#6E6B64', marginBottom: 14 }}>
                    Pulse <b>Posición igual</b> si el cuadro iluminado coincide con el de hace <b>{nLevel}</b> pasos, o <b>Letra igual</b> si la letra hablada coincide con la de hace <b>{nLevel}</b> pasos.
                  </p>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 76px)',
                      gridTemplateRows: 'repeat(3, 76px)',
                      gap: 8,
                      justifyContent: 'center',
                      margin: '0 auto 14px',
                    }}
                  >
                    {Array.from({ length: 9 }, (_, idx) => {
                      const active = nBackCurrent?.pos === idx;
                      return (
                        <div
                          key={idx}
                          style={{
                            borderRadius: 14,
                            background: active ? '#C96442' : '#FAF8F5',
                            border: `2px solid ${active ? '#C96442' : '#D8D2C7'}`,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: 24,
                            fontWeight: 800,
                            color: active ? '#FAF8F5' : 'transparent',
                            transition: 'all 0.15s ease',
                          }}
                        >
                          {active ? nBackCurrent?.let : ''}
                        </div>
                      );
                    })}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'center', gap: 12 }}>
                    <button type="button" className="paper-button" onClick={() => checkNBackMatch('pos')}>
                      Posición igual ({nLevel}-Back)
                    </button>
                    <button type="button" className="paper-button" onClick={() => checkNBackMatch('let')}>
                      Letra «{nBackCurrent?.let}» igual ({nLevel}-Back)
                    </button>
                  </div>
                </div>
              )}

              {game === 'raven_matrices' && (
                <div style={{ ...subCardStyle, padding: 20, marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                    <b>{RAVEN_PUZZLES[ravenIdx].q}</b>
                    <span>Reto {ravenIdx + 1} de {RAVEN_PUZZLES.length}</span>
                  </div>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 1fr)',
                      gap: 8,
                      maxWidth: 420,
                      margin: '12px auto',
                    }}
                  >
                    {RAVEN_PUZZLES[ravenIdx].grid.flat().map((cell, i) => (
                      <div
                        key={i}
                        style={{
                          padding: '16px 10px',
                          textAlign: 'center',
                          borderRadius: 12,
                          background: cell === '?' ? '#141413' : '#FAF8F5',
                          color: cell === '?' ? '#FAF8F5' : '#141413',
                          border: '1px solid #D8D2C7',
                          fontWeight: 700,
                          fontSize: 15,
                        }}
                      >
                        {cell}
                      </div>
                    ))}
                  </div>
                  <p style={{ fontSize: 12, color: '#6E6B64', textAlign: 'center', marginBottom: 10 }}>
                    Pista estructural: {RAVEN_PUZZLES[ravenIdx].rule}
                  </p>
                  <div style={{ display: 'flex', justifyContent: 'center', gap: 10, flexWrap: 'wrap' }}>
                    {RAVEN_PUZZLES[ravenIdx].options.map((opt, idx) => (
                      <button
                        key={idx}
                        type="button"
                        className="paper-button"
                        onClick={() => {
                          const ok = idx === RAVEN_PUZZLES[ravenIdx].answer;
                          const nextCorrect = ravenCorrect + (ok ? 1 : 0);
                          setRavenCorrect(nextCorrect);
                          if (ok) toast.success('¡Inducción relacional correcta!');
                          else toast.error('Respuesta incorrecta.');
                          if (ravenIdx + 1 >= RAVEN_PUZZLES.length) {
                            void finishGymSession('raven_matrices', Math.round((nextCorrect / RAVEN_PUZZLES.length) * 100), 4);
                          } else {
                            setRavenIdx(ravenIdx + 1);
                          }
                        }}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {game === 'ufov_speed' && (
                <div style={{ ...subCardStyle, padding: 20, marginBottom: 16, textAlign: 'center' }}>
                  <b style={{ display: 'block', marginBottom: 8 }}>
                    UFOV Doble Decisión (Harvard / Estudio ACTIVE) — Ronda {ufovRound}/5
                  </b>
                  {ufovPhase === 'flash' ? (
                    <div style={{ padding: 28, fontSize: 18, fontWeight: 700 }}>
                      Símbolo central: <span style={{ fontSize: 28, color: '#C96442' }}>{ufovTarget.center}</span> · Estímulo periférico en sector #{ufovTarget.sector + 1}
                    </div>
                  ) : (
                    <div>
                      <p style={{ fontSize: 13, color: '#6E6B64', marginBottom: 10 }}>
                        ¿En qué sector periférico (1–8) apareció el destello simultáneo?
                      </p>
                      <div style={{ display: 'flex', justifyContent: 'center', gap: 8, flexWrap: 'wrap' }}>
                        {Array.from({ length: 8 }, (_, s) => (
                          <button key={s} type="button" className="paper-button" onClick={() => answerUfov(s)}>
                            Sector {s + 1}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {game === 'stroop_switch' && (
                <div style={{ ...subCardStyle, padding: 20, marginBottom: 16, textAlign: 'center' }}>
                  <b style={{ display: 'block', marginBottom: 6 }}>
                    Alternancia Ejecutiva & Control Inhibitorio (Karbach & Kray / Harvard) — Ronda {stroopRound}/5
                  </b>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#C96442', marginBottom: 10 }}>
                    REGLA ACTIVA AHORA: Responda según {stroopTrial.rule === 'COLOR' ? 'el COLOR DE LA TINTA (ignore la palabra)' : 'el SIGNIFICADO DE LA PALABRA (ignore la tinta)'}
                  </div>
                  <div
                    style={{
                      fontSize: 36,
                      fontWeight: 900,
                      color: STROOP_COLORS[stroopTrial.inkIdx].hex,
                      margin: '14px 0',
                    }}
                  >
                    {STROOP_COLORS[stroopTrial.wordIdx].name}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'center', gap: 10 }}>
                    {STROOP_COLORS.map((c, idx) => (
                      <button key={c.name} type="button" className="paper-button" onClick={() => answerStroop(idx)}>
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {game === 'dsst_control' && (
                <div style={{ ...subCardStyle, padding: 20, marginBottom: 16, textAlign: 'center' }}>
                  <b style={{ display: 'block', marginBottom: 8 }}>
                    Prueba de Control WAIS Digit-Symbol (DSST) — Ítem {dsstRound}/10
                  </b>
                  <div style={{ display: 'flex', justifyContent: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
                    {DSST_MAP.map((m) => (
                      <div key={m.digit} style={{ background: '#FAF8F5', border: '1px solid #D8D2C7', borderRadius: 8, padding: '4px 10px', fontSize: 13 }}>
                        <b>{m.digit}</b> → {m.sym}
                      </div>
                    ))}
                  </div>
                  <div style={{ fontSize: 26, fontWeight: 800, marginBottom: 12 }}>
                    Dígito objetivo: <span style={{ color: '#C96442' }}>{dsstTarget}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'center', gap: 8, flexWrap: 'wrap' }}>
                    {DSST_MAP.map((m) => (
                      <button key={m.sym} type="button" className="paper-button" onClick={() => answerDsst(m.sym)}>
                        {m.sym}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Scientific Exercise Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: 12 }}>
                {gym.scientific_pillars.map((p: any) => (
                  <div key={p.id} style={subCardStyle}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <b style={{ fontSize: 14, color: '#141413' }}>{p.name}</b>
                      <span style={{ fontSize: 11.5, fontWeight: 700, color: '#2E6F40' }}>{p.best_level}</span>
                    </div>
                    <div style={{ fontSize: 11.5, fontWeight: 600, color: '#C96442', marginBottom: 6 }}>{p.study}</div>
                    <p style={{ fontSize: 12.5, color: '#6E6B64', margin: '0 0 10px', lineHeight: 1.45 }}>{p.mechanism}</p>
                    <button
                      type="button"
                      className="paper-button"
                      onClick={() => {
                        if (p.id === 'dual_nback') startDualNBack();
                        else if (p.id === 'raven_matrices') {
                          setRavenIdx(0);
                          setRavenCorrect(0);
                          setGame('raven_matrices');
                        } else if (p.id === 'ufov_speed') startUfov();
                        else if (p.id === 'stroop_switch') startStroop();
                        else startDsst();
                      }}
                    >
                      <Play size={13} /> Iniciar entrenamiento
                    </button>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {/* TAB 5: MENTAL HEALTH (PHQ-9/GAD-7), HEARING/VISION, CYCLE & CLINICAL EHR */}
        {tab === 'clinical' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
            {/* Mental Health & Standardized PHQ-9 / GAD-7 */}
            <section style={cardStyle}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>
                Salud Mental y Emocional (Estado de Ánimo · PHQ-9 · GAD-7)
              </h2>
              <div style={{ ...subCardStyle, marginBottom: 10 }}>
                <div><b>Estado actual:</b> {hub.mental.mood_today}</div>
                <div style={{ fontSize: 12.5, color: '#2E6F40' }}><b>PHQ-9 (Estado de ánimo):</b> {hub.mental.phq9_interpretation}</div>
                <div style={{ fontSize: 12.5, color: '#2E6F40' }}><b>GAD-7 (Ansiedad):</b> {hub.mental.gad7_interpretation}</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <input
                  className="paper-input"
                  value={moodInput}
                  onChange={(e) => setMoodInput(e.target.value)}
                  placeholder="¿Cómo se siente hoy? Reflexión guiada…"
                />
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12 }}>
                  <label>PHQ-9 (0-27): <input type="number" min={0} max={27} value={phqScore} onChange={(e) => setPhqScore(Number(e.target.value))} style={{ width: 48 }} /></label>
                  <label>GAD-7 (0-21): <input type="number" min={0} max={21} value={gadScore} onChange={(e) => setGadScore(Number(e.target.value))} style={{ width: 48 }} /></label>
                  <button
                    type="button"
                    className="paper-button"
                    onClick={() =>
                      logCategory(
                        'mental',
                        { mood: moodInput, phq9_score: phqScore, gad7_score: gadScore, note: moodInput },
                        'Evaluación emocional y cuestionarios PHQ-9/GAD-7 guardados.',
                      )
                    }
                  >
                    Guardar
                  </button>
                </div>
              </div>
            </section>

            {/* Hearing, Noise & Daylight Exposure */}
            <section style={cardStyle}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 7 }}>
                <Ear size={16} style={{ color: '#C96442' }} /> Salud Auditiva y Visual (Ruido dB · Audiometría · Luz Solar)
              </h2>
              <div style={{ ...subCardStyle, marginBottom: 10, fontSize: 13, lineHeight: 1.6 }}>
                <div><b>Ruido Ambiental:</b> {hub.sensory.ambient_db} dB — <span style={{ color: '#2E6F40', fontWeight: 600 }}>{hub.sensory.noise_status}</span></div>
                <div><b>Nivel en Auriculares:</b> {hub.sensory.headphone_db} dB</div>
                <div><b>Prueba Clínica de Audición:</b> Oído Izq {hub.sensory.hearing_test_left_dbhl} dB HL · Der {hub.sensory.hearing_test_right_dbhl} dB HL ({hub.sensory.hearing_grade})</div>
                <div><b>Tiempo Expuesto a Luz del Día:</b> {hub.sensory.daylight_minutes} / {hub.sensory.daylight_goal} min (protección miopía y ritmo circadiano)</div>
              </div>
              <button
                type="button"
                className="paper-button"
                data-variant="quiet"
                onClick={() => logCategory('sensory', { daylight_minutes: hub.sensory.daylight_minutes + 15 }, '+15 min de luz natural registrados')}
              >
                + 15 min Exposición a Luz del Día
              </button>
            </section>

            {/* Cycle, Fertility & Basal Temperature */}
            <section style={cardStyle}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>
                Seguimiento de Ciclo, Fertilidad Térmica y Embarazo
              </h2>
              <div style={{ ...subCardStyle, fontSize: 13, lineHeight: 1.6 }}>
                <div><b>Fase / Estado:</b> {hub.cycle.phase}</div>
                <div><b>Temperatura Basal:</b> {hub.cycle.basal_temp_c} °C ({hub.cycle.fertility_window})</div>
                <div><b>Síntomas registrados:</b> {(hub.cycle.symptoms || []).join(' · ')}</div>
              </div>
            </section>

            {/* Clinical EHR & Lab Records */}
            <section style={cardStyle}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>
                Logística Médica Unificada (EHR · Alergias · Vacunas · Analíticas IA)
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
                {hub.ehr.labs.map((l: any, i: number) => (
                  <div key={i} style={subCardStyle}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 700 }}>
                      <span>{l.marker}: {l.value}</span>
                      <span style={{ color: '#2E6F40' }}>{l.status} ({l.range})</span>
                    </div>
                    <div style={{ fontSize: 11.5, color: '#6E6B64', marginTop: 2 }}>{l.ai_note}</div>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <input
                  className="paper-input"
                  placeholder="Biomarcador (ej. Magnesio)"
                  value={labMarker}
                  onChange={(e) => setLabMarker(e.target.value)}
                />
                <input
                  className="paper-input"
                  placeholder="Valor (ej. 2.2 mg/dL)"
                  value={labValue}
                  onChange={(e) => setLabValue(e.target.value)}
                />
                <button
                  type="button"
                  className="paper-button"
                  onClick={() => {
                    if (!labMarker.trim()) return;
                    void logCategory('ehr', { marker: labMarker, value: labValue }, 'Resultado clínico añadido al EHR.');
                    setLabMarker('');
                    setLabValue('');
                  }}
                >
                  Añadir
                </button>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

export default HealthPage;
