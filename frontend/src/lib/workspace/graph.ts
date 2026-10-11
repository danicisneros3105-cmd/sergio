// The knowledge graph: pages and the concepts they share, linked on their own.
//
// Links come from what you wrote ([[mentions]], sub-pages, page links, tags)
// and from what the pages are about: words that matter in a page (frequent
// in it, rare elsewhere: TF-IDF) and are shared by two or more pages become
// concept nodes tying them together. Laid out in 3D with a small force
// simulation (deterministic: the same pages give the same shape).

import { mentions, plainText, type Page } from './model';

export type NodeKind = 'page' | 'concept' | 'tag';
export type LinkKind = 'mention' | 'child' | 'link' | 'tag' | 'concept';

export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  weight: number; // how connected (for size)
  x: number;
  y: number;
  z: number;
}

export interface GraphLink {
  a: string;
  b: string;
  kind: LinkKind;
}

const STOP = new Set(
  (
    'que para con por los las una uno unos unas del este esta estos estas ese esa eso como pero porque cuando donde ' +
    'muy mas menos sobre entre hasta desde tambien todo toda todos todas cada otro otra otros otras sin ser estar ' +
    'tiene tener hay hace hacer puede poder solo esto aqui alli ahora antes despues bien mal sus mis tus nuestro ' +
    'the and for with that this from have will your about into they them then than there their what which when ' +
    'while would could should been were also just only some more most such each other very'
  ).split(' '),
);

export function keywords(text: string): Map<string, number> {
  const counts = new Map<string, number>();
  const words = text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .match(/[a-zñ]{4,}/g);
  for (const w of words || []) {
    if (STOP.has(w)) continue;
    const stem = w.length > 5 ? w.replace(/(es|s)$/, '') : w; // «proyectos» ~ «proyecto»
    counts.set(stem, (counts.get(stem) || 0) + 1);
  }
  return counts;
}

export function buildGraph(pages: Page[], maxConcepts = 40): { nodes: GraphNode[]; links: GraphLink[] } {
  const live = pages.filter((p) => !p.archived);
  const byTitle = new Map(live.map((p) => [p.title.trim().toLowerCase(), p.id]));
  const ids = new Set(live.map((p) => p.id));
  const nodes = new Map<string, GraphNode>();
  const links: GraphLink[] = [];
  const seen = new Set<string>();
  const link = (a: string, b: string, kind: LinkKind) => {
    if (a === b) return;
    const key = [a, b].sort().join('|') + kind;
    if (seen.has(key)) return;
    seen.add(key);
    links.push({ a, b, kind });
  };
  for (const p of live) {
    nodes.set(p.id, { id: p.id, label: p.title || 'Sin título', kind: 'page', weight: 1, x: 0, y: 0, z: 0 });
  }
  for (const p of live) {
    if (p.parent && ids.has(p.parent)) link(p.parent, p.id, 'child');
    if (p.sealed) continue;
    for (const title of mentions(p)) {
      const target = byTitle.get(title.toLowerCase());
      if (target) link(p.id, target, 'mention');
    }
    for (const b of p.blocks) if (b.type === 'page' && b.pageId && ids.has(b.pageId)) link(p.id, b.pageId, 'link');
    for (const tag of p.tags || []) {
      const id = `tag:${tag.toLowerCase()}`;
      if (!nodes.has(id)) nodes.set(id, { id, label: `#${tag}`, kind: 'tag', weight: 1, x: 0, y: 0, z: 0 });
      link(p.id, id, 'tag');
    }
  }
  // Concepts: words that matter in two or more pages.
  const docs = live.filter((p) => !p.sealed).map((p) => ({ id: p.id, words: keywords(`${p.title} ${p.title} ${plainText(p)}`) }));
  const df = new Map<string, number>();
  for (const d of docs) for (const w of d.words.keys()) df.set(w, (df.get(w) || 0) + 1);
  const n = Math.max(1, docs.length);
  const scored: Array<{ word: string; score: number; pages: string[] }> = [];
  for (const [word, count] of df) {
    if (count < 2 || count > Math.max(3, n * 0.6)) continue; // shared, but not everywhere
    const pagesWith = docs.filter((d) => d.words.has(word));
    const idf = Math.log(1 + n / count);
    const tf = pagesWith.reduce((s, d) => s + Math.min(5, d.words.get(word) || 0), 0);
    scored.push({ word, score: tf * idf, pages: pagesWith.map((d) => d.id) });
  }
  scored.sort((a, b) => b.score - a.score || a.word.localeCompare(b.word));
  for (const c of scored.slice(0, maxConcepts)) {
    const id = `concept:${c.word}`;
    nodes.set(id, { id, label: c.word, kind: 'concept', weight: 1, x: 0, y: 0, z: 0 });
    for (const pid of c.pages) link(pid, id, 'concept');
  }
  for (const l of links) {
    nodes.get(l.a)!.weight += 1;
    nodes.get(l.b)!.weight += 1;
  }
  return { nodes: [...nodes.values()], links };
}

// A tiny seeded random (mulberry32) for a stable layout.
function random(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function layout3d(nodes: GraphNode[], links: GraphLink[], iterations = 160, seed = 7): GraphNode[] {
  const rand = random(seed);
  const out = nodes.map((nd) => ({ ...nd, x: rand() * 2 - 1, y: rand() * 2 - 1, z: rand() * 2 - 1 }));
  const index = new Map(out.map((nd, i) => [nd.id, i]));
  const k = 1 / Math.cbrt(Math.max(1, out.length));
  let temp = 0.3;
  for (let it = 0; it < iterations; it++) {
    const dx = new Float64Array(out.length);
    const dy = new Float64Array(out.length);
    const dz = new Float64Array(out.length);
    for (let i = 0; i < out.length; i++) {
      for (let j = i + 1; j < out.length; j++) {
        const ex = out[i].x - out[j].x;
        const ey = out[i].y - out[j].y;
        const ez = out[i].z - out[j].z;
        const d2 = Math.max(1e-4, ex * ex + ey * ey + ez * ez);
        const f = (k * k) / d2; // repulsion
        dx[i] += ex * f;
        dy[i] += ey * f;
        dz[i] += ez * f;
        dx[j] -= ex * f;
        dy[j] -= ey * f;
        dz[j] -= ez * f;
      }
    }
    for (const l of links) {
      const i = index.get(l.a)!;
      const j = index.get(l.b)!;
      const ex = out[i].x - out[j].x;
      const ey = out[i].y - out[j].y;
      const ez = out[i].z - out[j].z;
      const d = Math.max(1e-3, Math.sqrt(ex * ex + ey * ey + ez * ez));
      const f = d / k; // attraction
      dx[i] -= (ex / d) * f * 0.5;
      dy[i] -= (ey / d) * f * 0.5;
      dz[i] -= (ez / d) * f * 0.5;
      dx[j] += (ex / d) * f * 0.5;
      dy[j] += (ey / d) * f * 0.5;
      dz[j] += (ez / d) * f * 0.5;
    }
    for (let i = 0; i < out.length; i++) {
      const len = Math.max(1e-6, Math.sqrt(dx[i] ** 2 + dy[i] ** 2 + dz[i] ** 2));
      const step = Math.min(len, temp);
      out[i].x += (dx[i] / len) * step - out[i].x * 0.004; // a gentle pull to the centre
      out[i].y += (dy[i] / len) * step - out[i].y * 0.004;
      out[i].z += (dz[i] / len) * step - out[i].z * 0.004;
    }
    temp *= 0.97;
  }
  // Fit into a unit sphere around the middle of the mass: scale by the 85th
  // percentile distance (so one stray page does not shrink the rest) and
  // bring the strays in to the rim.
  const cx = out.reduce((s, nd) => s + nd.x, 0) / Math.max(1, out.length);
  const cy = out.reduce((s, nd) => s + nd.y, 0) / Math.max(1, out.length);
  const cz = out.reduce((s, nd) => s + nd.z, 0) / Math.max(1, out.length);
  const dists = out.map((nd) => Math.sqrt((nd.x - cx) ** 2 + (nd.y - cy) ** 2 + (nd.z - cz) ** 2)).sort((a, b) => a - b);
  const r = Math.max(1e-6, dists[Math.min(dists.length - 1, Math.floor(dists.length * 0.85))] || 1);
  return out.map((nd) => {
    let x = (nd.x - cx) / r;
    let y = (nd.y - cy) / r;
    let z = (nd.z - cz) / r;
    const d = Math.sqrt(x * x + y * y + z * z);
    if (d > 1) {
      x /= d;
      y /= d;
      z /= d;
    }
    return { ...nd, x, y, z };
  });
}

// Rotate (yaw, pitch) and project with perspective onto a canvas.
export function project(
  p: { x: number; y: number; z: number },
  yaw: number,
  pitch: number,
  zoom: number,
  width: number,
  height: number,
): { sx: number; sy: number; depth: number; scale: number } {
  const cy = Math.cos(yaw);
  const sy = Math.sin(yaw);
  const x1 = p.x * cy - p.z * sy;
  const z1 = p.x * sy + p.z * cy;
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  const y2 = p.y * cp - z1 * sp;
  const z2 = p.y * sp + z1 * cp;
  const camera = 3.2;
  const scale = (camera / (camera - z2)) * zoom * Math.min(width, height) * 0.38;
  return { sx: width / 2 + x1 * scale, sy: height / 2 + y2 * scale, depth: z2, scale: camera / (camera - z2) };
}
