// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { GalleryStage, dayLabel, groupByDay, type GalleryRow } from './GalleryStage';

const NOW = new Date(2026, 10, 3, 15, 0, 0); // 3 Nov 2026
const at = (y: number, m: number, d: number, h = 10) => new Date(y, m, d, h).getTime() / 1000;

const rows: GalleryRow[] = [
  { url: '/v1/creator/media/imagen-a.png', mini: '/m/a', tipo: 'imagen', nombre: 'imagen', fecha: at(2026, 10, 3) },
  { url: '/v1/creator/media/video-b.mp4', mini: '/m/b', tipo: 'video', nombre: 'video', fecha: at(2026, 10, 3, 9) },
  { url: '', tipo: '3d', nombre: 'Auto', modelo: 'auto', piezas: 181, fecha: at(2026, 10, 2) },
  { url: '/v1/creator/media/imagen-c.png', tipo: 'imagen', nombre: 'foto', fecha: at(2025, 0, 5) },
];

afterEach(cleanup);
const html = () => document.body.innerHTML;

describe('GalleryStage', () => {
  it('names the days like Photos does', () => {
    expect(dayLabel(at(2026, 10, 3), NOW)).toBe('Hoy');
    expect(dayLabel(at(2026, 10, 2), NOW)).toBe('Ayer');
    expect(dayLabel(at(2026, 9, 20), NOW)).toMatch(/20 de octubre/);
    expect(dayLabel(at(2025, 0, 5), NOW)).toMatch(/2025/);
    expect(dayLabel(0, NOW)).toBe('Sin fecha');
  });

  it('groups newest first, one group per day', () => {
    const g = groupByDay(rows, NOW);
    expect(g.map((x) => x.label.slice(0, 3))).toEqual(['Hoy', 'Aye', '5 d']);
    expect(g[0].rows.map((r) => r.tipo)).toEqual(['imagen', 'video']);
  });

  it('shows a tile for each item, with its kind, and a play mark on videos', () => {
    // The test dates are fixed; the clock must be too, or «Hoy» expires at midnight.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    render(<GalleryStage rows={rows} from={null} onClose={() => {}} />);
    expect(document.querySelectorAll('.gs-tile').length).toBe(4);
    expect(html()).toContain('4 elementos');
    expect(html()).toContain('gs-play');
    expect(html()).toContain('181 piezas');
    expect(html()).toContain('Hoy');
    // on the page itself, not inside the app frame
    expect(document.body.querySelector(':scope > .gs')).not.toBeNull();
  });

  it('filters by kind from the start', () => {
    render(<GalleryStage rows={rows} from={null} filter="video" onClose={() => {}} />);
    expect(document.querySelectorAll('.gs-tile').length).toBe(1);
    expect(html()).toContain('1 elemento');
  });
});
