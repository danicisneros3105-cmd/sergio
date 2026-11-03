// Galería: everything made with Sergio (pictures, videos, 3D models), in a fan.
import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../lib/api';
import { FanGallery, type FanItem } from '../components/Gallery/FanGallery';
import { pointAt } from '../lib/pointer';

const PartsViewer = lazy(() => import('../components/Chat/PartsViewer'));

interface Row {
  url: string;
  mini?: string;
  tipo: 'imagen' | 'video' | '3d';
  nombre: string;
  fecha: number;
  modelo?: string;
  piezas?: number;
}

const FILTERS: Array<{ key: 'todo' | FanItem['kind']; label: string }> = [
  { key: 'todo', label: 'Todo' },
  { key: 'imagen', label: 'Imágenes' },
  { key: 'video', label: 'Videos' },
  { key: '3d', label: '3D' },
];

const NICE: Record<string, string> = { portada: 'Portada', video: 'Video', imagen: 'Imagen', foto: 'Foto' };

export function GalleryPage() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [failed, setFailed] = useState('');
  const [tries, setTries] = useState(0);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['key']>('todo');
  const [open, setOpen] = useState<Row | null>(null);

  useEffect(() => {
    setFailed('');
    apiFetch('/v1/creator/galeria')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setRows(Array.isArray(d?.elementos) ? d.elementos : []))
      .catch((e: Error) => {
        // never show a failed load as an empty gallery
        setRows([]);
        setFailed(e.message === '401' || e.message === '403' ? 'Sergio necesita que vuelva a entrar.' : 'No pude cargar la galería.');
      });
  }, [tries]);

  const items = useMemo<FanItem[]>(
    () =>
      (rows ?? [])
        .filter((r) => filter === 'todo' || r.tipo === filter)
        .map((r, i) => ({
          key: `${r.tipo}-${r.url || r.modelo}-${i}`,
          kind: r.tipo,
          title: NICE[r.nombre] ?? r.nombre,
          src: r.url || undefined,
          thumb: r.mini || undefined,
          note: r.fecha ? new Date(r.fecha * 1000).toLocaleDateString() : undefined,
        })),
    [rows, filter],
  );

  useEffect(() => {
    if (rows && rows.length) pointAt({ target: '.fan', text: 'Pase el ratón por las cartas o use las flechas.', ms: 2600 });
  }, [rows]);

  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(null);
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [open]);

  const visible = (rows ?? []).filter((r) => filter === 'todo' || r.tipo === filter);

  return (
    <div className="paper-page" style={{ maxWidth: 1100 }}>
      <h1 className="paper-title">Galería</h1>
      <div className="gal-tabs" role="group" aria-label="Qué mostrar">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
      </div>
      {rows === null ? (
        <div aria-busy="true" style={{ height: 420 }} />
      ) : failed ? (
        <p className="paper-meta" role="alert" style={{ textAlign: 'center', marginTop: 48 }}>
          {failed}{' '}
          <button type="button" className="gal-retry" onClick={() => { setRows(null); setTries((n) => n + 1); }}>
            Reintentar
          </button>
        </p>
      ) : items.length === 0 ? (
        <p className="paper-meta" style={{ textAlign: 'center', marginTop: 48 }}>
          Aquí aparecerá lo que cree con Sergio: imágenes, videos y modelos 3D.
        </p>
      ) : (
        <FanGallery items={items} onOpen={(_it, i) => setOpen(visible[i] ?? null)} />
      )}
      {open && (
        <div className="gal-view" role="dialog" aria-modal="true" aria-label={open.nombre} onClick={() => setOpen(null)}>
          <button type="button" className="gal-close" aria-label="Cerrar" onClick={() => setOpen(null)}>
            ×
          </button>
          <div onClick={(e) => e.stopPropagation()}>
            {open.tipo === 'imagen' && <img src={open.url} alt={open.nombre} />}
            {open.tipo === 'video' && <video src={open.url} controls autoPlay playsInline />}
            {open.tipo === '3d' && open.modelo && (
              <div className="gal-3d">
                <Suspense fallback={null}>
                  <PartsViewer name={open.modelo} />
                </Suspense>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default GalleryPage;
