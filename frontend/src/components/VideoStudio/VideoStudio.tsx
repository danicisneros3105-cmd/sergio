import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  Play, Pause, SkipBack, SkipForward, Scissors, Plus, Minus,
  Volume2, VolumeX, Maximize, Film, Music, Type, Wand2,
  Sparkles, Zap, Download, Clock, Trash2,
  Undo, Redo, Flame, TrendingUp,
  Target, Palette, Sun, Moon, Wind, ScanLine,
  Subtitles, Mic, Image as ImageIcon, Video,
  MousePointer, RotateCcw, Crop,
  Bold, Italic,
  Gauge, BarChart3, Eye, EyeOff,
  Save, FolderOpen, Crown, Star, Trophy,
} from 'lucide-react';
import { VideoTimeline } from './VideoTimeline';
import { VideoEffects } from './VideoEffects';
import { SubtitleTool } from './SubtitleTool';
import { MusicLibrary } from './MusicLibrary';
import { TrendRadar } from './TrendRadar';
import { ViralScore } from './ViralScore';
import { ShotPlanner } from './ShotPlanner';
import { ExportModal } from './ExportModal';
import './VideoStudio.css';

export interface VideoClip {
  id: string;
  name: string;
  type: 'video' | 'image' | 'audio';
  src: string;
  start: number;
  end: number;
  track: number;
  visible: boolean;
  effects: string[];
  color: string;
}

export interface Subtitle {
  id: string;
  text: string;
  start: number;
  end: number;
}

const PRESETS = [
  { name: 'YouTube 4K', w: 3840, h: 2160, fps: 60 },
  { name: 'YouTube 1080p', w: 1920, h: 1080, fps: 30 },
  { name: 'TikTok/Reels', w: 1080, h: 1920, fps: 30 },
  { name: 'Instagram Feed', w: 1080, h: 1080, fps: 30 },
  { name: 'Twitter/X', w: 1280, h: 720, fps: 30 },
  { name: 'Stories', w: 1080, h: 1920, fps: 30 },
  { name: 'IMAX', w: 4096, h: 2160, fps: 24 },
  { name: 'CinemaScope', w: 2560, h: 1080, fps: 24 },
];

const DEMO_CLIPS: VideoClip[] = [
  { id: 'c1', name: 'Aerial City', type: 'video', src: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4', start: 0, end: 8, track: 0, visible: true, effects: [], color: '#e8b86d' },
  { id: 'c2', name: 'Ocean Waves', type: 'video', src: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4', start: 8, end: 16, track: 0, visible: true, effects: [], color: '#00f5d4' },
  { id: 'c3', name: 'Logo Reveal', type: 'image', src: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800', start: 2, end: 6, track: 1, visible: true, effects: ['glow'], color: '#ff6b9d' },
  { id: 'c4', name: 'BG Music', type: 'audio', src: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerMeltdowns.mp4', start: 0, end: 20, track: 3, visible: true, effects: [], color: '#a78bfa' },
];

const DEMO_SUBS: Subtitle[] = [
  { id: 's1', text: 'Bienvenido a Sergio Studio', start: 0, end: 3 },
  { id: 's2', text: 'Edicion profesional con IA', start: 3, end: 6 },
  { id: 's3', text: 'Crea contenido viral en minutos', start: 6, end: 9 },
  { id: 's4', text: 'Efectos de Hollywood al alcance', start: 9, end: 12 },
];

const VFX_CHIPS = [
  { name: 'Cinematic', color: '#e8b86d' },
  { name: 'Neon Glow', color: '#00f5d4' },
  { name: 'Glitch', color: '#ff6b6b' },
  { name: 'Vintage', color: '#fdcb6e' },
  { name: 'B&W', color: '#a1a1aa' },
  { name: 'Motion Blur', color: '#74b9ff' },
  { name: 'Chroma Key', color: '#00b894' },
  { name: 'Lens Flare', color: '#e17055' },
];

export default function VideoStudio() {
  const [projectName, setProjectName] = useState('Mi Proyecto Viral');
  const [clips, setClips] = useState<VideoClip[]>(DEMO_CLIPS);
  const [subtitles, setSubtitles] = useState<Subtitle[]>(DEMO_SUBS);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [volume, setVolume] = useState(0.8);
  const [isMuted, setIsMuted] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [activeTab, setActiveTab] = useState<'effects' | 'subtitles' | 'music' | 'trends' | 'viral' | 'shots'>('effects');
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [showExport, setShowExport] = useState(false);
  const [previewFilter, setPreviewFilter] = useState('');
  const [streakDays] = useState(() => {
    try {
      const s = Number(localStorage.getItem('sergio-streak-days') || '12');
      return s;
    } catch {
      return 12;
    }
  });
  const videoRef = useRef<HTMLVideoElement>(null);
  const rafRef = useRef<number>(0);

  const totalDuration = useMemo(() => Math.max(...clips.map((c) => c.end), 20), [clips]);

  const currentSub = useMemo(
    () => subtitles.find((s) => currentTime >= s.start && currentTime < s.end),
    [subtitles, currentTime],
  );

  useEffect(() => {
    if (!isPlaying) {
      cancelAnimationFrame(rafRef.current);
      return;
    }
    const tick = () => {
      setCurrentTime((t) => {
        if (t >= totalDuration) {
          setIsPlaying(false);
          return totalDuration;
        }
        return t + 0.033;
      });
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [isPlaying, totalDuration]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.volume = isMuted ? 0 : volume;
    }
  }, [volume, isMuted]);

  const addClip = useCallback(() => {
    const id = `c${Date.now()}`;
    const colors = ['#e8b86d', '#00f5d4', '#ff6b9d', '#a78bfa', '#74b9ff', '#fdcb6e'];
    const color = colors[Math.floor(Math.random() * colors.length)];
    setClips((prev) => [
      ...prev,
      { id, name: `Clip ${prev.length + 1}`, type: 'video', src: '', start: currentTime, end: currentTime + 5, track: 0, visible: true, effects: [], color },
    ]);
    setSelectedClipId(id);
    toast.success('Clip agregado');
  }, [currentTime]);

  const deleteSelected = useCallback(() => {
    if (!selectedClipId) return;
    setClips((prev) => prev.filter((c) => c.id !== selectedClipId));
    setSelectedClipId(null);
    toast.success('Clip eliminado');
  }, [selectedClipId]);

  const togglePlay = useCallback(() => setIsPlaying((p) => !p), []);
  const skipBack = useCallback(() => setCurrentTime((t) => Math.max(0, t - 5)), []);
  const skipForward = useCallback(() => setCurrentTime((t) => Math.min(totalDuration, t + 5)), [totalDuration]);
  const resetTime = useCallback(() => { setCurrentTime(0); setIsPlaying(false); }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === ' ') {
      e.preventDefault();
      togglePlay();
    } else if (e.key === 'ArrowLeft') {
      setCurrentTime((t) => Math.max(0, t - 1));
    } else if (e.key === 'ArrowRight') {
      setCurrentTime((t) => Math.min(totalDuration, t + 1));
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      deleteSelected();
    }
  }, [togglePlay, totalDuration, deleteSelected]);

  const activeVideoClip = useMemo(
    () => clips.find((c) => c.type === 'video' && currentTime >= c.start && currentTime < c.end && c.visible),
    [clips, currentTime],
  );

  const formatTime = (t: number) => {
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    const ms = Math.floor((t % 1) * 100);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`;
  };

  return (
    <div className="video-studio" tabIndex={0} onKeyDown={handleKeyDown}>
      {/* Top Bar */}
      <div className="vs-topbar">
        <div className="vs-topbar-left">
          <div className="vs-project">
            <input className="vs-project-name" value={projectName} onChange={(e) => setProjectName(e.target.value)} />
            <span className="vs-project-badge">Sergio Studio · Proyecto sin guardar</span>
          </div>
          {streakDays > 0 && (
            <div className="vs-streak"><Flame size={12} /> {streakDays} dias</div>
          )}
        </div>
        <div className="vs-topbar-center">
          <button title="Deshacer"><Undo size={16} /></button>
          <button title="Rehacer"><Redo size={16} /></button>
          <span className="vs-divider" />
          <button title="Cortar (C)" onClick={() => { const id = selectedClipId; if (id) setClips((prev) => prev.map((c) => c.id === id ? { ...c, end: currentTime } : c)); toast.success('Corte aplicado'); }}><Scissors size={16} /></button>
          <button title="Agregar clip (+)" onClick={addClip}><Plus size={16} /></button>
          <button title="Eliminar clip (Del)" onClick={deleteSelected}><Trash2 size={16} /></button>
          <span className="vs-divider" />
          <button className="vs-export-btn" onClick={() => setShowExport(true)}><Download size={14} /> Exportar</button>
        </div>
        <div className="vs-topbar-right">
          <button title="Guardar"><Save size={16} /></button>
          <button title="Abrir"><FolderOpen size={16} /></button>
        </div>
      </div>

      {/* Quick VFX Strip */}
      <div className="vs-vfx-strip">
        {VFX_CHIPS.map((vfx) => (
          <button key={vfx.name} className="vs-vfx-chip" onClick={() => setPreviewFilter(vfx.name.toLowerCase().replace(' ', '-'))}>
            <Sparkles size={12} color={vfx.color} /> {vfx.name}
          </button>
        ))}
      </div>

      {/* Workspace */}
      <div className="vs-workspace">
        {/* Left Panel */}
        <div className="vs-left-panel">
          <div className="vs-tabs">
            <button className={activeTab === 'effects' ? 'active' : ''} onClick={() => setActiveTab('effects')} title="Efectos"><Palette size={18} /></button>
            <button className={activeTab === 'subtitles' ? 'active' : ''} onClick={() => setActiveTab('subtitles')} title="Subtitulos"><Subtitles size={18} /></button>
            <button className={activeTab === 'music' ? 'active' : ''} onClick={() => setActiveTab('music')} title="Musica"><Music size={18} /></button>
            <button className={activeTab === 'trends' ? 'active' : ''} onClick={() => setActiveTab('trends')} title="Trends"><TrendingUp size={18} /></button>
            <button className={activeTab === 'viral' ? 'active' : ''} onClick={() => setActiveTab('viral')} title="Viral Score"><Zap size={18} /></button>
            <button className={activeTab === 'shots' ? 'active' : ''} onClick={() => setActiveTab('shots')} title="Shot Planner"><Target size={18} /></button>
          </div>
          <div className="vs-panel-content">
            {activeTab === 'effects' && <VideoEffects selectedClipId={selectedClipId} clips={clips} setClips={setClips} />}
            {activeTab === 'subtitles' && <SubtitleTool subtitles={subtitles} setSubtitles={setSubtitles} currentTime={currentTime} />}
            {activeTab === 'music' && <MusicLibrary />}
            {activeTab === 'trends' && <TrendRadar />}
            {activeTab === 'viral' && <ViralScore clips={clips} subtitles={subtitles} />}
            {activeTab === 'shots' && <ShotPlanner />}
          </div>
        </div>

        {/* Center: Preview + Timeline */}
        <div className="vs-center">
          <div className="vs-preview">
            <div className="vs-preview-screen">
              {activeVideoClip ? (
                <video
                  ref={videoRef}
                  className="vs-preview-video"
                  src={activeVideoClip.src}
                  style={{ filter: previewFilter }}
                  muted={isMuted}
                />
              ) : (
                <div className="vs-preview-screen" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#52525b', fontSize: 14 }}>
                  <Film size={48} style={{ opacity: 0.2 }} />
                </div>
              )}
              {currentSub && (
                <div className="vs-subtitle-overlay" style={{ bottom: '15%' }}>
                  {currentSub.text}
                </div>
              )}
              <div className="vs-watermark">SERGIO STUDIO</div>
            </div>

            {/* Transport Controls */}
            <div className="vs-transport">
              <div className="vs-transport-left">
                <button onClick={resetTime}><RotateCcw size={14} /></button>
                <button onClick={skipBack}><SkipBack size={16} /></button>
                <button className="vs-play-btn" onClick={togglePlay}>{isPlaying ? <Pause size={18} /> : <Play size={18} />}</button>
                <button onClick={skipForward}><SkipForward size={16} /></button>
                <span className="vs-time">{formatTime(currentTime)} / {formatTime(totalDuration)}</span>
              </div>
              <div className="vs-transport-right">
                <button onClick={() => setIsMuted((m) => !m)}>{isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}</button>
                <input className="vs-volume" type="range" min={0} max={1} step={0.05} value={volume} onChange={(e) => setVolume(Number(e.target.value))} />
                <button onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}><Minus size={12} /></button>
                <span className="vs-zoom">{Math.round(zoom * 100)}%</span>
                <button onClick={() => setZoom((z) => Math.min(4, z + 0.25))}><Plus size={12} /></button>
                <button><Maximize size={14} /></button>
              </div>
            </div>

            {/* Progress Bar */}
            <div className="vs-progress-bar" onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const pct = (e.clientX - rect.left) / rect.width;
              setCurrentTime(pct * totalDuration);
            }}>
              <div className="vs-progress-fill" style={{ width: `${(currentTime / totalDuration) * 100}%` }} />
              <div className="vs-progress-handle" style={{ left: `${(currentTime / totalDuration) * 100}%` }} />
              {/* Chapter markers */}
              <div className="vs-chapter" style={{ left: '0%' }} title="Intro" />
              <div className="vs-chapter" style={{ left: '25%' }} title="Hook" />
              <div className="vs-chapter" style={{ left: '70%' }} title="CTA" />
            </div>
          </div>

          {/* Timeline */}
          <div className="vs-timeline-wrap">
            <VideoTimeline
              clips={clips}
              setClips={setClips}
              subtitles={subtitles}
              currentTime={currentTime}
              totalDuration={totalDuration}
              selectedClipId={selectedClipId}
              setSelectedClipId={setSelectedClipId}
              zoom={zoom}
            />
          </div>
        </div>
      </div>

      {showExport && <ExportModal presets={PRESETS} onClose={() => setShowExport(false)} projectName={projectName} />}
    </div>
  );
}
