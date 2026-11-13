import { Play, Pause, SkipBack, SkipForward, Volume2, Maximize2 } from 'lucide-react';

interface Props {
  studio: any;
}

export function StudioPreview({ studio }: Props) {
  const fmt = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    const ms = Math.floor((s % 1) * 100);
    return `${m}:${sec.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`;
  };

  const active = studio.clips.find((c: any) =>
    studio.currentTime >= c.start && studio.currentTime <= c.end
  );

  return (
    <div className="studio-preview">
      <div className="preview-canvas" style={{ filter: studio.previewFilter }}>
        {active?.src ? (
          <img src={active.src} alt="" />
        ) : (
          <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            Arrastra clips aqui
          </span>
        )}
        <div className="preview-overlay">
          <span className="preview-badge">PREVIEW</span>
          <span className="preview-time">{fmt(studio.currentTime)} / {fmt(studio.totalDuration)}</span>
        </div>
      </div>
      <div className="preview-controls">
        <button onClick={() => studio.seek(0)}><SkipBack size={14} /></button>
        <button className="play-btn" onClick={studio.isPlaying ? studio.pause : studio.play}>
          {studio.isPlaying ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button onClick={() => studio.seek(studio.totalDuration)}><SkipForward size={14} /></button>
        <div style={{ width: 80, display: 'flex', alignItems: 'center', gap: 4 }}>
          <Volume2 size={12} color="var(--text-muted)" />
          <input
            type="range" min={0} max={100}
            value={studio.volume}
            onChange={e => studio.setVolume(Number(e.target.value))}
            style={{ width: 60, accentColor: 'var(--accent)' }}
          />
        </div>
        <div className="spacer" />
        <button><Maximize2 size={14} /></button>
      </div>
    </div>
  );
}
