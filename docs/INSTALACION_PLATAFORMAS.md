# Instalacion Multiplataforma — Sergio Studio

Guia completa para compilar e instalar Sergio Studio en **macOS, Windows, Linux, iOS, iPadOS y Android**.

---

## Resumen de Plataformas

| Plataforma | Tecnologia | Estado | Metodo de instalacion |
|---|---|---|---|
| **macOS** | Tauri v2 | Listo | `.dmg` o App Store |
| **Windows** | Tauri v2 | Listo | `.msi` o `.exe` (NSIS) |
| **Linux** | Tauri v2 | Listo | `.deb`, `.rpm`, `.AppImage` |
| **iOS / iPadOS** | Capacitor | Listo | Xcode + TestFlight / App Store |
| **Android** | Capacitor | Listo | Android Studio + APK / Play Store |
| **Web (PWA)** | Vite PWA | Listo | Instalar desde navegador |

---

## Requisitos Previos

### Todos los sistemas
- Node.js >= 20
- npm o pnpm
- Git

### Desktop (Tauri)
- **Rust** >= 1.75 (`curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)
- **macOS**: Xcode Command Line Tools (`xcode-select --install`)
- **Windows**: Visual Studio 2022 Build Tools + Windows SDK
- **Linux**: `sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev`

### Mobile (Capacitor)
- **iOS**: macOS + Xcode >= 15 + CocoaPods (`sudo gem install cocoapods`)
- **Android**: Android Studio + SDK + NDK

---

## 1. Compilacion Desktop (macOS / Windows / Linux)

```bash
# 1. Clonar repo
git clone https://github.com/danicisneros3105-cmd/sergio.git
cd sergio

# 2. Instalar dependencias del frontend
cd frontend
npm install

# 3. Instalar dependencias de Tauri
npm run tauri:init   # Solo la primera vez

# 4. Compilar para tu plataforma
npm run tauri:build
```

### Salidas por plataforma

| SO | Ruta de salida |
|---|---|
| macOS | `frontend/src-tauri/target/release/bundle/dmg/Sergio Studio_1.0.0_aarch64.dmg` |
| Windows | `frontend/src-tauri/target/release/bundle/msi/Sergio Studio_1.0.0_x64_en-US.msi` |
| Linux | `frontend/src-tauri/target/release/bundle/deb/sergio-studio_1.0.0_amd64.deb` |

### Desarrollo en vivo (hot reload)
```bash
cd frontend
npm run tauri:dev
```

---

## 2. Compilacion iOS / iPadOS

```bash
# 1. Desde la carpeta frontend, sincronizar Capacitor
npx cap sync ios

# 2. Abrir proyecto en Xcode
npx cap open ios

# 3. En Xcode:
#    - Seleccionar tu equipo de desarrollo (Apple ID)
#    - Configurar Bundle Identifier: com.sergiostudio.editor
#    - Firmar con tu certificado de desarrollo
#    - Product > Archive para distribucion
#    - O conectar iPhone y dar "Run"

# 4. Para publicar en App Store:
#    - App Store Connect > Nueva app
#    - Subir archivo .ipa via Transporter
```

### Permisos iOS (ya configurados en `ios/App/App/Info.plist`)
- **Camara**: NSCameraUsageDescription
- **Microfono**: NSMicrophoneUsageDescription
- **Galeria**: NSPhotoLibraryUsageDescription
- **Red local**: NSLocalNetworkUsageDescription
- **Background**: Audio, fetch, processing

---

## 3. Compilacion Android

```bash
# 1. Sincronizar Capacitor
npx cap sync android

# 2. Abrir en Android Studio
npx cap open android

# 3. En Android Studio:
#    - Build > Generate Signed Bundle/APK
#    - O conectar dispositivo y dar "Run"

# 4. Para Play Store:
#    - Google Play Console > Nueva app
#    - Subir Android App Bundle (.aab)
```

### Permisos Android (ya configurados en `android/app/src/main/AndroidManifest.xml`)
- Camara, microfono, almacenamiento
- Notificaciones push
- Servicio en foreground para procesamiento de video

---

## 4. Instalacion Web (PWA)

No requiere compilacion. Desde el frontend:

```bash
cd frontend
npm run build
```

Los archivos estaticos se generan en `../src/openjarvis/server/static_local`.

Para instalar como PWA:
1. Abrir la URL en Chrome/Safari/Edge
2. Aparecera el icono "Instalar" en la barra de direcciones
3. En iOS: Compartir > "Agregar a Inicio"

---

## 5. Acceso al Dispositivo por Plataforma

### Camara
- **Desktop (Tauri)**: Dialog de archivos nativo + acceso a webcam via WebRTC
- **Mobile (Capacitor)**: `@capacitor/camera` con prompt nativo
- **Web (PWA)**: `getUserMedia()` API

### Galeria / Archivos
- **Desktop (Tauri)**: `tauri-plugin-dialog` + `tauri-plugin-fs` con acceso a todo el sistema de archivos
- **Mobile (Capacitor)**: `@capacitor/camera` (galeria) + `@capacitor/filesystem`
- **Web (PWA)**: `<input type="file">` + File System Access API (Chrome)

### Microfono
- **Desktop**: Acceso via WebRTC + grabacion con MediaRecorder
- **Mobile**: `@capacitor-community/voice` o WebRTC
- **Web**: `getUserMedia({ audio: true })`

### Notificaciones
- **Desktop**: `tauri-plugin-notification` con soporte nativo
- **Mobile**: `@capacitor/local-notifications` + `@capacitor/push-notifications`
- **Web**: Web Notifications API + Service Worker

### Compartir (Share Sheet)
- **Desktop**: `tauri-plugin-shell` + clipboard
- **Mobile**: `@capacitor/share` con share sheet nativo
- **Web**: Web Share API

---

## 6. Hooks de React para Acceso al Dispositivo

El hook `useDeviceAccess` detecta automaticamente la plataforma y usa la API correcta:

```tsx
import { useDeviceAccess } from '@/hooks/useDeviceAccess';

function EditorPage() {
  const { camera, gallery, microphone, notifications, platform } = useDeviceAccess();

  const handleImport = async () => {
    // Funciona en Tauri, Capacitor y Web automaticamente
    const videos = await gallery.pickMedia({ mediaType: 'video', multiple: true });
    console.log('Videos importados:', videos);
  };

  const handleCapture = async () => {
    const photo = await camera.capture({ source: 'camera', quality: 95 });
    console.log('Foto capturada:', photo);
  };

  const handleExport = async (videoPath: string) => {
    await gallery.saveVideo(videoPath, 'mi_video_editado.mp4');
    await notifications.show({
      title: 'Exportacion completa',
      body: 'Tu video esta listo en la galeria',
    });
  };

  return (
    <div>
      <p>Plataforma detectada: {platform}</p>
      <button onClick={handleImport}>Importar video</button>
      <button onClick={handleCapture}>Grabar video</button>
    </div>
  );
}
```

---

## 7. Notarizacion y Distribucion

### macOS (Notarizacion obligatoria)
```bash
# Crear .dmg firmado
npm run tauri:build

# Notarizar con Apple
xcrun notarytool submit "Sergio Studio.dmg" \
  --apple-id "tu@email.com" \
  --team-id "TEAM_ID" \
  --password "app-specific-password" \
  --wait

# Staple
xcrun stapler staple "Sergio Studio.dmg"
```

### Windows (Firma de codigo)
```bash
# Con certificado EV
signtool sign /fd sha256 /a /tr http://timestamp.digicert.com \
  /td sha256 "Sergio Studio.exe"
```

### Linux (Repositorio)
```bash
# Generar .deb y .rpm
cargo tauri build

# Subir a PPA o repositorio personal
```

---

## 8. Solucion de Problemas

### Error: `Could not find Cargo.toml`
```bash
cd frontend/src-tauri
cargo check
```

### Error: `No signing certificate found` (iOS)
- Abrir Xcode > Preferences > Accounts > Add Apple ID
- Seleccionar team en proyecto

### Error: `Android SDK not found`
```bash
export ANDROID_HOME=$HOME/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools
```

### Video no procesa en mobile
- Verificar que ffmpeg esta embebido en el binary (Tauri) o disponible en PATH
- En Android, usar el plugin de filesystem para acceso a cache

---

## 9. Roadmap de Plataformas

| Feature | Desktop | iOS | Android | Web |
|---|---|---|---|---|
| Editor de video | ✅ | ✅ | ✅ | ✅ |
| Video Boost IMAX | ✅ | ⚠️ (lento) | ⚠️ (lento) | ❌ |
| Stabilizacion | ✅ | ✅ | ✅ | ❌ |
| Trend Radar | ✅ | ✅ | ✅ | ✅ |
| Human Thought | ✅ | ✅ | ✅ | ✅ |
| Voiceover local | ✅ | ⚠️ | ⚠️ | ❌ |
| VFX Blender | ✅ | ❌ | ❌ | ❌ |
| Export 4K | ✅ | ✅ | ✅ | ⚠️ |
| Offline mode | ✅ | ✅ | ✅ | ⚠️ |

*✅ Completo | ⚠️ Limitado | ❌ No disponible*

---

*Documentacion generada el 2026-11-13. Para soporte: abrir issue en GitHub.*
