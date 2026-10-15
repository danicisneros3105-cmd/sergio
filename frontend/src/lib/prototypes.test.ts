import { describe, expect, it } from 'vitest';
import { cssVars, designPrompt, setCssVar, splitAnswer, titleFrom, withBridge, withoutBridge, BRIDGE_MARK } from './prototypes';

const PAGE = '<!doctype html><html><head><style>:root { --fondo: #ffffff; --acento: #111111; --radio: 12px; --letra: Inter; }</style></head><body><h1>Hola</h1></body></html>';

describe('Prototipos', () => {
  it('asks for one self-contained file, and sends the current one for changes', () => {
    const first = designPrompt({ kind: 'presentacion', request: 'ventas del trimestre' });
    expect(first).toContain('```html');
    expect(first).toContain('1920×1080');
    expect(first).toContain('Encargo: ventas del trimestre');
    const change = designPrompt({ kind: 'prototipo', request: 'más aire', html: PAGE, comments: [{ target: '«Hola» (h1)', text: 'más grande' }] });
    expect(change).toContain(PAGE);
    expect(change).toContain('Sobre «Hola» (h1): más grande');
    expect(change).toContain('Cambio pedido: más aire');
  });

  it('splits the answer into the words and the HTML, even mid-stream', () => {
    const done = splitAnswer('Hice una portada sobria.\n```html\n' + PAGE + '\n```');
    expect(done.note).toBe('Hice una portada sobria.');
    expect(done.html).toBe(PAGE);
    expect(splitAnswer('Empiezo\n```html\n<!doctype html><html><body><div>a').html).toContain('<div>a');
    expect(splitAnswer('Antes ' + PAGE).html).toBe(PAGE);
    expect(splitAnswer('Solo texto').html).toBe('');
  });

  it('turns the design variables into knobs and changes one', () => {
    const vars = cssVars(PAGE);
    expect(vars.map((v) => [v.name, v.kind])).toEqual([
      ['--fondo', 'color'],
      ['--acento', 'color'],
      ['--radio', 'length'],
      ['--letra', 'other'],
    ]);
    const next = setCssVar(PAGE, '--radio', '20px');
    expect(cssVars(next).find((v) => v.name === '--radio')?.value).toBe('20px');
    expect(next).toContain('<h1>Hola</h1>');
  });

  it('adds the preview bridge and never keeps it', () => {
    const shown = withBridge(PAGE);
    expect(shown).toContain(BRIDGE_MARK);
    expect(shown.indexOf(BRIDGE_MARK)).toBeLessThan(shown.indexOf('</body>'));
    expect(withoutBridge(shown)).toBe(PAGE);
    expect(titleFrom('  una app   para reservar  ')).toBe('una app para reservar');
  });
});
