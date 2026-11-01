// The line above an empty chat («¡Ana ha vuelto!», «El micrófono es tuyo,
// Ana», «¿En qué trabajamos hoy, señor?»), personal and in the person's
// language. It follows their profile (lib/personal.ts): how they want to be
// addressed (never a gendered word unless they chose «señor» or «señora»),
// usted or tú, the tone they picked, or their own phrases. The same line
// stays for a few hours so it does not change on every click.

import { addressWord, personalLanguage, type Personal } from './personal';

export type GreetingKind = 'chat' | 'voice' | 'quick';

interface Ctx {
  /** «, señor» / «, Ana» / «». */
  w: string;
  /** The name, if they gave one. */
  n: string;
  /** Tú instead of usted (or the language's informal form). */
  tu: boolean;
  hour: number;
}

type Phrase = (c: Ctx) => string;

const daypart = (hour: number, morning: string, afternoon: string, evening: string) =>
  hour < 5 || hour >= 20 ? evening : hour < 13 ? morning : afternoon;

const PHRASES: Record<string, Record<'formal' | 'cercano' | 'divertido' | 'voice', Phrase[]>> = {
  es: {
    formal: [
      (c) => `¿En qué trabajamos hoy${c.w}?`,
      (c) => `${daypart(c.hour, 'Buenos días', 'Buenas tardes', 'Buenas noches')}${c.w}.`,
      (c) => (c.tu ? `¿Qué hacemos hoy${c.w}?` : `A su disposición${c.w}.`),
    ],
    cercano: [
      (c) => (c.n ? `¡${c.n} ha vuelto!` : c.tu ? '¡Has vuelto!' : `¡Ha vuelto${c.w}!`),
      (c) => (c.tu ? `Qué bueno verte${c.w}.` : `Qué bueno verle${c.w}.`),
      (c) => `¿Qué hacemos hoy${c.w}?`,
    ],
    divertido: [
      (c) => (c.n ? `Mira quién volvió: ${c.n}.` : c.tu ? 'Mira quién volvió.' : `Mire quién volvió${c.w}.`),
      (c) => (c.tu ? `El escenario es tuyo${c.w}.` : `El escenario es suyo${c.w}.`),
      (c) => `Café servido${c.w}. ¿Qué construimos hoy?`,
    ],
    voice: [
      (c) => (c.tu ? `El micrófono es tuyo${c.w}.` : `El micrófono es suyo${c.w}.`),
      (c) => (c.tu ? `Te escucho${c.w}.` : `Le escucho${c.w}.`),
    ],
  },
  en: {
    formal: [
      (c) => `What are we working on today${c.w}?`,
      (c) => `${daypart(c.hour, 'Good morning', 'Good afternoon', 'Good evening')}${c.w}.`,
      (c) => `At your service${c.w}.`,
    ],
    cercano: [
      (c) => (c.n ? `${c.n} is back!` : `Welcome back${c.w}!`),
      (c) => `Good to see you${c.w}.`,
      (c) => `What shall we do today${c.w}?`,
    ],
    divertido: [
      (c) => (c.n ? `Look who's back: ${c.n}.` : `Look who's back${c.w}.`),
      (c) => `The stage is yours${c.w}.`,
      (c) => `Coffee's ready${c.w}. What are we building?`,
    ],
    voice: [(c) => `The mic is yours${c.w}.`, (c) => `I'm listening${c.w}.`],
  },
  pt: {
    formal: [
      (c) => `Em que trabalhamos hoje${c.w}?`,
      (c) => `${daypart(c.hour, 'Bom dia', 'Boa tarde', 'Boa noite')}${c.w}.`,
    ],
    cercano: [(c) => (c.n ? `${c.n} voltou!` : `Que bom te ver${c.w}!`), (c) => `O que fazemos hoje${c.w}?`],
    divertido: [(c) => `O palco é seu${c.w}.`, (c) => `Café pronto${c.w}. O que vamos construir?`],
    voice: [(c) => `O microfone é seu${c.w}.`],
  },
  fr: {
    formal: [
      (c) => `Sur quoi travaillons-nous aujourd'hui${c.w} ?`,
      (c) => `${daypart(c.hour, 'Bonjour', 'Bonjour', 'Bonsoir')}${c.w}.`,
    ],
    cercano: [
      (c) => (c.n ? `${c.n} est de retour !` : c.tu ? `Ravi de te revoir${c.w} !` : `Ravi de vous revoir${c.w} !`),
      (c) => `On fait quoi aujourd'hui${c.w} ?`,
    ],
    divertido: [(c) => (c.tu ? `La scène est à toi${c.w}.` : `La scène est à vous${c.w}.`)],
    voice: [(c) => (c.tu ? `Le micro est à toi${c.w}.` : `Le micro est à vous${c.w}.`)],
  },
  de: {
    formal: [
      (c) => `Woran arbeiten wir heute${c.w}?`,
      (c) => `${daypart(c.hour, 'Guten Morgen', 'Guten Tag', 'Guten Abend')}${c.w}.`,
    ],
    cercano: [
      (c) => (c.n ? `${c.n} ist zurück!` : c.tu ? `Schön, dich zu sehen${c.w}!` : `Schön, Sie zu sehen${c.w}!`),
    ],
    divertido: [(c) => (c.tu ? `Die Bühne gehört dir${c.w}.` : `Die Bühne gehört Ihnen${c.w}.`)],
    voice: [(c) => (c.tu ? `Das Mikro gehört dir${c.w}.` : `Das Mikro gehört Ihnen${c.w}.`)],
  },
  it: {
    formal: [
      (c) => `Su cosa lavoriamo oggi${c.w}?`,
      (c) => `${daypart(c.hour, 'Buongiorno', 'Buongiorno', 'Buonasera')}${c.w}.`,
    ],
    cercano: [(c) => (c.tu ? `Che bello rivederti${c.w}!` : `Che bello rivederla${c.w}!`)],
    divertido: [(c) => (c.tu ? `Il palco è tuo${c.w}.` : `Il palco è suo${c.w}.`)],
    voice: [(c) => (c.tu ? `Il microfono è tuo${c.w}.` : `Il microfono è suo${c.w}.`)],
  },
};

function seed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0;
}

export function greetingLine(
  p: Personal,
  opts: { now?: Date; kind?: GreetingKind; lang?: string } = {},
): string {
  const now = opts.now ?? new Date();
  const kind = opts.kind ?? 'chat';
  // The app speaks Spanish: the greeting too, unless he chose another language
  // (an English browser said «At your service, sir.» over a Spanish screen).
  const lang = opts.lang ?? (p.idioma && p.idioma !== 'auto' ? personalLanguage(p) : 'es');
  const word = addressWord(p, lang);
  const c: Ctx = { w: word ? `, ${word}` : '', n: p.nombre.trim(), tu: p.trato === 'tu', hour: now.getHours() };
  // Stable for three hours, then another one.
  const key = `${now.getFullYear()}-${now.getMonth()}-${now.getDate()}-${Math.floor(now.getHours() / 3)}-${kind}`;
  const own = (p.saludos_propios ?? []).map((s) => s.trim()).filter(Boolean);
  if (own.length && kind !== 'voice') {
    const line = own[seed(key) % own.length];
    return line.replace(/\{(nombre|name)\}/gi, c.n || word).replace(/\s+([,.!?])/g, '$1').trim();
  }
  const table = PHRASES[lang] ?? PHRASES.en;
  const list = kind === 'voice' ? table.voice : table[p.tono_saludo] ?? table.formal;
  return list[seed(key) % list.length](c);
}
