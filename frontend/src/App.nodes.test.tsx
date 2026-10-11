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
import { NAV_ITEMS } from './components/Sidebar/Sidebar';

it('opens the real Nodes page from its desktop/menu URL', async () => {
  const stream = await renderToReadableStream(
    <MemoryRouter initialEntries={['/nodes']}><App /></MemoryRouter>,
  );
  await stream.allReady;
  const html = await new Response(stream).text();
  expect(html).toContain('Tus Nodes');
  expect(html).toContain('Personajes propios, objetivos y memoria bajo tu control.');
  expect(NAV_ITEMS.filter(item => item.path === '/nodes')).toHaveLength(1);
});
