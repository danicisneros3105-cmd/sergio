import { describe, expect, it } from 'vitest';
import { prettyName } from './hub';

describe('hub', () => {
  it('plugin names read like titles', () => {
    expect(prettyName('tipo-de-cambio')).toBe('Tipo de cambio');
    expect(prettyName('frase_del_dia')).toBe('Frase del dia');
    expect(prettyName('')).toBe('');
  });
});
