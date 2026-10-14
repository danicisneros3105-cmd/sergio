import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';
import { execSync } from 'child_process';
import fs from 'fs';

// Every build has its own id; /version.json tells an old open copy to reload
// (src/lib/freshness.ts), so after an update nobody keeps seeing the old web.
const buildId = (() => {
  let sha = 'local';
  try {
    sha = execSync('git rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  } catch {
    /* not a git checkout */
  }
  return `${sha}-${Date.now().toString(36)}`;
})();

// VITE_SUPABASE_ANON_KEY is intentionally NOT required here: a missing key
// disables the savings leaderboard at runtime (see src/lib/supabase.ts) rather
// than failing the build, so the package/app stays publishable without it.
// jarvis gui sets the proxy target without exposing an absolute API URL to the
// browser, so requests stay on Vite's origin even on a custom frontend port.
const apiTarget = process.env.OPENJARVIS_VITE_PROXY_TARGET
  || process.env.VITE_API_URL
  || 'http://localhost:8000';

// `npm run build:demo`: the whole app with no server, for the interactive demo.
const demo = process.env.VITE_DEMO === '1';

export default defineConfig({
  define: { __BUILD_ID__: JSON.stringify(buildId) },
  base: demo ? './' : '/',
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
      'sergio-demo': path.resolve(import.meta.dirname, demo ? './src/demo/install.ts' : './src/demo/none.ts'),
    },
  },
  plugins: [
    {
      name: 'sergio-version',
      apply: 'build',
      writeBundle(options) {
        fs.writeFileSync(path.join(options.dir || 'dist', 'version.json'), JSON.stringify({ build: buildId }));
      },
    },
    react(),
    tailwindcss(),
    !demo && VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Sergio',
        short_name: 'Sergio',
        description: 'Su asistente de IA, en su propio equipo',
        lang: 'es',
        start_url: '/',
        scope: '/',
        theme_color: '#161618',
        background_color: '#161618',
        display: 'standalone',
        orientation: 'any',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
        shortcuts: [
          { name: 'Chat', short_name: 'Chat', url: '/', icons: [{ src: 'pwa-192x192.png', sizes: '192x192' }] },
          { name: 'Cowork', short_name: 'Cowork', url: '/cowork', icons: [{ src: 'pwa-192x192.png', sizes: '192x192' }] },
          {
            name: 'Pensar a fondo',
            short_name: 'Pensar',
            url: '/pensar',
            icons: [{ src: 'pwa-192x192.png', sizes: '192x192' }],
          },
        ],
      },
      workbox: {
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        // Creator's big studios (3D, design, the code editor) are not part of
        // every update: they download the first time they are opened and
        // then stay cached (their file names change when they change).
        globIgnores: ['**/{CodeStudio,Studio3D,DesignStudio,editor.worker}-*.{js,css}'],
        navigateFallbackDenylist: [/^\/version\.json/, /^\/v1\//, /^\/health/, /^\/dashboard/, /^\/api\//],
        // Offline: the model list and server info come from the last time
        // there was a connection, so the chat still opens. Answers are kept
        // separately in IndexedDB (src/lib/offline.ts).
        runtimeCaching: [
          {
            urlPattern: ({ url }) => /\/assets\/(CodeStudio|Studio3D|DesignStudio|editor\.worker)-[\w-]+\.(js|css)$/.test(url.pathname),
            handler: 'CacheFirst',
            options: { cacheName: 'sergio-creator', expiration: { maxEntries: 24, maxAgeSeconds: 90 * 86400 } },
          },
          {
            urlPattern: ({ url, request }) =>
              request.method === 'GET' && /^\/v1\/(models|info)$/.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'sergio-api',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 10, maxAgeSeconds: 30 * 86400 },
            },
          },
        ],
      },
    }),
  ],
  build: {
    outDir: demo ? 'dist-demo' : '../src/openjarvis/server/static',
    emptyOutDir: true,
    // Preserve the Vite 6 browser baseline for existing desktop webviews.
    target: ['es2020', 'edge88', 'firefox78', 'chrome87', 'safari14'],
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'react', test: /node_modules[\\/](react|react-dom)[\\/]/ },
            {
              name: 'markdown',
              test: /node_modules[\\/](react-markdown|rehype-highlight|remark-gfm)[\\/]/,
            },
            { name: 'charts', test: /node_modules[\\/]recharts[\\/]/ },
            { name: 'router', test: /node_modules[\\/]react-router[\\/]/ },
          ],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // ws: true is required for the /v1/agents/events WebSocket. Without it
      // Vite proxies the HTTP request but not the upgrade, so the socket never
      // opens — no error, no close event, just silence — and every live agent
      // view sits empty in dev while working in a production build.
      '/v1': {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
      '/health': apiTarget,
      '/api': apiTarget,
    },
  },
});
