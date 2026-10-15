import { describe, expect, it } from 'vitest';
import {
  ancestors,
  childrenOf,
  colorParts,
  coverCss,
  editedAgo,
  hasInline,
  insertMention,
  linkSelection,
  mentionQuery,
  parseInline,
  slashTypesAreGrouped,
  tagColor,
  toggleMark,
} from './notion';
import { newPage, SLASH } from './model';

describe('the notes-app look', () => {
  it('parses inline formatting', () => {
    const parts = parseInline('Hola **mundo** y *bien*, __sub__ ~~no~~ `x` [web](https://a.b) [[Plan]]');
    expect(parts.map((p) => p.kind)).toEqual(['text', 'bold', 'text', 'italic', 'text', 'underline', 'text', 'strike', 'text', 'code', 'text', 'link', 'text', 'page']);
    expect(parts.find((p) => p.kind === 'link')).toMatchObject({ text: 'web', href: 'https://a.b' });
    expect(hasInline('texto normal')).toBe(false);
    expect(hasInline('con [[Página]]')).toBe(true);
  });

  it('toggles marks around a selection, and back', () => {
    const on = toggleMark('hola mundo', 5, 10, 'bold');
    expect(on.text).toBe('hola **mundo**');
    expect(on.text.slice(on.start, on.end)).toBe('mundo');
    const off = toggleMark(on.text, on.start, on.end, 'bold');
    expect(off.text).toBe('hola mundo');
    expect(linkSelection('ver aquí', 4, 8, 'https://x.y')).toBe('ver [aquí](https://x.y)');
  });

  it('finds the «@» being typed and turns it into a page link', () => {
    expect(mentionQuery('hablar con @Pla', 15)).toBe('Pla');
    expect(mentionQuery('correo a@b', 10)).toBeNull();
    const r = insertMention('ver @Pla y más', 8, 'Plan 2027');
    expect(r.text).toBe('ver [[Plan 2027]] y más');
    expect(r.caret).toBe('ver [[Plan 2027]]'.length);
  });

  it('walks a page path and lists children in creation order', () => {
    const a = { ...newPage('A'), createdAt: 1 };
    const b = { ...newPage('B', a.id), createdAt: 2 };
    const c = { ...newPage('C', b.id), createdAt: 3 };
    const d = { ...newPage('D', a.id), createdAt: 0 };
    const pages = { [a.id]: a, [b.id]: b, [c.id]: c, [d.id]: d };
    expect(ancestors(pages, c.id).map((p) => p.title)).toEqual(['A', 'B', 'C']);
    expect(childrenOf(pages, a.id).map((p) => p.title)).toEqual(['D', 'B']);
    expect(childrenOf(pages, null).map((p) => p.title)).toEqual(['A']);
    const loop = { ...a, parent: c.id };
    expect(ancestors({ ...pages, [a.id]: loop }, c.id).length).toBe(3); // a cycle never hangs
  });

  it('colours, covers, tags and times', () => {
    expect(colorParts('red')).toEqual({ text: 'red', bg: '' });
    expect(colorParts('blue_bg')).toEqual({ text: '', bg: 'blue' });
    expect(coverCss('g1')).toContain('gradient');
    expect(coverCss('file:x')).toBe('');
    expect(tagColor('Hecho')).toBe(tagColor('Hecho'));
    expect(editedAgo(1_000, 1_000 + 30_000)).toBe('Editado ahora');
    expect(editedAgo(0, 3 * 3600_000)).toBe('Editado hace 3 h');
    expect(slashTypesAreGrouped(SLASH.map((s) => s.type))).toBe(true);
  });
});
