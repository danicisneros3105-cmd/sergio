import { useState } from 'react';
import { Zap, Gauge, Palette, Music, Sparkles, ArrowRight } from 'lucide-react';

const PRESETS = [
  { id: 'imax', name: 'IMAX Quality', icon: Gauge, desc: 'HDR simulado, contraste dinamico, nitidez extrema', params: { contrast: 1.3, saturation: 1.15, sharpness: 1.4, grain: 0.05 } },
  { id: 'cinematic', name: 'Cinematic 24p', icon: Palette, desc: 'Color grade teal-orange, motion blur, cadencia filmica', params: { contrast: 1.15, saturation: 0.95, sharpness: 1.1, grain: 0.12 } },
  { id: 'viral', name: 'Viral Punch', icon: Zap, desc: 'Saturacion pop, micro-contraste, compresion para short-form', params: { contrast: 1.25, saturation: 1.3, sharpness: 1.2, grain: 0.02 } },
  { id: 'night', name: 'Night Mode', icon: Sparkles, desc: 'Recuperacion de sombras, reduccion de ruido, glow sutil', params: { contrast: 1.1, saturation: 0.9, sharpness: 1.0, grain: 0.08 } },
];

export function VideoBoost() {
  const [sel, setSel] = useState(0);
  const [processing, setProcessing] = useState(false);
  const p = PRESETS[sel];

  const run = () => {
    setProcessing(true);
    setTimeout(() => setProcessing(false), 2500);
  };

  return (
    <div className="boost-root fade-in">
      <div className="boost-header">
        <Zap size={18} color="var(--accent)" />
        <h2>VideoBoost AI</h2>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Mejora automatica de calidad visual</span>
      </div>

      <div className="boost-presets">
        {PRESETS.map((pr, i) => {
          const Icon = pr.icon;
          return (
            <button
              key={pr.id}
              className={`boost-preset ${sel === i ? 'active' : ''}`}
              onClick={() => setSel(i)}
            >
              <Icon size={16} />
              <span>{pr.name}</span>
            </button>
          );
        })}
      </div>

      <div className="boost-card">
        <h3>{p.name}</h3>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>{p.desc}</p>

        <div className="boost-params">
          {Object.entries(p.params).map(([k, v]) => (
            <div key={k} className="boost-param">
              <span className="boost-param-label">{k}</span>
              <div className="boost-bar">
                <div className="boost-fill" style={{ width: `${(v as number) * 60}%` }} />
              </div>
              <span className="boost-param-val">{(v as number).toFixed(2)}x</span>
            </div>
          ))}
        </div>

        <button className="boost-run" onClick={run} disabled={processing}>
          {processing ? (
            <><span className="boost-spinner" /> Procesando...</>
          ) : (
            <><Sparkles size={14} /> Aplicar Boost <ArrowRight size={14} /></>
          )}
        </button>
      </div>

      <div className="boost-features">
        {[
          { icon: Gauge, title: 'Super-Resolution', desc: '4K desde 1080p con IA' },
          { icon: Palette, title: 'Auto Color', desc: 'Grade adaptativo por escena' },
          { icon: Music, title: 'Audio Enhance', desc: 'Reduccion de ruido + compresion' },
          { icon: Zap, title: 'Stabilization', desc: 'Gyroflow-level stabilization' },
        ].map((f, i) => {
          const Icon = f.icon;
          return (
            <div key={i} className="boost-feature">
              <Icon size={16} color="var(--accent)" />
              <span className="boost-f-title">{f.title}</span>
              <span className="boost-f-desc">{f.desc}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
