import { describe, expect, it } from 'vitest';
import { needFrom } from './session';

describe('sign-in gate', () => {
  it('lets a signed-in person through', () => {
    expect(needFrom({ accounts: 3, local: false, me: { role: 'owner' } }, false)).toBe('ok');
  });
  it('asks to create the first account, and to sign in after that', () => {
    expect(needFrom({ accounts: 0, local: true, me: null }, false)).toBe('crear');
    expect(needFrom({ accounts: 2, local: false, me: null }, false)).toBe('entrar');
  });
  it('«Seguir sin cuenta» only works on this computer', () => {
    expect(needFrom({ accounts: 1, local: true, me: null }, true)).toBe('ok');
    expect(needFrom({ accounts: 1, local: false, me: null }, true)).toBe('entrar');
  });
  it('fails open when the server does not answer', () => {
    expect(needFrom(null, false)).toBe('ok');
  });
});
