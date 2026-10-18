// Salud, the way the phone's Health app works in 2026 (Resumen with readiness and
// highlights, Longevidad by areas, Explorar by category, Compartir) plus what its users ask
// for: data from any watch, ring or scale, notes and tags per day, what goes with a good
// night, goals, a doctor summary and a full export. Every number is the owner's own data;
// tabs live in ./health/. Salud mental holds the survey and the mental gym.

import { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router';
import { salud, type Catalog, type Summary } from '../lib/salud';
import { PaperPage } from '../components/Paper/PaperPage';
import portada from '../assets/salud/portada-salud.webp';
import { BrowseTab, MetricView } from './health/BrowseTab';
import { DevicesTab } from './health/DevicesTab';
import { LongevityTab } from './health/LongevityTab';
import { MindTab } from './health/MindTab';
import { ShareTab } from './health/ShareTab';
import { SummaryTab } from './health/SummaryTab';
import './health/health.css';

type Tab = 'resumen' | 'longevidad' | 'explorar' | 'compartir' | 'dispositivos' | 'mente';
const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'resumen', label: 'Resumen' },
  { key: 'longevidad', label: 'Longevidad' },
  { key: 'explorar', label: 'Explorar' },
  { key: 'compartir', label: 'Compartir' },
  { key: 'dispositivos', label: 'Dispositivos' },
  { key: 'mente', label: 'Salud mental' },
];

function tabFrom(search: string): Tab | null {
  const asked = new URLSearchParams(search).get('tab');
  return TABS.some((t) => t.key === asked) ? (asked as Tab) : null;
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
            {t.label}
          </button>
        ))}
      </nav>
      {problem && tab !== 'mente' && <p className="paper-meta">{problem}</p>}
      {tab === 'mente' && !open ? (
        <MindTab />
      ) : !catalog || !summary ? (
        !problem && <p className="paper-meta">Leyendo…</p>
      ) : open ? (
        <MetricView metricKey={open} onBack={() => setOpen(null)} onChanged={load} />
      ) : (
        <>
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
