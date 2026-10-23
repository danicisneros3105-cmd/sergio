// The chat looks and reads like iMessage (owner's decision, oct. 2026): his
// messages in blue on the right, Sergio's in grey on the left, bubbles of the
// same person close together with the tail only on the last one, the time
// centred when a while has passed, and «Entregado» / «Leído» under the last
// message he sent. These are the rules, kept apart so they are tested.

import type { ChatMessage } from '../types';

/** Same sender within this many ms: one group (tail only on the last). */
export const GROUP_MS = 60_000;
/** A pause this long puts the time centred above the next message. */
export const STAMP_MS = 15 * 60_000;

export interface BubbleFlags {
  /** Last bubble of a group: it gets the tail and more space below. */
  tail: boolean;
  /** Centred time above this message («Hoy 10:42»). */
  stamp: string;
  /** Under the owner's last message: «Entregado» or «Leído». */
  receipt: '' | 'Entregado' | 'Leído';
}

const DAY_NAMES = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sept', 'oct', 'nov', 'dic'];

function clock(d: Date): string {
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** «Hoy 10:42», «Ayer 21:05», «lun 10:42» this week, «23 oct 10:42» before. */
export function stampLabel(ts: number, now: number = Date.now()): string {
  const d = new Date(ts);
  const days = Math.round((startOfDay(new Date(now)) - startOfDay(d)) / 86_400_000);
  if (days <= 0) return `Hoy ${clock(d)}`;
  if (days === 1) return `Ayer ${clock(d)}`;
  if (days < 7) return `${DAY_NAMES[d.getDay()]} ${clock(d)}`;
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${clock(d)}`;
}

export function bubbleFlags(messages: ChatMessage[], now: number = Date.now()): BubbleFlags[] {
  const lastMine = messages.map((m) => m.role).lastIndexOf('user');
  return messages.map((m, i) => {
    const prev = messages[i - 1];
    const next = messages[i + 1];
    const tail = !next || next.role !== m.role || next.timestamp - m.timestamp > GROUP_MS;
    const stamp = !prev || m.timestamp - prev.timestamp > STAMP_MS ? stampLabel(m.timestamp, now) : '';
    let receipt: BubbleFlags['receipt'] = '';
    if (i === lastMine) receipt = messages.slice(i + 1).some((n) => n.role === 'assistant') ? 'Leído' : 'Entregado';
    return { tail, stamp, receipt };
  });
}

const MEDIA = /\/v1\/creator\/media\/[\w.-]+\.(?:png|jpe?g|webp|mp4)/g;

/** Pictures and videos Sergio made, found in a reply or its tools' results,
 *  so they always show in the chat even if the reply forgot to include them. */
export function mediaOf(message: ChatMessage): string[] {
  const shown = new Set(message.content.match(MEDIA) ?? []);
  const found: string[] = [];
  for (const call of message.toolCalls ?? []) {
    for (const url of call.result?.match(MEDIA) ?? []) {
      if (!shown.has(url) && !found.includes(url)) found.push(url);
    }
  }
  return found;
}

export const isVideo = (src: string) => /\.(mp4|webm|mov)(\?|$)/i.test(src);
