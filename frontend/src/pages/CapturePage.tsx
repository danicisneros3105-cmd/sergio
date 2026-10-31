import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { Aperture, Camera, Check, CircleDot, Eye, Monitor, ScanFace, Smartphone, Square, VideoOff } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';
import { useWorkspace } from '../lib/workspace/store';
import { FilePick, Recorder } from '../components/Workspace/MediaBlock';
import type { Block } from '../lib/workspace/model';
import { mediaProblem } from '../lib/compat';
import './vista.css';

interface DetectedFace {
  name?: string | null;
  score: number;
  angle?: string;
  quality?: string;
}

// Vista (once «Sergio ve»): the live camera and a quick capture.
export function CapturePage() {
  const navigate = useNavigate();
  const ready = useWorkspace((s) => s.ready);
  const load = useWorkspace((s) => s.load);
  const capture = useWorkspace((s) => s.capture);
  const [text, setText] = useState('');
  const [count, setCount] = useState(0);
  const [camActive, setCamActive] = useState(false);
  const [videoRec, setVideoRec] = useState(false);
  const [detected, setDetected] = useState<DetectedFace[]>([]);
  const [poseInfo, setPoseInfo] = useState<{ yaw: number; pitch: number; faces: number } | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const videoRecorderRef = useRef<MediaRecorder | null>(null);
  const videoChunksRef = useRef<Blob[]>([]);

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
      media: { file: dataUrl, name: `vista-${Date.now()}.jpg`, mime: 'image/jpeg' },
      text: text.trim() || 'Capturado desde Vista',
    });
    setText('');
    setCount((c) => c + 1);
    toast.success('Fotograma guardado en el Workspace.');
  };

  const toggleVideoRecording = async () => {
    if (videoRec && videoRecorderRef.current) {
      videoRecorderRef.current.stop();
      videoRecorderRef.current = null;
      setVideoRec(false);
      return;
    }
    try {
      let stream = streamRef.current;
      if (!stream) {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 1280, height: 720, facingMode: 'environment' },
          audio: true,
        });
        streamRef.current = stream;
        setCamActive(true);
        requestAnimationFrame(() => {
          if (videoRef.current && stream) {
            videoRef.current.srcObject = stream;
            void videoRef.current.play();
          }
        });
      }
      const mime = ['video/webm;codecs=vp9,opus', 'video/webm', 'video/mp4'].find((m) => MediaRecorder.isTypeSupported?.(m)) || '';
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      videoChunksRef.current = [];
      recorder.ondataavailable = (e) => e.data.size && videoChunksRef.current.push(e.data);
      recorder.onstop = async () => {
        const blob = new Blob(videoChunksRef.current, { type: recorder.mimeType || 'video/webm' });
        const ext = blob.type.includes('mp4') ? 'mp4' : 'webm';
        const form = new FormData();
        form.append('file', blob, `video-${Date.now()}.${ext}`);
        form.append('kind', 'video');
        form.append('caption', text.trim() || 'Video grabado desde dispositivo');
        const res = await apiFetch('/v1/devices/upload', { method: 'POST', body: form }).catch(() => null);
        if (res?.ok) {
          toast.success('Video guardado y sincronizado con el PC.');
        } else {
          toast.success('Video grabado.');
        }
        setCount((c) => c + 1);
      };
      recorder.start(2000);
      videoRecorderRef.current = recorder;
      setVideoRec(true);
      toast.success('Grabando video en vivo…');
    } catch {
      toast.error('No se pudo iniciar la grabación de video.');
    }
  };

  const requestPhoneVideo = async () => {
    try {
      const res = await apiFetch('/v1/devices/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_device: 'phone',
          action: 'record_video',
          params: { seconds: 30, note: text.trim() },
        }),
      });
      if (res.ok) {
        toast.success('Orden enviada al teléfono: empezando a grabar video.');
      }
    } catch {
      toast.error('No se pudo enviar la orden al teléfono.');
    }
  };

  useEffect(() => {
    const onRemoteCmd = (ev: Event) => {
      const detail = (ev as CustomEvent<{ action?: string }>).detail;
      if (!detail) return;
      if (detail.action === 'record_video' && !videoRec) {
        void toggleVideoRecording();
      } else if (detail.action === 'stop_video' && videoRec) {
        void toggleVideoRecording();
      } else if (detail.action === 'take_photo') {
        snapToWorkspace();
      }
    };
    window.addEventListener('sergio:device-command', onRemoteCmd);
    return () => window.removeEventListener('sergio:device-command', onRemoteCmd);
  });

  const openDesktopCamera = async () => {
    await apiFetch('/v1/desktop/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section: 'camera' }),
    }).catch(() => {});
    toast.success('Vista abierta en el PC.');
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

  const faces = poseInfo?.faces ?? 0;
  const who = detected.find((d) => d.name)?.name;

  // Minimal, like the rest of the app: a title, the picture and a row of
  // round icon buttons. Nothing follows the face around (owner, oct. 2026).
  return (
    <div className="paper-page">
      <div className="paper-page-inner vista">
        <header className="vista-head">
          <h1 className="paper-title">Vista</h1>
          <span className="vista-state" data-on={camActive || undefined}>
            <i aria-hidden />
            {camActive ? (who ? who : faces ? `${faces}` : 'En vivo') : 'En reposo'}
          </span>
        </header>

        <section className="vista-stage" data-on={camActive || undefined}>
          {camActive ? (
            <video ref={videoRef} muted playsInline />
          ) : (
            <button type="button" className="vista-wake" onClick={toggleCam} aria-label="Encender la cámara">
              <Eye size={28} strokeWidth={1.5} />
            </button>
          )}
          <div className="vista-bar" role="toolbar" aria-label="Controles de Vista">
            <button type="button" onClick={toggleCam} aria-label={camActive ? 'Apagar la cámara' : 'Encender la cámara'} title={camActive ? 'Apagar' : 'Encender'}>
              {camActive ? <VideoOff size={18} strokeWidth={1.7} /> : <Camera size={18} strokeWidth={1.7} />}
            </button>
            <button type="button" onClick={snapToWorkspace} disabled={!camActive} aria-label="Guardar este fotograma" title="Guardar fotograma">
              <Aperture size={18} strokeWidth={1.7} />
            </button>
            <button type="button" onClick={() => void toggleVideoRecording()} aria-label={videoRec ? 'Detener grabación de video' : 'Grabar video'} title={videoRec ? 'Detener video' : 'Grabar video'}>
              {videoRec ? <Square size={18} strokeWidth={1.9} /> : <CircleDot size={18} strokeWidth={1.7} />}
            </button>
            <button type="button" onClick={() => void requestPhoneVideo()} aria-label="Grabar video desde el teléfono" title="Grabar video desde mi teléfono">
              <Smartphone size={18} strokeWidth={1.7} />
            </button>
            <button type="button" onClick={openDesktopCamera} aria-label="Abrir en el PC" title="Abrir en el PC">
              <Monitor size={18} strokeWidth={1.7} />
            </button>
            <button type="button" onClick={() => navigate('/faces')} aria-label="Rostros" title="Rostros">
              <ScanFace size={18} strokeWidth={1.7} />
            </button>
          </div>
        </section>

        <section className="vista-note">
          <textarea
            ref={area}
            className="ws-capture"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save();
            }}
            placeholder="Una nota…"
            aria-label="Nota rápida"
          />
          <div className="vista-note-row">
            <button type="button" className="paper-button" onClick={save} disabled={!text.trim()}>
              <Check size={14} /> Guardar
            </button>
            <Recorder onSaved={media('audio')} />
            <FilePick accept="image/*" capture="environment" label="Foto" onSaved={media('image')} />
            <span className="vista-count">{count ? `${count} guardadas` : ''}</span>
          </div>
        </section>
      </div>
    </div>
  );
}

export default CapturePage;
