import { useRef, useCallback } from 'react';
import { Lock, Unlock, Scissors, Trash2 } from 'lucide-react';

const TRACKS = [
  { id: 'video', label: 'Video', color: '#d4a853' },
  { id: 'broll', label: 'B-Roll', color: '#2dd4bf' },
  { id: 'graphics', label: 'Graficos', color: '#a78bfa' },
  { id: 'audio', label: 'Audio', color: '#f472b6' },
] as const;

interface Props {
  studio: any;
}

export function StudioTimeline({ studio }: Props) {
  const laneRef = useRef<HTMLDivElement>(null);

  const pxPerSec = 8;
  const totalW = studio.totalDuration * pxPerSec;

  const splitAt = useCallback(() => {
    if (!studio.selectedClipId) return;
    studio.splitClip(studio.selectedClipId, studio.currentTime);
  }, [studio]);

  const deleteClip = useCallback(() => {
    if (!studio.selectedClipId) return;
    studio.removeClip(studio.selectedClipId);
    studio.setSelectedClipId(null);
  }, [studio]);

  return (
    <div className="studio-timeline">
      <div className="timeline-toolbar">
        <button onClick={splitAt} title="Dividir clip"><Scissors size={12} /></button>
        <button onClick={deleteClip} title="Eliminar clip"><Trash2 size={12} /></button>
        <span style={{ color: 'var(--text-muted)', fontSize: 10, marginLeft: 8 }}>
          {studio.clips.length} clips
        </span>
      </div>

      <div className="timeline-ruler" style={{ width: Math.max(totalW, 800) }}>
        {Array.from({ length: Math.ceil(studio.totalDuration / 5) + 1 }, (_, i) => {
          const s = i * 5;
          return (
            <span key={s}>
              <span className="tick major" style={{ left: s * pxPerSec }} />
              <span className="tick-label" style={{ left: s * pxPerSec }}>
                {Math.floor(s / 60)}:{(s % 60).toString().padStart(2, '0')}
              </span>
            </span>
          );
        })}
        <div className="timeline-playhead" style={{ left: studio.currentTime * pxPerSec }} />
      </div>

      <div className="timeline-tracks" ref={laneRef}>
        {TRACKS.map(t => (
          <div className="timeline-track" key={t.id}>
            <div className="track-label" style={{ color: t.color }}>
              {t.label}
            </div>
            <div className="track-lane" style={{ minWidth: Math.max(totalW, 800) }}>
              {studio.clips
                .filter((c: any) => c.track === t.id)
                .map((c: any) => (
                  <div
                    key={c.id}
                    className={`timeline-clip ${studio.selectedClipId === c.id ? 'selected' : ''}`}
                    style={{
                      left: c.start * pxPerSec,
                      width: (c.end - c.start) * pxPerSec,
                      background: `${t.color}22`,
                      color: t.color,
                      borderColor: `${t.color}44`,
                    }}
                    onClick={() => studio.setSelectedClipId(c.id)}
                  >
                    {c.name}
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
