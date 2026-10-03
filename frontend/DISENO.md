# Guía de diseño del frontend de Sergio

Esta guía es para cualquiera que rediseñe la interfaz, sea una persona, Claude
Design o Claude Code. La idea es cambiar el aspecto sin romper el
funcionamiento.

## Stack

- React 19 con TypeScript, Vite y Tailwind CSS v4.
- Componentes base de estilo shadcn en `src/components/ui/`.
- Iconos de `lucide-react`.

## Dónde está cada cosa

| Qué | Archivo |
|---|---|
| Colores, tipografía y sombras (tokens), con modo claro y oscuro | `src/index.css` (`:root` y `.dark`) |
| Estructura general: barra lateral y contenido | `src/components/Layout.tsx` |
| Barra lateral y navegación | `src/components/Sidebar/Sidebar.tsx` |
| Chat (mensajes, caja de texto) | `src/components/Chat/`, `src/pages/ChatPage.tsx` |
| Pestañas Globe y Clacky | `src/pages/ExtensionPage.tsx` |
| Campana de aprobaciones (las tareas de Clacky se aprueban aquí) | `src/components/ApprovalBell.tsx` |
| Ajustes | `src/pages/SettingsPage.tsx` |
| Nombre de la app y del icono (PWA) | `index.html`, `vite.config.ts` |

## Reglas para no romper nada

1. **Cambia el aspecto a través de los tokens** de `src/index.css`
   (`--color-*`). Así el modo claro y el oscuro siguen funcionando.
2. **No toques la lógica.** Sin una razón clara, no modifiques los archivos
   `src/lib/*`, `store.ts` ni las llamadas `apiFetch(...)`.
3. **No quites la campana de aprobaciones ni el iframe de Globe y Clacky.**
   Puedes cambiar su aspecto, pero no eliminarlos.
4. **Mantén el nombre "Sergio"** en los textos visibles.
5. **Antes de dar un cambio por terminado,** ejecuta:

   ```bash
   cd frontend
   npx -y npm@11 ci   # solo la primera vez
   npx tsc -b         # sin errores de tipos
   npx vitest run     # los tests deben pasar
   npm run dev        # revisar visualmente en http://127.0.0.1:5173
   ```

6. **Trabaja en una rama** (por ejemplo `diseno/nuevo-chat`) y abre un pull
   request hacia `main`. No subas los cambios directamente a `main`.
