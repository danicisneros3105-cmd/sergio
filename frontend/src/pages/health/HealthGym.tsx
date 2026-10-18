import { useCallback, useEffect, useRef, useState } from 'react';
import { Brain, Play } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { suspendLive } from '../../lib/liveSession';
import { speakLetter } from '../../lib/letterVoice';
import { Credits } from './Credits';

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
    q: 'Matriz Relacional 1 (Progresión + Rotación simultánea)',
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
  { name: 'VERDE', hex: 'var(--color-text)' },
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

export function HealthGym({ hub, setHub }: { hub: any; setHub: (hub: any) => void }) {
  const gym = hub.gym;

  // PNAS Cognitive Gym state
  const [game, setGame] = useState<GymGame>('none');
  // While an exercise is on, the always-on microphone must not hear its letters and answer them.
  useEffect(() => {
    if (game === 'none') return;
    suspendLive(true);
    return () => suspendLive(false);
  }, [game]);

  // 1) Dual N-Back state
  const [nLevel, setNLevel] = useState<number>(hub.gym?.n_back_level || 2);
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
        toast.success(`Sesión guardada: ${Math.round(score)} %.`);
      }
    },
    [],
  );

  // -- Dual N-Back Engine --
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
    speakLetter(seq[0].let);
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
      speakLetter(seq[idx].let);
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

  // -- UFOV Double Decision Engine --
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

  const cardStyle: React.CSSProperties = {
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    borderRadius: 14,
    padding: 18,
  };

  const subCardStyle: React.CSSProperties = {
    background: 'var(--color-hover)',
    border: '1px solid var(--color-border)',
    borderRadius: 12,
    padding: 14,
  };

  return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <section style={cardStyle}>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
                <h2 style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>Cinco ejercicios cortos</h2>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', background: 'var(--color-hover)', padding: '10px 16px', borderRadius: 16, border: '1px solid var(--color-border)' }}>
                  <div>
                    <small style={{ fontSize: 11, color: 'var(--color-text-tertiary)', display: 'block' }}>Sesiones</small>
                    <b style={{ fontSize: 22, color: 'var(--color-text)' }}>{gym.sessions_completed || 0}</b>
                  </div>
                  <div style={{ borderLeft: '1px solid var(--color-border)', paddingLeft: 12 }}>
                    <small style={{ fontSize: 11, color: 'var(--color-text-tertiary)', display: 'block' }}>Nivel N-Back</small>
                    <b style={{ fontSize: 18, color: 'var(--color-text)' }}>{gym.sessions_completed ? `${nLevel}-Back` : '—'}</b>
                  </div>
                </div>
              </div>

              {/* Active Game Stage */}
              {game === 'dual_nback' && (
                <div style={{ ...subCardStyle, padding: 20, marginBottom: 16, textAlign: 'center' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <b style={{ fontSize: 15 }}>Dual {nLevel}-Back Adaptativo — Paso {nBackStep + 1}/14</b>
                    <button
                      type="button"
                      className="paper-button"
                      data-variant="quiet"
                      onClick={() => finishGymSession('dual_nback', Math.min(100, 65 + nBackHits * 15), nLevel)}
                    >
                      Terminar y guardar
                    </button>
                  </div>
                  <p style={{ fontSize: 12.5, color: 'var(--color-text-tertiary)', marginBottom: 14 }}>
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
                            background: active ? 'var(--color-text)' : 'var(--color-surface)',
                            border: `2px solid ${active ? 'var(--color-text)' : 'var(--color-border)'}`,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: 24,
                            fontWeight: 800,
                            color: active ? 'var(--color-surface)' : 'transparent',
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
                          background: cell === '?' ? 'var(--color-text)' : 'var(--color-surface)',
                          color: cell === '?' ? 'var(--color-surface)' : 'var(--color-text)',
                          border: '1px solid var(--color-border)',
                          fontWeight: 700,
                          fontSize: 15,
                        }}
                      >
                        {cell}
                      </div>
                    ))}
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--color-text-tertiary)', textAlign: 'center', marginBottom: 10 }}>
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
                    UFOV Doble Decisión (Estudio ACTIVE) — Ronda {ufovRound}/5
                  </b>
                  {ufovPhase === 'flash' ? (
                    <div style={{ padding: 28, fontSize: 18, fontWeight: 700 }}>
                      Símbolo central: <span style={{ fontSize: 28, color: 'var(--color-text)' }}>{ufovTarget.center}</span> · Estímulo periférico en sector #{ufovTarget.sector + 1}
                    </div>
                  ) : (
                    <div>
                      <p style={{ fontSize: 13, color: 'var(--color-text-tertiary)', marginBottom: 10 }}>
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
                    Alternancia Ejecutiva & Control Inhibitorio (Karbach & Kray) — Ronda {stroopRound}/5
                  </b>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--color-text)', marginBottom: 10 }}>
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
                      <div key={m.digit} style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '4px 10px', fontSize: 13 }}>
                        <b>{m.digit}</b> → {m.sym}
                      </div>
                    ))}
                  </div>
                  <div style={{ fontSize: 26, fontWeight: 800, marginBottom: 12 }}>
                    Dígito objetivo: <span style={{ color: 'var(--color-text)' }}>{dsstTarget}</span>
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
                      <b style={{ fontSize: 14, color: 'var(--color-text)' }}>{p.name}</b>
                      <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--color-text)' }}>{gym.best?.[p.id] != null ? `Mejor: ${gym.best[p.id]} %` : ''}</span>
                    </div>
                    <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--color-text)', marginBottom: 6 }}>{p.study}</div>
                    <p style={{ fontSize: 12.5, color: 'var(--color-text-tertiary)', margin: '0 0 10px', lineHeight: 1.45 }}>{p.mechanism}</p>
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
              {gym.history?.length > 0 && (
                <ul className="gym-history" aria-label="Sus últimas sesiones">
                  {gym.history.slice(-6).reverse().map((h: any, i: number) => (
                    <li key={`${h.date}-${i}`}>
                      <span>{h.date}</span>
                      <b>{gym.scientific_pillars.find((p: any) => p.id === h.exercise)?.name ?? h.exercise}</b>
                      <em>{h.score} %</em>
                    </li>
                  ))}
                </ul>
              )}
              <Credits scope="gimnasio" />
            </section>
          </div>
  );
}
