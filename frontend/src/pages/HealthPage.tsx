// Salud, the way the phone's Health app works in 2026 (Resumen with readiness and
// highlights, Longevidad by areas, Explorar by category, Compartir) plus what its users ask
// for: data from any watch, ring or scale, notes and tags per day, what goes with a good
// night, goals, a doctor summary and a full export. Every number is the owner's own data;
// tabs live in ./health/. Simple first: Hoy (reminders, goals and the summary),
// Medicinas, Comida y ejercicio and Mente in sight; Longevidad, Explorar,
// Compartir and Dispositivos under «Más».

import { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router';
import { Brain, CalendarCheck, Ellipsis, Pill, Salad, type LucideIcon } from 'lucide-react';
import { salud, type Catalog, type Summary } from '../lib/salud';
import { PaperPage } from '../components/Paper/PaperPage';
import portada from '../assets/salud/portada-salud.webp';
import { BrowseTab, MetricView } from './health/BrowseTab';
import { DevicesTab } from './health/DevicesTab';
import { LongevityTab } from './health/LongevityTab';
import { MindTab } from './health/MindTab';
import { ShareTab } from './health/ShareTab';
import { MedsTab } from './health/MedsTab';
import { PlanTab } from './health/PlanTab';
import { SummaryTab } from './health/SummaryTab';
import { TodayBlock } from './health/TodayBlock';
import './health/health.css';

type Tab = 'resumen' | 'medicinas' | 'plan' | 'mente' | 'longevidad' | 'explorar' | 'compartir' | 'dispositivos';
// Simple first (owner, 24 Oct. 2026): four sections in sight, the rest under «Más».
const TABS: Array<{ key: Tab; label: string; icon: LucideIcon }> = [
  { key: 'resumen', label: 'Hoy', icon: CalendarCheck },
  { key: 'medicinas', label: 'Medicinas', icon: Pill },
  { key: 'plan', label: 'Comida y ejercicio', icon: Salad },
  { key: 'mente', label: 'Mente', icon: Brain },
];
const MORE: Array<{ key: Tab; label: string }> = [
  { key: 'longevidad', label: 'Longevidad' },
  { key: 'explorar', label: 'Explorar' },
  { key: 'compartir', label: 'Compartir' },
  { key: 'dispositivos', label: 'Dispositivos' },
];

function tabFrom(search: string): Tab | null {
  const asked = new URLSearchParams(search).get('tab');
  return [...TABS, ...MORE].some((t) => t.key === asked) ? (asked as Tab) : null;
}

export function HealthPage() {
  const { search } = useLocation();
  const [tab, setTab] = useState<Tab>(() => tabFrom(search) ?? 'resumen');
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [problem, setProblem] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(() => {
    salud
      .summary()
      .then((s) => {
        setSummary(s);
        setProblem('');
      })
      .catch(() => setProblem('No pude leer sus datos de salud. Compruebe que Sergio está en marcha.'));
  }, []);

  useEffect(() => {
    salud.catalog().then(setCatalog).catch(() => {});
    load();
    window.addEventListener('sergio:health-refresh', load);
    return () => window.removeEventListener('sergio:health-refresh', load);
  }, [load]);

  // A shortcut such as /salud?tab=mente switches tab even when Salud is already open.
  useEffect(() => {
    const asked = tabFrom(search);
    if (asked) {
      setOpen(null);
      setTab(asked);
    }
  }, [search]);

  const show = (key: string) => setOpen(key);

  return (
    <PaperPage title="Salud" wide>
      {tab === 'resumen' && !open && <img className="salud-cover" src={portada} alt="Personas en un parque: caminando, meditando, en bicicleta y leyendo" />}
      <nav className="paper-tabs salud-tabs" role="tablist" aria-label="Secciones de Salud">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            className="paper-tab"
            aria-selected={tab === t.key && !open}
            onClick={() => {
              setOpen(null);
              setTab(t.key);
            }}
          >
            <t.icon size={14} strokeWidth={1.8} aria-hidden />
            {t.label}
          </button>
        ))}
        <button
          type="button"
          role="tab"
          className="paper-tab"
          aria-selected={MORE.some((m) => m.key === tab) && !open}
          onClick={() => {
            setOpen(null);
            if (!MORE.some((m) => m.key === tab)) setTab('longevidad');
          }}
        >
          <Ellipsis size={14} strokeWidth={1.8} aria-hidden />
          Más
        </button>
      </nav>
      {MORE.some((m) => m.key === tab) && !open && (
        <div className="salud-more" role="tablist" aria-label="Más de Salud">
          {MORE.map((m) => (
            <button key={m.key} type="button" role="tab" className="mac-chip" aria-selected={tab === m.key} onClick={() => setTab(m.key)}>
              {m.label}
            </button>
          ))}
        </div>
      )}
      {problem && !['mente', 'medicinas', 'plan'].includes(tab) && <p className="paper-meta">{problem}</p>}
      {tab === 'mente' && !open ? (
        <MindTab />
      ) : tab === 'medicinas' && !open ? (
        <MedsTab />
      ) : tab === 'plan' && !open ? (
        <PlanTab />
      ) : !catalog || !summary ? (
        !problem && <p className="paper-meta">Leyendo…</p>
      ) : open ? (
        <MetricView metricKey={open} onBack={() => setOpen(null)} onChanged={load} />
      ) : (
        <>
          {tab === 'resumen' && <TodayBlock />}
          {tab === 'resumen' && <SummaryTab summary={summary} catalog={catalog} onOpen={show} onChanged={load} onConnect={() => setTab('dispositivos')} />}
          {tab === 'longevidad' && <LongevityTab onOpen={show} />}
          {tab === 'explorar' && <BrowseTab catalog={catalog} summary={summary} onOpen={show} />}
          {tab === 'compartir' && <ShareTab />}
          {tab === 'dispositivos' && <DevicesTab catalog={catalog} summary={summary} onChanged={load} />}
        </>
      )}
    </PaperPage>
  );
}

export default HealthPage;
