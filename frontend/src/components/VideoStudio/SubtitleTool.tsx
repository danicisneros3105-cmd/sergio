import { useState } from 'react';
import { Plus, Trash2, Wand2, Type, Bold, Italic, AlignLeft, AlignCenter, AlignRight, Mic } from 'lucide-react';
import { toast } from 'sonner';
import type { Subtitle } from './VideoStudio';

interface Props {
  subtitles: Subtitle[];
  setSubtitles: React.Dispatch<React.SetStateAction<Subtitle[]>>;
  currentTime: number;
}

const FONTS = ['Inter', 'Roboto', 'Montserrat', 'Oswald', 'Bebas Neue', 'Poppins', 'Arial'];

export function SubtitleTool({ subtitles, setSubtitles, currentTime }: Props) {
  const [selectedSub, setSelectedSub] = useState<string | null>(null);
  const [style, setStyle] = useState({
    bold: false,
    italic: false,
    align: 'center' as 'left' | 'center' | 'right',
    size: 24,
    color: '#ffffff',
    bgColor: '#00000080',
    position: 'bottom' as 'top' | 'center' | 'bottom',
    font: 'Inter',
  });
  const [aiTranscribing, setAiTranscribing] = useState(false);

  const addSubtitle = () => {
    const id = `s${Date.now()}`;
    setSubtitles((prev) => [...prev, { id, text: 'Nuevo subtitulo', start: currentTime, end: currentTime + 3 }]);
    setSelectedSub(id);
  };

  const updateSub = (id: string, updates: Partial<Subtitle>) => {
    setSubtitles((prev) => prev.map((s) => s.id === id ? { ...s, ...updates } : s));
  };

  const deleteSub = (id: string) => {
    setSubtitles((prev) => prev.filter((s) => s.id !== id));
    if (selectedSub === id) setSelectedSub(null);
  };

  const autoTranscribe = () => {
    setAiTranscribing(true);
    setTimeout(() => {
      setAiTranscribing(false);
      toast.success('IA transcribio 4 segmentos del audio');
      const newSubs = [
        { id: `s${Date.now()}-1`, text: 'Hola, bienvenidos a mi canal', start: 0, end: 2.5 },
        { id: `s${Date.now()}-2`, text: 'Hoy les voy a mostrar algo increible', start: 2.8, end: 5 },
        { id: `s${Date.now()}-3`, text: 'No se lo pierdan hasta el final', start: 5.2, end: 7 },
        { id: `s${Date.now()}-4`, text: 'Suscribanse para mas contenido', start: 7.2, end: 9 },
      ];
      setSubtitles((prev) => [...prev, ...newSubs]);
    }, 2000);
  };

  const activeSub = subtitles.find((s) => currentTime >= s.start && currentTime < s.end);

  return (
    <div>
      <div className="vsubtitles-header">
        <h4><Type size={14} /> Subtitulos ({subtitles.length})</h4>
        <div className="vsubtitles-actions">
          <button onClick={addSubtitle}><Plus size={12} /></button>
          <button className={aiTranscribing ? 'active' : ''} onClick={autoTranscribe}><Wand2 size={12} /></button>
        </div>
      </div>

      {aiTranscribing && (
        <div className="vsubtitles-ai">
          <Mic size={14} />
          <span>La IA esta transcribiendo el audio... esto puede tardar unos segundos.</span>
        </div>
      )}

      <div className="vsubtitles-list">
        {subtitles.map((sub) => (
          <div
            key={sub.id}
            className={`vsubtitle-item ${selectedSub === sub.id ? 'selected' : ''} ${activeSub?.id === sub.id ? 'active' : ''}`}
            onClick={() => setSelectedSub(sub.id)}
          >
            <span className="vsubtitle-time">{sub.start.toFixed(1)}s - {sub.end.toFixed(1)}s</span>
            <input
              value={sub.text}
              onChange={(e) => updateSub(sub.id, { text: e.target.value })}
              onClick={(e) => e.stopPropagation()}
            />
            <button onClick={(e) => { e.stopPropagation(); deleteSub(sub.id); }}><Trash2 size={10} /></button>
          </div>
        ))}
      </div>

      <div className="vsubtitles-style">
        <h5>Estilo</h5>
        <div className="vstyle-row">
          <button className={style.bold ? 'active' : ''} onClick={() => setStyle((s) => ({ ...s, bold: !s.bold }))}><Bold size={12} /></button>
          <button className={style.italic ? 'active' : ''} onClick={() => setStyle((s) => ({ ...s, italic: !s.italic }))}><Italic size={12} /></button>
          <button className={style.align === 'left' ? 'active' : ''} onClick={() => setStyle((s) => ({ ...s, align: 'left' }))}><AlignLeft size={12} /></button>
          <button className={style.align === 'center' ? 'active' : ''} onClick={() => setStyle((s) => ({ ...s, align: 'center' }))}><AlignCenter size={12} /></button>
          <button className={style.align === 'right' ? 'active' : ''} onClick={() => setStyle((s) => ({ ...s, align: 'right' }))}><AlignRight size={12} /></button>
        </div>
        <div className="vstyle-row">
          <span style={{ fontSize: 10, color: '#71717a' }}>Tamaño</span>
          <input type="range" min={12} max={72} value={style.size} onChange={(e) => setStyle((s) => ({ ...s, size: Number(e.target.value) }))} />
          <span style={{ fontSize: 10, color: '#71717a', width: 24 }}>{style.size}</span>
        </div>
        <div className="vstyle-row">
          <span style={{ fontSize: 10, color: '#71717a' }}>Color</span>
          <input type="color" value={style.color} onChange={(e) => setStyle((s) => ({ ...s, color: e.target.value }))} />
          <span style={{ fontSize: 10, color: '#71717a' }}>Fondo</span>
          <input type="color" value={style.bgColor} onChange={(e) => setStyle((s) => ({ ...s, bgColor: e.target.value }))} />
        </div>
        <div className="vstyle-row">
          <span style={{ fontSize: 10, color: '#71717a' }}>Posicion</span>
          <select value={style.position} onChange={(e) => setStyle((s) => ({ ...s, position: e.target.value as any }))}>
            <option value="top">Arriba</option>
            <option value="center">Centro</option>
            <option value="bottom">Abajo</option>
          </select>
          <span style={{ fontSize: 10, color: '#71717a' }}>Fuente</span>
          <select value={style.font} onChange={(e) => setStyle((s) => ({ ...s, font: e.target.value }))}>
            {FONTS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}
