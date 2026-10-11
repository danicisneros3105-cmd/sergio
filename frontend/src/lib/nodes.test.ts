import { describe, expect, it } from 'vitest';
import { dayLabel, describeRoutine, groupByDay, relative, statusLine } from './nodes';

describe('nodes words', () => {
  it('says what a Node is doing', () => {
    expect(statusLine({ status: 'working', doing: 'Busca en la web: pisos', waiting: '' })).toBe('Busca en la web: pisos');
    expect(statusLine({ status: 'needs_you', doing: '', waiting: 'Inicie sesión' })).toBe('Inicie sesión');
    expect(statusLine({ status: 'waiting_approval', doing: '', waiting: '' })).toBe('Espera su aprobación');
    expect(statusLine({ status: 'idle', doing: '', waiting: '' })).toBe('Disponible');
  });

  it('describes routines', () => {
    expect(describeRoutine({ every_minutes: 30, at: '', days: [] })).toBe('Cada 30 min');
    expect(describeRoutine({ every_minutes: 60, at: '', days: [] })).toBe('Cada hora');
    expect(describeRoutine({ every_minutes: 240, at: '', days: [] })).toBe('Cada 4 horas');
    expect(describeRoutine({ every_minutes: 1440, at: '', days: [] })).toBe('Cada día');
    expect(describeRoutine({ every_minutes: 0, at: '08:30', days: [0, 4] })).toBe('lun, vie a las 08:30');
    expect(describeRoutine({ every_minutes: 0, at: '21:00', days: [] })).toBe('Todos los días a las 21:00');
  });

  it('groups activity by day, newest first', () => {
    const now = new Date(2026, 9, 11, 12, 0, 0);
    const t = (h: number) => now.getTime() / 1000 - h * 3600;
    const groups = groupByDay(
      [
        { id: 'a', at: t(30), kind: 'done', text: 'ayer' },
        { id: 'b', at: t(1), kind: 'tool', text: 'hoy 1' },
        { id: 'c', at: t(2), kind: 'tool', text: 'hoy 2' },
      ],
      now,
    );
    expect(groups.map((g) => g.day)).toEqual(['Hoy', 'Ayer']);
    expect(groups[0].items.map((i) => i.id)).toEqual(['b', 'c']);
    expect(dayLabel(t(1), now)).toBe('Hoy');
  });

  it('says how long ago', () => {
    const now = 1_000_000_000_000;
    expect(relative(now / 1000 - 10, now)).toBe('ahora');
    expect(relative(now / 1000 - 600, now)).toBe('hace 10 min');
    expect(relative(now / 1000 - 3 * 3600, now)).toBe('hace 3 h');
    expect(relative(now / 1000 - 86400, now)).toBe('ayer');
  });
});
