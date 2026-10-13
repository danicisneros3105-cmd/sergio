// Creator's 3D studio, laid out like Blender: tools on the left, the
// viewport in the middle, the outliner and properties on the right, and a
// bar where you ask Sergio for an object. Shortcuts as in Blender: G move,
// R rotate, S scale, X / Supr delete, Shift+D duplicate, F frame, Ctrl+Z.
// "Arquitectura" adds walls (two clicks on the floor), doors, windows, a
// plan view and a DXF export.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js';
import { GLTFExporter } from 'three/examples/jsm/exporters/GLTFExporter.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import {
  Box,
  Copy,
  DoorOpen,
  Download,
  Eye,
  EyeOff,
  Focus,
  Grid3x3,
  Move3d,
  MousePointer2,
  Redo2,
  RectangleHorizontal,
  Rotate3d,
  Scale3d,
  Square,
  Trash2,
  Undo2,
  AppWindow,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { elapsedNote, useElapsed } from './useElapsed';
import {
  ADDABLE,
  DEG,
  buildGeometry,
  buildMaterial,
  fromRecipe,
  geometryKey,
  newId,
  opening,
  placeBeside,
  planOf,
  primitive,
  wall,
  type Item,
  type RecipePart,
} from './scene';

type Tool = 'select' | 'translate' | 'rotate' | 'scale' | 'wall' | 'door' | 'window';

const STORE = 'sergio.creator.scene';

function loadScene(key: string): Item[] {
  try {
    const raw = localStorage.getItem(`${STORE}.${key}`);
    const items = raw ? (JSON.parse(raw) as Item[]) : [];
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
}

function saveScene(key: string, items: Item[]): void {
  try {
    localStorage.setItem(`${STORE}.${key}`, JSON.stringify(items));
  } catch {
    // storage full or private window: the scene lives until the tab closes
  }
}

function download(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const snap = (v: number, step = 0.1) => Math.round(v / step) * step;

export function Studio3D({ mode }: { mode: 'modelado' | 'arquitectura' }) {
  const arch = mode === 'arquitectura';
  const host = useRef<HTMLDivElement>(null);
  const [items, setItemsState] = useState<Item[]>(() => loadScene(mode));
  const [selected, setSelected] = useState<string | null>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [tool, setTool] = useState<Tool>(arch ? 'wall' : 'translate');
  const [planView, setPlanView] = useState(arch);
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState('');
  const elapsed = useElapsed(busy);
  const [lastRequest, setLastRequest] = useState('');
  const undo = useRef<Item[][]>([]);
  const redo = useRef<Item[][]>([]);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  // Every change goes through here: undo stack + saved in this browser.
  const setItems = useCallback(
    (next: Item[] | ((prev: Item[]) => Item[]), record = true) => {
      setItemsState((prev) => {
        const value = typeof next === 'function' ? next(prev) : next;
        if (record) {
          undo.current.push(prev);
          if (undo.current.length > 100) undo.current.shift();
          redo.current = [];
        }
        saveScene(mode, value);
        return value;
      });
    },
    [mode],
  );

  // -- three.js world (created once) --------------------------------------------
  const world = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    orbit: OrbitControls;
    gizmo: TransformControls;
    meshes: Map<string, { mesh: THREE.Mesh; key: string }>;
    floor: THREE.Mesh;
    preview: THREE.Line;
  } | null>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    renderer.shadowMap.enabled = true;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#1d1f27');
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    const camera = new THREE.PerspectiveCamera(45, 1, 0.005, 2000);
    camera.position.set(4, 3.2, 5);
    const sun = new THREE.DirectionalLight('#ffffff', 2.2);
    sun.position.set(5, 9, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    scene.add(sun, new THREE.HemisphereLight('#dfe8ff', '#30323d', 0.6));
    const grid = new THREE.GridHelper(40, 40, '#5b6178', '#33364a');
    scene.add(grid);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.ShadowMaterial({ opacity: 0.22 }));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    floor.name = '__floor';
    scene.add(floor);
    const preview = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
      new THREE.LineBasicMaterial({ color: '#7b9cff' }),
    );
    preview.visible = false;
    scene.add(preview);
    const orbit = new OrbitControls(camera, renderer.domElement);
    orbit.enableDamping = true;
    orbit.target.set(0, 0.5, 0);
    const gizmo = new TransformControls(camera, renderer.domElement);
    gizmo.addEventListener('dragging-changed', (e) => {
      orbit.enabled = !e.value;
      if (!e.value) {
        // Commit the drag into the scene data (one undo step).
        const obj = gizmo.object as THREE.Mesh | undefined;
        if (!obj) return;
        const id = obj.userData.id as string;
        setItems((prev) =>
          prev.map((it) =>
            it.id === id
              ? {
                  ...it,
                  pos: [obj.position.x, obj.position.y, obj.position.z],
                  rot: [obj.rotation.x / DEG, obj.rotation.y / DEG, obj.rotation.z / DEG],
                  scale: [obj.scale.x, obj.scale.y, obj.scale.z],
                }
              : it,
          ),
        );
      }
    });
    scene.add(gizmo.getHelper());
    world.current = { renderer, scene, camera, orbit, gizmo, meshes: new Map(), floor, preview };

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el;
      renderer.setSize(w, h);
      camera.aspect = w / Math.max(1, h);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();
    let frame = 0;
    const loop = () => {
      orbit.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(loop);
    };
    loop();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      gizmo.dispose();
      orbit.dispose();
      renderer.dispose();
      pmrem.dispose();
      el.removeChild(renderer.domElement);
      world.current = null;
    };
  }, [setItems]);

  // -- data → meshes ------------------------------------------------------------
  useEffect(() => {
    const w = world.current;
    if (!w) return;
    const seen = new Set<string>();
    for (const it of items) {
      seen.add(it.id);
      const key = geometryKey(it);
      let entry = w.meshes.get(it.id);
      if (!entry || entry.key !== key) {
        if (entry) {
          if (w.gizmo.object === entry.mesh) w.gizmo.detach();
          w.scene.remove(entry.mesh);
          entry.mesh.geometry.dispose();
        }
        let geometry: THREE.BufferGeometry;
        try {
          geometry = buildGeometry(it);
        } catch {
          geometry = new THREE.BoxGeometry(...it.size);
        }
        const mesh = new THREE.Mesh(geometry, buildMaterial(it));
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        mesh.userData.id = it.id;
        w.scene.add(mesh);
        entry = { mesh, key };
        w.meshes.set(it.id, entry);
      }
      const m = entry.mesh;
      m.position.set(...it.pos);
      m.rotation.set(it.rot[0] * DEG, it.rot[1] * DEG, it.rot[2] * DEG, 'XYZ');
      m.scale.set(...it.scale);
      (m.material as THREE.MeshStandardMaterial).color.set(it.color);
      m.visible = it.visible;
    }
    for (const [id, entry] of w.meshes) {
      if (!seen.has(id)) {
        if (w.gizmo.object === entry.mesh) w.gizmo.detach();
        w.scene.remove(entry.mesh);
        entry.mesh.geometry.dispose();
        w.meshes.delete(id);
      }
    }
  }, [items]);

  // Selection and the active tool drive the gizmo.
  useEffect(() => {
    const w = world.current;
    if (!w) return;
    const entry = selected ? w.meshes.get(selected) : undefined;
    if (entry && ['translate', 'rotate', 'scale'].includes(tool)) {
      w.gizmo.attach(entry.mesh);
      w.gizmo.setMode(tool as 'translate' | 'rotate' | 'scale');
      w.gizmo.setTranslationSnap(arch ? 0.1 : null);
    } else w.gizmo.detach();
  }, [selected, tool, items, arch]);

  // Plan view: from above, no orbiting (like a drawing board).
  useEffect(() => {
    const w = world.current;
    if (!w) return;
    const box = new THREE.Box3();
    for (const { mesh } of w.meshes.values()) if (mesh.visible) box.expandByObject(mesh);
    if (planView) {
      // Straight down over the drawing, high enough to see all of it.
      const c = box.isEmpty() ? new THREE.Vector3(0, 0, 0) : box.getCenter(new THREE.Vector3());
      const extent = box.isEmpty() ? 0 : Math.max(box.max.x - box.min.x, box.max.z - box.min.z);
      w.orbit.target.set(c.x, 0, c.z);
      w.camera.position.set(c.x, Math.max(18, extent * 1.4), c.z + 0.001);
      w.orbit.enableRotate = false;
    } else {
      w.orbit.enableRotate = true;
      w.camera.position.set(w.orbit.target.x + 6, 5, w.orbit.target.z + 8);
      if (!box.isEmpty()) frameOn(itemsRef.current.filter((i) => i.visible).map((i) => i.id));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planView]);

  // -- pointer: select, or draw walls / place openings --------------------------
  const wallStart = useRef<[number, number] | null>(null);
  const floorPoint = (e: React.PointerEvent): [number, number] | null => {
    const w = world.current;
    if (!w) return null;
    const rect = w.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, w.camera);
    const hit = ray.intersectObject(w.floor)[0];
    if (!hit) return null;
    // Snap to the 10 cm grid and to the ends of existing walls (25 cm).
    let x = snap(hit.point.x);
    let z = snap(hit.point.z);
    for (const it of itemsRef.current.filter((i) => i.shape === 'wall')) {
      const half = it.size[0] / 2;
      const a = -it.rot[1] * DEG;
      for (const s of [-1, 1]) {
        const ex = it.pos[0] + Math.cos(a) * half * s;
        const ez = it.pos[2] + Math.sin(a) * half * s;
        if (Math.hypot(ex - hit.point.x, ez - hit.point.z) < 0.25) {
          x = ex;
          z = ez;
        }
      }
    }
    return [x, z];
  };

  const pick = (e: React.PointerEvent): string | null => {
    const w = world.current;
    if (!w) return null;
    const rect = w.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, w.camera);
    const meshes = [...w.meshes.values()].map((m) => m.mesh).filter((m) => m.visible);
    const hit = ray.intersectObjects(meshes, false)[0];
    return hit ? (hit.object.userData.id as string) : null;
  };

  const down = useRef<{ x: number; y: number } | null>(null);
  const onPointerDown = (e: React.PointerEvent) => {
    down.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const start = down.current;
    down.current = null;
    if (!start || Math.hypot(e.clientX - start.x, e.clientY - start.y) > 5) return; // it was an orbit drag
    if (world.current?.gizmo.dragging) return;
    if (tool === 'wall') {
      const p = floorPoint(e);
      if (!p) return;
      if (!wallStart.current) {
        wallStart.current = p;
        return;
      }
      const a = wallStart.current;
      if (Math.hypot(p[0] - a[0], p[1] - a[1]) < 0.15) return;
      const created = wall(a, p);
      setItems((prev) => [...prev, created]);
      wallStart.current = p; // keep drawing from the end, like a polyline
      setSelected(created.id);
      return;
    }
    if (tool === 'door' || tool === 'window') {
      const p = floorPoint(e);
      if (!p) return;
      // Align with the nearest wall.
      let angle = 0;
      let best = Infinity;
      for (const it of itemsRef.current.filter((i) => i.shape === 'wall')) {
        const d = Math.hypot(it.pos[0] - p[0], it.pos[2] - p[1]);
        if (d < best) {
          best = d;
          angle = it.rot[1];
        }
      }
      const created = opening(tool, p, angle);
      setItems((prev) => [...prev, created]);
      setSelected(created.id);
      return;
    }
    setSelected(pick(e));
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const w = world.current;
    if (!w) return;
    if (tool === 'wall' && wallStart.current) {
      const p = floorPoint(e);
      if (!p) return;
      w.preview.geometry.setFromPoints([
        new THREE.Vector3(wallStart.current[0], 0.02, wallStart.current[1]),
        new THREE.Vector3(p[0], 0.02, p[1]),
      ]);
      w.preview.visible = true;
    } else w.preview.visible = false;
  };

  // -- actions --------------------------------------------------------------------
  const sel = items.find((i) => i.id === selected) || null;

  const update = (patch: Partial<Item>) => {
    if (!sel) return;
    setItems((prev) => prev.map((it) => (it.id === sel.id ? { ...it, ...patch } : it)));
  };

  const remove = useCallback(() => {
    if (!selected) return;
    setItems((prev) => prev.filter((it) => it.id !== selected));
    setSelected(null);
  }, [selected, setItems]);

  const duplicate = useCallback(() => {
    const it = itemsRef.current.find((i) => i.id === selected);
    if (!it) return;
    const copy = { ...it, id: newId(), name: `${it.name} (copia)`, pos: [it.pos[0] + 0.3, it.pos[1], it.pos[2] + 0.3] as Item['pos'] };
    setItems((prev) => [...prev, copy]);
    setSelected(copy.id);
  }, [selected, setItems]);

  const doUndo = useCallback(() => {
    const prev = undo.current.pop();
    if (!prev) return;
    redo.current.push(itemsRef.current);
    setItems(prev, false);
  }, [setItems]);

  const doRedo = useCallback(() => {
    const next = redo.current.pop();
    if (!next) return;
    undo.current.push(itemsRef.current);
    setItems(next, false);
  }, [setItems]);

  // Frame the given items, else the selection, else everything visible.
  const frameOn = useCallback((ids?: string[]) => {
    const w = world.current;
    if (!w) return;
    const box = new THREE.Box3();
    const only = ids ?? (selectedRef.current ? [selectedRef.current] : null);
    for (const [id, { mesh }] of w.meshes) if (mesh.visible && (!only || only.includes(id))) box.expandByObject(mesh);
    if (box.isEmpty()) return;
    const centre = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    w.orbit.target.copy(centre);
    const dir = w.camera.position.clone().sub(centre).normalize();
    w.camera.position.copy(centre.clone().add(dir.multiplyScalar(size * 1.6)));
    w.camera.near = size / 200;
    w.camera.updateProjectionMatrix();
  }, []);
  const frame = useCallback(() => frameOn(), [frameOn]);

  // Blender's keys.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && k === 'z') {
        e.preventDefault();
        if (e.shiftKey) doRedo();
        else doUndo();
      } else if ((e.ctrlKey || e.metaKey) && k === 'y') doRedo();
      else if (e.shiftKey && k === 'd') duplicate();
      else if (k === 'g') setTool('translate');
      else if (k === 'r') setTool('rotate');
      else if (k === 's') setTool('scale');
      else if (k === 'x' || k === 'delete') remove();
      else if (k === 'f') frame();
      else if (k === 'escape') {
        wallStart.current = null;
        setSelected(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [doUndo, doRedo, duplicate, remove, frame]);

  // Sergio designs an object part by part (/v1/vision/holo_model).
  const ask = async () => {
    const request = prompt.trim();
    if (!request) return;
    setBusy('Sergio está diseñando las piezas…');
    try {
      const res = await apiFetch('/v1/vision/holo_model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'No pude diseñarlo.');
      const group = newId();
      const parts = placeBeside(itemsRef.current, fromRecipe(body.parts as RecipePart[], group));
      setItems((prev) => [...prev, ...parts]);
      setLastRequest(request);
      setPrompt('');
      setSelected(null);
      toast.success(`${body.name}: ${parts.length} piezas`);
      setTimeout(() => frameOn(parts.map((p) => p.id)), 60);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude diseñarlo.');
    } finally {
      setBusy('');
    }
  };

  const exportGlb = () => {
    const w = world.current;
    if (!w) return;
    const group = new THREE.Group();
    for (const { mesh } of w.meshes.values()) if (mesh.visible) group.add(mesh.clone());
    new GLTFExporter().parse(
      group,
      (out) => download(new Blob([out as ArrayBuffer], { type: 'model/gltf-binary' }), `creator-${mode}.glb`),
      () => toast.error('No pude exportar el modelo.'),
      { binary: true },
    );
  };

  const exportDxf = async () => {
    const plan = planOf(items);
    if (!plan.walls.length) return toast.error('Dibuje al menos un muro.');
    const res = await apiFetch('/v1/creator/plan/dxf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(plan),
    });
    if (!res.ok) return toast.error((await res.json().catch(() => ({}))).detail || 'No pude crear el plano.');
    download(await res.blob(), 'plano-sergio.dxf');
    toast.success('Plano DXF descargado (muros, huecos y cotas).');
  };

  // The same plan as a BIM building (IFC): walls, and doors and windows cut
  // into them, for FreeCAD or Blender with Bonsai.
  const exportIfc = async () => {
    const plan = planOf(items);
    if (!plan.walls.length) return toast.error('Dibuje al menos un muro.');
    const res = await apiFetch('/v1/creator/plan/ifc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(plan),
    });
    if (!res.ok) return toast.error((await res.json().catch(() => ({}))).detail || 'No pude crear el edificio IFC.');
    download(await res.blob(), 'plano-sergio.ifc');
    toast.success('Edificio IFC descargado.');
  };

  // Make the file and open it in the real program on the owner's PC.
  const openPlan = async (program: 'freecad' | 'bonsai' | 'librecad') => {
    const plan = planOf(items);
    if (!plan.walls.length) return toast.error('Dibuje al menos un muro.');
    const kind = program === 'librecad' ? 'dxf' : 'ifc';
    const res = await apiFetch('/v1/creator/plan/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...plan, program, kind }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) return toast.error(body.detail || 'No pude abrir el plano.');
    toast.success(body.message || 'Abriendo el plano…');
  };

  // Blender Pro writes a checked script from the same request; the owner's
  // Blender runs it (Scripting → Run) and it saves the .blend by itself.
  const toBlender = async () => {
    if (!lastRequest) return;
    setBusy('Sergio está preparando la versión de producción…');
    try {
      const name = lastRequest.replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '').slice(0, 40).toLowerCase() || 'modelo';
      const res = await apiFetch('/v1/vision/blender/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: lastRequest, save_path: `~/Sergio/Creator/${name}.blend` }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || typeof body.script !== 'string') throw new Error(body.detail || 'El estudio 3D no respondió.');
      download(new Blob([body.script], { type: 'text/x-python' }), `sergio-${name}.py`);
      toast.success(`Listo: sergio-${name}.py (Estudio 3D → Scripting → Ejecutar).`, {
        duration: 9000,
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'El estudio 3D no respondió.');
    } finally {
      setBusy('');
    }
  };

  const tools: Array<{ id: Tool; icon: typeof Box; label: string; key?: string }> = useMemo(
    () => [
      { id: 'select', icon: MousePointer2, label: 'Seleccionar' },
      { id: 'translate', icon: Move3d, label: 'Mover', key: 'G' },
      { id: 'rotate', icon: Rotate3d, label: 'Rotar', key: 'R' },
      { id: 'scale', icon: Scale3d, label: 'Escalar', key: 'S' },
      ...(arch
        ? [
            { id: 'wall' as Tool, icon: RectangleHorizontal, label: 'Muro (clic, clic)' },
            { id: 'door' as Tool, icon: DoorOpen, label: 'Puerta' },
            { id: 'window' as Tool, icon: AppWindow, label: 'Ventana' },
          ]
        : []),
    ],
    [arch],
  );

  const totalWalls = items.filter((i) => i.shape === 'wall').reduce((s, i) => s + i.size[0] * i.scale[0], 0);

  return (
    <div className="studio3d">
      <aside className="studio-tools" aria-label="Herramientas">
        {tools.map(({ id, icon: Icon, label, key }) => (
          <button
            key={id}
            type="button"
            className="studio-tool"
            aria-pressed={tool === id}
            title={key ? `${label} (${key})` : label}
            aria-label={label}
            onClick={() => {
              wallStart.current = null;
              setTool(id);
            }}
          >
            <Icon size={18} strokeWidth={1.7} />
          </button>
        ))}
        <span className="studio-sep" />
        <details className="studio-add">
          <summary className="studio-tool" title="Añadir" aria-label="Añadir objeto">
            <Box size={18} strokeWidth={1.7} />
          </summary>
          <div className="studio-menu" role="menu">
            {ADDABLE.map((a) => (
              <button
                key={a.shape}
                type="button"
                role="menuitem"
                onClick={(e) => {
                  const it = primitive(a.shape);
                  setItems((prev) => [...prev, it]);
                  setSelected(it.id);
                  (e.currentTarget.closest('details') as HTMLDetailsElement).open = false;
                }}
              >
                {a.label}
              </button>
            ))}
          </div>
        </details>
        <button type="button" className="studio-tool" title="Duplicar (Mayús+D)" aria-label="Duplicar" onClick={duplicate} disabled={!sel}>
          <Copy size={17} />
        </button>
        <button type="button" className="studio-tool" title="Borrar (X)" aria-label="Borrar" onClick={remove} disabled={!sel}>
          <Trash2 size={17} />
        </button>
        <span className="studio-sep" />
        <button type="button" className="studio-tool" title="Deshacer (Ctrl+Z)" aria-label="Deshacer" onClick={doUndo}>
          <Undo2 size={17} />
        </button>
        <button type="button" className="studio-tool" title="Rehacer (Ctrl+Mayús+Z)" aria-label="Rehacer" onClick={doRedo}>
          <Redo2 size={17} />
        </button>
        <button type="button" className="studio-tool" title="Encuadrar (F)" aria-label="Encuadrar" onClick={frame}>
          <Focus size={17} />
        </button>
        <button
          type="button"
          className="studio-tool"
          aria-pressed={planView}
          title="Vista en planta"
          aria-label="Vista en planta"
          onClick={() => setPlanView((v) => !v)}
        >
          {planView ? <Square size={17} /> : <Grid3x3 size={17} />}
        </button>
      </aside>

      <div className="studio-view">
        <div
          ref={host}
          className="studio-canvas"
          data-testid="viewport"
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          onPointerMove={onPointerMove}
        />
        <div className="studio-hud">
          {arch
            ? tool === 'wall'
              ? wallStart.current
                ? 'Clic para terminar el muro · Esc para soltar'
                : 'Clic en el suelo para empezar un muro'
              : `${items.filter((i) => i.shape === 'wall').length} muros · ${totalWalls.toFixed(2)} m`
            : `${items.length} objetos`}
          {busy && <b> · {busy}{elapsedNote(elapsed)}</b>}
        </div>
        <form
          className="studio-ask"
          onSubmit={(e) => {
            e.preventDefault();
            void ask();
          }}
        >
          <input
            className="paper-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={arch ? 'Pídale a Sergio un mueble o una pieza: «una mesa de comedor de madera»' : 'Describa un objeto: «una taza de café», «un dron», «una silla»'}
            aria-label="Pedir un objeto a Sergio"
            disabled={!!busy}
          />
          <button type="submit" className="paper-button" disabled={!!busy || !prompt.trim()}>
            Crear
          </button>
        </form>
      </div>

      <aside className="studio-side">
        <section className="studio-panel">
          <h3>Escena</h3>
          <ul className="studio-outliner">
            {items.length === 0 && <li className="studio-empty">Vacía. Añada un objeto o pídaselo a Sergio.</li>}
            {items.map((it) => (
              <li key={it.id} aria-selected={it.id === selected}>
                <button type="button" onClick={() => setSelected(it.id)}>
                  <i style={{ background: it.color }} />
                  {it.name}
                </button>
                <button
                  type="button"
                  className="mac-icon-btn"
                  aria-label={it.visible ? `Ocultar ${it.name}` : `Mostrar ${it.name}`}
                  onClick={() => setItems((prev) => prev.map((x) => (x.id === it.id ? { ...x, visible: !x.visible } : x)))}
                >
                  {it.visible ? <Eye size={14} /> : <EyeOff size={14} />}
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section className="studio-panel">
          <h3>Propiedades</h3>
          {sel ? (
            <div className="studio-props">
              <label>
                Nombre
                <input className="paper-input" value={sel.name} onChange={(e) => update({ name: e.target.value.slice(0, 60) })} />
              </label>
              {(['pos', 'rot', 'scale'] as const).map((k) => (
                <fieldset key={k}>
                  <legend>{k === 'pos' ? 'Posición (m)' : k === 'rot' ? 'Rotación (°)' : 'Escala'}</legend>
                  {[0, 1, 2].map((i) => (
                    <input
                      key={i}
                      type="number"
                      step={k === 'rot' ? 5 : 0.05}
                      aria-label={`${k} ${'XYZ'[i]}`}
                      value={Number(sel[k][i].toFixed(3))}
                      onChange={(e) => {
                        const v = Number(e.target.value);
                        if (!Number.isFinite(v)) return;
                        const next = [...sel[k]] as [number, number, number];
                        next[i] = v;
                        update({ [k]: next } as Partial<Item>);
                      }}
                    />
                  ))}
                </fieldset>
              ))}
              {sel.shape === 'wall' && (
                <fieldset>
                  <legend>Muro (m)</legend>
                  <input type="number" step={0.1} aria-label="Altura" title="Altura" value={sel.size[1]} onChange={(e) => {
                    const h = Math.max(0.1, Number(e.target.value) || 0.1);
                    update({ size: [sel.size[0], h, sel.size[2]], pos: [sel.pos[0], h / 2, sel.pos[2]] });
                  }} />
                  <input type="number" step={0.05} aria-label="Grosor" title="Grosor" value={sel.size[2]} onChange={(e) => update({ size: [sel.size[0], sel.size[1], Math.max(0.05, Number(e.target.value) || 0.05)] })} />
                </fieldset>
              )}
              <label>
                Color
                <input type="color" value={sel.color} onChange={(e) => update({ color: e.target.value })} />
              </label>
            </div>
          ) : (
            <p className="studio-empty">Seleccione un objeto en la vista o en la lista.</p>
          )}
        </section>
        <section className="studio-panel studio-export">
          <button type="button" className="paper-button" data-variant="quiet" onClick={exportGlb} disabled={!items.length}>
            <Download size={15} /> Exportar GLB
          </button>
          {arch && (
            <>
              <button type="button" className="paper-button" data-variant="quiet" onClick={exportDxf}>
                <Download size={15} /> Plano DXF
              </button>
              <button type="button" className="paper-button" data-variant="quiet" onClick={exportIfc}>
                <Download size={15} /> Edificio IFC (BIM)
              </button>
              <div className="studio-open-in" role="group" aria-label="Abrir el plano en">
                <span>Abrir en</span>
                <button type="button" className="mac-chip" onClick={() => void openPlan('freecad')}>
                  Planos
                </button>
                <button type="button" className="mac-chip" onClick={() => void openPlan('bonsai')}>
                  BIM
                </button>
                <button type="button" className="mac-chip" onClick={() => void openPlan('librecad')}>
                  Plano 2D
                </button>
              </div>
            </>
          )}
          {lastRequest && (
            <button type="button" className="paper-button" onClick={toBlender} disabled={!!busy}>
              Producción 3D
            </button>
          )}
          <button
            type="button"
            className="paper-button"
            data-variant="quiet"
            onClick={() => {
              if (items.length && window.confirm('¿Empezar una escena vacía?')) {
                setItems([]);
                setSelected(null);
              }
            }}
          >
            Nueva escena
          </button>
        </section>
      </aside>
    </div>
  );
}

export default Studio3D;
