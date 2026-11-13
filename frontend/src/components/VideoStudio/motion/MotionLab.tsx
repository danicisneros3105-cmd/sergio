import { useState } from 'react';
import { Box, Wand2, Layers, Type, Move3d, Download } from 'lucide-react';

const ASSETS = [
  { id: 'a1', name: 'Lower Third Minimal', type: 'lower-third', category: 'Overlay', preview: 'LT' },
  { id: 'a2', name: 'Transition Glitch', type: 'transition', category: 'Transition', preview: 'GL' },
  { id: 'a3', name: '3D Earth Rotate', type: '3d', category: '3D Model', preview: '3D' },
  { id: 'a4', name: 'Particle Explosion', type: 'vfx', category: 'VFX', preview: 'VX' },
  { id: 'a5', name: 'Kinetic Typography', type: 'template', category: 'Text', preview: 'KT' },
  { id: 'a6', name: 'Neon Glow Lower', type: 'lower-third', category: 'Overlay', preview: 'NL' },
  { id: 'a7', name: 'Morph Transition', type: 'transition', category: 'Transition', preview: 'MT' },
  { id: 'a8', name: 'Volumetric Light', type: 'vfx', category: 'VFX', preview: 'VL' },
];

export function MotionLab() {
  const [cat, setCat] = useState('all');
  const [preview, setPreview] = useState(ASSETS[0]);

  const filtered = ASSETS.filter(a => cat === 'all' || a.type === cat);
  const cats = ['all', 'template', 'vfx', '3d', 'lower-third', 'transition'];

  return (
    <div className="motion-root fade-in">
      <div className="motion-sidebar">
        <div className="motion-header">
          <Box size={14} />
          <span>Motion Lab</span>
        </div>
        {cats.map(c => (
          <button
            key={c}
            className={`motion-chip ${cat === c ? 'active' : ''}`}
            onClick={() => setCat(c)}
          >
            {c === 'all' ? 'Todos' : c === 'lower-third' ? 'Lower Third' : c === '3d' ? '3D' : c.charAt(0).toUpperCase() + c.slice(1)}
          </button>
        ))}
      </div>

      <div className="motion-main">
        <div className="motion-preview">
          <div className="motion-canvas">
            <span style={{ fontSize: 32, fontWeight: 700, color: 'var(--accent)' }}>{preview.preview}</span>
          </div>
          <div className="motion-info">
            <h3>{preview.name}</h3>
            <span className="motion-cat">{preview.category}</span>
            <button className="tb-btn primary"><Download size={12} /> Usar Asset</button>
          </div>
        </div>

        <div className="motion-grid">
          {filtered.map(a => (
            <button
              key={a.id}
              className={`motion-tile ${preview.id === a.id ? 'active' : ''}`}
              onClick={() => setPreview(a)}
            >
              <span className="motion-tile-icon">{a.preview}</span>
              <span className="motion-tile-name">{a.name}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
