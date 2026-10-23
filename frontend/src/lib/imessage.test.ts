import { expect, it } from 'vitest';
import { bubbleFlags, mediaOf, stampLabel } from './imessage';
import type { ChatMessage } from '../types';

const at = (h: number, m: number, day = 23) => new Date(2026, 9, day, h, m).getTime();
const msg = (role: 'user' | 'assistant', ts: number, content = 'x', extra: Partial<ChatMessage> = {}): ChatMessage => ({
  id: `${role}-${ts}`,
  role,
  content,
  timestamp: ts,
  ...extra,
});

it('says the time like iMessage', () => {
  const now = at(18, 0);
  expect(stampLabel(at(10, 5), now)).toBe('Hoy 10:05');
  expect(stampLabel(at(21, 40, 22), now)).toBe('Ayer 21:40');
  expect(stampLabel(at(9, 0, 20), now)).toBe('mar 9:00');
  expect(stampLabel(at(9, 0, 2), now)).toBe('2 oct 9:00');
});

it('groups bubbles, stamps pauses and marks the last sent message', () => {
  const list = [
    msg('user', at(10, 0)),
    msg('user', at(10, 0) + 5_000),
    msg('assistant', at(10, 1)),
    msg('user', at(11, 0)),
  ];
  const flags = bubbleFlags(list, at(18, 0));
  expect(flags.map((f) => f.tail)).toEqual([false, true, true, true]);
  expect(flags.map((f) => f.stamp)).toEqual(['Hoy 10:00', '', '', 'Hoy 11:00']);
  expect(flags.map((f) => f.receipt)).toEqual(['', '', '', 'Entregado']);
  const answered = bubbleFlags([...list, msg('assistant', at(11, 1))], at(18, 0));
  expect(answered[3].receipt).toBe('Leído');
});

it('shows the pictures and videos a tool made even if the reply forgot them', () => {
  const m = msg('assistant', at(10, 0), 'Aquí está ![a](/v1/creator/media/imagen-aaaa.png)', {
    toolCalls: [
      { id: '1', tool: 'image_generate', arguments: '{}', status: 'success', result: 'Imagen lista.\n\n![a](/v1/creator/media/imagen-aaaa.png)' },
      { id: '2', tool: 'video_create', arguments: '{}', status: 'success', result: 'Video listo ![v](/v1/creator/media/video-bbbb.mp4)' },
    ],
  });
  expect(mediaOf(m)).toEqual(['/v1/creator/media/video-bbbb.mp4']);
});
