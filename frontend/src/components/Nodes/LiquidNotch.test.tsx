import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { LiquidNotch } from './LiquidNotch';

it('shows real running counts and provides a keyboard accessible destination', () => {
  const html = renderToStaticMarkup(<LiquidNotch running={3} />);
  expect(html).toContain('3 objetivos en ejecución. Abrir Agent Swarm');
  expect(html).toContain('href="/agents"');
  expect(html).toContain('+2');
  expect(html).toContain('filterUnits="userSpaceOnUse"');
  expect(html).not.toContain('display: none');
});

it('does not fabricate activity for idle or invalid counts', () => {
  for (const running of [0, -1, NaN, Infinity]) {
    expect(renderToStaticMarkup(<LiquidNotch running={running} />)).toBe('');
  }
});

it('gives simultaneous instances distinct filter references and keeps text outside the filter', () => {
  const html = renderToStaticMarkup(<><LiquidNotch running={2} /><LiquidNotch running={3} /></>);
  const ids = [...html.matchAll(/<filter id="([^"]+)"/g)].map(m => m[1]);
  expect(new Set(ids).size).toBe(2);
  for (const id of ids) expect(html).toContain(`url(#${id})`);
  expect(html.match(/<\/svg><span class="node-liquid-label"/g)).toHaveLength(2);
});
