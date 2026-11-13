import { useState } from 'react';
import { Palette, Music, Type, Zap } from 'lucide-react';
import { VideoEffects } from '../panels/VideoEffects';
import { MusicLibrary } from '../panels/MusicLibrary';
import { SubtitleTool } from '../panels/SubtitleTool';
import { ViralScore } from '../panels/ViralScore';

interface Props {
  studio: any;
}

const PANELS = [
  { id: 'effects', label: 'Efectos', icon: Palette },
  { id: 'music', label: 'Musica', icon: Music },
  { id: 'subs', label: 'Subtitulos', icon: Type },
  { id: 'viral', label: 'Viral', icon: Zap },
] as const;

export function StudioPanel({ studio }: Props) {
  const [tab, setTab] = useState('effects');

  return (
    <div className="studio-panel">
      <div className="panel-tabs">
        {PANELS.map(p => (
          <button
            key={p.id}
            className={`panel-tab ${tab === p.id ? 'active' : ''}`}
            onClick={() => setTab(p.id)}
          >
            <p.icon size={12} />
          </button>
        ))}
      </div>
      <div className="panel-content">
        {tab === 'effects' && <VideoEffects studio={studio} />}
        {tab === 'music' && <MusicLibrary />}
        {tab === 'subs' && <SubtitleTool studio={studio} />}
        {tab === 'viral' && <ViralScore />}
      </div>
    </div>
  );
}
