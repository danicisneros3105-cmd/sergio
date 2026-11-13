import { useCallback, useRef, useState } from 'react';
import { Eye, EyeOff, Lock, Unlock, Scissors, Trash2, GripVertical } from 'lucide-react';
import type { VideoClip, Subtitle } from './VideoStudio';

interface Props {
  clips: VideoClip[];
  setClips: React.Dispatch<React.SetStateAction<VideoClip[]>>;
  subtitles: Subtitle[];
  currentTime: number;
  totalDuration: number;
  selectedClipId: string | null;
  setSelectedClipId: (id: string | null) => void;
  zoom: number;
}

const TRACK_LABELS = ['Video Principal', 'B-Roll / Overlay', 'Graphics / Text', 'Audio / Musica'];
const TRACK_COLORS = ['#e8b86d20', '#00f5d420', '#ff6b9d20', '#a78bfa20'];

export function VideoTimeline({ clips, setClips, subtitles, currentTime, totalDuration, selectedClipId, setSelectedClipId, zoom }: Props) {
  const [dragging, setDragging] = useState<string | null>(null);
  const [resizing, setResizing] = useState<{ id: string; edge: 'left' | 'right' } | null>(null);
  const [lockedTracks, setLockedTracks] = useState<Set<number>>(new Set());
  const timelineRef = useRef<HTMLDivElement>(null);
  const startXRef = useRef(0);
  const startStartRef = useRef(0);
  const startEndRef = useRef(0);

  const pxPerSecond = 40 * zoom;
  const totalWidth = totalDuration * pxPerSecond;

  const handleMouseDown = useCallback((e: React.MouseEvent, clipId: string, edge?: 'left' | 'right') => {
    e.stopPropagation();
    setSelectedClipId(clipId);
    const clip = clips.find((c) => c.id === clipId);
    if (!clip) return;
    if (edge) {
      setResizing({ id: clipId, edge });
      startXRef.current = e.clientX;
      startStartRef.current = clip.start;
      startEndRef.current = clip.end;
    } else {
      setDragging(clipId);
      startXRef.current = e.clientX;
      startStartRef.current = clip.start;
      startEndRef.current = clip.end;
    }
  }, [clips, setSelectedClipId]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!timelineRef.current) return;
    const deltaPx = e.clientX - startXRef.current;
    const deltaSec = deltaPx / pxPerSecond;

    if (resizing) {
      setClips((prev) => prev.map((c) => {
        if (c.id !== resizing.id) return c;
        if (resizing.edge === 'left') {
          return { ...c, start: Math.max(0, Math.min(c.end - 0.5, startStartRef.current + deltaSec)) };
        }
        return { ...c, end: Math.max(c.start + 0.5, startEndRef.current + deltaSec) };
      }));
    } else if (dragging) {
      setClips((prev) => prev.map((c) => {
        if (c.id !== dragging) return c;
        const duration = c.end - c.start;
        const newStart = Math.max(0, startStartRef.current + deltaSec);
        return { ...c, start: newStart, end: newStart + duration };
      }));
    }
  }, [dragging, resizing, pxPerSecond, setClips]);

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    setResizing(null);
  }, []);

  const splitClip = useCallback((clipId: string) => {
    setClips((prev) => {
      const idx = prev.findIndex((c) => c.id === clipId);
      if (idx === -1) return prev;
      const clip = prev[idx];
      const splitAt = currentTime;
      if (splitAt <= clip.start || splitAt >= clip.end) return prev;
      const left = { ...clip, end: splitAt };
      const right = { ...clip, id: `c${Date.now()}`, start: splitAt };
      return [...prev.slice(0, idx), left, right, ...prev.slice(idx + 1)];
    });
  }, [currentTime, setClips]);

  const deleteClip = useCallback((clipId: string) => {
    setClips((prev) => prev.filter((c) => c.id !== clipId));
  }, [setClips]);

  const toggleVisibility = useCallback((clipId: string) => {
    setClips((prev) => prev.map((c) => c.id === clipId ? { ...c, visible: !c.visible } : c));
  }, [setClips]);

  const toggleTrackLock = useCallback((trackIdx: number) => {
    setLockedTracks((prev) => {
      const next = new Set(prev);
      if (next.has(trackIdx)) next.delete(trackIdx);
      else next.add(trackIdx);
      return next;
    });
  }, []);

  return (
    <div className="vtimeline" ref={timelineRef} onMouseMove={handleMouseMove} onMouseUp={handleMouseUp} onMouseLeave={handleMouseUp}>
      {/* Ruler */}
      <div className="vtimeline-ruler" style={{ width: totalWidth }}>
        {Array.from({ length: Math.ceil(totalDuration) + 1 }).map((_, i) => (
          <div key={i} className="vtimeline-marker" style={{ left: i * pxPerSecond }}>
            <span>{i}s</span>
          </div>
        ))}
        <div className="vtimeline-playhead" style={{ left: currentTime * pxPerSecond }}>
          <div className="vtimeline-playhead-line" />
        </div>
      </div>

      {/* Tracks */}
      <div className="vtimeline-tracks">
        {Array.from({ length: 4 }).map((_, trackIdx) => (
          <div key={trackIdx} className="vtimeline-track" style={{ backgroundColor: TRACK_COLORS[trackIdx] }}>
            <div className="vtimeline-track-header">
              <span>{TRACK_LABELS[trackIdx]}</span>
              <button onClick={() => toggleTrackLock(trackIdx)}>{lockedTracks.has(trackIdx) ? <Lock size={12} /> : <Unlock size={12} />}</button>
            </div>
            <div className="vtimeline-track-lane" style={{ width: totalWidth, position: 'relative' }}>
              {clips.filter((c) => c.track === trackIdx).map((clip) => (
                <div
                  key={clip.id}
                  className={`vtimeline-clip ${selectedClipId === clip.id ? 'selected' : ''} ${!clip.visible ? 'hidden' : ''}`}
                  style={{
                    left: clip.start * pxPerSecond,
                    width: (clip.end - clip.start) * pxPerSecond,
                    backgroundColor: clip.color,
                    borderColor: clip.color,
                  }}
                  onMouseDown={(e) => !lockedTracks.has(trackIdx) && handleMouseDown(e, clip.id)}
                  onDoubleClick={() => splitClip(clip.id)}
                >
                  <div className="vtimeline-clip-resize left" onMouseDown={(e) => { e.stopPropagation(); handleMouseDown(e, clip.id, 'left'); }} />
                  <div className="vtimeline-clip-content">
                    <span className="vtimeline-clip-name">{clip.name}</span>
                    <span className="vtimeline-clip-time">{clip.start.toFixed(1)}s - {clip.end.toFixed(1)}s</span>
                  </div>
                  <div className="vtimeline-clip-resize right" onMouseDown={(e) => { e.stopPropagation(); handleMouseDown(e, clip.id, 'right'); }} />
                  <div className="vtimeline-clip-actions">
                    <button onClick={(e) => { e.stopPropagation(); toggleVisibility(clip.id); }}>{clip.visible ? <Eye size={10} /> : <EyeOff size={10} />}</button>
                    <button onClick={(e) => { e.stopPropagation(); deleteClip(clip.id); }}><Trash2 size={10} /></button>
                  </div>
                </div>
              ))}
              {/* Subtitles on track 2 */}
              {trackIdx === 2 && subtitles.map((sub) => (
                <div
                  key={sub.id}
                  className="vtimeline-subtitle"
                  style={{
                    left: sub.start * pxPerSecond,
                    width: (sub.end - sub.start) * pxPerSecond,
                  }}
                  onClick={() => { /* edit subtitle */ }}
                >
                  {sub.text.slice(0, 20)}{sub.text.length > 20 ? '...' : ''}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
