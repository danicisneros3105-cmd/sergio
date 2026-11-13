import { useState } from 'react';
import { Film, Sparkles, Layers, Search, Wand2, Zap, Cpu } from 'lucide-react';
import { useStudio } from '@/hooks/useStudio';
import { StudioToolbar } from './StudioToolbar';
import { StudioPreview } from './StudioPreview';
import { StudioTimeline } from './StudioTimeline';
import { StudioPanel } from './StudioPanel';
import { ChannelAnalyzer } from '../channels/ChannelAnalyzer';
import { VideoStyleEngine } from '../styleengine/VideoStyleEngine';
import { ClipFinder } from '../clipfinder/ClipFinder';
import { MotionLab } from '../motion/MotionLab';
import { VideoBoost } from '../boost/VideoBoost';
import './StudioShell.css';

const TABS = [
  { id: 'editor' as const, label: 'Editor', icon: Film },
  { id: 'channels' as const, label: 'Canales', icon: Sparkles },
  { id: 'style' as const, label: 'Estilo', icon: Layers },
  { id: 'clips' as const, label: 'Clips', icon: Search },
  { id: 'motion' as const, label: 'Motion', icon: Wand2 },
  { id: 'boost' as const, label: 'Boost', icon: Zap },
] as const;

export default function VideoStudio() {
  const studio = useStudio();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="studio-root">
      <StudioToolbar studio={studio} />

      <div className="studio-tabs">
        {TABS.map(t => {
          const Icon = t.icon;
          const active = studio.activeTab === t.id;
          return (
            <button
              key={t.id}
              className={`studio-tab ${active ? 'active' : ''}`}
              onClick={() => studio.setActiveTab(t.id)}
            >
              <Icon size={15} />
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>

      <div className="studio-body">
        {studio.activeTab === 'editor' && (
          <>
            <div className="studio-workspace">
              <StudioPreview studio={studio} />
              {sidebarOpen && <StudioPanel studio={studio} />}
            </div>
            <button
              className="sidebar-toggle"
              onClick={() => setSidebarOpen(s => !s)}
              title={sidebarOpen ? 'Ocultar panel' : 'Mostrar panel'}
            >
              {sidebarOpen ? '◀' : '▶'}
            </button>
            <StudioTimeline studio={studio} />
          </>
        )}
        {studio.activeTab === 'channels' && <ChannelAnalyzer />}
        {studio.activeTab === 'style' && <VideoStyleEngine studio={studio} />}
        {studio.activeTab === 'clips' && <ClipFinder />}
        {studio.activeTab === 'motion' && <MotionLab />}
        {studio.activeTab === 'boost' && <VideoBoost />}
      </div>
    </div>
  );
}
