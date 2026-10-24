// Must run first: any device (http on the home network, older Safari).
import './lib/compat';
// In the demo build it answers every server call itself.
import 'sergio-demo';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, MemoryRouter } from 'react-router';
import { ErrorBoundary } from './components/ErrorBoundary';
import App from './App';
import { initApiBase } from './lib/api';
import { initAnalytics } from './lib/analytics';
import { consumePairFragment } from './lib/pairing';
import { watchFreshness } from './lib/freshness';
import { startPerf } from './lib/perf';
import '@fontsource-variable/josefin-sans';
import '@fontsource-variable/inter';
import './index.css';
import './components/Studio/refinement.css';

function applyTheme() {
  try {
    const raw = localStorage.getItem('openjarvis-settings');
    const settings = raw ? JSON.parse(raw) : {};
    const theme = settings.theme || 'system';
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
    } else if (theme === 'light') {
      document.documentElement.classList.add('light');
      document.documentElement.classList.remove('dark');
    }
  } catch { /* use system default */ }
}

// A phone opened from the `sergio movil` QR code: keep its key, then render.
consumePairFragment();
applyTheme();
if (!import.meta.env.VITE_DEMO) watchFreshness();
// A slow device goes light (no blur or long animations) so it stays smooth.
startPerf();

// Fetch the API base URL from the Tauri backend before rendering.
// This ensures JARVIS_PORT is defined in one place (the Rust backend).
// In non-Tauri environments this is a no-op.
// The demo lives inside another page: its own memory router, no URLs.
const Router = import.meta.env.VITE_DEMO ? MemoryRouter : BrowserRouter;

initApiBase().finally(() => {
  // Kick off analytics init in the background — it's never awaited so
  // a slow/failed identity fetch never delays UI render.
  void initAnalytics();

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary>
        <Router>
          <App />
        </Router>
      </ErrorBoundary>
    </StrictMode>,
  );
});
