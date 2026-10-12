// Creator's design and image studio (Fabric.js). "Diseño" is a Canva-style
// canvas: formats, texts, shapes, photos, a brush, layers, and Sergio
// designing the whole layout from one sentence. "Imagen" is the photo
// editor: adjustments and filters on this computer, background removal
// (OpenCV, local) and generative edits / new images with Gemini.
// Everything is undoable and stays in this browser until exported.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Canvas,
  Circle,
  FabricImage,
  type FabricObject,
  PencilBrush,
  Rect,
  Textbox,
  filters,
} from 'fabric';
import {
  ArrowDown,
  ArrowUp,
  Brush,
  Circle as CircleIcon,
  Copy,
  Download,
  FlipHorizontal2,
  ImagePlus,
  Redo2,
  RotateCw,
  Square,
  Trash2,
  Type,
  Undo2,
  Wand2,
  Eraser,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { elapsedNote, useElapsed } from './useElapsed';

type Mode = 'diseno' | 'imagen';

export const FORMATS = [
  { id: 'post', label: 'Post cuadrado', w: 1080, h: 1080 },
  { id: 'story', label: 'Historia / Reel', w: 1080, h: 1920 },
  { id: 'slide', label: 'Presentación', w: 1920, h: 1080 },
  { id: 'thumb', label: 'Miniatura de YouTube', w: 1280, h: 720 },
  { id: 'poster', label: 'Póster A4', w: 1240, h: 1754 },
  { id: 'card', label: 'Tarjeta de visita', w: 1050, h: 600 },
] as const;

const FONTS = ['Inter Variable', 'Josefin Sans Variable', 'Georgia', 'Courier New'];

/** One design element as Sergio returns it (/v1/creator/design). */
export interface LayoutElement {
  type: 'rect' | 'circle' | 'text';
  x: number;
  y: number;
  w?: number;
  h?: number;
  r?: number;
  fill?: string;
  radius?: number;
  text?: string;
  size?: number;
  weight?: number;
  color?: string;
  align?: 'left' | 'center' | 'right';
}

/** Sergio's layout → Fabric objects (pure; tested). */
export function layoutObjects(elements: LayoutElement[]): FabricObject[] {
  const out: FabricObject[] = [];
  for (const e of elements) {
    if (e.type === 'rect') {
      out.push(
        new Rect({ left: e.x, top: e.y, width: e.w ?? 100, height: e.h ?? 100, fill: e.fill, rx: e.radius ?? 0, ry: e.radius ?? 0 }),
      );
    } else if (e.type === 'circle') {
      out.push(new Circle({ left: e.x, top: e.y, radius: e.r ?? 50, fill: e.fill }));
    } else if (e.type === 'text' && e.text) {
      out.push(
        new Textbox(e.text, {
          left: e.x,
          top: e.y,
          width: e.w ?? 600,
          fontSize: e.size ?? 40,
          fontWeight: e.weight ?? 700,
          fill: e.color ?? '#111111',
          textAlign: e.align ?? 'left',
          fontFamily: FONTS[0],
        }),
      );
    }
  }
  for (const o of out) o.set({ originX: 'left', originY: 'top' });
  return out;
}

const objectLabel = (o: FabricObject): string => {
  if (o instanceof Textbox) return `Texto · ${o.text?.slice(0, 18) ?? ''}`;
  if (o instanceof FabricImage) return 'Imagen';
  if (o instanceof Circle) return 'Círculo';
  if (o instanceof Rect) return 'Rectángulo';
  if (o.type === 'path') return 'Trazo';
  return 'Elemento';
};

function download(url: string, name: string): void {
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
}

/** data: URL → Blob without fetch (the page's security policy refuses
 *  fetching data: URLs, rightly). */
export function blobOf(dataUrl: string): Blob {
  const [head, body = ''] = dataUrl.split(',', 2);
  const mime = /data:([^;,]+)/.exec(head)?.[1] ?? 'application/octet-stream';
  const bin = head.includes(';base64') ? atob(body) : decodeURIComponent(body);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

interface Adjust {
  brightness: number;
  contrast: number;
  saturation: number;
  blur: number;
  gray: boolean;
  sepia: boolean;
  vintage: boolean;
  sharpen: boolean;
}
const NO_ADJUST: Adjust = { brightness: 0, contrast: 0, saturation: 0, blur: 0, gray: false, sepia: false, vintage: false, sharpen: false };

function applyAdjust(img: FabricImage, a: Adjust): void {
  const list: FabricImage['filters'] = [];
  if (a.brightness) list.push(new filters.Brightness({ brightness: a.brightness }));
  if (a.contrast) list.push(new filters.Contrast({ contrast: a.contrast }));
  if (a.saturation) list.push(new filters.Saturation({ saturation: a.saturation }));
  if (a.gray) list.push(new filters.Grayscale());
  if (a.sepia) list.push(new filters.Sepia());
  if (a.vintage) list.push(new filters.Vintage());
  if (a.sharpen) list.push(new filters.Convolute({ matrix: [0, -1, 0, -1, 5, -1, 0, -1, 0] }));
  if (a.blur) list.push(new filters.Blur({ blur: a.blur }));
  img.filters = list;
  img.applyFilters();
  (img as FabricImage & { sergioAdjust?: Adjust }).sergioAdjust = a;
}

export function DesignStudio({ mode }: { mode: Mode }) {
  const isImage = mode === 'imagen';
  const stage = useRef<HTMLDivElement>(null);
  const canvasEl = useRef<HTMLCanvasElement>(null);
  const fabric = useRef<Canvas | null>(null);
  const [format, setFormat] = useState(() => (isImage ? { id: 'free', label: 'Imagen', w: 1280, h: 960 } : FORMATS[0]));
  const [zoom, setZoom] = useState(0.5);
  const [active, setActive] = useState<FabricObject | null>(null);
  const [layers, setLayers] = useState<FabricObject[]>([]);
  const [drawing, setDrawing] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState('');
  const elapsed = useElapsed(busy);
  const [, force] = useState(0);
  const history = useRef<{ undo: string[]; redo: string[]; quiet: boolean }>({ undo: [], redo: [], quiet: false });
  const storeKey = `sergio.creator.${mode}`;
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    const c = fabric.current;
    if (!c) return;
    setLayers([...c.getObjects()].reverse());
    setActive(c.getActiveObject() ?? null);
    force((n) => n + 1);
  }, []);

  // Listeners on the canvas live as long as it does: they read these refs.
  const formatRef = useRef(format);
  formatRef.current = format;
  const snapshot = () => JSON.stringify({ format: formatRef.current, canvas: fabric.current?.toObject(['sergioAdjust']) });

  // Every change: one undo step, saved in this browser.
  const record = useCallback(() => {
    const h = history.current;
    if (h.quiet || !fabric.current) return;
    const now = snapshot();
    if (h.undo[h.undo.length - 1] === now) return;
    h.undo.push(now);
    if (h.undo.length > 60) h.undo.shift();
    h.redo = [];
    try {
      localStorage.setItem(storeKey, now);
    } catch {
      // too big for local storage (large photos): kept until the tab closes
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeKey, refresh]);
  const recordRef = useRef(record);
  recordRef.current = record;

  const restore = useCallback(
    async (state: string) => {
      const c = fabric.current;
      if (!c) return;
      const data = JSON.parse(state) as { format: typeof format; canvas: object };
      history.current.quiet = true;
      setFormat(data.format);
      await c.loadFromJSON(data.canvas);
      c.getObjects().forEach((o) => {
        const a = (o as FabricImage & { sergioAdjust?: Adjust }).sergioAdjust;
        if (o instanceof FabricImage && a) applyAdjust(o, a);
      });
      c.requestRenderAll();
      history.current.quiet = false;
      refresh();
    },
    [refresh],
  );

  // -- canvas (created once) ------------------------------------------------------
  useEffect(() => {
    if (!canvasEl.current) return;
    const c = new Canvas(canvasEl.current, { preserveObjectStacking: true, backgroundColor: '#ffffff' });
    fabric.current = c;
    c.freeDrawingBrush = new PencilBrush(c);
    c.freeDrawingBrush.width = 8;
    c.freeDrawingBrush.color = '#4f7cff';
    const onChange = () => recordRef.current();
    c.on('object:modified', onChange);
    c.on('object:added', onChange);
    c.on('object:removed', onChange);
    c.on('path:created', onChange);
    c.on('selection:created', refresh);
    c.on('selection:updated', refresh);
    c.on('selection:cleared', refresh);
    const saved = (() => {
      try {
        return localStorage.getItem(storeKey);
      } catch {
        return null;
      }
    })();
    if (saved) {
      restore(saved)
        .then(() => {
          history.current.undo = [saved];
        })
        .catch(() => undefined);
    } else {
      history.current.undo = [snapshot()];
    }
    return () => {
      fabric.current = null;
      void c.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fit the page into the stage (zoomed view; exports are full size).
  useEffect(() => {
    const c = fabric.current;
    const el = stage.current;
    if (!c || !el) return;
    const fit = () => {
      const z = Math.min((el.clientWidth - 48) / format.w, (el.clientHeight - 48) / format.h, 1);
      const zz = Math.max(0.05, z);
      setZoom(zz);
      c.setDimensions({ width: Math.round(format.w * zz), height: Math.round(format.h * zz) });
      c.setZoom(zz);
      c.requestRenderAll();
    };
    fit();
    recordRef.current(); // a new format is one undo step (no-op when unchanged)
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [format]);

  useEffect(() => {
    const c = fabric.current;
    if (c) c.isDrawingMode = drawing;
  }, [drawing]);

  // -- actions ----------------------------------------------------------------------
  const add = (o: FabricObject) => {
    const c = fabric.current;
    if (!c) return;
    setDrawing(false);
    c.add(o);
    c.setActiveObject(o);
    c.requestRenderAll();
    refresh();
  };

  const centre = () => ({ left: format.w * 0.1, top: format.h * 0.1 });

  const addTitle = () =>
    add(new Textbox('Su título aquí', { ...centre(), width: format.w * 0.8, fontSize: Math.round(format.w / 12), fontWeight: 800, fill: '#14161f', fontFamily: FONTS[0] }));
  const addText = () =>
    add(new Textbox('Escriba algo', { ...centre(), width: format.w * 0.6, fontSize: Math.round(format.w / 30), fontWeight: 450, fill: '#3a3f55', fontFamily: FONTS[0] }));
  const addRect = () => add(new Rect({ ...centre(), width: format.w * 0.3, height: format.h * 0.2, fill: '#4f7cff', rx: 24, ry: 24 }));
  const addCircle = () => add(new Circle({ ...centre(), radius: Math.min(format.w, format.h) * 0.12, fill: '#a35cff' }));

  const placeImage = async (url: string, fill = false) => {
    const c = fabric.current;
    if (!c) return;
    const img = await FabricImage.fromURL(url, { crossOrigin: 'anonymous' });
    const scale = fill
      ? Math.min(format.w / (img.width || 1), format.h / (img.height || 1))
      : Math.min((format.w * 0.6) / (img.width || 1), (format.h * 0.6) / (img.height || 1), 1);
    img.scale(scale);
    img.set({
      left: (format.w - (img.width || 0) * scale) / 2,
      top: (format.h - (img.height || 0) * scale) / 2,
    });
    add(img);
    return img;
  };

  const openFile = async (file: File) => {
    if (!file.type.startsWith('image/')) return toast.error('Eso no es una imagen.');
    const url = await new Promise<string>((ok, fail) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result));
      r.onerror = () => fail(r.error);
      r.readAsDataURL(file);
    });
    if (isImage) {
      // The photo sets the page: a photo editor works on the photo itself.
      const probe = await FabricImage.fromURL(url);
      const w = probe.width || 1280;
      const h = probe.height || 960;
      const k = Math.min(1, 4096 / Math.max(w, h));
      fabric.current?.clear();
      if (fabric.current) fabric.current.backgroundColor = ''; // transparent: a photo editor keeps cut-outs clear
      setFormat({ id: 'free', label: file.name.slice(0, 40), w: Math.round(w * k), h: Math.round(h * k) });
      setTimeout(() => void placeImage(url, true), 30);
    } else await placeImage(url);
  };

  const remove = () => {
    const c = fabric.current;
    if (!c) return;
    c.getActiveObjects().forEach((o) => c.remove(o));
    c.discardActiveObject();
    c.requestRenderAll();
    refresh();
  };

  const duplicate = async () => {
    const c = fabric.current;
    const o = c?.getActiveObject();
    if (!c || !o) return;
    const copy = await o.clone();
    copy.set({ left: (o.left ?? 0) + 30, top: (o.top ?? 0) + 30 });
    add(copy);
  };

  const layer = (dir: 'up' | 'down') => {
    const c = fabric.current;
    const o = c?.getActiveObject();
    if (!c || !o) return;
    if (dir === 'up') c.bringObjectForward(o);
    else c.sendObjectBackwards(o);
    c.requestRenderAll();
    record();
  };

  const set = (patch: Record<string, unknown>) => {
    const c = fabric.current;
    const o = c?.getActiveObject();
    if (!c || !o) return;
    o.set(patch);
    o.setCoords();
    c.requestRenderAll();
    record();
  };

  const undo = async () => {
    const h = history.current;
    if (h.undo.length < 2) return;
    h.redo.push(h.undo.pop() as string);
    await restore(h.undo[h.undo.length - 1]);
  };
  const redo = async () => {
    const h = history.current;
    const next = h.redo.pop();
    if (!next) return;
    h.undo.push(next);
    await restore(next);
  };

  const exportAs = (kind: 'png' | 'jpeg' | 'svg') => {
    const c = fabric.current;
    if (!c) return;
    c.discardActiveObject();
    c.requestRenderAll();
    const name = `sergio-${mode}-${format.w}x${format.h}`;
    if (kind === 'svg') {
      const svg = c.toSVG({ width: `${format.w}`, height: `${format.h}`, viewBox: { x: 0, y: 0, width: format.w, height: format.h } });
      const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
      download(url, `${name}.svg`);
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } else {
      // JPG has no transparency: a clear page becomes white, not black.
      const clear = kind === 'jpeg' && !c.backgroundColor;
      if (clear) c.backgroundColor = '#ffffff';
      download(c.toDataURL({ format: kind, quality: 0.92, multiplier: 1 / zoom }), `${name}.${kind === 'jpeg' ? 'jpg' : 'png'}`);
      if (clear) {
        c.backgroundColor = '';
        c.requestRenderAll();
      }
    }
  };

  // Sergio designs the whole page from one sentence.
  const designWithSergio = async () => {
    const request = prompt.trim();
    const c = fabric.current;
    if (!request || !c) return;
    setBusy('Sergio está diseñando…');
    try {
      const res = await apiFetch('/v1/creator/design', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request, width: format.w, height: format.h }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'No pude diseñarlo.');
      history.current.quiet = true;
      c.clear();
      c.backgroundColor = body.background || '#ffffff';
      for (const o of layoutObjects(body.elements as LayoutElement[])) c.add(o);
      c.requestRenderAll();
      history.current.quiet = false;
      record();
      setPrompt('');
      toast.success('Diseño listo. Todo se puede editar: toque cualquier elemento.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude diseñarlo.');
    } finally {
      history.current.quiet = false;
      setBusy('');
    }
  };

  // The selected photo (or the only one) for the image tools.
  const targetImage = (): FabricImage | null => {
    const c = fabric.current;
    if (!c) return null;
    const a = c.getActiveObject();
    if (a instanceof FabricImage) return a;
    const all = c.getObjects().filter((o): o is FabricImage => o instanceof FabricImage);
    return all.length === 1 ? all[0] : null;
  };

  const replaceImage = async (old: FabricImage, blob: Blob) => {
    const c = fabric.current;
    if (!c) return;
    const url = await new Promise<string>((ok) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result));
      r.readAsDataURL(blob);
    });
    const img = await FabricImage.fromURL(url);
    const shown = (old.width || 1) * (old.scaleX || 1);
    img.scale(shown / (img.width || 1));
    img.set({ left: old.left, top: old.top, angle: old.angle, flipX: old.flipX });
    history.current.quiet = true;
    const index = c.getObjects().indexOf(old);
    c.remove(old);
    c.insertAt(Math.max(0, index), img);
    c.setActiveObject(img);
    c.requestRenderAll();
    history.current.quiet = false;
    record();
  };

  const imageBlob = async (img: FabricImage) => blobOf(img.toDataURL({ format: 'png', multiplier: 1 / (img.scaleX || 1) }));

  const cutout = async () => {
    const img = targetImage();
    if (!img) return toast.error('Seleccione una foto primero.');
    setBusy('Quitando el fondo en este equipo…');
    try {
      const form = new FormData();
      form.append('image', await imageBlob(img), 'foto.png');
      const res = await apiFetch('/v1/creator/image/cutout', { method: 'POST', body: form });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'No pude quitar el fondo.');
      const method = res.headers.get('X-Sergio-Recorte');
      await replaceImage(img, await res.blob());
      if (method === 'grabcut') toast.message('Fondo quitado con el método básico: no pude descargar la red de recorte (¿sin internet?).');
      else toast.success('Fondo quitado. Ctrl+Z lo deshace.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude quitar el fondo.');
    } finally {
      setBusy('');
    }
  };

  const generative = async () => {
    const text = prompt.trim();
    if (!text) return toast.error('Describa la imagen o el cambio.');
    const img = targetImage();
    setBusy(img ? 'Editando la foto con IA…' : 'Creando la imagen con IA…');
    try {
      let res: Response;
      if (img) {
        const form = new FormData();
        form.append('image', await imageBlob(img), 'foto.png');
        form.append('instruction', text);
        res = await apiFetch('/v1/creator/image/edit', { method: 'POST', body: form });
      } else {
        res = await apiFetch('/v1/creator/image/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: text }),
        });
      }
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'La IA de imagen no respondió.');
      const blob = await res.blob();
      if (img) await replaceImage(img, blob);
      else await openFile(new File([blob], 'sergio.png', { type: 'image/png' }));
      setPrompt('');
      toast.success(img ? 'Cambio aplicado. Ctrl+Z lo deshace.' : 'Imagen creada.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'La IA de imagen no respondió.');
    } finally {
      setBusy('');
    }
  };

  const adjustOf = (img: FabricImage | null): Adjust => ({
    ...NO_ADJUST,
    ...((img as (FabricImage & { sergioAdjust?: Adjust }) | null)?.sergioAdjust ?? {}),
  });
  const adjust = (patch: Partial<Adjust>) => {
    const img = targetImage();
    if (!img) return;
    applyAdjust(img, { ...adjustOf(img), ...patch });
    fabric.current?.requestRenderAll();
    force((n) => n + 1);
  };

  // Keys: Supr deletes, Ctrl+Z / Ctrl+Y, Ctrl+D duplicates (not while typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      const editing = fabric.current?.getActiveObject() as (FabricObject & { isEditing?: boolean }) | undefined;
      if (editing?.isEditing) return;
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && k === 'z') {
        e.preventDefault();
        void (e.shiftKey ? redo() : undo());
      } else if ((e.ctrlKey || e.metaKey) && k === 'y') void redo();
      else if ((e.ctrlKey || e.metaKey) && k === 'd') {
        e.preventDefault();
        void duplicate();
      } else if (k === 'delete' || k === 'backspace') remove();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const img = targetImage();
  const adj = adjustOf(img);
  const text = active instanceof Textbox ? active : null;
  const fill = typeof active?.fill === 'string' ? active.fill : '#000000';

  return (
    <div className="studio2d" data-mode={mode}>
      <aside className="studio-tools" aria-label="Herramientas">
        {!isImage && (
          <>
            <button type="button" className="studio-tool" title="Título" aria-label="Añadir título" onClick={addTitle}>
              <Type size={19} strokeWidth={2.2} />
            </button>
            <button type="button" className="studio-tool" title="Texto" aria-label="Añadir texto" onClick={addText}>
              <Type size={15} />
            </button>
            <button type="button" className="studio-tool" title="Rectángulo" aria-label="Añadir rectángulo" onClick={addRect}>
              <Square size={17} />
            </button>
            <button type="button" className="studio-tool" title="Círculo" aria-label="Añadir círculo" onClick={addCircle}>
              <CircleIcon size={17} />
            </button>
          </>
        )}
        <button type="button" className="studio-tool" title={isImage ? 'Abrir foto' : 'Añadir foto'} aria-label={isImage ? 'Abrir foto' : 'Añadir foto'} onClick={() => fileInput.current?.click()}>
          <ImagePlus size={17} />
        </button>
        <button type="button" className="studio-tool" title="Pincel" aria-label="Pincel" aria-pressed={drawing} onClick={() => setDrawing((d) => !d)}>
          <Brush size={17} />
        </button>
        <span className="studio-sep" />
        <button type="button" className="studio-tool" title="Duplicar (Ctrl+D)" aria-label="Duplicar" onClick={() => void duplicate()} disabled={!active}>
          <Copy size={17} />
        </button>
        <button type="button" className="studio-tool" title="Borrar (Supr)" aria-label="Borrar" onClick={remove} disabled={!active}>
          <Trash2 size={17} />
        </button>
        <button type="button" className="studio-tool" title="Traer adelante" aria-label="Traer adelante" onClick={() => layer('up')} disabled={!active}>
          <ArrowUp size={17} />
        </button>
        <button type="button" className="studio-tool" title="Enviar atrás" aria-label="Enviar atrás" onClick={() => layer('down')} disabled={!active}>
          <ArrowDown size={17} />
        </button>
        <span className="studio-sep" />
        <button type="button" className="studio-tool" title="Deshacer (Ctrl+Z)" aria-label="Deshacer" onClick={() => void undo()}>
          <Undo2 size={17} />
        </button>
        <button type="button" className="studio-tool" title="Rehacer (Ctrl+Y)" aria-label="Rehacer" onClick={() => void redo()}>
          <Redo2 size={17} />
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="image/*"
          hidden
          data-testid="image-file"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void openFile(f);
            e.target.value = '';
          }}
        />
      </aside>

      <div className="studio-view">
        <div
          ref={stage}
          className="studio-stage"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files?.[0];
            if (f) void openFile(f);
          }}
        >
          <div className="studio-page" data-testid="design-page">
            <canvas ref={canvasEl} />
          </div>
          {isImage && !img && !busy && layers.length === 0 && (
            <div className="studio-drop">
              <ImagePlus size={28} />
              <b>Arrastre una foto aquí</b>
              <span>o pídale a Sergio que cree una imagen abajo</span>
            </div>
          )}
        </div>
        <div className="studio-hud">
          {format.label} · {format.w}×{format.h} px · {Math.round(zoom * 100)} %{busy && <b> · {busy}{elapsedNote(elapsed)}</b>}
        </div>
        <form
          className="studio-ask"
          onSubmit={(e) => {
            e.preventDefault();
            void (isImage ? generative() : designWithSergio());
          }}
        >
          <input
            className="paper-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={!!busy}
            aria-label={isImage ? 'Pedir una imagen o un cambio' : 'Pedir un diseño a Sergio'}
            placeholder={
              isImage
                ? img
                  ? 'Cambio con IA: «cambia el cielo a atardecer», «quita la persona del fondo»'
                  : 'Describa una imagen nueva: «una taza de café en una mesa de madera, luz suave»'
                : 'Describa el diseño: «post para la apertura de mi cafetería el sábado, 20 % de descuento»'
            }
          />
          <button type="submit" className="paper-button" disabled={!!busy || !prompt.trim()}>
            <Wand2 size={15} /> {isImage ? (img ? 'Aplicar' : 'Crear') : 'Diseñar'}
          </button>
        </form>
      </div>

      <aside className="studio-side">
        {!isImage && (
          <section className="studio-panel">
            <h3>Formato</h3>
            <div className="studio-formats">
              {FORMATS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  aria-pressed={format.id === f.id}
                  onClick={() => setFormat(f)}
                >
                  <i style={{ aspectRatio: `${f.w} / ${f.h}` }} />
                  <span>{f.label}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {isImage && (
          <section className="studio-panel">
            <h3>Foto</h3>
            {img ? (
              <div className="studio-props">
                {(
                  [
                    ['brightness', 'Brillo', -0.6, 0.6],
                    ['contrast', 'Contraste', -0.6, 0.6],
                    ['saturation', 'Saturación', -1, 1],
                    ['blur', 'Desenfoque', 0, 0.6],
                  ] as const
                ).map(([k, label, min, max]) => (
                  <label key={k} className="studio-slider">
                    {label}
                    <input
                      type="range"
                      min={min}
                      max={max}
                      step={0.02}
                      value={adj[k]}
                      onChange={(e) => adjust({ [k]: Number(e.target.value) })}
                      onPointerUp={record}
                      onKeyUp={record}
                    />
                  </label>
                ))}
                <div className="studio-chips">
                  {(
                    [
                      ['gray', 'B/N'],
                      ['sepia', 'Sepia'],
                      ['vintage', 'Vintage'],
                      ['sharpen', 'Nitidez'],
                    ] as const
                  ).map(([k, label]) => (
                    <button
                      key={k}
                      type="button"
                      aria-pressed={adj[k]}
                      onClick={() => {
                        adjust({ [k]: !adj[k] });
                        record();
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="studio-chips">
                  <button type="button" onClick={() => set({ angle: ((img.angle ?? 0) + 90) % 360 })}>
                    <RotateCw size={14} /> Girar
                  </button>
                  <button type="button" onClick={() => set({ flipX: !img.flipX })}>
                    <FlipHorizontal2 size={14} /> Espejo
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      applyAdjust(img, NO_ADJUST);
                      fabric.current?.requestRenderAll();
                      record();
                    }}
                  >
                    Original
                  </button>
                </div>
                <button type="button" className="paper-button" onClick={() => void cutout()} disabled={!!busy}>
                  <Eraser size={15} /> Quitar fondo
                </button>
              </div>
            ) : (
              <p className="studio-empty">Abra o arrastre una foto, o cree una con IA.</p>
            )}
          </section>
        )}

        <section className="studio-panel">
          <h3>{active ? objectLabel(active) : 'Página'}</h3>
          <div className="studio-props">
            {active ? (
              <>
                {!(active instanceof FabricImage) && (
                  <label>
                    Color
                    <input type="color" value={/^#[0-9a-f]{6}$/i.test(fill) ? fill : '#000000'} onChange={(e) => set({ fill: e.target.value })} />
                  </label>
                )}
                {text && (
                  <>
                    <label>
                      Letra
                      <select className="paper-input" value={String(text.fontFamily)} onChange={(e) => set({ fontFamily: e.target.value })}>
                        {FONTS.map((f) => (
                          <option key={f} value={f}>
                            {f.replace(' Variable', '')}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Tamaño
                      <input type="number" min={6} max={600} value={Math.round(text.fontSize ?? 40)} onChange={(e) => set({ fontSize: Math.max(6, Number(e.target.value) || 6) })} />
                    </label>
                    <div className="studio-chips">
                      <button type="button" aria-pressed={Number(text.fontWeight) >= 700} onClick={() => set({ fontWeight: Number(text.fontWeight) >= 700 ? 450 : 800 })}>
                        Negrita
                      </button>
                      {(['left', 'center', 'right'] as const).map((a) => (
                        <button key={a} type="button" aria-pressed={text.textAlign === a} onClick={() => set({ textAlign: a })}>
                          {a === 'left' ? 'Izq.' : a === 'center' ? 'Centro' : 'Der.'}
                        </button>
                      ))}
                    </div>
                  </>
                )}
                <label className="studio-slider">
                  Opacidad
                  <input type="range" min={0.05} max={1} step={0.05} value={active.opacity ?? 1} onChange={(e) => set({ opacity: Number(e.target.value) })} />
                </label>
              </>
            ) : (
              <label>
                Fondo
                <input
                  type="color"
                  value={typeof fabric.current?.backgroundColor === 'string' ? fabric.current.backgroundColor : '#ffffff'}
                  onChange={(e) => {
                    const c = fabric.current;
                    if (!c) return;
                    c.backgroundColor = e.target.value;
                    c.requestRenderAll();
                    record();
                  }}
                />
              </label>
            )}
            {drawing && (
              <label>
                Color del pincel
                <input
                  type="color"
                  defaultValue="#4f7cff"
                  onChange={(e) => {
                    const b = fabric.current?.freeDrawingBrush;
                    if (b) b.color = e.target.value;
                  }}
                />
              </label>
            )}
          </div>
        </section>

        <section className="studio-panel">
          <h3>Capas</h3>
          <ul className="studio-outliner">
            {layers.length === 0 && <li className="studio-empty">Sin elementos todavía.</li>}
            {layers.map((o, i) => (
              <li key={i} aria-selected={o === active}>
                <button
                  type="button"
                  onClick={() => {
                    fabric.current?.setActiveObject(o);
                    fabric.current?.requestRenderAll();
                    refresh();
                  }}
                >
                  <i style={{ background: typeof o.fill === 'string' ? o.fill : '#9aa3b5' }} />
                  {objectLabel(o)}
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="studio-panel studio-export">
          <button type="button" className="paper-button" onClick={() => exportAs('png')}>
            <Download size={15} /> Descargar PNG
          </button>
          <button type="button" className="paper-button" data-variant="quiet" onClick={() => exportAs('jpeg')}>
            JPG
          </button>
          {!isImage && (
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => exportAs('svg')}>
              SVG
            </button>
          )}
          <button
            type="button"
            className="paper-button"
            data-variant="quiet"
            onClick={() => {
              const c = fabric.current;
              if (!c || !c.getObjects().length || !window.confirm('¿Empezar de cero?')) return;
              c.clear();
              c.backgroundColor = '#ffffff';
              c.requestRenderAll();
              record();
            }}
          >
            Empezar de cero
          </button>
        </section>
      </aside>
    </div>
  );
}

export default DesignStudio;
