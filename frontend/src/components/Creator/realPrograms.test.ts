import { describe, expect, it } from 'vitest';
import { anatomyNames, withMemoryStorage, withoutAnatomyLinks } from '../../lib/anatomy';
import { embedUrl, programState, type Program } from '../../lib/creatorPrograms';
import { chartPaths } from './BolsaStudio';

const prog = (p: Partial<Program>): Program => ({
  id: 'x',
  name: 'X',
  space: 'diseno',
  where: 'web',
  what: '',
  license: 'MIT',
  ...p,
});

describe('Anatomy in the chat', () => {
  it('finds each linked figure once, in reply and tool results', () => {
    const reply = 'Mire la lámina: /v1/creator/anatomy/view/raptor-engine y otra vez /v1/creator/anatomy/view/raptor-engine';
    const tool = 'aparece en el chat con este enlace: /v1/creator/anatomy/view/caché-x /v1/creator/anatomy/view/cache_x';
    expect(anatomyNames(reply, tool, undefined)).toEqual(['raptor-engine', 'cache_x']);
    expect(anatomyNames('nada aquí')).toEqual([]);
  });

  it('hides the raw links from the reply', () => {
    expect(withoutAnatomyLinks('Le dejo la lámina: /v1/creator/anatomy/view/raptor-engine\nOtra línea')).toBe(
      'Le dejo la lámina:\nOtra línea',
    );
    expect(withoutAnatomyLinks('Vea (/v1/creator/anatomy/view/caja).')).toBe('Vea.');
  });

  it('gives sandboxed figures a storage in memory', () => {
    const page = withMemoryStorage('<!doctype html><html><head><title>t</title></head></html>');
    expect(page.indexOf('<script>')).toBeGreaterThan(page.indexOf('<head>'));
    expect(withMemoryStorage('<p>x</p>').startsWith('<script>')).toBe(true);
  });
});

describe('Creator programs', () => {
  it('embeds web programs on the page host, VSCodium with its token', () => {
    expect(embedUrl(prog({ id: 'opendesign', port: 8790 }), 'localhost')).toBe('http://localhost:8790/');
    expect(embedUrl(prog({ id: 'vscodium', port: 8791, token: 'a b' }), '127.0.0.1')).toBe('http://127.0.0.1:8791/?tkn=a%20b');
  });

  it('says what state each program is in', () => {
    expect(programState(prog({ installed: true }))).toBe('listo');
    expect(programState(prog({ installed: false }))).toBe('falta');
    expect(programState(prog({ where: 'windows', reachable: false }))).toBe('sin-escritorio');
    expect(programState(prog({ installing: true }))).toBe('instalando');
  });
});

describe('Bolsa chart', () => {
  const candle = (date: string, close: number) => ({ date, open: close, high: close + 1, low: close - 1, close, volume: 0 });
  it('draws history, then the forecast and its band, on one scale', () => {
    const history = [candle('2026-01-01', 10), candle('2026-01-02', 12)];
    const forecast = [candle('2026-01-03', 14), candle('2026-01-04', 13)];
    const p = chartPaths(history, forecast);
    expect(p.lo).toBe(9);
    expect(p.hi).toBe(15);
    expect(p.past.startsWith('M')).toBe(true);
    expect(p.ahead.split(/[ML]/).filter(Boolean)).toHaveLength(3); // joins the last real close
    expect(p.band.endsWith('Z')).toBe(true);
    expect(chartPaths(history, []).ahead).toBe('');
  });
});
