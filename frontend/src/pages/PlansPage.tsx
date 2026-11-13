import { useState } from 'react';
import { Check, Zap, Users, Video, TrendingUp, Sparkles } from 'lucide-react';
import './plans.css';

const PLANS = [
  {
    name: 'Creator',
    price: 19,
    period: 'mes',
    channels: 2,
    videos: 20,
    features: ['Export 1080p', 'Efectos basicos', 'Music library', 'ViralScore', '1 canal YT'],
  },
  {
    name: 'Pro',
    price: 49,
    period: 'mes',
    channels: 5,
    videos: 100,
    features: ['Export 4K', 'Motion Lab', 'ClipFinder', 'Channel Analyzer', 'VideoBoost AI', '3 canales YT'],
    highlight: true,
  },
  {
    name: 'Studio',
    price: 129,
    period: 'mes',
    channels: 20,
    videos: 500,
    features: ['Todo Pro', 'API access', 'White-label', 'Prioridad render', 'Soporte dedicado', 'Canales ilimitados'],
  },
];

const EARNINGS = [
  { plan: 'Creator', channels: 1, videos: 20, cpm: 4, views: '500K', revenue: '$2,000/mes' },
  { plan: 'Pro', channels: 3, videos: 80, cpm: 5, views: '3M', revenue: '$15,000/mes' },
  { plan: 'Studio', channels: 10, videos: 300, cpm: 6, views: '15M', revenue: '$90,000/mes' },
];

const COMPETITION = [
  { name: 'CapCut', price: '$10-20/mo', pros: 'Gratuito basico', cons: 'Sin IA avanzada', ours: 'Motor de estilo' },
  { name: 'Runway', price: '$15-95/mo', pros: 'Gen-4.5 fuerte', cons: 'Solo generacion', ours: 'Edicion completa' },
  { name: 'OpusClip', price: '$15-29/mo', pros: 'Shorts auto', cons: 'Sin timeline', ours: 'NLE profesional' },
  { name: 'Descript', price: '$24-35/mo', pros: 'Text-based', cons: 'Lento', ours: '30fps analisis' },
  { name: 'Sergio', price: '$19-129/mo', pros: 'Todo en uno', cons: 'Nuevo', ours: 'Nosotros' },
];

export default function PlansPage() {
  const [tab, setTab] = useState<'plans' | 'earnings' | 'competition'>('plans');

  return (
    <div className="plans-root">
      <div className="plans-tabs">
        {[
          { id: 'plans' as const, label: 'Planes', icon: Zap },
          { id: 'earnings' as const, label: 'Ganancias', icon: TrendingUp },
          { id: 'competition' as const, label: 'Competencia', icon: Sparkles },
        ].map(t => {
          const Icon = t.icon;
          return (
            <button key={t.id} className={`plans-tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
              <Icon size={14} /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'plans' && (
        <div className="plans-grid fade-in">
          {PLANS.map(p => (
            <div key={p.name} className={`plan-card ${p.highlight ? 'highlight' : ''}`}>
              {p.highlight && <div className="plan-badge">Mas Popular</div>}
              <h3>{p.name}</h3>
              <div className="plan-price">
                <span className="plan-currency">$</span>
                <span className="plan-amount">{p.price}</span>
                <span className="plan-period">/{p.period}</span>
              </div>
              <div className="plan-meta">
                <span><Users size={12} /> {p.channels} canales</span>
                <span><Video size={12} /> {p.videos} videos/mes</span>
              </div>
              <ul className="plan-features">
                {p.features.map(f => (
                  <li key={f}><Check size={12} /> {f}</li>
                ))}
              </ul>
              <button className={`plan-cta ${p.highlight ? 'primary' : ''}`}>
                Elegir {p.name}
              </button>
            </div>
          ))}
        </div>
      )}

      {tab === 'earnings' && (
        <div className="earnings-table fade-in">
          <table>
            <thead>
              <tr>
                <th>Plan</th><th>Canales</th><th>Videos/mes</th><th>CPM avg</th><th>Vistas/mes</th><th>Ingreso estimado</th>
              </tr>
            </thead>
            <tbody>
              {EARNINGS.map((e, i) => (
                <tr key={i}>
                  <td><span className="earn-plan">{e.plan}</span></td>
                  <td>{e.channels}</td>
                  <td>{e.videos}</td>
                  <td>${e.cpm}</td>
                  <td>{e.views}</td>
                  <td><span className="earn-rev">{e.revenue}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="earn-note">* Estimados basados en CPM promedio de $4-6 en contenido en ingles. Resultados varian por nicho.</p>
        </div>
      )}

      {tab === 'competition' && (
        <div className="comp-table fade-in">
          <table>
            <thead>
              <tr><th>Herramienta</th><th>Precio</th><th>Pros</th><th>Contras</th><th>Sergio vs</th></tr>
            </thead>
            <tbody>
              {COMPETITION.map((c, i) => (
                <tr key={i} className={c.ours === 'Nosotros' ? 'sergio-row' : ''}>
                  <td><strong>{c.name}</strong></td>
                  <td>{c.price}</td>
                  <td>{c.pros}</td>
                  <td>{c.cons}</td>
                  <td>{c.ours}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
