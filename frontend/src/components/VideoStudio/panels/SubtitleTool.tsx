import { useState } from 'react';
import { Type, AlignLeft, AlignCenter, AlignRight, Sparkles } from 'lucide-react';

const FONTS = ['Inter', 'Poppins', 'Bebas Neue', 'Roboto Mono', 'Oswald', 'Montserrat'];

interface Props {
  studio: any;
}

export function SubtitleTool({ studio }: Props) {
  const [style, setStyle] = useState({
    bold: false, italic: false, size: 24, color: '#fff',
    bgColor: '#00000080', align: 'center' as const, position: 'bottom' as const, font: 'Inter'
  });

  const generate = () => {
    const subs = [
      { id: 's1', start: 0, end: 3, text: 'Bienvenidos a Sergio Studio' },
      { id: 's2', start: 3.5, end: 7, text: 'Edicion profesional con IA' },
      { id: 's3', start: 7.5, end: 12, text: 'Crea contenido viral en minutos' },
    ];
    studio.setSubtitles(subs);
  };

  return (
    <div className="fade-in">
      <div className="card">
        <button className="tb-btn primary" style={{ width: '100%', justifyContent: 'center' }} onClick={generate}>
          <Sparkles size={12} /> Auto-Transcribir
        </button>
      </div>

      <div className="card">
        <div className="card-title">Estilo</div>
        <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
          {[{ k: 'bold', l: 'B' }, { k: 'italic', l: 'I' }].map(t => (
            <button
              key={t.k}
              className={`style-toggle ${(style as any)[t.k] ? 'active' : ''}`}
              onClick={() => setStyle(s => ({ ...s, [t.k]: !(s as any)[t.k] }))}
            >
              {t.l}
            </button>
          ))}
        </div>
        <label style={{ fontSize: 10, color: 'var(--text-muted)' }}>Tamaño</label>
        <input type="range" min={12} max={72} value={style.size}
          onChange={e => setStyle(s => ({ ...s, size: Number(e.target.value) }))}
          style={{ width: '100%', accentColor: 'var(--accent)' }} />
        <label style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>Fuente</label>
        <select className="studio-input" value={style.font} onChange={e => setStyle(s => ({ ...s, font: e.target.value }))}>
          {FONTS.map(f => <option key={f} value={f}>{f}</option>)}
        </select>
        <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
          {['left', 'center', 'right'].map(a => (
            <button key={a} className={`style-toggle ${style.align === a ? 'active' : ''}`}
              onClick={() => setStyle(s => ({ ...s, align: a as any }))}>
              {a === 'left' ? <AlignLeft size={10} /> : a === 'center' ? <AlignCenter size={10} /> : <AlignRight size={10} />}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Subtitulos ({studio.subtitles.length})</div>
        {studio.subtitles.map((s: any) => (
          <div key={s.id} className="sub-row">
            <span className="sub-time">{s.start.toFixed(1)}s</span>
            <span className="sub-text">{s.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
