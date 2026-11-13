import { useState } from 'react';
import { Layers, Play, Check } from 'lucide-react';

const PATTERNS = [
  {
    id: 'progressive',
    name: 'Ritmo Progresivo',
    channel: 'Ryan Trahan',
    desc: 'Inicio lento que acelera gradualmente. Cada minuto incrementa la densidad de cortes un 20%.',
    params: { startBpm: 90, peakBpm: 140, rampDuration: 15 },
    tips: ['Intro 15s sin cortes', 'Minuto 2: primer twist', 'Minuto 4: climax visual', 'Outro: resumen 10s'],
  },
  {
    id: 'contrast',
    name: 'Contraste Extremo',
    channel: 'Ryan Trahan',
    desc: 'Alternancia abrupta entre calma y caos. Silencio de 2s seguido de burst de 5 cortes en 3s.',
    params: { silenceDuration: 2, burstCuts: 5, burstWindow: 3 },
    tips: ['Pausa dramatica antes de reveal', 'Musica se corta completamente', 'Explosion visual inmediata', 'Vuelta a calma'],
  },
  {
    id: 'loop',
    name: 'Bucle Narrativo',
    channel: 'MrBeast',
    desc: 'Hook preview del resultado final al inicio, luego desarrollo cronologico. Cierre que cierra el loop.',
    params: { hookDuration: 5, loopClarity: 95 },
    tips: ['Frame 1: resultado final', 'Flashback text overlay', 'Build tension cada 60s', 'Loop visual final = frame 1'],
  },
  {
    id: 'hybrid',
    name: 'Tempo Hibrido',
    channel: 'Zach D Films',
    desc: 'Mezcla de ritmos: segmentos educativos lentos + transiciones rapidas entre conceptos.',
    params: { slowSegments: 3, fastTransitions: 8, mixRatio: 0.4 },
    tips: ['Segmento A: explicacion calm', 'Swipe rapido a B', 'Datos animados', 'Conclusion integrada'],
  },
  {
    id: 'anchor',
    name: 'Ancla Visual',
    channel: 'your nextcore',
    desc: 'Talking head como ancla constante. B-roll cinematico que refuerza cada frase clave.',
    params: { anchorRatio: 0.6, bRollRatio: 0.4, cutOnKeyword: true },
    tips: ['Camara fija ancla', 'B-roll en palabras clave', 'Musica sin letra', 'Color grade consistente'],
  },
];

interface Props {
  studio: any;
}

export function VideoStyleEngine({ studio }: Props) {
  const [sel, setSel] = useState(0);
  const [applied, setApplied] = useState<string[]>([]);
  const p = PATTERNS[sel];

  const apply = () => {
    setApplied(a => a.includes(p.id) ? a : [...a, p.id]);
    // Aplicar al studio
    studio.setClips((prev: any[]) => prev.map((c: any) => ({ ...c, stylePattern: p.id })));
  };

  return (
    <div className="style-root fade-in">
      <div className="style-sidebar">
        <div className="style-header">
          <Layers size={14} />
          <span>Motor de Estilo</span>
        </div>
        {PATTERNS.map((pat, i) => (
          <button
            key={pat.id}
            className={`style-chip ${sel === i ? 'active' : ''} ${applied.includes(pat.id) ? 'applied' : ''}`}
            onClick={() => setSel(i)}
          >
            <span>{pat.name}</span>
            {applied.includes(pat.id) && <Check size={10} />}
          </button>
        ))}
      </div>

      <div className="style-main">
        <div className="style-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h3>{p.name}</h3>
              <span className="style-channel">Basado en {p.channel}</span>
            </div>
            <button className="tb-btn primary" onClick={apply}>
              <Play size={12} /> Aplicar
            </button>
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8, lineHeight: 1.6 }}>{p.desc}</p>
        </div>

        <div className="style-grid">
          <div className="style-card">
            <div className="card-title">Parametros</div>
            {Object.entries(p.params).map(([k, v]) => (
              <div key={k} className="param-row">
                <span className="param-key">{k}</span>
                <span className="param-val">{String(v)}</span>
              </div>
            ))}
          </div>

          <div className="style-card">
            <div className="card-title">Tips de Ejecucion</div>
            {p.tips.map((t, i) => (
              <div key={i} className="tip-row">
                <span style={{ color: 'var(--accent)', marginRight: 6 }}>{i + 1}.</span>
                {t}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
