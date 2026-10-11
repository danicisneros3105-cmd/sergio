import { describe, expect, it } from 'vitest';
import { seal, unseal, WrongPassphrase } from './crypto';
import { block } from './model';

describe('end-to-end encryption', () => {
  it('seals blocks so only the passphrase opens them', async () => {
    const blocks = [block('h1', 'Diario privado'), block('text', 'Nadie más lo lee.')];
    const sealed = await seal(blocks, 'una frase larga', 1000);
    expect(sealed.data).not.toContain('Diario');
    expect(atob(sealed.data)).not.toContain('Nadie');
    const opened = await unseal(sealed, 'una frase larga');
    expect(opened.map((b) => b.text)).toEqual(['Diario privado', 'Nadie más lo lee.']);
    await expect(unseal(sealed, 'otra frase cualquiera')).rejects.toBeInstanceOf(WrongPassphrase);
  });

  it('uses a fresh salt and nonce each time and refuses short passphrases', async () => {
    const a = await seal([block('text', 'x')], 'una frase larga', 1000);
    const b = await seal([block('text', 'x')], 'una frase larga', 1000);
    expect(a.salt).not.toBe(b.salt);
    expect(a.iv).not.toBe(b.iv);
    expect(a.data).not.toBe(b.data);
    await expect(seal([], 'corta')).rejects.toThrow('8 caracteres');
  });
});
