import { useState } from 'react';
import { Play, Clock, TrendingUp, Flame } from 'lucide-react';
import type { MusicTrack } from '@/types/video';

const TRACKS: MusicTrack[] = [
  { id: 'm1', name: 'Neon Drive', artist: 'Synthwave Boy', genre: 'Synthwave', mood: 'Energetic', duration: '2:34', trending: true },
  { id: 'm2', name: 'Lo-Fi Dreams', artist: 'Chillhop', genre: 'Lo-Fi', mood: 'Calm', duration: '3:12' },
  { id: 'm3', name: 'Epic Trailer', artist: 'Cinematic', genre: 'Orchestral', mood: 'Dramatic', duration: '1:45', viral: true },
  { id: 'm4', name: 'Trap King', artist: '808 Mafia', genre: 'Trap', mood: 'Intense', duration: '2:08', trending: true },
  { id: 'm5', name: 'Acoustic Sun', artist: 'Folk Vibes', genre: 'Acoustic', mood: 'Warm', duration: '2:56' },
  { id: 'm6', name: 'Cyber Punk', artist: 'Glitch Mob', genre: 'Electronic', mood: 'Aggressive', duration: '2:22', viral: true },
  { id: 'm7', name: 'Piano Solo', artist: 'Neo Classical', genre: 'Classical', mood: 'Emotional', duration: '3:30' },
  { id: 'm8', name: 'Bossa', artist: 'Latin Vibes', genre: 'Latin', mood: 'Smooth', duration: '2:15' },
];

export function MusicLibrary() {
  const [genre, setGenre] = useState('all');
  const [mood, setMood] = useState('all');

  const filtered = TRACKS.filter(t =>
    (genre === 'all' || t.genre === genre) &&
    (mood === 'all' || t.mood === mood)
  );

  return (
    <div className="fade-in">
      <div className="card">
        <div className="card-title">Filtros</div>
        <select className="studio-input" style={{ marginBottom: 6 }} value={genre} onChange={e => setGenre(e.target.value)}>
          <option value="all">Todos los generos</option>
          {[...new Set(TRACKS.map(t => t.genre))].map(g => <option key={g} value={g}>{g}</option>)}
        </select>
        <select className="studio-input" value={mood} onChange={e => setMood(e.target.value)}>
          <option value="all">Todos los moods</option>
          {[...new Set(TRACKS.map(t => t.mood))].map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {filtered.map(t => (
        <div key={t.id} className="music-row">
          <button className="music-play"><Play size={12} /></button>
          <div className="music-info">
            <div className="music-name">
              {t.name}
              {t.trending && <TrendingUp size={10} color="var(--teal)" />}
              {t.viral && <Flame size={10} color="var(--accent)" />}
            </div>
            <div className="music-meta">{t.artist} · {t.genre}</div>
          </div>
          <div className="music-dur"><Clock size={10} /> {t.duration}</div>
        </div>
      ))}
    </div>
  );
}
