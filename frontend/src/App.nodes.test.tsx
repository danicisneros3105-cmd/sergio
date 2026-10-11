import { renderToReadableStream } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { expect, it, vi } from 'vitest';

vi.hoisted(() => {
  const data = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value); },
    removeItem: (key: string) => { data.delete(key); },
  });
});

vi.mock('./components/Layout', async () => {
  const { Outlet } = await import('react-router');
  return { Layout: () => <Outlet /> };
});
vi.mock('./components/Desktop/UpdateChecker', () => ({ UpdateChecker: () => null }));
vi.mock('./components/ui/sonner', () => ({ Toaster: () => null }));
vi.mock('./lib/api', async (original) => ({
  ...await original<typeof import('./lib/api')>(),
  isTauri: () => false,
}));

import App from './App';
import { TOOLBAR_ITEMS } from './components/Shell/Toolbar';

it('opens the real Nodes page from its desktop/menu URL', async () => {
  const stream = await renderToReadableStream(
    <MemoryRouter initialEntries={['/nodes']}><App /></MemoryRouter>,
  );
  await stream.allReady;
  const html = await new Response(stream).text();
  // The Nodes page itself (still loading its list), not the error screen.
  expect(html).toContain('paper-page');
  expect(html).not.toContain('Cargando espacio de trabajo');
  expect(TOOLBAR_ITEMS.filter(item => item.path === '/nodes')).toHaveLength(1);
});
