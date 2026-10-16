// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

vi.mock('../../lib/connectors-api', () => ({ listConnectors: vi.fn(async () => []) }));
vi.mock('sonner', () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));
vi.mock('../../lib/mcp', async original => ({
  ...await original<typeof import('../../lib/mcp')>(),
  fetchConnectors: vi.fn(), fetchDirectory: vi.fn(), addConnector: vi.fn(), connectConnector: vi.fn(), callConnector: vi.fn(),
}));
import { ConnectorsPanel } from './ConnectorsPanel';
import * as mcp from '../../lib/mcp';

const server: mcp.Connector = {
  id: 'git', name: 'Git', kind: 'cli', url: '', command: ['git'], cwd: '/work/my project',
  source: 'custom', directory_id: '', enabled: true, status: 'connected', error: '', oauth: false, own_client: false,
  tools: [{ name: 'run', title: 'Ejecutar CLI', description: '', read_only: false, permission: 'ask' }],
};
function mount() { return render(<MemoryRouter><ConnectorsPanel /></MemoryRouter>); }
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(mcp.fetchConnectors).mockResolvedValue({ servers: [], redirect_uri: '' });
  vi.mocked(mcp.fetchDirectory).mockResolvedValue({ categories: [], connectors: [] });
  vi.mocked(mcp.addConnector).mockResolvedValue({ server });
  vi.mocked(mcp.connectConnector).mockResolvedValue({ status: 'connected', server });
  vi.mocked(mcp.callConnector).mockResolvedValue({ content: [{ type: 'text', text: 'git version fixture' }] });
});
afterEach(cleanup);

it('configures CLI with structured arguments and restores focus after Escape', async () => {
  mount();
  const trigger = screen.getByRole('button', { name: /Añadir conector personalizado/ });
  trigger.focus(); fireEvent.click(trigger);
  fireEvent.click(screen.getByRole('radio', { name: 'CLI' }));
  fireEvent.change(screen.getByLabelText('Ejecutable'), { target: { value: 'git' } });
  fireEvent.change(screen.getByLabelText('Argumentos (JSON)'), { target: { value: '["-C","/work/my project"]' } });
  fireEvent.change(screen.getByLabelText('Carpeta de trabajo'), { target: { value: '/work' } });
  fireEvent.click(screen.getByRole('button', { name: 'Añadir' }));
  await waitFor(() => expect(mcp.addConnector).toHaveBeenCalledWith(expect.objectContaining({
    kind: 'cli', command: ['git'], args: ['-C', '/work/my project'], cwd: '/work', env: {},
  })));
});

it('restores focus and scroll when a sheet closes', async () => {
  mount();
  const trigger = screen.getByRole('button', { name: /Añadir conector personalizado/ });
  trigger.focus(); fireEvent.click(trigger);
  expect(document.body.style.overflow).toBe('hidden');
  fireEvent.keyDown(document, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(document.activeElement).toBe(trigger);
  expect(document.body.style.overflow).toBe('');
});

it('distinguishes connection errors from an empty list and retries', async () => {
  vi.mocked(mcp.fetchConnectors).mockRejectedValueOnce(new Error('Servicio no disponible'));
  mount();
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.getByText('Servicio no disponible')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
});

it('requires the explicit execution button and shows the returned tool output', async () => {
  vi.mocked(mcp.fetchConnectors).mockResolvedValue({ servers: [server], redirect_uri: '' });
  mount();
  fireEvent.click(await screen.findByRole('button', { name: /Git CLI/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Probar' }));
  expect(mcp.callConnector).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Argumentos (JSON)'), { target: { value: '{"arguments":["--version"]}' } });
  fireEvent.click(screen.getByRole('button', { name: 'Autorizar y ejecutar' }));
  await waitFor(() => expect(mcp.callConnector).toHaveBeenCalledWith('git', 'run', { arguments: ['--version'] }));
  expect(await screen.findByText(/git version fixture/)).toBeTruthy();
});
