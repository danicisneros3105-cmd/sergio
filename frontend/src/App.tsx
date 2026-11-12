import { lazy, Suspense, useEffect } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useEffectOnce } from "usehooks-ts";

import { ProtectedRoute } from "./components/Auth/ProtectedRoute";
import Layout from "./components/Layout";
import { Onboarding } from "./components/Onboarding";
import { PrivateShell } from "./components/Shell/PrivateShell";
import { PublicShell } from "./components/Shell/PublicShell";
import { useTheme } from "./hooks/useTheme";
import AgentsPage from "./pages/AgentsPage";
import ChatPage from "./pages/ChatPage";
import ConnectomePage from "./pages/ConnectomePage";
import DataSourcesPage from "./pages/DataSourcesPage";
import DebugPage from "./pages/DebugPage";
import ExtensionPage from "./pages/ExtensionPage";
import ExtensionsPage from "./pages/ExtensionsPage";
import FacesPage from "./pages/FacesPage";
import GalleryPage from "./pages/GalleryPage";
import GetStartedPage from "./pages/GetStartedPage";
import HelpPage from "./pages/HelpPage";
import { HomePage } from "./pages/HomePage";
import { LandingPage } from "./pages/LandingPage";
import LogsPage from "./pages/LogsPage";
import MeetingPage from "./pages/MeetingPage";
import NodesPage from "./pages/NodesPage";
import OrganizerPage from "./pages/OrganizerPage";
import PayPage from "./pages/PayPage";
import PlansPage from "./pages/PlansPage";
import ProfilePage from "./pages/ProfilePage";
import ProjectsPage from "./pages/ProjectsPage";
import SettingsPage from "./pages/SettingsPage";
import WorkspacePage from "./pages/WorkspacePage";
import { useAuthStore } from "./stores/auth";
import { useConfigStore } from "./stores/config";
import { useGlobalStore } from "./stores/global";
import { isPublicPage } from "./utils/public";

const AutomatizarPage = lazy(() => import("./pages/AutomatizarPage"));
const SwarmPage = lazy(() => import("./pages/SwarmPage"));
const ExtensionsPage = lazy(() => import("./pages/ExtensionsPage"));
const CreatorPage = lazy(() => import("./pages/CreatorPage").then((m) => ({ default: m.CreatorPage })));
const HealthPage = lazy(() => import("./pages/HealthPage"));
const CapturePage = lazy(() => import("./pages/CapturePage"));
const CoworkPage = lazy(() => import("./pages/CoworkPage"));

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function PublicRouteGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (loading) return;
    if (user && isPublicPage(location.pathname)) {
      navigate("/chat", { replace: true });
    }
  }, [user, loading, location.pathname, navigate]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 dark:border-white" />
      </div>
    );
  }

  return <>{children}</>;
}

function AppContent() {
  const { user } = useAuthStore();
  const { config } = useConfigStore();
  const { theme } = useTheme();

  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [theme]);

  const onboardingCompleted =
    user?.onboarding_completed ?? config?.onboarding_completed ?? true;

  if (!user) {
    return (
      <PublicShell>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="get-started" element={<GetStartedPage />} />
          <Route path="planes" element={<PlansPage />} />
          <Route path="pagar" element={<PayPage />} />
          <Route path="pagar/:estado" element={<PayPage />} />
          <Route path="ayuda" element={<HelpPage />} />
          <Route path="debug" element={<DebugPage />} />
          <Route path="*" element={<LandingPage />} />
        </Routes>
      </PublicShell>
    );
  }

  if (!onboardingCompleted) {
    return (
      <Layout>
        <Onboarding />
      </Layout>
    );
  }

  return (
    <PrivateShell>
      <Suspense fallback={<div className="p-8 text-center">Cargando…</div>}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="creator/*" element={<CreatorPage />} />
          <Route path="editor" element={<CreatorPage />} />
          <Route path="galeria" element={<GalleryPage />} />
          <Route path="proyectos" element={<ProjectsPage />} />
          <Route path="nodes" element={<NodesPage />} />
          <Route path="nodes/:id" element={<NodesPage />} />
          <Route path="swarm" element={<SwarmPage />} />
          <Route path="swarm/:id" element={<SwarmPage />} />
          <Route path="workspace" element={<OrganizerPage />} />
          <Route path="workspace/:id" element={<WorkspacePage />} />
          <Route path="capturar" element={<CapturePage />} />
          <Route path="reunion" element={<MeetingPage />} />
          <Route path="dashboard" element={<Navigate to="/settings?tab=cuenta" replace />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="get-started" element={<GetStartedPage />} />
          <Route path="data-sources" element={<DataSourcesPage />} />
          <Route path="agents" element={<Navigate to="/nodes" replace />} />
          <Route path="planes" element={<PlansPage />} />
          <Route path="pagar" element={<PayPage />} />
          <Route path="pagar/:estado" element={<PayPage />} />
          <Route path="ayuda" element={<HelpPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="clacky" element={<ExtensionPage name="clacky" />} />
          <Route path="faces" element={<FacesPage />} />
          <Route path="extensiones" element={<ExtensionsPage />} />
          <Route path="extensiones/:tab" element={<ExtensionsPage />} />
          <Route path="studio" element={<Navigate to="/extensiones" replace />} />
          <Route path="developer" element={<Navigate to="/extensiones" replace />} />
          <Route path="pensar" element={<Navigate to="/chat" replace />} />
          <Route path="cowork" element={<CoworkPage />} />
          <Route path="automatizar" element={<AutomatizarPage />} />
          <Route path="salud" element={<HealthPage />} />
          <Route path="perfil" element={<ProfilePage />} />
          <Route path="atajos" element={<ConnectomePage />} />
          <Route path="uso" element={<Navigate to="/settings?tab=cuenta" replace />} />
          <Route path="cerebro" element={<ConnectomePage />} />
          <Route path="debug" element={<DebugPage />} />
          <Route path="*" element={<HomePage />} />
        </Routes>
      </Suspense>
    </PrivateShell>
  );
}

export default function App() {
  const { checkAuth } = useAuthStore();
  const { fetchConfig } = useConfigStore();
  const { isPaused, resume } = useGlobalStore();

  useEffectOnce(() => {
    checkAuth();
    fetchConfig();
  });

  return (
    <>
      <ScrollToTop />
      <PublicRouteGuard>
        <AppContent />
      </PublicRouteGuard>
    </>
  );
}
