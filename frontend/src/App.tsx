import { useEffect, useState, useCallback, useRef, lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Layout } from './components/Layout';
import { ChatPage } from './pages/ChatPage';
// Everything else loads on demand: the first screen opens in milliseconds.
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })));
const GetStartedPage = lazy(() => import('./pages/GetStartedPage').then((m) => ({ default: m.GetStartedPage })));
const DataSourcesPage = lazy(() => import('./pages/DataSourcesPage').then((m) => ({ default: m.DataSourcesPage })));
const LogsPage = lazy(() => import('./pages/LogsPage').then((m) => ({ default: m.LogsPage })));
const ExtensionPage = lazy(() => import('./pages/ExtensionPage').then((m) => ({ default: m.ExtensionPage })));
const FacesPage = lazy(() => import('./pages/FacesPage').then((m) => ({ default: m.FacesPage })));
const ThinkPage = lazy(() => import('./pages/ThinkPage').then((m) => ({ default: m.ThinkPage })));
const HealthPage = lazy(() => import('./pages/HealthPage').then((m) => ({ default: m.HealthPage })));
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })));
const CoworkPage = lazy(() => import('./pages/CoworkPage').then((m) => ({ default: m.CoworkPage })));
const WorkspacePage = lazy(() => import('./pages/WorkspacePage'));
const CapturePage = lazy(() => import('./pages/CapturePage'));
const HomePage = lazy(() => import('./pages/HomePage'));
const NodesPage = lazy(() => import('./pages/NodesPage'));
const ConnectomePage = lazy(() => import('./pages/ConnectomePage'));
const SignInPage = lazy(() => import('./pages/SignInPage'));
const MeetingPage = lazy(() => import('./pages/MeetingPage'));
const UsagePage = lazy(() => import('./pages/UsagePage'));
const PlansPage = lazy(() => import('./pages/PlansPage').then((m) => ({ default: m.PlansPage })));
const HelpPage = lazy(() => import('./pages/HelpPage').then((m) => ({ default: m.HelpPage })));
const SwarmPage = lazy(() => import('./pages/SwarmPage'));
const ExtensionsPage = lazy(() => import('./pages/ExtensionsPage'));
import { ModelSheet } from './components/ModelSheet';
import { CelebrationLayer } from './components/Celebration/CelebrationLayer';
import { Shortcuts } from './components/Shortcuts/Shortcuts';
import { SetupScreen } from './components/SetupScreen';
import { Toaster } from './components/ui/sonner';
import { useAppStore } from './lib/store';
import { fetchModels, fetchServerInfo, fetchSavings, submitSavings, isTauri } from './lib/api';
import { UpdateChecker } from './components/Desktop/UpdateChecker';
import { track, hashId } from './lib/analytics';


export default function App() {
  const [setupDone, setSetupDone] = useState(!isTauri());
  const handleSetupReady = useCallback(() => {
    setSetupDone(true);
    // Only fire once per install — guard against setup screen re-appearing
    // on reinstalls or dev reloads.
    if (!localStorage.getItem('oj-setup-completed')) {
      localStorage.setItem('oj-setup-completed', '1');
      track('setup_completed', { preset: 'default' });
    }
  }, []);
  const prevModelRef = useRef<string>('');
  const setModels = useAppStore((s) => s.setModels);
  const setModelsLoading = useAppStore((s) => s.setModelsLoading);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const setServerInfo = useAppStore((s) => s.setServerInfo);
  const setSavings = useAppStore((s) => s.setSavings);
  const settings = useAppStore((s) => s.settings);
  const commandPaletteOpen = useAppStore((s) => s.commandPaletteOpen);
  const optInEnabled = useAppStore((s) => s.optInEnabled);
  const optInDisplayName = useAppStore((s) => s.optInDisplayName);
  const optInEmail = useAppStore((s) => s.optInEmail);
  const optInAnonId = useAppStore((s) => s.optInAnonId);
  const savings = useAppStore((s) => s.savings);

  // Apply theme class to <html>
  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('dark', 'light');
    if (settings.theme === 'dark') root.classList.add('dark');
    else if (settings.theme === 'light') root.classList.add('light');
  }, [settings.theme]);

  // Sync overlay conversations into the main app
  const importOverlay = useAppStore((s) => s.importOverlayConversation);
  useEffect(() => {
    if (!isTauri()) return;
    importOverlay();
    const interval = setInterval(importOverlay, 5000);
    return () => clearInterval(interval);
  }, [importOverlay]);

  // Fetch models on mount
  useEffect(() => {
    fetchModels()
      .then((m) => {
        setModels(m);
      })
      .catch(() => setModels([]))
      .finally(() => setModelsLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch server info
  useEffect(() => {
    fetchServerInfo().then(setServerInfo).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll savings and optionally share to Supabase
  useEffect(() => {
    const refresh = () =>
      fetchSavings()
        .then((data) => {
          setSavings(data);
          if (optInEnabled && optInDisplayName && data) {
            const claudeEntry = data.per_provider.find(
              (p) => p.provider === 'claude-fable-5',
            );
            const dollarSavings = claudeEntry ? claudeEntry.total_cost : 0;
            const energySaved = data.per_provider.reduce(
              (sum, p) => sum + (p.energy_wh || 0),
              0,
            );
            const flopsSaved = data.per_provider.reduce(
              (sum, p) => sum + (p.flops || 0),
              0,
            );
            submitSavings({
              anon_id: optInAnonId,
              display_name: optInDisplayName,
              email: '',
              total_calls: data.total_calls,
              total_tokens: data.total_tokens,
              dollar_savings: dollarSavings,
              energy_wh_saved: energySaved,
              flops_saved: flopsSaved,
              token_counting_version: data.token_counting_version ?? 1,
            });
          }
        })
        .catch(() => {});
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [optInEnabled, optInDisplayName, optInAnonId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fire model_changed when the user switches models. First mount is
  // not a "change" — only emit when both prev and current are real and
  // differ.
  useEffect(() => {
    const prev = prevModelRef.current;
    const curr = selectedModel || '';
    prevModelRef.current = curr;
    if (!prev || !curr || prev === curr) return;
    void (async () => {
      const [fromHash, toHash] = await Promise.all([
        hashId(prev),
        hashId(curr),
      ]);
      track('model_changed', {
        from_model_hash: fromHash,
        to_model_hash: toHash,
      });
    })();
  }, [selectedModel]);

  // app_opened — one-shot per app launch, fires after analytics has had
  // a chance to initialize. platform + version are super-properties
  // registered in analytics.ts initAnalytics, so no per-call props needed.
  useEffect(() => {
    const t = setTimeout(() => {
      track('app_opened', {});
    }, 500);
    return () => clearTimeout(t);
  }, []);

  const toggleSystemPanel = useAppStore((s) => s.toggleSystemPanel);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/⌘ K is the shortcut palette now (components/Shortcuts); the model
      // picker opens from it («Cambiar de modelo») and from the chat.
      if ((e.metaKey || e.ctrlKey) && e.key === 'i') {
        e.preventDefault();
        toggleSystemPanel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleSystemPanel]);


  if (!setupDone) {
    return <SetupScreen onReady={handleSetupReady} />;
  }

  return (
    <>
      <UpdateChecker />
      <ErrorBoundary>
      <Suspense fallback={<div role="status" aria-live="polite" className="p-6">Cargando espacio de trabajo…</div>}>
      <Routes>
        <Route path="entrar" element={<SignInPage />} />
        <Route element={<Layout />}>
          <Route index element={<ChatPage />} />
          <Route path="biblioteca" element={<HomePage />} />
          <Route path="nodes" element={<NodesPage />} />
          <Route path="nodes/:id" element={<NodesPage />} />
          <Route path="swarm" element={<SwarmPage />} />
          <Route path="swarm/:id" element={<SwarmPage />} />
          <Route path="creator/*" element={<Navigate to="/chat" replace />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="workspace" element={<WorkspacePage />} />
          <Route path="workspace/:id" element={<WorkspacePage />} />
          <Route path="capturar" element={<CapturePage />} />
          <Route path="reunion" element={<MeetingPage />} />
          <Route path="dashboard" element={<Navigate to="/uso" replace />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="get-started" element={<GetStartedPage />} />
          <Route path="data-sources" element={<DataSourcesPage />} />
          <Route path="agents" element={<Navigate to="/nodes" replace />} />
          <Route path="planes" element={<PlansPage />} />
          <Route path="ayuda" element={<HelpPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="clacky" element={<ExtensionPage name="clacky" />} />
          <Route path="faces" element={<FacesPage />} />
          <Route path="extensiones" element={<ExtensionsPage />} />
          <Route path="extensiones/:tab" element={<ExtensionsPage />} />
          <Route path="studio" element={<Navigate to="/extensiones" replace />} />
          <Route path="developer" element={<Navigate to="/extensiones" replace />} />
          <Route path="pensar" element={<ThinkPage />} />
          <Route path="cowork" element={<CoworkPage />} />
          <Route path="salud" element={<HealthPage />} />
          <Route path="perfil" element={<ProfilePage />} />
          <Route path="atajos" element={<ConnectomePage />} />
          <Route path="uso" element={<UsagePage />} />
          <Route path="cerebro" element={<ConnectomePage />} />
          {/* An address that does not exist goes home, never to a blank page. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
      </Suspense>
      </ErrorBoundary>
      <Toaster position="bottom-right" />
      {commandPaletteOpen && <ModelSheet />}
      <CelebrationLayer />
      <Shortcuts />
    </>
  );
}
