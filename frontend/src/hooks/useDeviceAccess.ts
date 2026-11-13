/**
 * useDeviceAccess — Hook unificado para acceso al dispositivo
 * Detecta automaticamente la plataforma (Tauri / Capacitor / Web)
 * y usa la API nativa correcta sin que el componente se preocupe.
 */

import { useState, useCallback, useEffect } from 'react';

// ============================================================
// Deteccion de plataforma
// ============================================================

function detectPlatform(): 'tauri' | 'capacitor' | 'web' {
  if (typeof window !== 'undefined') {
    // @ts-expect-error Tauri injecta __TAURI__
    if (window.__TAURI__) return 'tauri';
    // @ts-expect-error Capacitor injecta Capacitor
    if (window.Capacitor?.isNativePlatform()) return 'capacitor';
  }
  return 'web';
}

// ============================================================
// Capacitor plugins (lazy load para evitar crash en desktop)
// ============================================================

async function loadCapacitorCamera() {
  const { Camera, CameraSource, CameraResultType } = await import('@capacitor/camera');
  return { Camera, CameraSource, CameraResultType };
}

async function loadCapacitorFilesystem() {
  const { Filesystem, Directory, Encoding } = await import('@capacitor/filesystem');
  return { Filesystem, Directory, Encoding };
}

async function loadCapacitorLocalNotifications() {
  const { LocalNotifications } = await import('@capacitor/local-notifications');
  return { LocalNotifications };
}

async function loadCapacitorShare() {
  const { Share } = await import('@capacitor/share');
  return { Share };
}

async function loadCapacitorMedia() {
  const { Media } = await import('@capacitor-community/media');
  return { Media };
}

// ============================================================
// Tauri plugins (lazy load para evitar crash en mobile)
// ============================================================

async function loadTauriDialog() {
  const { open, save } = await import('@tauri-apps/plugin-dialog');
  return { open, save };
}

async function loadTauriFs() {
  const { readFile, writeFile, readDir, create, exists, mkdir } = await import('@tauri-apps/plugin-fs');
  return { readFile, writeFile, readDir, create, exists, mkdir };
}

async function loadTauriNotification() {
  const { isPermissionGranted, requestPermission, sendNotification } = await import('@tauri-apps/plugin-notification');
  return { isPermissionGranted, requestPermission, sendNotification };
}

async function loadTauriClipboard() {
  const { readText, writeText } = await import('@tauri-apps/plugin-clipboard-manager');
  return { readText, writeText };
}

async function loadTauriOs() {
  const { platform } = await import('@tauri-apps/plugin-os');
  return { platform };
}

async function loadTauriShell() {
  const { open } = await import('@tauri-apps/plugin-shell');
  return { open };
}

// ============================================================
// Tipos
// ============================================================

export interface CameraCaptureOptions {
  source?: 'prompt' | 'camera' | 'gallery';
  quality?: number;
  allowEditing?: boolean;
}

export interface GalleryPickOptions {
  mediaType?: 'video' | 'image' | 'mixed';
  multiple?: boolean;
  quality?: number;
}

export interface GallerySaveOptions {
  data: string | Blob | ArrayBuffer;
  filename: string;
  albumName?: string;
}

export interface NotificationOptions {
  title: string;
  body: string;
  icon?: string;
  tag?: string;
  actions?: { action: string; title: string }[];
}

export interface ShareOptions {
  title?: string;
  text?: string;
  url?: string;
  files?: File[];
}

export interface FilesystemReadOptions {
  path: string;
  encoding?: 'utf8' | 'base64' | 'binary';
}

export interface FilesystemWriteOptions {
  path: string;
  data: string | ArrayBuffer;
  encoding?: 'utf8' | 'base64';
}

// ============================================================
// Hook principal
// ============================================================

export function useDeviceAccess() {
  const [platform, setPlatform] = useState<'tauri' | 'capacitor' | 'web'>('web');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setPlatform(detectPlatform());
    setReady(true);
  }, []);

  // ==========================================================
  // Camara
  // ==========================================================
  const camera = {
    capture: useCallback(async (opts: CameraCaptureOptions = {}) => {
      if (platform === 'capacitor') {
        const { Camera, CameraSource, CameraResultType } = await loadCapacitorCamera();
        const sourceMap: Record<string, CameraSource> = {
          prompt: CameraSource.Prompt,
          camera: CameraSource.Camera,
          gallery: CameraSource.Photos,
        };
        const result = await Camera.getPhoto({
          quality: opts.quality ?? 90,
          allowEditing: opts.allowEditing ?? false,
          resultType: CameraResultType.Uri,
          source: sourceMap[opts.source ?? 'prompt'] ?? CameraSource.Prompt,
        });
        return result.webPath ?? result.path;
      }

      if (platform === 'tauri') {
        const { open } = await loadTauriDialog();
        const selected = await open({
          multiple: false,
          filters: [
            { name: 'Images', extensions: ['jpg', 'jpeg', 'png', 'webp'] },
            { name: 'Videos', extensions: ['mp4', 'mov', 'webm'] },
          ],
        });
        return selected;
      }

      // Web fallback
      return new Promise<string | null>((resolve) => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*,video/*';
        input.capture = opts.source === 'camera' ? 'environment' : undefined;
        input.onchange = () => {
          const file = input.files?.[0];
          if (file) resolve(URL.createObjectURL(file));
          else resolve(null);
        };
        input.click();
      });
    }, [platform]),
  };

  // ==========================================================
  // Galeria / Media Picker
  // ==========================================================
  const gallery = {
    pickMedia: useCallback(async (opts: GalleryPickOptions = {}) => {
      if (platform === 'capacitor') {
        const { Camera, CameraSource, CameraResultType } = await loadCapacitorCamera();
        const result = await Camera.pickImages({
          quality: opts.quality ?? 90,
          limit: opts.multiple ? 0 : 1,
        });
        return result.photos.map(p => p.webPath ?? p.path);
      }

      if (platform === 'tauri') {
        const { open } = await loadTauriDialog();
        const extMap: Record<string, string[]> = {
          video: ['mp4', 'mov', 'avi', 'mkv', 'webm'],
          image: ['jpg', 'jpeg', 'png', 'webp', 'gif'],
          mixed: ['mp4', 'mov', 'avi', 'mkv', 'webm', 'jpg', 'jpeg', 'png', 'webp', 'gif'],
        };
        const selected = await open({
          multiple: opts.multiple ?? false,
          filters: [{ name: 'Media', extensions: extMap[opts.mediaType ?? 'mixed'] ?? extMap.mixed }],
        });
        return Array.isArray(selected) ? selected : selected ? [selected] : [];
      }

      // Web fallback
      return new Promise<string[]>((resolve) => {
        const input = document.createElement('input');
        input.type = 'file';
        const acceptMap: Record<string, string> = { video: 'video/*', image: 'image/*', mixed: 'image/*,video/*' };
        input.accept = acceptMap[opts.mediaType ?? 'mixed'] ?? acceptMap.mixed;
        input.multiple = opts.multiple ?? false;
        input.onchange = () => {
          const files = input.files ? Array.from(input.files) : [];
          resolve(files.map(f => URL.createObjectURL(f)));
        };
        input.click();
      });
    }, [platform]),

    pickVideo: useCallback(async (multiple = false) => {
      return gallery.pickMedia({ mediaType: 'video', multiple });
    }, [gallery.pickMedia]),

    saveVideo: useCallback(async (videoData: string | Blob, filename: string) => {
      if (platform === 'capacitor') {
        try {
          const { Media } = await loadCapacitorMedia();
          const { Filesystem, Directory } = await loadCapacitorFilesystem();

          // Guardar en cache temporal
          let base64Data = '';
          if (typeof videoData === 'string' && videoData.startsWith('data:')) {
            base64Data = videoData.split(',')[1];
          } else if (videoData instanceof Blob) {
            const arrayBuffer = await videoData.arrayBuffer();
            base64Data = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
          }

          const tempPath = `temp_${Date.now()}_${filename}`;
          await Filesystem.writeFile({
            path: tempPath,
            data: base64Data,
            directory: Directory.Cache,
          });

          const { uri } = await Filesystem.getUri({ path: tempPath, directory: Directory.Cache });
          await Media.saveVideo({ path: uri });
          return true;
        } catch (e) {
          console.error('Error saving video:', e);
          return false;
        }
      }

      if (platform === 'tauri') {
        try {
          const { writeFile } = await loadTauriFs();
          const { save } = await loadTauriDialog();
          const path = await save({ defaultPath: filename });
          if (!path) return false;

          let data: Uint8Array;
          if (typeof videoData === 'string' && videoData.startsWith('data:')) {
            const binary = atob(videoData.split(',')[1]);
            data = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) data[i] = binary.charCodeAt(i);
          } else if (videoData instanceof Blob) {
            data = new Uint8Array(await videoData.arrayBuffer());
          } else {
            data = new Uint8Array(await new Response(videoData).arrayBuffer());
          }

          await writeFile(path, data);
          return true;
        } catch (e) {
          console.error('Error saving video:', e);
          return false;
        }
      }

      // Web fallback — descarga directa
      const blob = videoData instanceof Blob ? videoData : await fetch(videoData).then(r => r.blob());
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      return true;
    }, [platform]),
  };

  // ==========================================================
  // Microfono
  // ==========================================================
  const microphone = {
    requestPermission: useCallback(async () => {
      if (platform === 'capacitor') {
        const { Camera } = await loadCapacitorCamera();
        const { CameraSource, CameraResultType } = await import('@capacitor/camera');
        // Capacitor no tiene permiso de microfono directo, usamos la API web
        return navigator.mediaDevices.getUserMedia({ audio: true }).then(() => true).catch(() => false);
      }
      if (platform === 'tauri') {
        return navigator.mediaDevices.getUserMedia({ audio: true }).then(() => true).catch(() => false);
      }
      return navigator.mediaDevices.getUserMedia({ audio: true }).then(() => true).catch(() => false);
    }, [platform]),

    record: useCallback(async (durationMs = 5000): Promise<Blob | null> => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mediaRecorder = new MediaRecorder(stream);
        const chunks: Blob[] = [];

        return new Promise((resolve) => {
          mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
          mediaRecorder.onstop = () => {
            stream.getTracks().forEach(t => t.stop());
            resolve(new Blob(chunks, { type: 'audio/webm' }));
          };
          mediaRecorder.start();
          setTimeout(() => mediaRecorder.stop(), durationMs);
        });
      } catch {
        return null;
      }
    }, []),
  };

  // ==========================================================
  // Notificaciones
  // ==========================================================
  const notifications = {
    requestPermission: useCallback(async () => {
      if (platform === 'capacitor') {
        const { LocalNotifications } = await loadCapacitorLocalNotifications();
        const result = await LocalNotifications.requestPermissions();
        return result.display === 'granted';
      }
      if (platform === 'tauri') {
        const { requestPermission } = await loadTauriNotification();
        return await requestPermission();
      }
      if ('Notification' in window) {
        const result = await Notification.requestPermission();
        return result === 'granted';
      }
      return false;
    }, [platform]),

    show: useCallback(async (opts: NotificationOptions) => {
      if (platform === 'capacitor') {
        const { LocalNotifications } = await loadCapacitorLocalNotifications();
        await LocalNotifications.schedule({
          notifications: [{
            id: Date.now(),
            title: opts.title,
            body: opts.body,
            schedule: { at: new Date() },
            actionTypeId: opts.tag,
            extra: opts.actions ? { actions: opts.actions } : undefined,
          }],
        });
        return;
      }
      if (platform === 'tauri') {
        const { sendNotification } = await loadTauriNotification();
        sendNotification({ title: opts.title, body: opts.body, icon: opts.icon });
        return;
      }
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(opts.title, {
          body: opts.body,
          icon: opts.icon,
          tag: opts.tag,
        });
      }
    }, [platform]),
  };

  // ==========================================================
  // Filesystem
  // ==========================================================
  const filesystem = {
    readFile: useCallback(async (opts: FilesystemReadOptions) => {
      if (platform === 'capacitor') {
        const { Filesystem, Directory, Encoding } = await loadCapacitorFilesystem();
        const result = await Filesystem.readFile({
          path: opts.path,
          directory: Directory.Documents,
          encoding: opts.encoding === 'utf8' ? Encoding.UTF8 : undefined,
        });
        return result.data;
      }
      if (platform === 'tauri') {
        const { readFile } = await loadTauriFs();
        const data = await readFile(opts.path);
        if (opts.encoding === 'utf8') return new TextDecoder().decode(data);
        return data;
      }
      // Web — usa File System Access API o IndexedDB
      if ('showOpenFilePicker' in window) {
        const [handle] = await (window as any).showOpenFilePicker();
        const file = await handle.getFile();
        if (opts.encoding === 'utf8') return await file.text();
        return await file.arrayBuffer();
      }
      return null;
    }, [platform]),

    writeFile: useCallback(async (opts: FilesystemWriteOptions) => {
      if (platform === 'capacitor') {
        const { Filesystem, Directory, Encoding } = await loadCapacitorFilesystem();
        let data = opts.data;
        if (opts.data instanceof ArrayBuffer) {
          data = btoa(String.fromCharCode(...new Uint8Array(opts.data)));
        }
        await Filesystem.writeFile({
          path: opts.path,
          data: data as string,
          directory: Directory.Documents,
          encoding: opts.encoding === 'utf8' ? Encoding.UTF8 : Encoding.Base64,
        });
        return true;
      }
      if (platform === 'tauri') {
        const { writeFile } = await loadTauriFs();
        let data: Uint8Array;
        if (typeof opts.data === 'string') {
          if (opts.encoding === 'base64') {
            const binary = atob(opts.data);
            data = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) data[i] = binary.charCodeAt(i);
          } else {
            data = new TextEncoder().encode(opts.data);
          }
        } else {
          data = new Uint8Array(opts.data);
        }
        await writeFile(opts.path, data);
        return true;
      }
      // Web fallback
      if ('showSaveFilePicker' in window) {
        const handle = await (window as any).showSaveFilePicker({ suggestedName: opts.path });
        const writable = await handle.createWritable();
        let blob: Blob;
        if (typeof opts.data === 'string') {
          blob = new Blob([opts.data], { type: 'text/plain' });
        } else {
          blob = new Blob([opts.data]);
        }
        await writable.write(blob);
        await writable.close();
        return true;
      }
      return false;
    }, [platform]),

    getAppDir: useCallback(async () => {
      if (platform === 'capacitor') {
        const { Filesystem, Directory } = await loadCapacitorFilesystem();
        const { uri } = await Filesystem.getUri({ path: '', directory: Directory.Documents });
        return uri;
      }
      if (platform === 'tauri') {
        const { platform } = await loadTauriOs();
        const osName = await platform();
        const home = osName === 'windows' ? '%USERPROFILE%' : '~';
        return `${home}/SergioStudio`;
      }
      return '/sergio-studio';
    }, [platform]),
  };

  // ==========================================================
  // Share
  // ==========================================================
  const share = {
    shareVideo: useCallback(async (opts: ShareOptions) => {
      if (platform === 'capacitor') {
        const { Share } = await loadCapacitorShare();
        await Share.share({
          title: opts.title,
          text: opts.text,
          url: opts.url,
          files: opts.files?.map(f => URL.createObjectURL(f)),
          dialogTitle: 'Compartir video',
        });
        return;
      }
      if (platform === 'tauri') {
        const { open } = await loadTauriShell();
        if (opts.url) await open(opts.url);
        else if (opts.files?.[0]) {
          const { writeText } = await loadTauriClipboard();
          await writeText(opts.url ?? opts.text ?? '');
        }
        return;
      }
      // Web Share API
      if (navigator.share) {
        try {
          const shareData: ShareData = { title: opts.title, text: opts.text, url: opts.url };
          if (opts.files && opts.files.length > 0) {
            shareData.files = opts.files;
          }
          await navigator.share(shareData);
        } catch {
          // Fallback a clipboard
          await navigator.clipboard.writeText(opts.url ?? opts.text ?? '');
        }
      } else {
        await navigator.clipboard.writeText(opts.url ?? opts.text ?? '');
      }
    }, [platform]),
  };

  // ==========================================================
  // Auto-request de notificaciones al instalar PWA
  // ==========================================================
  useEffect(() => {
    if (platform === 'web' && 'Notification' in window && Notification.permission === 'default') {
      // Esperar a que el usuario interactue antes de pedir permiso
      const handler = () => {
        notifications.requestPermission();
        window.removeEventListener('click', handler);
      };
      window.addEventListener('click', handler, { once: true });
    }
  }, [platform, notifications]);

  return {
    platform,
    ready,
    camera,
    gallery,
    microphone,
    notifications,
    filesystem,
    share,
  };
}

export default useDeviceAccess;
