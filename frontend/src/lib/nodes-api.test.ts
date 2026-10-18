import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { NodeAvatar } from '../components/Nodes/NodeAvatar';

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'test');
  vi.stubGlobal('localStorage', {getItem: () => JSON.stringify({apiKey: 'owner-token'})});
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it('Nodes requests carry owner auth and preserve reviewed arguments', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ok:true}), {status:200}));
  vi.stubGlobal('fetch', fetch);
  const { nodesRequest } = await import('./nodes-api');
  await nodesRequest('/a/connections/b/execute', 'POST', {ticket:'one-use', tool:'echo', tool_arguments:{text:'Exact Case'}});
  const [url, options] = fetch.mock.calls[0];
  expect(url).toBe('/v1/nodes/a/connections/b/execute');
  expect(options.headers.Authorization).toBe('Bearer owner-token');
  expect(JSON.parse(options.body).tool_arguments.text).toBe('Exact Case');
});

it('surfaces Dev denial and malformed errors without false success', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Requiere plan Dev'}), {status:403})));
  const { nodesRequest } = await import('./nodes-api');
  await expect(nodesRequest('/api-key', 'POST', {})).rejects.toThrow('Requiere plan Dev');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('not JSON', {status:502})));
  await expect(nodesRequest('/x')).rejects.toThrow('502');
});

it('renders three distinct original avatars with bounded static geometry', () => {
  // Each is now a phenakistoscope disc: 12 inked frames (and the ring that holds
  // them) instead of one flat drawing, so the bound is per disc, not per drawing.
  const avatars = ['lumen','bruma','nival'].map(species => renderToStaticMarkup(createElement(NodeAvatar, {colour:'#ba8097', species, fur:1})));
  expect(new Set(avatars).size).toBe(3);
  for (const avatar of avatars) {
    expect(avatar).not.toContain('<image');
    expect(avatar).not.toContain('NaN');
    expect(avatar.length).toBeLessThan(150000);
    expect(avatar).toContain('aria-hidden="true"');
  }
});
