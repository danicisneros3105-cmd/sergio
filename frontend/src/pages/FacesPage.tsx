import { useCallback, useEffect, useRef, useState } from 'react';
import { Camera, Loader2, Trash2, UserPlus, ScanFace } from 'lucide-react';
import { apiFetch } from '../lib/api';

interface Person {
  name: string;
  samples: number;
}

interface FaceResult {
  name: string | null;
  score: number;
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body.detail ?? `Error ${res.status}`;
  } catch {
    return `Error ${res.status}`;
  }
}

// Local face recognition: the photo goes only to this computer's Sergio server.
export function FacesPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [people, setPeople] = useState<Person[]>([]);
  const [results, setResults] = useState<FaceResult[] | null>(null);
  const [name, setName] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const loadPeople = useCallback(async () => {
    const res = await apiFetch('/v1/faces');
    if (res.ok) setPeople((await res.json()).people);
  }, []);

  useEffect(() => {
    loadPeople();
    const video = videoRef.current;
    return () => {
      const stream = video?.srcObject as MediaStream | null;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [loadPeople]);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraOn(true);
      setMessage('');
    } catch {
      setMessage('Could not open the camera. Allow camera access in the browser.');
    }
  };

  const snapshot = (): Promise<Blob | null> =>
    new Promise((resolve) => {
      const video = videoRef.current;
      if (!video || !video.videoWidth) return resolve(null);
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext('2d')?.drawImage(video, 0, 0);
      canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.9);
    });

  const send = async (path: string, extra: Record<string, string> = {}) => {
    const blob = await snapshot();
    if (!blob) {
      setMessage('Turn on the camera first.');
      return null;
    }
    const form = new FormData();
    form.append('image', blob, 'camera.jpg');
    Object.entries(extra).forEach(([k, v]) => form.append(k, v));
    setBusy(true);
    try {
      const res = await apiFetch(path, { method: 'POST', body: form });
      if (!res.ok) {
        setMessage(await readError(res));
        return null;
      }
      return res.json();
    } finally {
      setBusy(false);
    }
  };

  const identify = async () => {
    const body = await send('/v1/faces/identify');
    if (body) {
      setResults(body.faces);
      setMessage(body.faces.length ? '' : 'No faces in the picture.');
    }
  };

  const enroll = async () => {
    const body = await send('/v1/faces/enroll', { name, consent: String(consent) });
    if (body) {
      setMessage(`${body.name} saved (${body.samples} photo(s)). Add 3–5 from different angles.`);
      loadPeople();
    }
  };

  const forget = async (person: string) => {
    const res = await apiFetch(`/v1/faces/${encodeURIComponent(person)}`, { method: 'DELETE' });
    if (res.ok) loadPeople();
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <header>
          <h1 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>
            Faces
          </h1>
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            Sergio recognizes only the people you enroll, with their consent. Everything stays on
            this computer.
          </p>
        </header>

        <div className="rounded-xl overflow-hidden bg-black aspect-video flex items-center justify-center">
          <video ref={videoRef} className={cameraOn ? 'w-full h-full object-cover' : 'hidden'} muted playsInline />
          {!cameraOn && (
            <button
              onClick={startCamera}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-white"
              style={{ background: 'var(--color-accent)' }}
            >
              <Camera size={16} /> Turn on camera
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-3 items-center">
          <button
            onClick={identify}
            disabled={busy || !cameraOn}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-white disabled:opacity-50"
            style={{ background: 'var(--color-accent)' }}
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : <ScanFace size={16} />} Who is this?
          </button>
          {results && (
            <span className="text-sm" style={{ color: 'var(--color-text)' }}>
              {results.map((r) => r.name ?? 'Unknown person').join(', ')}
            </span>
          )}
        </div>

        <section className="rounded-xl p-4 space-y-3" style={{ background: 'var(--color-bg-secondary)' }}>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
            Enroll a person
          </h2>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name"
            className="w-full px-3 py-2 rounded-lg text-sm border"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}
          />
          <label className="flex items-start gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1" />
            This person agreed to be recognized by Sergio.
          </label>
          <button
            onClick={enroll}
            disabled={busy || !cameraOn || !name.trim() || !consent}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-white disabled:opacity-50"
            style={{ background: 'var(--color-accent)' }}
          >
            <UserPlus size={16} /> Save face
          </button>
        </section>

        {message && (
          <p className="text-sm" style={{ color: 'var(--color-warning)' }}>
            {message}
          </p>
        )}

        <section className="space-y-2">
          <h2 className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
            Enrolled ({people.length})
          </h2>
          {people.map((p) => (
            <div
              key={p.name}
              className="flex items-center justify-between px-3 py-2 rounded-lg"
              style={{ background: 'var(--color-bg-secondary)' }}
            >
              <span className="text-sm" style={{ color: 'var(--color-text)' }}>
                {p.name} · {p.samples} photo(s)
              </span>
              <button onClick={() => forget(p.name)} title="Forget" style={{ color: 'var(--color-text-secondary)' }}>
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
