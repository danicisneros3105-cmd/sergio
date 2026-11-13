import { useState, useCallback, useRef } from 'react';
import type { Clip, Subtitle, EffectDef } from '@/types/video';

export function useStudio() {
  const [projectName, setProjectName] = useState('Proyecto Sergio');
  const [clips, setClips] = useState<Clip[]>([]);
  const [subtitles, setSubtitles] = useState<Subtitle[]>([]);
  const [activeEffects, setActiveEffects] = useState<EffectDef[]>([]);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [volume, setVolume] = useState(80);
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'editor'|'channels'|'style'|'motion'|'clips'|'boost'>('editor');
  const [previewFilter, setPreviewFilter] = useState('');
  const [totalDuration, setTotalDuration] = useState(120);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selectedClip = clips.find(c => c.id === selectedClipId) ?? null;

  const play = useCallback(() => {
    setIsPlaying(true);
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      setCurrentTime(t => {
        if (t >= totalDuration) { setIsPlaying(false); return 0; }
        return t + 0.1;
      });
    }, 100);
  }, [totalDuration]);

  const pause = useCallback(() => {
    setIsPlaying(false);
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, []);

  const seek = useCallback((t: number) => setCurrentTime(Math.max(0, Math.min(t, totalDuration))), [totalDuration]);

  const addClip = useCallback((clip: Clip) => setClips(p => [...p, clip]), []);
  const removeClip = useCallback((id: string) => setClips(p => p.filter(c => c.id !== id)), []);
  const updateClip = useCallback((id: string, patch: Partial<Clip>) =>
    setClips(p => p.map(c => c.id === id ? { ...c, ...patch } : c)), []);

  const splitClip = useCallback((id: string, at: number) => {
    setClips(p => {
      const idx = p.findIndex(c => c.id === id);
      if (idx === -1) return p;
      const c = p[idx];
      if (at <= c.start || at >= c.end) return p;
      const left: Clip = { ...c, end: at };
      const right: Clip = { ...c, id: c.id + '_b', start: at };
      const next = [...p];
      next[idx] = left;
      next.splice(idx + 1, 0, right);
      return next;
    });
  }, []);

  const addEffect = useCallback((e: EffectDef) => setActiveEffects(p => [...p, e]), []);
  const removeEffect = useCallback((id: string) => setActiveEffects(p => p.filter(e => e.id !== id)), []);

  return {
    projectName, setProjectName,
    clips, setClips, addClip, removeClip, updateClip, splitClip,
    subtitles, setSubtitles,
    activeEffects, addEffect, removeEffect,
    currentTime, setCurrentTime, seek,
    isPlaying, play, pause,
    volume, setVolume,
    selectedClipId, setSelectedClipId, selectedClip,
    activeTab, setActiveTab,
    previewFilter, setPreviewFilter,
    totalDuration, setTotalDuration,
  };
}
