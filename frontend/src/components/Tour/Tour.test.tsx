import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('react-router', () => ({ useNavigate: () => vi.fn() }));
vi.mock('../../lib/store', () => ({ useAppStore: { getState: () => ({ setCommandPaletteOpen: vi.fn() }) } }));

import { Tour } from './Tour';

describe('the tour', () => {
  it('opens on the first of eleven steps with a widget', () => {
    const html = renderToStaticMarkup(<Tour onClose={() => {}} />);
    expect(html).toContain('Bienvenido a Sergio');
    expect(html).toContain('Paso 1 de 11');
    expect(html).toContain('tour-widget');
    expect(html.match(/Ir al paso/g)?.length).toBe(11);
  });
});
