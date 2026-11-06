// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.resetModules();
});

it('keeps conversations separate after sign-out and sign-in as a different account', async () => {
  const a = 'a'.repeat(16);
  const b = 'b'.repeat(16);
  const first = await import('./browserAccount');
  first.saveBrowserAccount({ id: a, token: 'sg_one', base: '' });
  vi.resetModules();
  const accountA = await import('./browserAccount');
  const storeA = await import('./store');
  const chatA = storeA.useAppStore.getState().createConversation('model-a');
  expect(storeA.useAppStore.getState().conversations.some((c) => c.id === chatA)).toBe(true);
  accountA.clearBrowserAccount();
  expect(accountA.scopedDataKey('openjarvis-conversations')).toContain(a);
  expect(accountA.sessionToken('')).toBe('');
  accountA.saveBrowserAccount({ id: b, token: 'sg_two', base: '' });
  vi.resetModules();
  const accountB = await import('./browserAccount');
  const storeB = await import('./store');
  expect(accountB.scopedDataKey('openjarvis-conversations')).toContain(b);
  expect(storeB.useAppStore.getState().conversations).toEqual([]);
  expect(accountB.sessionToken('https://another-server.invalid')).toBe('');
  accountB.saveBrowserAccount({ id: a, token: 'sg_rotated', base: '' });
  vi.resetModules();
  const returned = await import('./store');
  expect(returned.useAppStore.getState().conversations.some((c) => c.id === chatA)).toBe(true);
});
