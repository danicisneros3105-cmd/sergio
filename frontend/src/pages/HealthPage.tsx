// Salud, the way the phone's Health app works in 2026 (Resumen with readiness and
// highlights, Longevidad by areas, Explorar by category, Compartir) plus what its users ask
// for: data from any watch, ring or scale, notes and tags per day, what goes with a good
// night, goals, a doctor summary and a full export. Every number is the owner's own data;
// tabs live in ./health/.

import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';
import { salud, type Catalog, type Summary } from '../lib/salud';
import { PaperPage } from '../components/Paper/PaperPage';
import { BrowseTab, MetricView } from './health/BrowseTab';
import { DevicesTab } from './health/DevicesTab';
import { HealthGym } from './health/HealthGym';
import { LongevityTab } from './health/LongevityTab';
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
  { key: 'mente', label: 'Mente' },
];

/** The mental gym still keeps its sessions in the older health hub. */
function MindTab() {
  const [hub, setHub] = useState<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  useEffect(() => {
    apiFetch('/v1/desktop/health')
      .then((r) => r.json())
      .then((d) => setHub(d.hub ?? null))
      .catch(() => setHub(null));
  }, []);
  if (!hub) return <p className="paper-meta">Leyendo…</p>;
  return <HealthGym hub={hub} setHub={setHub} />;
}

export function HealthPage() {
  const [tab, setTab] = useState<Tab>('resumen');
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

  const show = (key: string) => setOpen(key);

  return (
    <PaperPage title="Salud" wide>
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
      {problem && <p className="paper-meta">{problem}</p>}
      {!catalog || !summary ? (
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
          {tab === 'mente' && <MindTab />}
        </>
      )}
    </PaperPage>
  );
}

export default HealthPage;
