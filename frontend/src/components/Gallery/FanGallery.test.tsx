import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { FanGallery, rise } from './FanGallery';

describe('FanGallery', () => {
  it('fans out the cards and pages after the hand', () => {
    const items = Array.from({ length: 12 }, (_, i) => ({ key: `k${i}`, kind: 'imagen' as const, title: `Foto ${i}`, src: `/x${i}.png` }));
    const html = renderToStaticMarkup(<FanGallery items={items} onOpen={() => {}} hand={9} />);
    expect(html.match(/class="fan-card"/g)?.length).toBe(9);
    expect(html).toContain('1–9 de 12');
    expect(html).toContain('rotate(');
  });

  it('shows a 3D model as a card with its label', () => {
    const html = renderToStaticMarkup(<FanGallery items={[{ key: 'a', kind: '3d', title: 'Auto' }]} onOpen={() => {}} />);
    expect(html).toContain('Modelo 3D');
    expect(html).not.toContain('fan-pager');
  });

  it('raises the card under the pointer most and its neighbours a little', () => {
    expect(rise(3, 3)).toBe(1);
    expect(rise(2, 3)).toBeGreaterThan(0.4);
    expect(rise(2, 3)).toBeLessThan(1);
    expect(rise(0, 3)).toBeLessThan(0.01);
    expect(rise(1, null)).toBe(0);
  });
});
