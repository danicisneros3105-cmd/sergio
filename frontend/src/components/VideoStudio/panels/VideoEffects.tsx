import { useState } from 'react';
import { Search, X, Sliders } from 'lucide-react';
import type { EffectDef } from '@/types/video';

const CATEGORIES = ['color', 'filter', 'distort', 'vfx', 'transition'] as const;

const EFFECTS: EffectDef[] = [
  { id: 'c1', name: 'Cine HDR', category: 'color' },
  { id: 'c2', name: 'Teal & Orange', category: 'color' },
  { id: 'c3', name: 'Cine D', category: 'color' },
  { id: 'c4', name: 'Vintage 35mm', category: 'color' },
  { id: 'c5', name: 'Cyberpunk', category: 'color' },
  { id: 'f1', name: 'Gaussian Blur', category: 'filter' },
  { id: 'f2', name: 'Sharpen', category: 'filter' },
  { id: 'f3', name: 'Noise Grain', category: 'filter' },
  { id: 'd1', name: 'Lens Distortion', category: 'distort' },
  { id: 'd2', name: 'Chromatic Aberration', category: 'distort' },
  { id: 'd3', name: 'Glitch', category: 'distort' },
  { id: 'v1', name: 'Particle Dust', category: 'vfx' },
  { id: 'v2', name: 'Light Leak', category: 'vfx' },
  { id: 'v3', name: 'Speed Ramp', category: 'vfx' },
  { id: 't1', name: 'Cross Dissolve', category: 'transition' },
  { id: 't2', name: 'Zoom Blur', category: 'transition' },
  { id: 't3', name: 'Morph Cut', category: 'transition' },
];

interface Props {
  studio: any;
}

export function VideoEffects({ studio }: Props) {
  const [cat, setCat] = useState<string>('all');
  const [q, setQ] = useState('');

  const filtered = EFFECTS.filter(e =>
    (cat === 'all' || e.category === cat) &&
    e.name.toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div className="fade-in">
      <div className="card">
        <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
          <Search size={12} color="var(--text-muted)" />
          <input
            className="studio-input"
            placeholder="Buscar efecto..."
            value={q}
            onChange={e => setQ(e.target.value)}
            style={{ padding: '4px 8px', fontSize: 11 }}
          />
        </div>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          <button
            className={`chip ${cat === 'all' ? 'active' : ''}`}
            onClick={() => setCat('all')}
          >Todos</button>
          {CATEGORIES.map(c => (
            <button
              key={c}
              className={`chip ${cat === c ? 'active' : ''}`}
              onClick={() => setCat(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Activos ({studio.activeEffects.length})</div>
        {studio.activeEffects.length === 0 && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Sin efectos activos</span>
        )}
        {studio.activeEffects.map((e: EffectDef) => (
          <div key={e.id} className="fx-row">
            <span>{e.name}</span>
            <button onClick={() => studio.removeEffect(e.id)}><X size={10} /></button>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {filtered.map(e => (
          <button
            key={e.id}
            className="fx-tile"
            onClick={() => studio.addEffect(e)}
          >
            <Sliders size={14} />
            <span>{e.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
