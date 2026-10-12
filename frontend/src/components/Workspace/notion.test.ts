import { describe, expect, it } from 'vitest';
import { cellHref, monthGrid, multiValues } from './TableViews';
import { bookmarkParts } from './ExtraBlocks';
import { block, newPage, toMarkdown } from '../../lib/workspace/model';

describe('Workspace, Notion-like additions', () => {
  it('builds a Monday-first month grid', () => {
    const oct = monthGrid(2026, 9); // October 2026 starts on a Thursday
    expect(oct[0].iso).toBe('2026-09-28');
    expect(oct.find((d) => d.inMonth)?.iso).toBe('2026-10-01');
    expect(oct.filter((d) => d.inMonth)).toHaveLength(31);
    expect(oct.length % 7).toBe(0);
  });

  it('links only real urls, emails and phones', () => {
    expect(cellHref({ id: 'c', name: 'Web', type: 'url' }, 'sergio.app/precios')).toBe('https://sergio.app/precios');
    expect(cellHref({ id: 'c', name: 'Mail', type: 'email' }, 'ana@empresa.com')).toBe('mailto:ana@empresa.com');
    expect(cellHref({ id: 'c', name: 'Mail', type: 'email' }, 'no es correo')).toBe('');
    expect(cellHref({ id: 'c', name: 'Tel', type: 'phone' }, '+593 99 123 4567')).toBe('tel:+593991234567');
    expect(cellHref({ id: 'c', name: 'Texto', type: 'text' }, 'https://x.y')).toBe('');
    expect(multiValues(' a, b ,,c ')).toEqual(['a', 'b', 'c']);
  });

  it('reads a bookmark without fetching the site', () => {
    expect(bookmarkParts('https://www.example.com/guia-de-viaje/')).toEqual({
      href: 'https://www.example.com/guia-de-viaje/',
      host: 'example.com',
      path: '/guia-de-viaje',
    });
    expect(bookmarkParts('no es un enlace')).toBeNull();
  });

  it('exports equations, bookmarks and the index to Markdown', () => {
    const page = newPage('Física', null, [
      block('toc'),
      block('h1', 'Energía'),
      block('equation', 'E = mc^2'),
      block('h2', 'Fuentes'),
      block('bookmark', 'https://es.wikipedia.org/wiki/Energía'),
    ]);
    const md = toMarkdown(page);
    expect(md).toContain('- Energía\n  - Fuentes');
    expect(md).toContain('$$\nE = mc^2\n$$');
    expect(md).toContain('<https://es.wikipedia.org/wiki/Energía>');
  });
});
