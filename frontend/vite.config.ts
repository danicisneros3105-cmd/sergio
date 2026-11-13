import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  server: {
    proxy: {
      '/voicevox': {
        target: 'http://localhost:50021',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/voicevox/, ''),
      },
    },
  },
  plugins: [react(), VitePWA({
    registerType: 'autoUpdate',
    injectRegister: 'auto',
    manifest: {
      name: 'Sergio Studio — Editor de Video con IA',
      short_name: 'Sergio Studio',
      description: 'Editor de video profesional con IA. Video Boost IMAX, creador de videos para redes sociales, trend radar, y mas.',
      theme_color: '#070b11',
      background_color: '#070b11',
      display: 'standalone',
      display_override: ['standalone', 'fullscreen', 'minimal-ui'],
      orientation: 'any',
      start_url: '/',
      scope: '/',
      lang: 'es',
      dir: 'ltr',
      categories: ['photo', 'video', 'productivity'],
      icons: [
        { src: '/pwa-64x64.png', sizes: '64x64', type: 'image/png' },
        { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
        { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
        { src: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png', purpose: 'any maskable' },
      ],
      screenshots: [
        {
          src: '/screenshot-wide.jpg',
          sizes: '1280x720',
          type: 'image/jpeg',
          form_factor: 'wide',
          label: 'Editor de video con IA en modo oscuro'
        },
        {
          src: '/screenshot-narrow.jpg',
          sizes: '750x1334',
          type: 'image/jpeg',
          form_factor: 'narrow',
          label: 'Sergio Studio en dispositivo movil'
        }
      ],
      shortcuts: [
        {
          name: 'Chat IA',
          short_name: 'Chat',
          description: 'Hablar con Sergio IA',
          url: '/chat',
          icons: [{ src: '/pwa-192x192.png', sizes: '192x192' }]
        },
        {
          name: 'Editor de Video',
          short_name: 'Editor',
          description: 'Editor de video con timeline',
          url: '/editor',
          icons: [{ src: '/pwa-192x192.png', sizes: '192x192' }]
        },
        {
          name: 'Studio',
          short_name: 'Studio',
          description: 'Panel de creacion de contenido',
          url: '/studio',
          icons: [{ src: '/pwa-192x192.png', sizes: '192x192' }]
        },
        {
          name: 'Galeria',
          short_name: 'Galeria',
          description: 'Galeria de videos editados',
          url: '/gallery',
          icons: [{ src: '/pwa-192x192.png', sizes: '192x192' }]
        }
      ],
      share_target: {
        action: '/editor',
        method: 'POST',
        enctype: 'multipart/form-data',
        params: {
          title: 'name',
          text: 'description',
          url: 'link',
          files: [
            { name: 'media', accept: ['video/*', 'image/*'] }
          ]
        }
      }
    },
    workbox: {
      globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2,mp4,webm}'],
      runtimeCaching: [
        {
          urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
          handler: 'CacheFirst',
          options: {
            cacheName: 'google-fonts-cache',
            expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
            cacheableResponse: { statuses: [0, 200] }
          }
        },
        {
          urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
          handler: 'CacheFirst',
          options: {
            cacheName: 'gstatic-fonts-cache',
            expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
            cacheableResponse: { statuses: [0, 200] }
          }
        }
      ]
    }
  })],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
