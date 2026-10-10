import { useEffect, useState } from 'react';
import { ScanFace, Target, UserRound } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { PaperPage, PaperSection } from '../components/Paper/PaperPage';
import { DesktopSections, type DesktopSection } from '../components/Paper/DesktopSections';

const SECTIONS: DesktopSection[] = [
  { key: 'profile', label: 'Mi perfil', meta: 'Lo que Sergio sabe de usted', icon: UserRound },
  { key: 'goals', label: 'Mis metas', meta: 'Planes y práctica', icon: Target },
  { key: 'faces', label: 'Mi cara', meta: 'Face ID de Sergio', icon: ScanFace },
];

export function ProfilePage() {
  const [text, setText] = useState('');
  const [updates, setUpdates] = useState<number | null>(null);
  const [problem, setProblem] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch('/v1/desktop/profile');
        const body = await res.json();
        if (cancelled) return;
        if (res.ok) {
          setText(String(body.text ?? ''));
          setUpdates(Number(body.updates ?? 0));
        } else setProblem(String(body.detail ?? `Error ${res.status}`));
      } catch {
        if (!cancelled) setProblem('No puedo conectar con Sergio.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PaperPage title="Perfil" subtitle="Quién es usted para Sergio. Se actualiza solo, al menos dos veces y media por semana." wide>
      <PaperSection
        label="Resumen"
        aside={
          updates !== null && (
            <span className="paper-meta text-[11.5px]" style={{ color: 'var(--color-text-tertiary)' }}>
              {updates} actualizaciones
            </span>
          )
        }
      >
        <p className="text-[15px] leading-relaxed max-w-2xl" style={{ color: problem ? 'var(--color-text-secondary)' : 'var(--color-text)' }}>
          {problem || text || 'Leyendo…'}
        </p>
      </PaperSection>
      <PaperSection label="Abrir en el PC">
        <DesktopSections sections={SECTIONS} />
      </PaperSection>
    </PaperPage>
  );
}
