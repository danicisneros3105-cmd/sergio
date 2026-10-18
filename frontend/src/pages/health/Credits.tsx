// Who did the research behind a section, in small print at the end: institution
// names as text, the study, a link to it, and the notice that Sergio has no tie
// to them. Logos appear only if the owner added them with permission.

import { useEffect, useState } from 'react';
import { salud, type CreditsInfo } from '../../lib/salud';

function Logo({ keyName }: { keyName: string }) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    let url = '';
    let alive = true;
    salud
      .logo(keyName)
      .then((blob) => {
        url = URL.createObjectURL(blob);
        if (alive) setSrc(url);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [keyName]);
  return src ? <img src={src} alt="" height={16} /> : null;
}

export function Credits({ scope }: { scope: 'mente' | 'gimnasio' }) {
  const [info, setInfo] = useState<CreditsInfo | null>(null);
  useEffect(() => {
    salud.credits(scope).then(setInfo).catch(() => setInfo(null));
  }, [scope]);
  if (!info || !info.studies.length) return null;
  return (
    <footer className="credits" aria-label="Investigaciones citadas">
      <h3 className="credits-title">Investigaciones</h3>
      <ul>
        {info.studies.map((s) => (
          <li key={s.topic}>
            <b>{s.topic}.</b> {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.cite}</a> : s.cite}
            {s.institutions.length > 0 && (
              <span className="credits-where">
                {s.institutions.map((i) => (
                  <span key={i.key} className="credits-inst">
                    {i.logo && <Logo keyName={i.key} />}
                    {i.name}
                  </span>
                ))}
              </span>
            )}
          </li>
        ))}
      </ul>
      <p className="credits-notice">{info.notice}</p>
    </footer>
  );
}
