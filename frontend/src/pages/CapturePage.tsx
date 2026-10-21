import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { Camera, Check, Eye, Monitor, Sparkles, VideoOff } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';
import { useWorkspace } from '../lib/workspace/store';
import { FilePick, Recorder } from '../components/Workspace/MediaBlock';
import type { Block } from '../lib/workspace/model';
import { mediaProblem } from '../lib/compat';

interface DetectedFace {
  name?: string | null;
  score: number;
  angle?: string;
  quality?: string;
}

// "Sergio ve" & Captura, in the app's colours (theme variables only).
export function CapturePage() {
  const navigate = useNavigate();
  const ready = useWorkspace((s) => s.ready);
  const load = useWorkspace((s) => s.load);
  const capture = useWorkspace((s) => s.capture);
  const [text, setText] = useState('');
  const [count, setCount] = useState(0);
  const [camActive, setCamActive] = useState(false);
  const [detected, setDetected] = useState<DetectedFace[]>([]);
  const [poseInfo, setPoseInfo] = useState<{ yaw: number; pitch: number; faces: number } | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (!ready) void load();
    area.current?.focus();
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [ready, load]);

  const toggleCam = async () => {
    if (camActive) {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setCamActive(false);
      setDetected([]);
      setPoseInfo(null);
      return;
    }
    const problem = mediaProblem('cámara');
    if (problem) {
      toast.error(problem);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 960, height: 540, facingMode: 'user' },
      });
      streamRef.current = stream;
      setCamActive(true);
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          void videoRef.current.play();
        }
      });
    } catch {
      toast.error('No se pudo abrir la cámara. Verifique los permisos.');
    }
  };

  useEffect(() => {
    if (!camActive) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      if (cancelled || !videoRef.current || !videoRef.current.videoWidth) return;
      const canvas = document.createElement('canvas');
      canvas.width = 480;
      canvas.height = Math.round((videoRef.current.videoHeight / videoRef.current.videoWidth) * 480);
      canvas.getContext('2d')?.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
      const blob: Blob | null = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', 0.82));
      if (!blob || cancelled) return;
      try {
        const f1 = new FormData();
        f1.append('image', blob, 'look.jpg');
        const [pRes, idRes] = await Promise.all([
          apiFetch('/v1/faces/pose', { method: 'POST', body: f1 }),
          (() => {
            const f2 = new FormData();
            f2.append('image', blob, 'id.jpg');
            return apiFetch('/v1/faces/identify', { method: 'POST', body: f2 });
          })(),
        ]);
        if (pRes.ok) {
          const p = await pRes.json();
          if (p.face) setPoseInfo({ yaw: p.yaw, pitch: p.pitch, faces: p.faces });
          else setPoseInfo(null);
        }
        if (idRes.ok) {
          const idData = await idRes.json();
          setDetected(idData.faces || []);
        }
      } catch {
        // Ignore transient frame errors
      }
    }, 900);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [camActive]);

  const snapToWorkspace = () => {
    if (!videoRef.current || !videoRef.current.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    canvas.getContext('2d')?.drawImage(videoRef.current, 0, 0);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
    capture({
      kind: 'image',
      media: { file: dataUrl, name: `sergio-ve-${Date.now()}.jpg`, mime: 'image/jpeg' },
      text: text.trim() || 'Capturado desde Sergio ve',
    });
    setText('');
    setCount((c) => c + 1);
    toast.success('Fotograma guardado en el Workspace.');
  };

  const openDesktopCamera = async () => {
    await apiFetch('/v1/desktop/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section: 'camera' }),
    }).catch(() => {});
    toast.success('Ventana flotante «Sergio ve» sincronizada.');
  };

  const saved = () => {
    setCount((c) => c + 1);
    toast.success('Guardado en la Bandeja de entrada.');
  };

  const save = () => {
    if (!text.trim()) return;
    capture({ text: text.trim() });
    setText('');
    saved();
    area.current?.focus();
  };

  const media = (kind: 'audio' | 'image') => (m: NonNullable<Block['media']>) => {
    capture({ kind, media: m, text: text.trim() || undefined });
    setText('');
    saved();
  };

  return (
    <div className="paper-page">
      <div className="paper-page-inner" style={{ maxWidth: 820 }}>
        <header className="paper-head" style={{ marginBottom: 20 }}>
          <div>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 12,
                fontWeight: 600,
                padding: '4px 10px',
                borderRadius: 999,
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text)',
                marginBottom: 8,
              }}
            >
              <Eye size={13} /> Sergio ve · Visión en vivo & Captura
            </span>
            <h1 className="paper-title">Sergio ve</h1>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="paper-button" onClick={toggleCam}>
              {camActive ? <VideoOff size={15} /> : <Camera size={15} />}
              {camActive ? 'Apagar cámara' : 'Encender «Sergio ve»'}
            </button>
            <button type="button" className="paper-button" data-variant="quiet" onClick={openDesktopCamera}>
              <Monitor size={15} /> Ventana flotante PC
            </button>
          </div>
        </header>

        {/* Live "Sergio ve" viewport */}
        <section
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 22,
            padding: 16,
            marginBottom: 20,
            boxShadow: 'none',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 12,
              padding: '6px 12px',
              background: 'var(--color-bg-secondary)',
              borderRadius: 999,
              border: '1px solid var(--color-border)',
            }}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600, color: 'var(--color-text)' }}>
              <span
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: '50%',
                  background: camActive ? 'var(--color-text)' : 'var(--color-text-secondary)',
                  boxShadow: camActive ? '0 0 0 4px color-mix(in srgb, var(--color-text) 15%, transparent)' : 'none',
                }}
              />
              Sergio ve
              {poseInfo ? ` · ${poseInfo.faces} rostro${poseInfo.faces === 1 ? '' : 's'} en vista` : camActive ? ' · observando' : ' · cámara en reposo'}
            </span>
            <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
              {detected.length > 0
                ? detected.map((d) => (d.name ? `${d.name} (${Math.round(d.score * 100)}%)` : 'Invitado')).join(' · ')
                : poseInfo
                  ? `Ángulo ${poseInfo.yaw.toFixed(0)}° / ${poseInfo.pitch.toFixed(0)}°`
                  : 'Cifrado local activo'}
            </span>
          </div>

          {camActive ? (
            <div style={{ position: 'relative', borderRadius: 16, overflow: 'hidden', background: 'var(--color-bg-secondary)', aspectRatio: '16/9' }}>
              <video
                ref={videoRef}
                muted
                playsInline
                style={{ width: '100%', height: '100%', objectFit: 'cover', transform: 'scaleX(-1)' }}
              />
              <div
                style={{
                  position: 'absolute',
                  bottom: 12,
                  left: 12,
                  right: 12,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                }}
              >
                <span
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text)',
                    padding: '6px 12px',
                    borderRadius: 999,
                    fontSize: 12.5,
                    fontWeight: 600,
                  }}
                >
                  {detected[0]?.name
                    ? `Reconocido: ${detected[0].name} · ${Math.round(detected[0].score * 100)}%`
                    : poseInfo
                      ? 'Rostro detectado en tiempo real'
                      : 'Apunte la cámara a una persona, documento u objeto'}
                </span>
                <button type="button" className="paper-button" onClick={snapToWorkspace}>
                  <Camera size={14} /> Capturar al Workspace
                </button>
              </div>
            </div>
          ) : (
            <div
              style={{
                borderRadius: 16,
                background: 'var(--color-bg-secondary)',
                border: '1px dashed var(--color-border)',
                padding: '36px 24px',
                textAlign: 'center',
              }}
            >
              <Eye size={32} style={{ margin: '0 auto 10px', color: 'var(--color-text)' }} />
              <p style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--color-text)', marginBottom: 4 }}>
                Vista unificada de «Sergio ve»
              </p>
              <p style={{ fontSize: 13, color: 'var(--color-text-secondary)', maxWidth: 460, margin: '0 auto 14px' }}>
                Encienda la cámara aquí o abra la ventana flotante en su PC para que Sergio reconozca rostros, gestos, objetos y documentos con el mismo diseño cálido de toda la app.
              </p>
              <div className="flex items-center justify-center gap-2">
                <button type="button" className="paper-button" onClick={toggleCam}>
                  <Camera size={14} /> Activar vista en vivo
                </button>
                <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/faces')}>
                  <Sparkles size={14} /> Configurar Face ID
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Quick Workspace Capture */}
        <section
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 18,
            padding: 16,
          }}
        >
          <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)', marginBottom: 8 }}>
            Nota rápida o captura multimodal
          </h2>
          <textarea
            ref={area}
            className="ws-capture"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save();
            }}
            placeholder="Una idea, una observación de cámara, una tarea, lo que sea…"
            aria-label="Nota rápida"
          />
          <div className="flex flex-wrap items-center gap-2 mt-3">
            <button type="button" className="paper-button" onClick={save} disabled={!text.trim()}>
              <Check size={14} /> Guardar en bandeja
            </button>
            <Recorder onSaved={media('audio')} />
            <FilePick accept="image/*" capture="environment" label="Subir foto" onSaved={media('image')} />
            <span className="ml-auto text-[12px]" style={{ color: 'var(--color-text-tertiary)' }}>
              {count ? `${count} guardadas` : 'Ctrl+Enter guarda'}
            </span>
          </div>
        </section>

        <button type="button" className="paper-tab mt-6" onClick={() => navigate('/workspace')}>
          Ir al Workspace →
        </button>
      </div>
    </div>
  );
}

export default CapturePage;
