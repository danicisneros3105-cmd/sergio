import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

describe('desktop cloud provider settings', () => {
  it('offers Atlas Cloud key storage alongside its provider status', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null });
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} });
    const { SettingsPage } = await import('./SettingsPage');
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );

    expect(html).toContain('Atlas Cloud');
    expect(html).toContain('Fuentes de datos'); // the «Más» links
    const atlasKeyInput = html.match(/<input[^>]*placeholder="Clave de Atlas Cloud"[^>]*>/)?.[0];
    expect(atlasKeyInput).toBeDefined();
    expect(atlasKeyInput).toContain('disabled'); // locked until server verifies Dev
    expect(html).toContain('requiere Dev');
    vi.unstubAllGlobals();
  });
});
