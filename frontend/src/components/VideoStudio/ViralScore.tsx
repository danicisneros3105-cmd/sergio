import { useState, useEffect, useMemo } from 'react';
import { Zap, TrendingUp, Eye, Clock, MessageCircle, Share2, Heart, AlertTriangle, CheckCircle, Sparkles, Gauge, BarChart3, Target, Flame, Trophy, Star } from 'lucide-react';
import type { VideoClip, Subtitle } from './VideoStudio';

interface Props {
  clips: VideoClip[];
  subtitles: Subtitle[];
}

interface ScoreBreakdown {
  hook: number;
  pacing: number;
  audio: number;
  visuals: number;
  length: number;
  text: number;
  overall: number;
}

interface Tip {
  icon: React.ReactNode;
  text: string;
  priority: 'high' | 'medium' | 'low';
}

export function ViralScore({ clips, subtitles }: Props) {
  const [score, setScore] = useState<ScoreBreakdown | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const totalDuration = useMemo(() => Math.max(...clips.map(c => c.end), 0), [clips]);
  const hasAudio = clips.some(c => c.type === 'audio');
  const hasSubtitles = subtitles.length > 0;
  const clipCount = clips.filter(c => c.type === 'video' || c.type === 'image').length;

  useEffect(() => {
    setAnalyzing(true);
    const timer = setTimeout(() => {
      const hook = Math.min(95, 40 + clipCount * 12 + (hasSubtitles ? 15 : 0));
      const pacing = totalDuration < 15 ? 90 : totalDuration < 60 ? 80 : totalDuration < 180 ? 65 : 50;
      const audio = hasAudio ? 85 : 45;
      const visuals = Math.min(95, 50 + clipCount * 8 + (clips.some(c => c.effects.length > 0) ? 15 : 0));
      const length = totalDuration < 15 ? 95 : totalDuration < 30 ? 88 : totalDuration < 60 ? 78 : totalDuration < 180 ? 65 : 40;
      const text = hasSubtitles ? 90 : 55;
      const overall = Math.round((hook + pacing + audio + visuals + length + text) / 6);
      setScore({ hook, pacing, audio, visuals, length, text, overall });
      setAnalyzing(false);
    }, 2000);
    return () => clearTimeout(timer);
  }, [clips, subtitles, totalDuration, hasAudio, hasSubtitles, clipCount]);

  const tips: Tip[] = useMemo(() => {
    const t: Tip[] = [];
    if (totalDuration > 60) t.push({ icon: <Clock size={12} />, text: 'Considera recortar a menos de 60s para mejor retencion', priority: 'high' });
    if (!hasSubtitles) t.push({ icon: <AlertTriangle size={12} />, text: 'Agrega subtitulos: el 85% ve videos sin sonido', priority: 'high' });
    if (!hasAudio) t.push({ icon: <AlertTriangle size={12} />, text: 'Agrega musica o SFX para mejor engagement', priority: 'high' });
    if (clipCount < 3) t.push({ icon: <Sparkles size={12} />, text: 'Usa mas cortes en los primeros 3 segundos (hook)', priority: 'medium' });
    if (!clips.some(c => c.effects.length > 0)) t.push({ icon: <Sparkles size={12} />, text: 'Aplica un efecto visual para destacar', priority: 'medium' });
    if (totalDuration < 15) t.push({ icon: <CheckCircle size={12} />, text: 'Duracion perfecta para Shorts/Reels', priority: 'low' });
    if (hasSubtitles && subtitles.length > 5) t.push({ icon: <CheckCircle size={12} />, text: 'Buena densidad de subtitulos', priority: 'low' });
    return t;
  }, [totalDuration, hasSubtitles, hasAudio, clipCount, clips, subtitles.length]);

  const getGrade = (s: number) => {
    if (s >= 90) return { label: 'VIRAL', color: '#00f5d4', icon: <Trophy size={14} /> };
    if (s >= 75) return { label: 'BUENO', color: '#e8b86d', icon: <Star size={14} /> };
    if (s >= 60) return { label: 'REGULAR', color: '#fdcb6e', icon: <Gauge size={14} /> };
    return { label: 'MEJORAR', color: '#ff6b6b', icon: <AlertTriangle size={14} /> };
  };

  if (analyzing) {
    return (
      <div className="vviral">
        <div className="vviral-analyzing">
          <Sparkles size={24} className="spin" />
          <p>Analizando potencial viral con IA...</p>
          <span>Escaneando hook, pacing, audio, visuales y texto</span>
        </div>
      </div>
    );
  }

  if (!score) return null;

  const grade = getGrade(score.overall);

  return (
    <div className="vviral">
      <div className="vviral-header">
        <h4><Zap size={15} /> Viral Score</h4>
        <button onClick={() => setShowDetails(!showDetails)}>{showDetails ? 'Resumen' : 'Detalles'}</button>
      </div>

      <div className="vviral-score-ring">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="42" fill="none" stroke="#1a1a2e" strokeWidth="8" />
          <circle
            cx="50" cy="50" r="42" fill="none" stroke={grade.color}
            strokeWidth="8" strokeLinecap="round"
            strokeDasharray={`${score.overall * 2.64} 264`}
            transform="rotate(-90 50 50)"
          />
        </svg>
        <div className="vviral-score-value" style={{ color: grade.color }}>
          <span>{score.overall}</span>
          <small>{grade.label}</small>
        </div>
      </div>

      {showDetails && (
        <div className="vviral-breakdown">
          {[
            { key: 'hook', label: 'Hook (primeros 3s)', icon: <Flame size={10} /> },
            { key: 'pacing', label: 'Ritmo / Pacing', icon: <Gauge size={10} /> },
            { key: 'audio', label: 'Audio / Musica', icon: <BarChart3 size={10} /> },
            { key: 'visuals', label: 'Visuales / Efectos', icon: <Eye size={10} /> },
            { key: 'length', label: 'Duracion optima', icon: <Clock size={10} /> },
            { key: 'text', label: 'Texto / Subtitulos', icon: <MessageCircle size={10} /> },
          ].map(item => {
            const val = score[item.key as keyof ScoreBreakdown] as number;
            return (
              <div key={item.key} className="vviral-metric">
                <div className="vviral-metric-label">{item.icon} {item.label}</div>
                <div className="vviral-metric-bar">
                  <div className="vviral-metric-fill" style={{ width: `${val}%`, backgroundColor: val >= 80 ? '#00f5d4' : val >= 60 ? '#e8b86d' : '#ff6b6b' }} />
                </div>
                <span>{val}</span>
              </div>
            );
          })}
        </div>
      )}

      <div className="vviral-tips">
        <h5><Target size={12} /> Recomendaciones</h5>
        {tips.map((tip, i) => (
          <div key={i} className={`vviral-tip ${tip.priority}`}>
            {tip.icon}
            <span>{tip.text}</span>
          </div>
        ))}
      </div>

      <div className="vviral-prediction">
        <h5><TrendingUp size={12} /> Proyeccion estimada</h5>
        <div className="vviral-stats">
          <span><Eye size={10} /> {score.overall >= 90 ? '500K+' : score.overall >= 75 ? '100K+' : score.overall >= 60 ? '50K+' : '10K+'} vistas</span>
          <span><Heart size={10} /> {score.overall >= 90 ? '50K+' : score.overall >= 75 ? '10K+' : score.overall >= 60 ? '5K+' : '1K+'} likes</span>
          <span><Share2 size={10} /> {score.overall >= 90 ? '10K+' : score.overall >= 75 ? '2K+' : score.overall >= 60 ? '500+' : '100+'} shares</span>
        </div>
      </div>
    </div>
  );
}
