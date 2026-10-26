// A 3D model inside the chat that comes apart piece by piece (lib/despiece.ts).
// Turn it with the finger or the mouse, slide «Despiece» to separate the
// pieces, tap one to see its name and what it does, «Solo esta» to look at it
// alone. It draws only when something changes (never a 60 fps loop), with a
// lighter renderer on slow devices, so it runs on a phone or a school laptop.

import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { Maximize2, RotateCcw } from 'lucide-react';
import { apiFetch, getBase } from '../../lib/api';
import { LOOKS, explodedOffset, type ModelMeta, type Part, type PartsModel } from '../../lib/despiece';

interface Piece {
  id: string;
  nombre: string;
  grupo: string;
  que_hace: string;
  object: THREE.Object3D;
  home: THREE.Vector3; // its own position (in its parent)
  homeWorld: THREE.Vector3; // the same, in the scene
  centre: THREE.Vector3; // the middle of its shape, in the scene
  dir: [number, number, number];
}

const CM = 0.01; // the parts list is in centimetres; the scene in metres

function geometryFor(p: Part): THREE.BufferGeometry {
  const [a, b, c] = p.medidas.map((v) => v * CM);
  switch (p.forma) {
    case 'cilindro':
      return new THREE.CylinderGeometry(a, a, b, 32);
    case 'esfera':
      return new THREE.SphereGeometry(a, 32, 16);
    case 'toro': {
      const g = new THREE.TorusGeometry(a, Math.max(b, 0.001), 16, 48);
      g.rotateX(-Math.PI / 2); // lying flat (XZ), as the model was told
      return g;
    }
    case 'capsula':
      return new THREE.CapsuleGeometry(a, b, 8, 16);
    case 'cono':
      return new THREE.ConeGeometry(a, b, 32);
    case 'perfil':
      return new THREE.LatheGeometry((p.puntos ?? []).map(([r, y]) => new THREE.Vector2(r * CM, y * CM)), 48);
    default: {
      const r = Math.min(p.redondeo * CM, a / 2, b / 2, c / 2);
      return r > 0.0005 ? new RoundedBoxGeometry(a, b, c, 3, r) : new THREE.BoxGeometry(a, b, c);
    }
  }
}

function materialFor(p: Part): THREE.MeshStandardMaterial {
  const look = LOOKS[p.material] ?? LOOKS.plastico;
  const m = new THREE.MeshStandardMaterial({
    color: p.color,
    metalness: look.metalness,
    roughness: look.roughness,
    transparent: look.opacity !== undefined,
    opacity: look.opacity ?? 1,
  });
  if (look.glow) {
    m.emissive = new THREE.Color(p.color);
    m.emissiveIntensity = 0.8;
  }
  return m;
}

function buildParts(model: PartsModel, scene: THREE.Group): Piece[] {
  const dirs = new Map(model.grupos.map((g) => [g.id, g.direccion]));
  return model.piezas.map((p) => {
    const mesh = new THREE.Mesh(geometryFor(p), materialFor(p));
    mesh.position.set(...(p.posicion.map((v) => v * CM) as [number, number, number]));
    mesh.rotation.set(...(p.rotacion.map((d) => THREE.MathUtils.degToRad(d)) as [number, number, number]));
    mesh.name = p.nombre;
    scene.add(mesh);
    return { id: p.id, nombre: p.nombre, grupo: p.grupo, que_hace: p.que_hace, object: mesh, home: mesh.position.clone(), homeWorld: new THREE.Vector3(), centre: new THREE.Vector3(), dir: dirs.get(p.grupo) ?? [0, 0, 0] };
  });
}

function gltfParts(root: THREE.Object3D): Piece[] {
  const out: Piece[] = [];
  root.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) {
      const top = o.parent && o.parent !== root ? o.parent.name || 'Modelo' : 'Modelo';
      out.push({ id: o.uuid, nombre: o.name || top || 'Pieza', grupo: top, que_hace: '', object: o, home: o.position.clone(), homeWorld: new THREE.Vector3(), centre: new THREE.Vector3(), dir: [0, 0, 0] });
    }
  });
  return out;
}

export default function PartsViewer({ name }: { name: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [meta, setMeta] = useState<ModelMeta | null>(null);
  const [error, setError] = useState('');
  const [pieces, setPieces] = useState<Piece[]>([]);
  const [apart, setApart] = useState(0);
  const [picked, setPicked] = useState<Piece | null>(null);
  const [alone, setAlone] = useState(false);
  const stage = useRef<{ render: () => void; reset: () => void; frame: (apart: number) => void; size: number; centre: THREE.Vector3 } | null>(null);

  // Load the model and set the scene up once.
  useEffect(() => {
    let alive = true;
    let cleanup = () => {};
    (async () => {
      try {
        const res = await apiFetch(`/v1/creator/despiece/view/${encodeURIComponent(name)}`);
        if (!res.ok) throw new Error('Ese modelo ya no está en este equipo.');
        const m: ModelMeta = await res.json();
        if (!alive || !host.current) return;
        setMeta(m);
        const light = document.documentElement.dataset.ligero === '1';
        const renderer = new THREE.WebGLRenderer({ antialias: !light, alpha: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, light ? 1 : 1.75));
        const el = host.current;
        const w = el.clientWidth || 600;
        const h = el.clientHeight || 380;
        renderer.setSize(w, h);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        el.appendChild(renderer.domElement);
        const scene = new THREE.Scene();
        scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8a8f, 1.4));
        const sun = new THREE.DirectionalLight(0xffffff, 1.6);
        sun.position.set(3, 5, 4);
        scene.add(sun);
        const camera = new THREE.PerspectiveCamera(38, w / h, 0.01, 500);
        const group = new THREE.Group();
        scene.add(group);
        let list: Piece[];
        if (m.tipo === 'piezas') {
          const data: PartsModel = await (await apiFetch(m.url)).json();
          list = buildParts(data, group);
        } else {
          const base = getBase().replace(/\/$/, '');
          const gltf = await new GLTFLoader().loadAsync(`${base}${m.url}`);
          group.add(gltf.scene);
          list = gltfParts(gltf.scene);
        }
        if (!alive) return;
        group.updateMatrixWorld(true);
        for (const p of list) {
          p.object.getWorldPosition(p.homeWorld);
          new THREE.Box3().setFromObject(p.object).getCenter(p.centre);
        }
        const box = new THREE.Box3().setFromObject(group);
        const centre = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3()).length() || 1;
        const controls = new OrbitControls(camera, renderer.domElement);
        const render = () => renderer.render(scene, camera);
        let spread = 0; // how far apart the pieces are now (the camera follows)
        const reset = () => {
          spread = 0;
          camera.position.copy(centre).add(new THREE.Vector3(size * 0.75, size * 0.45, size * 0.85));
          controls.target.copy(centre);
          controls.update();
          render();
        };
        controls.addEventListener('change', render);
        // Pull the camera back as the pieces spread, so they stay in view.
        const frame = (apart: number) => {
          const dir = camera.position.clone().sub(controls.target);
          const now = dir.length();
          const want = (now / (1 + spread * 0.9)) * (1 + apart * 0.9);
          spread = apart;
          camera.position.copy(controls.target).add(dir.setLength(want));
          controls.update();
          render();
        };
        // Tap a piece: the nearest one under the finger.
        const ray = new THREE.Raycaster();
        const onTap = (e: PointerEvent) => {
          if ((e as PointerEvent & { _moved?: boolean })._moved) return;
          const r = renderer.domElement.getBoundingClientRect();
          ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
          const hit = ray.intersectObjects(list.map((p) => p.object), true).find((x) => x.object.visible);
          const piece = hit ? list.find((p) => p.object === hit.object || p.object.getObjectById(hit.object.id)) ?? null : null;
          setPicked(piece);
        };
        let down: [number, number] | null = null;
        const onDown = (e: PointerEvent) => { down = [e.clientX, e.clientY]; };
        const onUp = (e: PointerEvent) => {
          if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 5) onTap(e);
          down = null;
        };
        renderer.domElement.addEventListener('pointerdown', onDown);
        renderer.domElement.addEventListener('pointerup', onUp);
        const resize = new ResizeObserver(() => {
          const nw = el.clientWidth;
          const nh = el.clientHeight;
          if (!nw || !nh) return;
          renderer.setSize(nw, nh);
          camera.aspect = nw / nh;
          camera.updateProjectionMatrix();
          render();
        });
        resize.observe(el);
        stage.current = { render, reset, frame, size, centre };
        setPieces(list);
        reset();
        cleanup = () => {
          resize.disconnect();
          controls.dispose();
          renderer.domElement.removeEventListener('pointerdown', onDown);
          renderer.domElement.removeEventListener('pointerup', onUp);
          group.traverse((o) => {
            const mesh = o as THREE.Mesh;
            mesh.geometry?.dispose();
            const mat = mesh.material as THREE.Material | THREE.Material[] | undefined;
            (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => x.dispose());
          });
          renderer.dispose();
          renderer.domElement.remove();
        };
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'No pude abrir el modelo.');
      }
    })();
    return () => {
      alive = false;
      cleanup();
      stage.current = null;
    };
  }, [name]);

  // Take apart, highlight and isolate: move the pieces, then draw once.
  useEffect(() => {
    const s = stage.current;
    if (!s || !pieces.length) return;
    const c: [number, number, number] = [s.centre.x, s.centre.y, s.centre.z];
    for (const p of pieces) {
      // The offset is worked out in the scene, then put back in the piece's
      // parent (a downloaded model nests and scales its parts).
      const off = explodedOffset([p.centre.x, p.centre.y, p.centre.z], c, p.dir, s.size * 0.4, apart);
      if (apart === 0 || !p.object.parent) p.object.position.copy(p.home);
      else p.object.position.copy(p.object.parent.worldToLocal(p.homeWorld.clone().add(new THREE.Vector3(...off))));
      p.object.visible = !alone || !picked || p === picked;
      p.object.traverse((o) => {
        const mat = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
        if (mat && 'emissive' in mat) {
          if (mat.userData.glow === undefined) {
            mat.userData.glow = mat.emissive.getHex();
            mat.userData.glowAt = mat.emissiveIntensity;
          }
          mat.emissive.setHex(p === picked ? 0x0a84ff : mat.userData.glow);
          mat.emissiveIntensity = p === picked ? 0.35 : mat.userData.glowAt;
        }
      });
    }
    s.frame(apart);
  }, [pieces, apart, picked, alone]);

  const groups = useMemo(() => {
    const by = new Map<string, Piece[]>();
    for (const p of pieces) by.set(p.grupo, [...(by.get(p.grupo) ?? []), p]);
    return [...by.entries()];
  }, [pieces]);

  if (error) return <p className="anatomy-embed-error">{error}</p>;
  return (
    <figure className="parts-viewer">
      <div className="parts-stage" ref={host}>
        {!pieces.length && <div className="anatomy-embed-wait">Armando el modelo…</div>}
        <div className="parts-tools">
          <button type="button" className="mac-icon-btn" aria-label="Volver a la vista inicial" onClick={() => { setPicked(null); setAlone(false); setApart(0); stage.current?.reset(); }}>
            <RotateCcw size={16} />
          </button>
          <button type="button" className="mac-icon-btn" aria-label="Pantalla completa" onClick={() => host.current?.parentElement?.requestFullscreen?.()}>
            <Maximize2 size={16} />
          </button>
        </div>
      </div>
      <div className="parts-bar">
        <label className="parts-slider">
          <span>Despiece</span>
          <input type="range" min={0} max={1} step={0.01} value={apart} onChange={(e) => setApart(Number(e.target.value))} aria-label="Separar las piezas" />
        </label>
        <span className="parts-count">{pieces.length} piezas</span>
      </div>
      {picked && (
        <div className="parts-card" role="status">
          <b>{picked.nombre}</b>
          {picked.que_hace && <span>{picked.que_hace}</span>}
          <div className="parts-card-actions">
            <button type="button" onClick={() => setAlone(!alone)}>{alone ? 'Ver todo' : 'Solo esta'}</button>
            <button type="button" onClick={() => { setPicked(null); setAlone(false); }}>Cerrar</button>
          </div>
        </div>
      )}
      {groups.length > 1 && (
        <details className="parts-list">
          <summary>Todas las piezas</summary>
          <div className="parts-list-body">
          {groups.map(([g, list]) => (
            <div key={g} className="parts-group">
              <span className="parts-group-name">{meta?.tipo === 'piezas' ? g.replace(/-/g, ' ') : g}</span>
              {list.map((p) => (
                <button key={p.id} type="button" aria-pressed={picked === p} onClick={() => setPicked(p)}>{p.nombre}</button>
              ))}
            </div>
          ))}
          </div>
        </details>
      )}
      {meta && (
        <figcaption className="parts-credit">
          {meta.titulo}
          {meta.fuente ? ` · ${meta.fuente}` : ''}
          {meta.licencia ? ` · licencia ${meta.licencia}` : ''}
        </figcaption>
      )}
    </figure>
  );
}
