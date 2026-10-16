import { afterEach, describe, expect, it, vi } from 'vitest';
import { signInWindow } from './mcp';

vi.mock('./api', () => ({ apiFetch: vi.fn(), getBase: () => 'https://sergio.test' }));

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('connector sign-in', () => {
  it('accepts only the callback origin and the actual popup', async () => {
    vi.useFakeTimers();
    let listener: (e: unknown) => void = () => {};
    const popup = { closed: false, location: { href: '' }, close: vi.fn() };
    const win = {
      location: { origin: 'https://sergio.test' },
      open: vi.fn(() => popup),
      addEventListener: vi.fn((_name, fn) => { listener = fn; }),
      removeEventListener: vi.fn(),
    };
    vi.stubGlobal('window', win);
    const result = signInWindow('https://provider.test/authorize');
    let completed = false;
    void result.then(() => { completed = true; });
    listener({ origin: 'https://evil.test', source: popup, data: { sergio: 'mcp-connected', ok: true } });
    listener({ origin: 'https://sergio.test', source: {}, data: { sergio: 'mcp-connected', ok: true } });
    await Promise.resolve();
    expect(completed).toBe(false);
    listener({ origin: 'https://sergio.test', source: popup, data: { sergio: 'mcp-connected', ok: true } });
    expect(await result).toBe(true);
    expect(popup.close).toHaveBeenCalledOnce();
    expect(win.removeEventListener).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('reports a blocked popup instead of pretending authentication completed', async () => {
    vi.stubGlobal('window', { open: () => null });
    await expect(signInWindow('https://provider.test')).rejects.toThrow('Permita la ventana');
  });

  it('confirms server state when the external browser cannot post back', async () => {
    vi.useFakeTimers();
    const popup = { closed: false, location: { href: '' }, close: vi.fn() };
    vi.stubGlobal('window', { location: { origin: 'https://sergio.test' }, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    const verify = vi.fn().mockResolvedValue(true);
    const result = signInWindow('https://provider.test', popup as unknown as Window, verify);
    await vi.advanceTimersByTimeAsync(1000);
    expect(await result).toBe(true);
    expect(verify).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('reuses the window reserved during the click and expires pending login', async () => {
    vi.useFakeTimers();
    const popup = { closed: false, location: { href: '' }, close: vi.fn() };
    const open = vi.fn();
    vi.stubGlobal('window', { open, location: { origin: 'https://sergio.test' }, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    const result = signInWindow('https://provider.test/authorize', popup as unknown as Window);
    expect(open).not.toHaveBeenCalled();
    expect(popup.location.href).toBe('https://provider.test/authorize');
    await vi.advanceTimersByTimeAsync(15 * 60 * 1000);
    expect(await result).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });
});
