import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
}

beforeEach(() => {
  vi.resetModules();
  (globalThis as unknown as { localStorage: MemoryStorage }).localStorage = new MemoryStorage();
});

afterEach(() => {
  (globalThis as unknown as { localStorage?: MemoryStorage }).localStorage = undefined;
});

describe('chat sections', () => {
  it('keeps text, voice and quick chats apart and continues the recent ones', async () => {
    const { useAppStore, chatKindOf } = await import('./store');
    const st = useAppStore.getState();
    const text = st.createConversation('m');
    st.addMessage(text, { id: 'u1', role: 'user', content: 'hola', timestamp: Date.now() });
    const voice = useAppStore.getState().chatFor('voz');
    expect(voice).not.toBe(text);
    expect(useAppStore.getState().activeId).toBe(text); // the chat on screen stays
    expect(useAppStore.getState().chatFor('voz')).toBe(voice); // one voice chat, continued
    const quick = useAppStore.getState().chatFor('rapido');
    const kinds = useAppStore.getState().conversations.map((c) => [c.id, chatKindOf(c)]);
    expect(Object.fromEntries(kinds)).toEqual({ [text]: 'texto', [voice]: 'voz', [quick]: 'rapido' });
  });

  it('does not pile up empty chats', async () => {
    const { useAppStore } = await import('./store');
    const a = useAppStore.getState().createConversation('m');
    const b = useAppStore.getState().createConversation('m');
    expect(b).toBe(a);
    expect(useAppStore.getState().conversations).toHaveLength(1);
  });

  it('reads old chats made only of voice turns as voice', async () => {
    const { chatKindOf } = await import('./store');
    const voiceOnly = { messages: [{ id: '1', role: 'user' as const, content: 'x', timestamp: 1, voice: true }] };
    expect(chatKindOf(voiceOnly)).toBe('voz');
    expect(chatKindOf({ messages: [] })).toBe('texto');
  });
});
