import { describe, expect, it } from 'vitest';
import { brandFor, brandsIn, isLight } from './brands';

describe('brand logos', () => {
  it('finds a service by id, by name or inside a tool name', () => {
    expect(brandFor('google-drive')?.title).toBe('Google Drive');
    expect(brandFor('gdrive')?.title).toBe('Google Drive');
    expect(brandFor(undefined, 'GitHub')?.hex).toBe('181717');
    expect(brandFor('mcp__notion__search')?.title).toBe('Notion');
    expect(brandFor('mi-servidor-propio')).toBeNull();
  });

  it('only turns written service names into logos', () => {
    expect(brandsIn('Busca en Gmail y sube el resumen a Google Drive').map((b) => b.title)).toEqual(
      expect.arrayContaining(['Gmail', 'Google Drive']),
    );
    expect(brandsIn('pon la caja en el box y haz zoom')).toEqual([]);
  });

  it('gives light colours a dark tile', () => {
    expect(isLight('FFFFFF')).toBe(true);
    expect(isLight('181717')).toBe(false);
  });
});
