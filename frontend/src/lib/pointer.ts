// Sergio's own pointer: when he shows or explains something on the screen he
// moves a cursor to it (owner, 2 Nov 2026). Anyone can ask for it with
// pointAt(); the tours do, and so does a reply that carries «[[señalar:…]]».

export interface PointRequest {
  /** A CSS selector, or the visible words of a button / link / heading. */
  target?: string;
  /** Or a place on the screen, in pixels. */
  x?: number;
  y?: number;
  /** What Sergio says next to it (short). */
  text?: string;
  /** How long it stays, in ms (default: by the length of the text). */
  ms?: number;
  /** Click it once it gets there. */
  click?: boolean;
}

export const POINT_EVENT = 'sergio:point';

export function pointAt(req: PointRequest): void {
  window.dispatchEvent(new CustomEvent<PointRequest>(POINT_EVENT, { detail: req }));
}

/** The element a target names: a selector first, then visible words. */
export function findTarget(target: string, root: ParentNode = document): HTMLElement | null {
  const t = target.trim();
  if (!t) return null;
  try {
    const el = root.querySelector<HTMLElement>(t);
    if (el) return el;
  } catch {
    /* not a selector: words */
  }
  const want = plain(t);
  const candidates = Array.from(
    root.querySelectorAll<HTMLElement>('button, a, [role="button"], [role="tab"], h1, h2, h3, label, [aria-label]'),
  ).filter(visible);
  let best: HTMLElement | null = null;
  let score = 0;
  for (const el of candidates) {
    const name = plain(el.getAttribute('aria-label') || el.textContent || '');
    if (!name) continue;
    const s = name === want ? 3 : name.startsWith(want) ? 2 : name.includes(want) ? 1 : 0;
    if (s > score) {
      best = el;
      score = s;
    }
  }
  return best;
}

function visible(el: HTMLElement): boolean {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < window.innerHeight && r.left < window.innerWidth;
}

function plain(s: string): string {
  return s
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

const MARK = /\[\[\s*se[ñn]alar\s*:\s*([^|\]]+?)\s*(?:\|\s*([^\]]+?))?\s*\]\]/gi;

/** «[[señalar: Ajustes | Aquí cambia su voz]]» in a reply: the requests,
 * and the text without the marks (they never show). */
export function pointMarks(text: string): { clean: string; points: PointRequest[] } {
  const points: PointRequest[] = [];
  const clean = text.replace(MARK, (_m, target: string, said?: string) => {
    points.push({ target: target.trim(), text: (said || '').trim() || undefined });
    return '';
  });
  return { clean: points.length ? clean.replace(/[ \t]{2,}/g, ' ').trim() : text, points };
}
