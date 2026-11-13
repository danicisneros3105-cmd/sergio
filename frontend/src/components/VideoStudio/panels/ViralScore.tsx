import { useState, useEffect } from 'react';

const METRICS = [
  { label: 'Hook (0-3s)', weight: 25 },
  { label: 'Ritmo de cortes', weight: 20 },
  { label: 'Retencion', weight: 20 },
  { label: 'Audio/SFX', weight: 15 },
  { label: 'Color grade', weight: 10 },
  { label: 'CTA final', weight: 10 },
];

const TIPS = [
  { text: 'Usa un hook visual en los primeros 3 segundos', priority: 'high' },
  { text: 'Aumenta la frecuencia de cortes cada 30s', priority: 'high' },
  { text: 'Anade musica de fondo con energia creciente', priority: 'medium' },
  { text: 'Incluye un zoom sutil en momentos clave', priority: 'medium' },
  { text: 'Termina con una pregunta o CTA clara', priority: 'low' },
];

export function ViralScore() {
  const [score, setScore] = useState(0);
  const target = 78;

  useEffect(() => {
    let s = 0;
    const iv = setInterval(() => {
      s += 1;
      if (s >= target) { setScore(target); clearInterval(iv); }
      else setScore(s);
    }, 12);
    return () => clearInterval(iv);
  }, []);

  const grade = score >= 90 ? 'VIRAL' : score >= 75 ? 'BUENO' : score >= 60 ? 'REGULAR' : 'MEJORAR';
  const color = score >= 90 ? '#22c55e' : score >= 75 ? '#d4a853' : score >= 60 ? '#f59e0b' : '#ef4444';
  const r = 52, c = 2 * Math.PI * r;
  const offset = c - (score / 100) * c;

  return (
    <div className="fade-in">
      <div className="card" style={{ textAlign: 'center' }}>
        <svg width="120" height="120" style={{ margin: '0 auto' }}>
          <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
          <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="8"
            strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset .4s ease', transform: 'rotate(-90deg)', transformOrigin: '60px 60px' }} />
          <text x="60" y="58" textAnchor="middle" fill={color} fontSize="24" fontWeight="700">{score}</text>
          <text x="60" y="76" textAnchor="middle" fill="var(--text-muted)" fontSize="10">{grade}</text>
        </svg>
      </div>

      <div className="card">
        <div className="card-title">Metricas</div>
        {METRICS.map(m => (
          <div key={m.label} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)' }}>
              <span>{m.label}</span>
              <span>{m.weight}%</span>
            </div>
            <div style={{ height: 4, background: 'var(--bg)', borderRadius: 2, marginTop: 2 }}>
              <div style={{ height: 4, width: `${m.weight * 3.2}%`, background: 'var(--accent)', borderRadius: 2, transition: 'width .6s' }} />
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Sugerencias</div>
        {TIPS.map((t, i) => (
          <div key={i} className={`tip-row ${t.priority}`}>
            <span className={`tip-dot ${t.priority}`} />
            <span style={{ fontSize: 11 }}>{t.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
