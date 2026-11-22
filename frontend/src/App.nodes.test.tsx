// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';

vi.hoisted(() => {
  const data = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value); },
    removeItem: (key: string) => { data.delete(key); },
  });
});

vi.mock('./components/VideoLayout', async () => {
  const { Outlet } = await import('react-router');
  return { VideoLayout: () => <Outlet /> };
});
vi.mock('./components/ui/sonner', () => ({ Toaster: () => null }));
vi.mock('./components/Celebration/CelebrationLayer', () => ({ CelebrationLayer: () => null }));
vi.mock('./pages/VideoPage', () => ({ VideoPage: () => <div data-testid="video-home">Video</div> }));
vi.mock('./lib/api', () => ({
  isTauri: () => false,
  fetchModels: async () => [],
  fetchServerInfo: async () => ({}),
  fetchSavings: async () => ({ per_provider: [] }),
  submitSavings: vi.fn(),
}));
vi.mock('./lib/analytics', () => ({ track: vi.fn(), hashId: async () => '' }));

import App from './App';

afterEach(() => cleanup());

function CurrentPath() {
  const { pathname } = useLocation();
  return <output data-testid="current-path">{pathname}</output>;
}

it('redirects retired areas to the Video screen', async () => {
  for (const path of ['/chat', '/nodes', '/salud', '/proyectos', '/swarm', '/cowork']) {
    const view = render(
      <MemoryRouter initialEntries={[path]}>
        <App />
        <CurrentPath />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('current-path')).toHaveTextContent('/video'));
    expect(screen.getByTestId('video-home')).toBeInTheDocument();
    view.unmount();
  }
});

it('keeps the Video home route available', async () => {
  render(
    <MemoryRouter initialEntries={['/']}>
      <App />
      <CurrentPath />
    </MemoryRouter>,
  );
  await waitFor(() => expect(screen.getByTestId('current-path')).toHaveTextContent('/video'));
  expect(screen.getByTestId('video-home')).toBeInTheDocument();
});
