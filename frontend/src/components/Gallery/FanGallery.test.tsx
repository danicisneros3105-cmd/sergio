import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { FanGallery } from './FanGallery';

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
});
