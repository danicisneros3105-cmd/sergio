// Who Sergio is talking to and how they want it (`/v1/personal/perfil`,
// `personal.py` on the server): how to be addressed («señor», «señora», by
// name, neutral or «tú»), language, country and the line above the chat.
// With no profile the owner's defaults hold: «señor», de usted.
//
// The profile is kept in memory and in this browser, so the greeting is
// right on the first paint; the server copy wins as soon as it arrives.

import { useSyncExternalStore } from 'react';
import { apiFetch } from './api';

export type Address = 'señor' | 'señora' | 'nombre' | 'neutro' | 'tu';
export type GreetingTone = 'formal' | 'cercano' | 'divertido';

export interface Personal {
  nombre: string;
  trato: Address;
  idioma: string; // 'auto' or a language code
  pais: string;
  tono_saludo: GreetingTone;
  saludos_propios: string[];
}

export const DEFAULT_PERSONAL: Personal = {
  nombre: '',
  trato: 'señor',
  idioma: 'auto',
  pais: '',
  tono_saludo: 'formal',
  saludos_propios: [],
};

export const ADDRESS_OPTIONS: { value: Address; label: string }[] = [
  { value: 'señor', label: '«Señor»' },
  { value: 'señora', label: '«Señora»' },
  { value: 'nombre', label: 'Por mi nombre' },
  { value: 'neutro', label: 'Sin género' },
  { value: 'tu', label: 'De tú' },
];

export const TONE_OPTIONS: { value: GreetingTone; label: string }[] = [
  { value: 'formal', label: 'Formal' },
  { value: 'cercano', label: 'Cercano' },
  { value: 'divertido', label: 'Divertido' },
];

const KEY = 'sergio:personal';
let current: Personal = read();
let fetched = false;
const listeners = new Set<() => void>();

function read(): Personal {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULT_PERSONAL, ...JSON.parse(raw) } : DEFAULT_PERSONAL;
  } catch {
    return DEFAULT_PERSONAL;
  }
}

function set(next: Personal): void {
  current = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* private mode: memory only */
  }
  listeners.forEach((fn) => fn());
}

function pick(data: Record<string, unknown>): Personal {
  const out = { ...DEFAULT_PERSONAL };
  for (const key of Object.keys(DEFAULT_PERSONAL) as (keyof Personal)[]) {
    if (key in data && data[key] != null) (out as Record<string, unknown>)[key] = data[key];
  }
  return out;
}

export async function loadPersonal(): Promise<Personal> {
  fetched = true;
  try {
    const res = await apiFetch('/v1/personal/perfil');
    if (res.ok) set(pick(await res.json()));
  } catch {
    /* offline: what this browser remembers */
  }
  return current;
}

export async function savePersonal(changes: Partial<Personal>): Promise<Personal> {
  set({ ...current, ...changes });
  const res = await apiFetch('/v1/personal/perfil', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.detail || `Error ${res.status}`);
  set(pick(await res.json()));
  return current;
}

export function getPersonal(): Personal {
  return current;
}

export function usePersonal(): Personal {
  if (!fetched && typeof window !== 'undefined') void loadPersonal();
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    () => current,
    () => current,
  );
}

/** The language the interface speaks to this person: their choice, else the browser's. */
export function personalLanguage(p: Personal = current): string {
  if (p.idioma && p.idioma !== 'auto') return p.idioma;
  const nav = typeof navigator !== 'undefined' ? navigator.language || 'es' : 'es';
  return nav.slice(0, 2).toLowerCase();
}

const WORDS: Record<string, { sir: string; madam: string }> = {
  es: { sir: 'señor', madam: 'señora' },
  en: { sir: 'sir', madam: 'madam' },
  pt: { sir: 'senhor', madam: 'senhora' },
  fr: { sir: 'monsieur', madam: 'madame' },
  de: { sir: 'mein Herr', madam: 'meine Dame' },
  it: { sir: 'signore', madam: 'signora' },
};

/** What goes after a comma when Sergio speaks to this person («señor», «Ana», or nothing). */
export function addressWord(p: Personal = current, lang = personalLanguage(p)): string {
  const words = WORDS[lang] ?? WORDS.en;
  if (p.trato === 'señor') return words.sir;
  if (p.trato === 'señora') return words.madam;
  return p.nombre.trim();
}

/** «, señor» / «, Ana» / «» — ready to put before the closing mark. */
export function withAddress(p: Personal = current, lang?: string): string {
  const word = addressWord(p, lang);
  return word ? `, ${word}` : '';
}

/** «Bienvenido, señor» / «Bienvenida, señora» / «Le damos la bienvenida, Ana». */
export function welcome(p: Personal = current): string {
  const word = agree(p, 'Bienvenido', 'Bienvenida', p.trato === 'tu' ? 'Te damos la bienvenida' : 'Le damos la bienvenida');
  return `${word}${withAddress(p, 'es')}`;
}

/** Spanish adjectives that agree: «Bienvenido», «Bienvenida», or a neutral way round. */
export function agree(p: Personal, masculine: string, feminine: string, neutral: string): string {
  if (p.trato === 'señor') return masculine;
  if (p.trato === 'señora') return feminine;
  return neutral;
}
