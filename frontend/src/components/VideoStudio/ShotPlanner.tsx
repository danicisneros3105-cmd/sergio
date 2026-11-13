import { useState } from 'react';
import { Target, Plus, Trash2, Camera, Clock, Hash, Lightbulb, Film, Mic, Sun, Moon, Cloud, Sparkles, Wand2 } from 'lucide-react';
import { toast } from 'sonner';

interface Shot {
  id: string;
  number: number;
  type: 'wide' | 'medium' | 'close' | 'extreme' | 'aerial' | 'pov';
  description: string;
  duration: number;
  lighting: 'natural' | 'studio' | 'lowkey' | 'highkey' | 'neon';
  movement: 'static' | 'pan' | 'tilt' | 'dolly' | 'handheld' | 'gimbal' | 'drone';
  audio: 'dialogue' | 'music' | 'ambient' | 'silence' | 'voiceover';
  notes: string;
}

const SHOT_TYPES = [
  { key: 'wide', label: 'Plano General', desc: 'Contexto y ambiente' },
  { key: 'medium', label: 'Plano Medio', desc: 'Accion y personajes' },
  { key: 'close', label: 'Primer Plano', desc: 'Emocion y detalle' },
  { key: 'extreme', label: 'Macro', desc: 'Texturas y detalles' },
  { key: 'aerial', label: 'Aereo', desc: 'Vista de pajaro' },
  { key: 'pov', label: 'POV', desc: 'Punto de vista' },
];

const LIGHTING = [
  { key: 'natural', label: 'Natural', icon: Sun },
  { key: 'studio', label: 'Estudio', icon: Lightbulb },
  { key: 'lowkey', label: 'Bajo Clave', icon: Moon },
  { key: 'highkey', label: 'Alto Clave', icon: Sun },
  { key: 'neon', label: 'Neon', icon: Sparkles },
];

const MOVEMENT = [
  { key: 'static', label: 'Estatico' },
  { key: 'pan', label: 'Pan' },
  { key: 'tilt', label: 'Tilt' },
  { key: 'dolly', label: 'Dolly' },
  { key: 'handheld', label: 'Mano alzada' },
  { key: 'gimbal', label: 'Gimbal' },
  { key: 'drone', label: 'Dron' },
];

const AUDIO = [
  { key: 'dialogue', label: 'Dialogo', icon: Mic },
  { key: 'music', label: 'Musica', icon: Sparkles },
  { key: 'ambient', label: 'Ambiente', icon: Cloud },
  { key: 'silence', label: 'Silencio', icon: Moon },
  { key: 'voiceover', label: 'Voiceover', icon: Mic },
];

export function ShotPlanner() {
  const [shots, setShots] = useState<Shot[]>([
    { id: 'sh1', number: 1, type: 'aerial', description: 'Dron panoramic city at golden hour', duration: 5, lighting: 'natural', movement: 'drone', audio: 'ambient', notes: 'Establish location' },
    { id: 'sh2', number: 2, type: 'medium', description: 'Subject walking toward camera', duration: 3, lighting: 'natural', movement: 'gimbal', audio: 'music', notes: 'Build anticipation' },
    { id: 'sh3', number: 3, type: 'close', description: 'Face expression - emotional hook', duration: 4, lighting: 'lowkey', movement: 'static', audio: 'dialogue', notes: 'The hook' },
  ]);
  const [selectedShot, setSelectedShot] = useState<string | null>(null);
  const [aiSuggesting, setAiSuggesting] = useState(false);

  const addShot = () => {
    const id = `sh${Date.now()}`;
    setShots(prev => [...prev, {
      id, number: prev.length + 1, type: 'medium', description: '', duration: 3,
      lighting: 'natural', movement: 'static', audio: 'dialogue', notes: '',
    }]);
    setSelectedShot(id);
  };

  const updateShot = (id: string, updates: Partial<Shot>) => {
    setShots(prev => prev.map(s => s.id === id ? { ...s, ...updates } : s));
  };

  const deleteShot = (id: string) => {
    setShots(prev => prev.filter(s => s.id !== id).map((s, i) => ({ ...s, number: i + 1 })));
    if (selectedShot === id) setSelectedShot(null);
  };

  const aiSuggest = () => {
    setAiSuggesting(true);
    setTimeout(() => {
      const suggestions = [
        { type: 'wide' as const, desc: 'Plano general del ambiente para contexto', lighting: 'natural' as const, movement: 'static' as const },
        { type: 'close' as const, desc: 'Primer plano del producto/sujeto principal', lighting: 'studio' as const, movement: 'dolly' as const },
        { type: 'pov' as const, desc: 'POV interactivo para engagement', lighting: 'neon' as const, movement: 'handheld' as const },
      ];
      const sug = suggestions[Math.floor(Math.random() * suggestions.length)];
      const id = `sh${Date.now()}`;
      setShots(prev => [...prev, {
        id, number: prev.length + 1, type: sug.type, description: sug.desc, duration: 4,
        lighting: sug.lighting, movement: sug.movement, audio: 'music', notes: 'Sugerido por IA',
      }]);
      setAiSuggesting(false);
      toast.success('IA sugirio una nueva toma');
    }, 1500);
  };

  const totalDuration = shots.reduce((a, s) => a + s.duration, 0);

  const activeShot = shots.find(s => s.id === selectedShot);

  return (
    <div className="vshots">
      <div className="vshots-header">
        <h4><Target size={15} /> Shot Planner</h4>
        <span className="vshots-duration"><Clock size={10} /> {totalDuration}s total</span>
      </div>
      <div className="vshots-actions">
        <button onClick={addShot}><Plus size={12} /> Agregar toma</button>
        <button onClick={aiSuggest} disabled={aiSuggesting}><Wand2 size={12} /> {aiSuggesting ? 'Pensando...' : 'Sugerir con IA'}</button>
      </div>
      <div className="vshots-list">
        {shots.map(shot => (
          <div key={shot.id} className={`vshot-item ${shot.id === selectedShot ? 'selected' : ''}`} onClick={() => setSelectedShot(shot.id)}>
            <span className="vshot-number">{shot.number}</span>
            <span className="vshot-type">{SHOT_TYPES.find(t => t.key === shot.type)?.label}</span>
            <span className="vshot-desc">{shot.description || 'Sin descripcion'}</span>
            <span className="vshot-dur">{shot.duration}s</span>
            <button onClick={e => { e.stopPropagation(); deleteShot(shot.id); }}><Trash2 size={10} /></button>
          </div>
        ))}
      </div>
      {activeShot && (
        <div className="vshot-editor">
          <h5>Editar Toma {activeShot.number}</h5>
          <input value={activeShot.description} onChange={e => updateShot(activeShot.id, { description: e.target.value })} placeholder="Descripcion de la toma" />
          <div className="vshot-grid">
            <div>
              <label>Tipo</label>
              <select value={activeShot.type} onChange={e => updateShot(activeShot.id, { type: e.target.value as any })}>
                {SHOT_TYPES.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <label>Duracion (s)</label>
              <input type="number" min={1} max={60} value={activeShot.duration} onChange={e => updateShot(activeShot.id, { duration: Number(e.target.value) })} />
            </div>
            <div>
              <label>Iluminacion</label>
              <select value={activeShot.lighting} onChange={e => updateShot(activeShot.id, { lighting: e.target.value as any })}>
                {LIGHTING.map(l => <option key={l.key} value={l.key}>{l.label}</option>)}
              </select>
            </div>
            <div>
              <label>Movimiento</label>
              <select value={activeShot.movement} onChange={e => updateShot(activeShot.id, { movement: e.target.value as any })}>
                {MOVEMENT.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label>Audio</label>
            <div className="vshot-audio">
              {AUDIO.map(a => (
                <button key={a.key} className={activeShot.audio === a.key ? 'active' : ''} onClick={() => updateShot(activeShot.id, { audio: a.key as any })}>
                  <a.icon size={12} /> {a.label}
                </button>
              ))}
            </div>
          </div>
          <textarea value={activeShot.notes} onChange={e => updateShot(activeShot.id, { notes: e.target.value })} placeholder="Notas adicionales..." />
        </div>
      )}
    </div>
  );
}
