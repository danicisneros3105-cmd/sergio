// 3D models that take apart inside the chat (creator/despiece.py on the
// server): a reply or a tool result that links to one gets the viewer under
// it (components/Chat/PartsViewer.tsx); the raw link is not shown.

const VIEW = /\/v1\/creator\/despiece\/view\/([a-z0-9][a-z0-9-]{0,79})(?![\wÀ-ɏ-])/g;

/** Names of the models a text links to, in order, without repeats. */
export function despieceNames(...texts: Array<string | undefined>): string[] {
  const out: string[] = [];
  for (const text of texts) {
    for (const m of (text || '').matchAll(VIEW)) if (!out.includes(m[1])) out.push(m[1]);
  }
  return out;
}

export function withoutDespieceLinks(text: string): string {
  return text
    .replace(/[ \t]*\(?\/v1\/creator\/despiece\/view\/[a-z0-9][a-z0-9-]{0,79}\)?\.?(?![\wÀ-ɏ-])/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .trim();
}

export type Shape = 'caja' | 'cilindro' | 'esfera' | 'toro' | 'capsula' | 'cono' | 'perfil';

export interface Part {
  id: string;
  nombre: string;
  grupo: string;
  forma: Shape;
  medidas: [number, number, number];
  redondeo: number;
  posicion: [number, number, number];
  rotacion: [number, number, number];
  color: string;
  material: string;
  que_hace: string;
  puntos?: [number, number][];
}

export interface PartsModel {
  titulo: string;
  descripcion: string;
  grupos: { id: string; nombre: string; direccion: [number, number, number] }[];
  piezas: Part[];
}

export interface ModelMeta {
  name: string;
  titulo: string;
  descripcion: string;
  tipo: 'piezas' | 'gltf';
  archivo: string;
  fuente: string;
  licencia: string;
  url: string;
  piezas?: number;
}

/** How each material looks (MeshStandardMaterial settings). */
export const LOOKS: Record<string, { metalness: number; roughness: number; opacity?: number; glow?: boolean }> = {
  pintura: { metalness: 0.45, roughness: 0.32 },
  metal: { metalness: 0.9, roughness: 0.35 },
  cromo: { metalness: 1, roughness: 0.08 },
  goma: { metalness: 0, roughness: 0.92 },
  vidrio: { metalness: 0.1, roughness: 0.05, opacity: 0.35 },
  plastico: { metalness: 0, roughness: 0.6 },
  cuero: { metalness: 0, roughness: 0.7 },
  tela: { metalness: 0, roughness: 0.95 },
  luz: { metalness: 0, roughness: 0.3, glow: true },
  madera: { metalness: 0, roughness: 0.8 },
};

/**
 * Where a piece goes when the model comes apart: its group's direction plus
 * a little outward push from the model's centre, so pieces of one group
 * also separate from each other. *amount* 0 = assembled, 1 = fully apart.
 */
export function explodedOffset(
  centre: [number, number, number],
  modelCentre: [number, number, number],
  groupDir: [number, number, number],
  size: number,
  amount: number,
): [number, number, number] {
  const out = [0, 1, 2].map((i) => centre[i] - modelCentre[i]);
  const len = Math.hypot(...out) || 1;
  const g = Math.hypot(...groupDir);
  return [0, 1, 2].map((i) => {
    const radial = (out[i] / len) * 0.35;
    const group = g ? (groupDir[i] / g) * 0.65 : radial;
    return (group + radial) * size * amount;
  }) as [number, number, number];
}
