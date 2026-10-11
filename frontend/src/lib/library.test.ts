import { describe, expect, it } from 'vitest';
import { conversationItems, DEFAULT_MARKS, filterItems, pageItems, paginate, SECTION_ITEMS, sortItems, toggleMark } from './library';
import { block, newPage } from './workspace/model';
import type { Conversation } from '../types';

const NOW = Date.UTC(2026, 9, 10, 12);

describe('the home library', () => {
  const convo = (id: string, title: string, at: number, n = 2): Conversation => ({
    id,
    title,
    createdAt: at,
    updatedAt: at,
    model: 'm',
    messages: Array.from({ length: n }, (_, i) => ({ id: `${id}${i}`, role: i % 2 ? 'assistant' : 'user', content: `línea ${i}`, timestamp: at }) as never),
  });

  it('turns conversations and pages into documents with useful metadata', () => {
    const items = conversationItems([convo('a', 'Viaje', NOW - 86_400_000), convo('empty', 'Nada', NOW, 0)], NOW);
    expect(items).toHaveLength(1);
    expect(items[0].meta).toBe('2 mensajes · Ayer');
    const page = newPage('Proyecto', null, [block('todo', 'uno', { checked: true }), block('todo', 'dos')], NOW);
    const [p] = pageItems([page, { ...newPage('Vieja'), archived: true }], NOW);
    expect(p.meta).toBe('50 % · Hoy');
    expect(p.path).toBe(`/workspace/${page.id}`);
  });

  it('sorts, filters and pages like the e-paper home', () => {
    const items = [...SECTION_ITEMS, ...conversationItems([convo('a', 'Zeta', NOW), convo('b', 'Alfa', NOW - 1000)], NOW)];
    expect(sortItems(items, 'name')[0].title).toBe('Agent Swarm');
    expect(sortItems(items, 'recent')[0].title).toBe('Zeta');
    expect(filterItems(items, 'conversation')).toHaveLength(2);
    const pg = paginate(items, 9, 4);
    expect(pg.page).toBe(2);
    expect(pg.pages).toBe(2);
    expect(pg.items).toHaveLength(2);
  });

  it('marks toggle', () => {
    expect(toggleMark(DEFAULT_MARKS, 'section:salud')).not.toContain('section:salud');
    expect(toggleMark([], 'x')).toEqual(['x']);
  });
});
