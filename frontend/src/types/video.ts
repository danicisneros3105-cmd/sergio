// ── Shared Types for Sergio Video Studio ─────────────────────────────────────

export interface Clip {
  id: string;
  name: string;
  start: number;   // seconds in timeline
  end: number;
  duration: number; // clip original duration
  track: TrackId;
  src?: string;
  type?: 'video' | 'audio' | 'image' | 'text';
  locked?: boolean;
}

export type TrackId = 'video' | 'broll' | 'graphics' | 'audio';

export interface Subtitle {
  id: string;
  start: number;
  end: number;
  text: string;
  style?: SubtitleStyle;
}

export interface SubtitleStyle {
  bold?: boolean;
  italic?: boolean;
  size?: number;
  color?: string;
  bgColor?: string;
  align?: 'left' | 'center' | 'right';
  position?: 'top' | 'center' | 'bottom';
  font?: string;
}

export interface EffectDef {
  id: string;
  name: string;
  category: 'color' | 'filter' | 'distort' | 'vfx' | 'transition';
  intensity?: number;
}

export interface MusicTrack {
  id: string;
  name: string;
  artist: string;
  genre: string;
  mood: string;
  duration: string;
  trending?: boolean;
  viral?: boolean;
}

export interface Trend {
  id: string;
  title: string;
  category: string;
  platform: string;
  growth: number;
}

export interface Shot {
  id: string;
  type: string;
  description: string;
  duration: number;
  lighting: string;
  movement: string;
  audio: string;
  notes: string;
}

export interface ChannelProfile {
  name: string;
  handle: string;
  avatar: string;
  subscribers: string;
  avgViews: string;
  style: string;
  patterns: string[];
  avgDuration: string;
  color: string;
  signature: string[];
}

export interface EditingPattern {
  id: string;
  name: string;
  channel: string;
  description: string;
  fps: number;
  cutsPerMin: number;
  zoomFreq: number;
  musicEnergy: number;
  hookStyle: string;
  colorGrade: string;
  tips: string[];
}

export interface ClipSource {
  id: string;
  title: string;
  source: string;
  duration: string;
  resolution: string;
  license: string;
  thumbnail: string;
  tags: string[];
}

export interface MotionAsset {
  id: string;
  name: string;
  type: 'template' | 'vfx' | '3d' | 'lower-third' | 'transition';
  category: string;
  preview: string;
  compatible: string[];
}

export interface BoostPreset {
  id: string;
  name: string;
  category: string;
  params: Record<string, number | string>;
}

export interface PlanInfo {
  name: string;
  price: number;
  period: string;
  channels: number;
  videos: number;
  features: string[];
  highlight?: boolean;
}
