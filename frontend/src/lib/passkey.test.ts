import { describe, expect, it } from 'vitest';
import { b64u, deviceName, passkeyProblem, unb64u } from './passkey';

describe('passkeys', () => {
  it('round-trips the bytes the device signs', () => {
    const bytes = new Uint8Array([0, 1, 2, 250, 251, 252, 253, 254, 255]);
    const text = b64u(bytes);
    expect(text).not.toMatch(/[+/=]/);
    expect(Array.from(unb64u(text))).toEqual(Array.from(bytes));
  });

  it('names the device from what the browser says', () => {
    expect(deviceName('Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X)')).toBe('iPhone');
    expect(deviceName('Mozilla/5.0 (Linux; Android 16; Pixel 10 Pro Fold) Mobile')).toBe('Teléfono Android');
    expect(deviceName('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')).toBe('PC con Windows');
    expect(deviceName('Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0)')).toBe('Mac');
  });

  it('explains a refusal in plain words', () => {
    expect(passkeyProblem(new DOMException('x', 'NotAllowedError'))).toMatch(/Cancelado/);
    expect(passkeyProblem(new DOMException('x', 'SecurityError'))).toMatch(/https/);
    expect(passkeyProblem(new Error('La firma no coincide.'))).toBe('La firma no coincide.');
  });
});
