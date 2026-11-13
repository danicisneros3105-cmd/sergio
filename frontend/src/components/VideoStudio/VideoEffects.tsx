import { useMemo, useState } from 'react';
import { Search, Plus, Eye, EyeOff, X, Sparkles, Palette, Blinds, Sun, Moon, Wind, ScanLine, Zap } from 'lucide-react';
import type { VideoClip } from './VideoStudio';

interface Props {
  selectedClipId: string | null;
  clips: VideoClip[];
  setClips: React.Dispatch<React.SetStateAction<VideoClip[]>>;
}

const CATEGORIES = [
  { key: 'color', label: 'Color', icon: Palette },
  { key: 'filter', label: 'Filtros', icon: Blinds },
  { key: 'distort', label: 'Distorsion', icon: Wind },
  { key: 'vfx', label: 'VFX', icon: Sparkles },
  { key: 'transition', label: 'Transiciones', icon: Zap },
] as const;

const EFFECTS: Record<string, Array<{ name: string; desc: string; preset: string }>> = {
  color: [
    { name: 'Contraste +', desc: 'Aumenta contraste cinematico', preset: 'contrast(1.3)' },
    { name: 'Saturacion +', desc: 'Colores mas vibrantes', preset: 'saturate(1.5)' },
    { name: 'Tinte Calido', desc: 'Tono dorado', preset: 'sepia(0.3) saturate(1.2)' },
    { name: 'Tinte Frio', desc: 'Tono azulado', preset: 'hue-rotate(180deg) saturate(0.8)' },
    { name: 'Vintage', desc: 'Look retro', preset: 'sepia(0.6) contrast(0.9)' },
    { name: 'Neon', desc: 'Colores neon intensos', preset: 'saturate(2) contrast(1.2) hue-rotate(30deg)' },
  ],
  filter: [
    { name: 'Desenfoque', desc: 'Blur gaussiano', preset: 'blur(4px)' },
    { name: 'B&W', desc: 'Blanco y negro', preset: 'grayscale(1)' },
    { name: 'Sepia', desc: 'Sepia clasica', preset: 'sepia(1)' },
    { name: 'Invertir', desc: 'Colores invertidos', preset: 'invert(1)' },
    { name: 'Pixelar', desc: 'Efecto pixelado', preset: 'contrast(1.5)' },
    { name: 'Difuminar', desc: 'Difuminado artistico', preset: 'blur(8px) brightness(1.1)' },
  ],
  distort: [
    { name: 'Glitch', desc: 'Efecto glitch digital', preset: 'hue-rotate(90deg) contrast(1.5)' },
    { name: 'Ondas', desc: 'Ondulacion', preset: 'contrast(1.1)' },
    { name: 'Espejo', desc: 'Reflejo horizontal', preset: 'contrast(1)' },
    { name: 'Kaleidoscopio', desc: 'Patron caleidoscopico', preset: 'hue-rotate(45deg)' },
    { name: 'Vortex', desc: 'Remolino', preset: 'hue-rotate(180deg)' },
    { name: 'Ruido', desc: 'Ruido filmico', preset: 'contrast(1.1) brightness(0.95)' },
  ],
  vfx: [
    { name: 'Lens Flare', desc: 'Destello de lente', preset: 'brightness(1.2)' },
    { name: 'Bloom', desc: 'Resplandor suave', preset: 'brightness(1.3) blur(2px)' },
    { name: 'Chromatic', desc: 'Aberracion cromatica', preset: 'contrast(1.2)' },
    { name: 'Motion Blur', desc: 'Desenfoque de movimiento', preset: 'blur(3px)' },
    { name: 'Vignette', desc: 'Vineta oscura', preset: 'brightness(0.9)' },
    { name: 'Glow', desc: 'Brillo difuso', preset: 'brightness(1.4) saturate(1.3)' },
  ],
  transition: [
    { name: 'Fade', desc: 'Transicion suave', preset: 'opacity' },
    { name: 'Slide', desc: 'Deslizamiento', preset: 'translate' },
    { name: 'Zoom', desc: 'Zoom transicion', preset: 'scale' },
    { name: 'Spin', desc: 'Rotacion', preset: 'rotate' },
    { name: 'Wipe', desc: 'Barrido', preset: 'clip-path' },
    { name: 'Morph', desc: 'Morphing', preset: 'filter' },
  ],
};

export function VideoEffects({ selectedClipId, clips, setClips }: Props) {
  const [search, setSearch] = useState('');
  const [activeCat, setActiveCat] = useState<string>('color');

  const selectedClip = useMemo(() => clips.find((c) => c.id === selectedClipId), [clips, selectedClipId]);

  const filtered = useMemo(() => {
    const all = Object.values(EFFECTS).flat();
    if (!search) return all;
    return all.filter((e) => e.name.toLowerCase().includes(search.toLowerCase()) || e.desc.toLowerCase().includes(search.toLowerCase()));
  }, [search]);

  const addEffect = (effectName: string) => {
    if (!selectedClipId) return;
    setClips((prev) => prev.map((c) => c.id === selectedClipId ? { ...c, effects: [...c.effects, effectName] } : c));
  };

  const removeEffect = (effectName: string) => {
    if (!selectedClipId) return;
    setClips((prev) => prev.map((c) => c.id === selectedClipId ? { ...c, effects: c.effects.filter((e) => e !== effectName) } : c));
  };

  const toggleEffect = (effectName: string) => {
    if (!selectedClip) return;
    if (selectedClip.effects.includes(effectName)) {
      removeEffect(effectName);
    } else {
      addEffect(effectName);
    }
  };

  if (!selectedClip) {
    return (
      <div className="veffects-empty">
        <Sparkles size={32} />
        <p>Selecciona un clip en la timeline para aplicar efectos</p>
      </div>
    );
  }

  return (
    <div>
      <div className="veffects-search">
        <Search size={12} />
        <input placeholder="Buscar efectos..." value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      {!search && (
        <div className="veffects-cats">
          {CATEGORIES.map((cat) => (
            <button key={cat.key} className={activeCat === cat.key ? 'active' : ''} onClick={() => setActiveCat(cat.key)}>
              <cat.icon size={10} /> {cat.label}
            </button>
          ))}
        </div>
      )}

      <div className="veffects-list">
        {(search ? filtered : EFFECTS[activeCat]).map((effect) => (
          <div key={effect.name} className="veffect-card" onClick={() => toggleEffect(effect.name)}>
            <div className="veffect-info">
              <span className="veffect-name">{effect.name}</span>
              <span className="veffect-desc">{effect.desc}</span>
            </div>
            <button className="veffect-add">
              {selectedClip.effects.includes(effect.name) ? <X size={14} /> : <Plus size={14} />}
            </button>
          </div>
        ))}
      </div>

      {selectedClip.effects.length > 0 && (
        <div className="veffects-active">
          <h4>Efectos activos</h4>
          {selectedClip.effects.map((e) => (
            <span key={e} className="veffect-tag">
              {e} <button onClick={() => removeEffect(e)}><X size={10} /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
