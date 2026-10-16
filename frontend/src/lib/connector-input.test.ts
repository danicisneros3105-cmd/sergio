import { expect, it } from 'vitest';
import { parseArguments, parseEnvironment } from './connector-input';

it('keeps paths with spaces, quotes and empty arguments intact', () => {
  const args = ['C:\\Users\\Daniel\\Mi proyecto', 'say "hello"', '', '; touch ignored'];
  expect(parseArguments(JSON.stringify(args))).toEqual(args);
  expect(parseArguments('')).toEqual([]);
});
it('rejects shell strings and invalid structured arguments', () => {
  for (const text of ['git status', '{}', '[1]', '[null]', '["\\u0000"]']) {
    expect(() => parseArguments(text)).toThrow();
  }
});
it('keeps explicitly provided secrets in a validated environment object', () => {
  expect(parseEnvironment('{"TOKEN":"test=a"}')).toEqual({ TOKEN: 'test=a' });
  for (const text of ['[]', 'null', '{"BAD NAME":"a"}', '{"TOKEN":1}']) expect(() => parseEnvironment(text)).toThrow();
});
