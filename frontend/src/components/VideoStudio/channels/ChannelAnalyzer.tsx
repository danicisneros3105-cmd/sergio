import { useState } from 'react';
import { Users, Eye, Clock, Zap, BarChart3 } from 'lucide-react';

const CHANNELS = [
  {
    name: 'MrBeast', handle: '@MrBeast', subscribers: '302M', avgViews: '180M',
    style: 'Fast cuts extremos, zooms dinamicos, hooks visuales en frame 1',
    patterns: ['Hook 0-3s con texto enorme', 'Zoom cut cada 4-8s', 'Countdown tension', 'CTA agresivo final'],
    avgDuration: '12-18 min', color: '#22c55e',
    signature: ['"Last to leave" format', 'Dinero visual en pantalla', 'Reacciones exageradas'],
  },
  {
    name: 'Ryan Trahan', handle: '@RyanTrahan', subscribers: '16M', avgViews: '8M',
    style: 'Narrativa documental con ritmo progresivo, contrastes humor-serio',
    patterns: ['Intro relajada 15s', 'Escalada de ritmo min 2', 'Plot twist visual', 'Outro reflexivo'],
    avgDuration: '15-25 min', color: '#3b82f6',
    signature: ['Penny Challenge', '1€ = 1 dia', 'Narracion en primera persona'],
  },
  {
    name: 'Zach D Films', handle: '@zachdfilms', subscribers: '8M', avgViews: '15M',
    style: 'Animacion 3D fotorealista con storytelling educativo',
    patterns: ['Hook pregunta inquietante', 'Blender photoreal', 'Datos animados', 'Conclusion visual'],
    avgDuration: '3-8 min', color: '#a855f7',
    signature: ['What if escenarios', 'Simulaciones 3D', 'Estilo documental animado'],
  },
  {
    name: 'Ricks Clips', handle: '@RicksClips', subscribers: '4M', avgViews: '5M',
    style: 'Ciencia explicada con motion graphics limpios y ritmo didactico',
    patterns: ['Titulo curiosity gap', 'Animacion 2D/3D mix', 'Voiceover calm', 'Resumen visual final'],
    avgDuration: '5-10 min', color: '#f59e0b',
    signature: ['Efecto mariposa visual', 'Timeline animado', 'Comparaciones numericas'],
  },
  {
    name: 'your nextcore', handle: '@yournextcore', subscribers: '1.2M', avgViews: '2M',
    style: 'Talking head minimalista + B-roll cinematografico + motivacion',
    patterns: ['Intro hablando camara', 'B-roll calidad cine', 'Musica epica', 'Mensaje inspirador'],
    avgDuration: '8-15 min', color: '#ec4899',
    signature: ['Frases de impacto', 'Montaje motivacional', 'Estetica oscura premium'],
  },
];

export function ChannelAnalyzer() {
  const [sel, setSel] = useState(0);
  const ch = CHANNELS[sel];

  return (
    <div className="channel-root fade-in">
      <div className="channel-sidebar">
        {CHANNELS.map((c, i) => (
          <button
            key={c.name}
            className={`channel-chip ${sel === i ? 'active' : ''}`}
            onClick={() => setSel(i)}
          >
            <span className="channel-dot" style={{ background: c.color }} />
            <span>{c.name}</span>
          </button>
        ))}
      </div>

      <div className="channel-main">
        <div className="channel-header">
          <div className="channel-avatar" style={{ background: ch.color }}>{ch.name[0]}</div>
          <div>
            <h2>{ch.name} <span className="channel-handle">{ch.handle}</span></h2>
            <div className="channel-stats">
              <span><Users size={12} /> {ch.subscribers}</span>
              <span><Eye size={12} /> {ch.avgViews}/video</span>
              <span><Clock size={12} /> {ch.avgDuration}</span>
            </div>
          </div>
        </div>

        <div className="channel-grid">
          <div className="channel-card">
            <div className="card-title"><Zap size={12} /> Estilo de Edicion</div>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>{ch.style}</p>
          </div>

          <div className="channel-card">
            <div className="card-title"><BarChart3 size={12} /> Patrones Detectados</div>
            {ch.patterns.map((p, i) => (
              <div key={i} className="pattern-row">
                <span className="pattern-num" style={{ color: ch.color }}>{i + 1}</span>
                <span>{p}</span>
              </div>
            ))}
          </div>

          <div className="channel-card">
            <div className="card-title">Firmas Distintivas</div>
            {ch.signature.map((s, i) => (
              <div key={i} className="signature-row">
                <span style={{ color: ch.color, marginRight: 6 }}>#</span>
                {s}
              </div>
            ))}
          </div>

          <div className="channel-card">
            <div className="card-title">Analisis a 30fps</div>
            <div className="fps-grid">
              {[
                { label: 'Cortes/min', val: ch.name === 'MrBeast' ? '45+' : ch.name === 'Ryan Trahan' ? '18' : ch.name === 'Zach D Films' ? '8' : ch.name === 'Ricks Clips' ? '12' : '10' },
                { label: 'Zoom cuts', val: ch.name === 'MrBeast' ? 'Cada 6s' : 'Esporadico' },
                { label: 'Hook type', val: ch.name === 'MrBeast' ? 'Visual shock' : ch.name === 'Ryan Trahan' ? 'Narrativo' : ch.name === 'Zach D Films' ? 'Pregunta 3D' : 'Curiosity gap' },
                { label: 'Music BPM', val: ch.name === 'MrBeast' ? '140+' : ch.name === 'Ryan Trahan' ? '90-120' : ch.name === 'Zach D Films' ? '80' : '100' },
              ].map(m => (
                <div key={m.label} className="fps-cell">
                  <span className="fps-label">{m.label}</span>
                  <span className="fps-val">{m.val}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
