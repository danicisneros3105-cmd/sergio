import { describe, expect, it } from 'vitest';
import {
  MAX_ANSWERS,
  answerKey,
  findAnswer,
  isNetworkError,
  isOffline,
  memoryStore,
  normalize,
  offlineReply,
  rememberAnswer,
} from './offline';

describe('offline answers', () => {
  it('normalizes accents, case and punctuation', () => {
    expect(normalize('¿Qué hora es en  Tokio?')).toBe('que hora es en tokio');
    expect(answerKey('¿Qué hora es?')).toBe(answerKey('que HORA es'));
  });

  it('finds a saved answer for the same question', async () => {
    const store = memoryStore();
    await rememberAnswer('¿Cuál es la capital de Francia?', 'París.', { store, model: 'm', at: 5 });
    const hit = await findAnswer('cual es la capital de francia', { store });
    expect(hit?.answer).toBe('París.');
    expect(hit?.model).toBe('m');
    expect(await findAnswer('otra cosa', { store })).toBeNull();
  });

  it('keys follow-ups by the answer they follow', async () => {
    const store = memoryStore();
    await rememberAnswer('¿y mañana?', 'Lloverá.', { store, previousAnswer: 'Hoy hace sol en Quito.' });
    expect(await findAnswer('¿y mañana?', { store })).toBeNull();
    expect(
      (await findAnswer('y mañana', { store, previousAnswer: 'Hoy hace sol en Quito.' }))?.answer,
    ).toBe('Lloverá.');
  });

  it('keeps only the newest answers', async () => {
    const store = memoryStore();
    for (let i = 0; i < MAX_ANSWERS + 5; i++) {
      await rememberAnswer(`pregunta ${i}`, `respuesta ${i}`, { store, at: i });
    }
    expect((await store.all()).length).toBe(MAX_ANSWERS);
    expect(await findAnswer('pregunta 0', { store })).toBeNull();
    expect((await findAnswer(`pregunta ${MAX_ANSWERS + 4}`, { store }))?.answer).toBe(
      `respuesta ${MAX_ANSWERS + 4}`,
    );
  });

  it('ignores empty input and a missing store', async () => {
    const store = memoryStore();
    await rememberAnswer('  ', 'x', { store });
    await rememberAnswer('hola', '', { store });
    expect(await store.all()).toEqual([]);
    expect(await findAnswer('hola', { store: null })).toBeNull();
    await rememberAnswer('hola', 'x', { store: null });
  });

  it('survives a broken store', async () => {
    const broken = {
      get: () => Promise.reject(new Error('quota')),
      put: () => Promise.reject(new Error('quota')),
      all: () => Promise.reject(new Error('quota')),
      remove: () => Promise.reject(new Error('quota')),
    };
    await rememberAnswer('hola', 'x', { store: broken });
    expect(await findAnswer('hola', { store: broken })).toBeNull();
  });

  it('tells a missing network from a server error', () => {
    expect(isNetworkError(new TypeError('Failed to fetch'))).toBe(true);
    expect(isNetworkError(new TypeError('NetworkError when attempting to fetch resource.'))).toBe(true);
    expect(isNetworkError(new TypeError('Load failed'))).toBe(true);
    expect(isNetworkError(new Error('HTTP 500'))).toBe(false);
    expect(isOffline({ onLine: false })).toBe(true);
    expect(isOffline({ onLine: true })).toBe(false);
    expect(isOffline(undefined)).toBe(false);
  });

  it('marks a saved reply with its date', () => {
    const text = offlineReply({ key: 'k', question: 'q', answer: 'Hola.', model: '', at: 0 });
    expect(text.startsWith('Hola.\n\n_Sin conexión:')).toBe(true);
  });
});
