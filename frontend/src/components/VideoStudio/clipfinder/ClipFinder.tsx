import { useState } from 'react';
import { Search, ExternalLink, Clock, Film, Download } from 'lucide-react';

const SOURCES = [
  { id: 'c1', title: 'Timelapse ciudad cyberpunk', source: 'Pexels', duration: '0:15', resolution: '4K', license: 'Free', tags: ['timelapse', 'city', 'cyberpunk'] },
  { id: 'c2', title: 'Olas rompiendo drone', source: 'Pixabay', duration: '0:22', resolution: '4K', license: 'Free', tags: ['ocean', 'drone', 'nature'] },
  { id: 'c3', title: 'Coding screen dark mode', source: 'Pexels', duration: '0:30', resolution: '1080p', license: 'Free', tags: ['code', 'tech', 'screen'] },
  { id: 'c4', title: 'Fuego slow motion', source: 'Videvo', duration: '0:12', resolution: '4K', license: 'CC0', tags: ['fire', 'slowmo', 'vfx'] },
  { id: 'c5', title: 'Aurora boreal time-lapse', source: 'Pexels', duration: '0:45', resolution: '4K', license: 'Free', tags: ['aurora', 'nature', 'sky'] },
  { id: 'c6', title: 'Cafe pouring overhead', source: 'Pixabay', duration: '0:08', resolution: '4K', license: 'Free', tags: ['coffee', 'lifestyle', 'macro'] },
];

export function ClipFinder() {
  const [q, setQ] = useState('');
  const [tag, setTag] = useState('all');

  const filtered = SOURCES.filter(s =>
    s.title.toLowerCase().includes(q.toLowerCase()) &&
    (tag === 'all' || s.tags.includes(tag))
  );

  const allTags = [...new Set(SOURCES.flatMap(s => s.tags))];

  return (
    <div className="clip-root fade-in">
      <div className="clip-search">
        <Search size={14} color="var(--text-muted)" />
        <input
          className="studio-input"
          placeholder="Buscar clips en Pexels, Pixabay, Videvo..."
          value={q}
          onChange={e => setQ(e.target.value)}
        />
      </div>
      <div className="clip-tags">
        <button className={`chip ${tag === 'all' ? 'active' : ''}`} onClick={() => setTag('all')}>Todos</button>
        {allTags.map(t => (
          <button key={t} className={`chip ${tag === t ? 'active' : ''}`} onClick={() => setTag(t)}>{t}</button>
        ))}
      </div>

      <div className="clip-grid">
        {filtered.map(c => (
          <div key={c.id} className="clip-card">
            <div className="clip-thumb">
              <Film size={20} color="var(--text-muted)" />
              <span className="clip-res">{c.resolution}</span>
            </div>
            <div className="clip-info">
              <div className="clip-title">{c.title}</div>
              <div className="clip-meta">
                <span><ExternalLink size={10} /> {c.source}</span>
                <span><Clock size={10} /> {c.duration}</span>
                <span className="clip-license">{c.license}</span>
              </div>
              <div className="clip-actions">
                <button className="tb-btn" style={{ flex: 1 }}><Download size={10} /> Importar</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
