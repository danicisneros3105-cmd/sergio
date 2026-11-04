import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('react-router', () => ({ useNavigate: () => vi.fn() }));
vi.mock('../../lib/store', () => ({ useAppStore: { getState: () => ({ setCommandPaletteOpen: vi.fn() }) } }));

import { Tour } from './Tour';
import { CLIPS } from './MotionClip';

describe('the tour', () => {
  it('opens on the first of eleven steps with a widget', () => {
    const html = renderToStaticMarkup(<Tour onClose={() => {}} />);
    expect(html).toContain('Bienvenido a Sergio');
    expect(html).toContain('Paso 1 de 11');
    expect(html).toContain('tour-widget');
    expect(html.match(/Ir al paso/g)?.length).toBe(11);
  });

  it('shows a silent motion clip on every step (4 Nov 2026)', () => {
    const html = renderToStaticMarkup(<Tour onClose={() => {}} />);
    expect(html).toContain('Animación: Bienvenido a Sergio');
    expect(html).not.toContain('<audio');
    expect(Object.keys(CLIPS).sort()).toEqual(
      ['atajos', 'auto', 'chat', 'dividir', 'hola', 'modelos', 'nodes', 'salud', 'uso', 'video', 'voz'],
    );
    for (const c of Object.values(CLIPS)) expect(c.length).toBeLessThanOrEqual(7000);
  });
});
