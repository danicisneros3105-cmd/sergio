import { useState } from 'react';
import { Music, Search, Play, Pause, Heart, Plus, Volume2, Sparkles, Zap } from 'lucide-react';
import { toast } from 'sonner';

interface Track {
  id: string;
  name: string;
  artist: string;
  genre: string;
  mood: string;
  duration: string;
  trending?: boolean;
  viral?: boolean;
}

const TRACKS: Track[] = [
  { id: 't1', name: 'Neon Nights', artist: 'SynthWave Pro', genre: 'electronic', mood: 'energetic', duration: '2:34', trending: true },
  { id: 't2', name: 'City Lights', artist: 'LoFi Beats', genre: 'lofi', mood: 'chill', duration: '3:12', viral: true },
  { id: 't3', name: 'Epic Cinematic', artist: 'Orchestra AI', genre: 'cinematic', mood: 'dramatic', duration: '2:45' },
  { id: 't4', name: 'Tropical Vibes', artist: 'Summer Mix', genre: 'pop', mood: 'happy', duration: '2:18', trending: true },
  { id: 't5', name: 'Dark Ambient', artist: 'Mystery Sound', genre: 'ambient', mood: 'mysterious', duration: '4:02' },
  { id: 't6', name: 'Hype Beat', artist: 'Trap King', genre: 'trap', mood: 'energetic', duration: '1:58', viral: true },
  { id: 't7', name: 'Acoustic Dreams', artist: 'Guitar Soul', genre: 'acoustic', mood: 'calm', duration: '3:30' },
  { id: 't8', name: 'Retro Arcade', artist: '8-Bit Hero', genre: 'electronic', mood: 'fun', duration: '2:05' },
  { id: 't9', name: 'Corporate Upbeat', artist: 'Business Pro', genre: 'corporate', mood: 'motivational', duration: '2:22' },
  { id: 't10', name: 'Horror Tension', artist: 'Scary Sound', genre: 'cinematic', mood: 'tense', duration: '3:45' },
];

const SFX = [
  { name: 'Whoosh', icon: Zap },
  { name: 'Impact', icon: Sparkles },
  { name: 'Rise', icon: Music },
  { name: 'Transition', icon: Zap },
  { name: 'Pop', icon: Sparkles },
  { name: 'Click', icon: Zap },
  { name: 'Applause', icon: Music },
  { name: 'Suspense', icon: Sparkles },
];

export function MusicLibrary() {
  const [search, setSearch] = useState('');
  const [genreFilter, setGenreFilter] = useState('all');
  const [moodFilter, setMoodFilter] = useState('all');
  const [playing, setPlaying] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());

  const genres = ['all', ...Array.from(new Set(TRACKS.map((t) => t.genre)))];
  const moods = ['all', ...Array.from(new Set(TRACKS.map((t) => t.mood)))];

  const filtered = TRACKS.filter((t) => {
    if (genreFilter !== 'all' && t.genre !== genreFilter) return false;
    if (moodFilter !== 'all' && t.mood !== moodFilter) return false;
    if (search && !t.name.toLowerCase().includes(search.toLowerCase()) && !t.artist.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const toggleFavorite = (id: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const addToTimeline = (track: Track) => {
    toast.success(`"${track.name}" agregado a la linea de tiempo`);
  };

  const playSfx = (name: string) => {
    toast.success(`Reproduciendo SFX: ${name}`);
  };

  return (
    <div>
      <div className="vmusic-header">
        <h4><Music size={14} /> Biblioteca Musical</h4>
        <span className="vmusic-count">{filtered.length} pistas</span>
      </div>

      <div className="vmusic-search">
        <Search size={12} />
        <input placeholder="Buscar pistas..." value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <div className="vmusic-filters">
        <select value={genreFilter} onChange={(e) => setGenreFilter(e.target.value)}>
          {genres.map((g) => <option key={g} value={g}>{g === 'all' ? 'Todos los generos' : g}</option>)}
        </select>
        <select value={moodFilter} onChange={(e) => setMoodFilter(e.target.value)}>
          {moods.map((m) => <option key={m} value={m}>{m === 'all' ? 'Todos los moods' : m}</option>)}
        </select>
      </div>

      <div className="vmusic-list">
        {filtered.map((track) => (
          <div key={track.id} className="vmusic-track">
            <button className="vmusic-play" onClick={() => setPlaying(playing === track.id ? null : track.id)}>
              {playing === track.id ? <Pause size={12} /> : <Play size={12} />}
            </button>
            <div className="vmusic-info">
              <span className="vmusic-name">
                {track.name}
                {track.trending && <span className="vmusic-badge trending">Trending</span>}
                {track.viral && <span className="vmusic-badge viral">Viral</span>}
              </span>
              <span className="vmusic-meta">{track.artist} · {track.genre} · {track.mood} · {track.duration}</span>
            </div>
            <div className="vmusic-actions">
              <button className={favorites.has(track.id) ? 'active' : ''} onClick={() => toggleFavorite(track.id)}><Heart size={12} /></button>
              <button onClick={() => addToTimeline(track)}><Plus size={12} /></button>
            </div>
          </div>
        ))}
      </div>

      <div className="vmusic-sfx">
        <h5><Volume2 size={12} /> Efectos de Sonido</h5>
        <div className="vmusic-sfx-grid">
          {SFX.map((sfx) => (
            <button key={sfx.name} className="vmusic-sfx-chip" onClick={() => playSfx(sfx.name)}>
              <sfx.icon size={10} /> {sfx.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
