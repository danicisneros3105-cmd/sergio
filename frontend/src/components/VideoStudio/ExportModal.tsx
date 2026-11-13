import { useState } from 'react';
import { Download, X, Youtube, Instagram, Music, Twitter, Video, Gauge, Zap, Crown, Star, AlertTriangle, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

interface Preset {
  name: string;
  w: number;
  h: number;
  fps: number;
  bitrate: string;
}

interface Props {
  presets: Preset[];
  onClose: () => void;
  projectName: string;
}

const QUALITIES = [
  { label: 'Ultra (4K)', desc: 'Maxima calidad, archivo grande', icon: Crown },
  { label: 'Alta (1080p)', desc: 'Calidad profesional', icon: Star },
  { label: 'Media (720p)', desc: 'Balance calidad/tamano', icon: Gauge },
  { label: 'Web (480p)', desc: 'Para preview rapido', icon: Zap },
];

const FORMATS = ['MP4 (H.264)', 'MP4 (H.265/HEVC)', 'MOV (ProRes)', 'WebM', 'GIF'];

export function ExportModal({ presets, onClose, projectName }: Props) {
  const [selectedPreset, setSelectedPreset] = useState(presets[1]);
  const [selectedQuality, setSelectedQuality] = useState(QUALITIES[1]);
  const [selectedFormat, setSelectedFormat] = useState(FORMATS[0]);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [showUpsell, setShowUpsell] = useState(false);

  const handleExport = () => {
    setExporting(true);
    setProgress(0);
    const interval = setInterval(() => {
      setProgress(p => {
        if (p >= 100) {
          clearInterval(interval);
          setExporting(false);
          toast.success('Video exportado exitosamente');
          onClose();
          return 100;
        }
        return p + Math.random() * 8;
      });
    }, 400);
  };

  const estimatedSize = Math.round((selectedPreset.w * selectedPreset.h * selectedPreset.fps * 0.0001) / (selectedQuality.label.includes('Ultra') ? 1 : selectedQuality.label.includes('Alta') ? 2 : selectedQuality.label.includes('Media') ? 4 : 8));

  return (
    <div className="vexport-overlay" onClick={onClose}>
      <div className="vexport-modal" onClick={e => e.stopPropagation()}>
        <div className="vexport-header">
          <h3><Download size={18} /> Exportar Video</h3>
          <button onClick={onClose}><X size={16} /></button>
        </div>

        <div className="vexport-body">
          {/* Preset Platform */}
          <div className="vexport-section">
            <h4>Plataforma destino</h4>
            <div className="vexport-presets">
              {presets.map(p => (
                <button key={p.name} className={selectedPreset.name === p.name ? 'active' : ''} onClick={() => setSelectedPreset(p)}>
                  {p.name.includes('TikTok') || p.name.includes('Reels') || p.name.includes('Stories') ? <Music size={14} /> :
                   p.name.includes('YouTube') ? <Youtube size={14} /> :
                   p.name.includes('Instagram') ? <Instagram size={14} /> :
                   p.name.includes('Twitter') ? <Twitter size={14} /> : <Video size={14} />}
                  <span>{p.name}</span>
                  <small>{p.w}x{p.h} · {p.fps}fps</small>
                </button>
              ))}
            </div>
          </div>

          {/* Quality */}
          <div className="vexport-section">
            <h4>Calidad</h4>
            <div className="vexport-qualities">
              {QUALITIES.map(q => (
                <button key={q.label} className={selectedQuality.label === q.label ? 'active' : ''} onClick={() => {
                  setSelectedQuality(q);
                  if (q.label.includes('Ultra')) setShowUpsell(true);
                }}>
                  <q.icon size={14} />
                  <span>{q.label}</span>
                  <small>{q.desc}</small>
                </button>
              ))}
            </div>
          </div>

          {/* Format */}
          <div className="vexport-section">
            <h4>Formato</h4>
            <div className="vexport-formats">
              {FORMATS.map(f => (
                <button key={f} className={selectedFormat === f ? 'active' : ''} onClick={() => setSelectedFormat(f)}>
                  {f}
                </button>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div className="vexport-summary">
            <div><span>Archivo:</span> <b>{projectName}.{selectedFormat.split(' ')[0].toLowerCase()}</b></div>
            <div><span>Resolucion:</span> <b>{selectedPreset.w}x{selectedPreset.h}</b></div>
            <div><span>FPS:</span> <b>{selectedPreset.fps}</b></div>
            <div><span>Tamano estimado:</span> <b>~{estimatedSize} MB</b></div>
            <div><span>Duracion:</span> <b>45s</b></div>
          </div>

          {/* Upsell for free users */}
          {showUpsell && (
            <div className="vexport-upsell">
              <Crown size={16} />
              <div>
                <p>Exportar en 4K Ultra requiere Sergio Studio Pro</p>
                <span>Actualiza para desbloquear calidad maxima, sin marca de agua, y exportacion prioritaria.</span>
              </div>
              <button onClick={() => toast('Redirigiendo a planes...')}>Ver planes</button>
            </div>
          )}

          {/* Watermark warning */}
          <div className="vexport-watermark">
            <AlertTriangle size={12} />
            <span>Exportacion gratuita incluye marca de agua "Sergio Studio". Eliminala con cualquier plan pago.</span>
          </div>
        </div>

        <div className="vexport-footer">
          {exporting ? (
            <div className="vexport-progress">
              <div className="vexport-progress-bar" style={{ width: `${Math.min(100, progress)}%` }} />
              <span>{Math.min(100, Math.round(progress))}% — Renderizando...</span>
            </div>
          ) : (
            <>
              <button className="vexport-cancel" onClick={onClose}>Cancelar</button>
              <button className="vexport-btn" onClick={handleExport}>
                <Sparkles size={14} /> Exportar video
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
