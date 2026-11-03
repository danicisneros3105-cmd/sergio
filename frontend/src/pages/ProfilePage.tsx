import { useEffect, useState } from 'react';
import { ScanFace, Target, UserRound } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { PaperPage, PaperSection } from '../components/Paper/PaperPage';
import { DesktopSections, type DesktopSection } from '../components/Paper/DesktopSections';
import './profile.css';

interface Profile {
  companion: boolean;
  text: string;
  updates: number;
  last?: number;
  message?: string;
  traits?: string[];
  interests?: string[];
  goals?: string[];
  adjustments?: string[];
  hours?: string[];
  facts?: string[];
  talk?: { detalle?: string; humor?: string; nota?: string };
}

// Parts of the profile that live in the PC app's own windows.
const SECTIONS: DesktopSection[] = [
  { key: 'faces', label: 'Mi cara', meta: 'Visage de Sergio', icon: ScanFace, to: '/faces' },
  { key: 'goals', label: 'Mis metas', meta: 'Planes y práctica', icon: Target },
  { key: 'results', label: 'Resultados', meta: 'Lo que ha practicado', icon: UserRound },
];

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="profile-list">
      <h3 className="paper-label">{title}</h3>
      <ul>
        {items.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

interface Streak {
  seguidos: number;
  mejor: number;
  este_mes: number;
  total: number;
}

const STREAK_KEY = 'sergio-racha-oculta';

/** Days with Sergio: something to be proud of, never a debt. No warnings, no
 * «you lost it», no notifications; it only exists on this page and can be
 * hidden (owner asked for a guilt streak on 2 Nov 2026; a rest day is not a
 * failure, so the number only goes up what it was). */
function Constancy() {
  const [streak, setStreak] = useState<Streak | null>(null);
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem(STREAK_KEY) === '1';
    } catch {
      return false;
    }
  });
  useEffect(() => {
    apiFetch('/v1/personal/semana')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.racha && setStreak(d.racha as Streak))
      .catch(() => {});
  }, []);
  if (!streak || streak.total === 0) return null;
  const toggle = () => {
    const next = !hidden;
    setHidden(next);
    try {
      localStorage.setItem(STREAK_KEY, next ? '1' : '0');
    } catch {
      /* a convenience only */
    }
  };
  return (
    <PaperSection
      label="Su constancia"
      aside={
        <button type="button" className="paper-meta" onClick={toggle}>
          {hidden ? 'Mostrar' : 'Ocultar'}
        </button>
      }
    >
      {hidden ? null : (
        <div className="streak">
          {streak.seguidos >= 2 && (
            <div>
              <b>{streak.seguidos}</b>
              <span>días seguidos</span>
            </div>
          )}
          <div>
            <b>{streak.este_mes}</b>
            <span>{streak.este_mes === 1 ? 'día este mes' : 'días este mes'}</span>
          </div>
          <div>
            <b>{streak.mejor}</b>
            <span>su mejor racha</span>
          </div>
        </div>
      )}
    </PaperSection>
  );
}

export function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [problem, setProblem] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch('/v1/desktop/profile');
        const body = await res.json().catch(() => ({}));
        if (cancelled) return;
        if (res.ok) setProfile(body as Profile);
        else setProblem(String(body.detail ?? `Error ${res.status}`));
      } catch {
        if (!cancelled) setProblem('No puedo conectar con Sergio.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const when = profile?.last ? new Date(profile.last * 1000).toLocaleDateString('es', { day: 'numeric', month: 'long' }) : '';
  const talk = profile?.talk;
  const talkLines = [
    talk?.detalle ? `Respuestas ${{ breve: 'breves', normal: 'normales', detallado: 'detalladas' }[talk.detalle] ?? talk.detalle}` : '',
    talk?.humor && talk.humor !== 'normal' ? `Humor: ${talk.humor}` : '',
    talk?.nota,
  ].filter(Boolean) as string[];

  return (
    <PaperPage title="Perfil" wide>
      <PaperSection
        label="Resumen"
        aside={
          profile && profile.updates > 0 ? (
            <span className="paper-meta">
              {profile.updates} {profile.updates === 1 ? 'actualización' : 'actualizaciones'}
              {when && ` · última el ${when}`}
            </span>
          ) : undefined
        }
      >
        <p className="profile-summary" data-muted={!profile?.text ? '1' : undefined}>
          {problem || profile?.message || profile?.text || (profile ? 'Aún no hay perfil: se arma con el uso.' : 'Leyendo…')}
        </p>
      </PaperSection>

      {profile?.companion && (
        <PaperSection label="Lo que sé de usted">
          <div className="profile-grid">
            <List title="Rasgos" items={profile.traits} />
            <List title="Intereses" items={profile.interests} />
            <List title="Metas" items={profile.goals} />
            <List title="Horas en que suele estar" items={profile.hours} />
            <List title="Cómo le hablo" items={talkLines} />
            <List title="Me lo ha contado" items={profile.facts} />
            <List title="Lo que he ajustado" items={profile.adjustments} />
          </div>
          {!profile.traits?.length && !profile.goals?.length && !profile.hours?.length && !profile.facts?.length && (
            <p className="paper-meta">Todavía no hay detalles. Aparecerán tras la primera actualización.</p>
          )}
        </PaperSection>
      )}

      <Constancy />

      <PaperSection label="Abrir">
        <DesktopSections sections={SECTIONS} />
      </PaperSection>
    </PaperPage>
  );
}

export default ProfilePage;
