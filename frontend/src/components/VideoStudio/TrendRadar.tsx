import { useState } from 'react';
import { TrendingUp, Sparkles, Hash, Flame, Music, Video, Zap, Wand2 } from 'lucide-react';
import { toast } from 'sonner';

interface Trend {
  id: string;
  hashtag: string;
  platform: string;
  category: string;
  views: string;
  growth: number;
  hook: string;
  audio: string;
}

const TRENDS: Trend[] = [
  { id: 'tr1', hashtag: '#DayInMyLife', platform: 'TikTok', category: 'lifestyle', views: '2.4B', growth: 145, hook: 'POV: tu dia en 60 segundos', audio: 'lofi beats trending' },
  { id: 'tr2', hashtag: '#GlowUp', platform: 'Instagram', category: 'beauty', views: '890M', growth: 89, hook: 'Antes vs Despues transformacion', audio: 'emotional cinematic' },
  { id: 'tr3', hashtag: '#LearnOnTikTok', platform: 'TikTok', category: 'educacion', views: '3.1B', growth: 203, hook: 'Esto te cambiara la vida', audio: 'upbeat corporate' },
  { id: 'tr4', hashtag: '#BehindTheScenes', platform: 'YouTube', category: 'creator', views: '1.2B', growth: 67, hook: 'Asi se hizo este video', audio: 'curious ambient' },
  { id: 'tr5', hashtag: '#QuickRecipes', platform: 'Instagram', category: 'food', views: '560M', growth: 112, hook: 'Receta en 15 segundos', audio: 'tropical vibes' },
  { id: 'tr6', hashtag: '#FitnessMotivation', platform: 'TikTok', category: 'fitness', views: '1.8B', growth: 78, hook: 'Resultados en 30 dias', audio: 'hype beat trap' },
  { id: 'tr7', hashtag: '#TechReview', platform: 'YouTube', category: 'tech', views: '720M', growth: 55, hook: 'Este gadget es increible', audio: 'electronic synth' },
  { id: 'tr8', hashtag: '#ComedySketch', platform: 'TikTok', category: 'comedy', views: '4.5B', growth: 310, hook: 'Cuando tu amigo dice...', audio: 'funny sound effects' },
];

export function TrendRadar() {
  const [category, setCategory] = useState('all');
  const [platform, setPlatform] = useState('all');
  const [generating, setGenerating] = useState(false);
  const [idea, setIdea] = useState<string | null>(null);

  const categories = ['all', ...Array.from(new Set(TRENDS.map((t) => t.category)))];
  const platforms = ['all', ...Array.from(new Set(TRENDS.map((t) => t.platform)))];

  const filtered = TRENDS.filter((t) => {
    if (category !== 'all' && t.category !== category) return false;
    if (platform !== 'all' && t.platform !== platform) return false;
    return true;
  });

  const generateIdea = () => {
    setGenerating(true);
    setTimeout(() => {
      setGenerating(false);
      const trend = filtered[Math.floor(Math.random() * filtered.length)];
      const ideas = [
        `Crea un video ${trend.category} usando el audio "${trend.audio}". Hook: ${trend.hook}. Usa transiciones rapidas en los primeros 3 segundos.`,
        `Video tipo "${trend.hashtag}" para ${trend.platform}. Empieza con un primer plano impactante y anade texto en pantalla cada 2 segundos.`,
        `Toma el trend "${trend.hashtag}" y dale tu propio giro. Agrega un plot twist en el segundo 5 para retencion.`,
      ];
      setIdea(ideas[Math.floor(Math.random() * ideas.length)]);
      toast.success('IA genero una idea viral');
    }, 1500);
  };

  return (
    <div>
      <div className="vtrends-header">
        <h4><TrendingUp size={14} /> Trend Radar</h4>
        <div className="vtrends-live">
          <span className="pulse" />
          <span>En vivo</span>
        </div>
      </div>

      <div className="vtrends-filters">
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          {categories.map((c) => <option key={c} value={c}>{c === 'all' ? 'Todas' : c}</option>)}
        </select>
        <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
          {platforms.map((p) => <option key={p} value={p}>{p === 'all' ? 'Todas' : p}</option>)}
        </select>
      </div>

      <div className="vtrends-list">
        {filtered.map((trend) => (
          <div key={trend.id} className={`vtrend-card ${trend.growth > 150 ? 'hot' : ''}`}>
            <div className="vtrend-top">
              <span className="vtrend-hashtag">{trend.hashtag}</span>
              {trend.growth > 150 && (
                <span className="vtrend-hot"><Flame size={10} /> {trend.growth}%</span>
              )}
            </div>
            <div className="vtrend-meta">
              <span>{trend.platform === 'TikTok' ? <Music size={10} /> : trend.platform === 'YouTube' ? <Video size={10} /> : <Zap size={10} />} {trend.platform}</span>
              <span>{trend.views} vistas</span>
              <span style={{ color: trend.growth > 100 ? '#00f5d4' : '#e8b86d' }}>+{trend.growth}%</span>
            </div>
            <div className="vtrend-hook"><Hash size={10} /> Hook: {trend.hook}</div>
            <div className="vtrend-audio"><Music size={10} /> Audio: {trend.audio}</div>
            <button className="vtrend-use" onClick={() => toast.success(`Trend "${trend.hashtag}" agregado al proyecto`)}>
              <Sparkles size={10} /> Usar trend
            </button>
          </div>
        ))}
      </div>

      <div className="vtrends-generator">
        <button onClick={generateIdea} disabled={generating}>
          <Wand2 size={14} /> {generating ? 'Generando idea viral...' : 'Generar idea con IA'}
        </button>
        {idea && (
          <div className="vtrends-idea">
            <Sparkles size={14} />
            <span>{idea}</span>
          </div>
        )}
      </div>
    </div>
  );
}
