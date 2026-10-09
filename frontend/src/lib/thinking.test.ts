import { describe, expect, it } from 'vitest';
import { lastUserQuestion, thinkingUrl } from './thinking';
import type { ChatMessage } from '../types';

const msg = (role: 'user' | 'assistant', content: string): ChatMessage => ({
  id: content,
  role,
  content,
  timestamp: 0,
});

describe('thinkingUrl', () => {
  it('uses ws/wss on the same server', () => {
    expect(thinkingUrl('', 'https://abc.trycloudflare.com')).toBe('wss://abc.trycloudflare.com/v1/thinking/stream');
    expect(thinkingUrl('http://127.0.0.1:8000', 'tauri://localhost')).toBe('ws://127.0.0.1:8000/v1/thinking/stream');
  });
});

describe('lastUserQuestion', () => {
  it('finds the most recent question the user asked', () => {
    expect(lastUserQuestion([msg('user', 'primera'), msg('assistant', 'r'), msg('user', ' segunda '), msg('assistant', 'r2')])).toBe(
      'segunda',
    );
    expect(lastUserQuestion([msg('assistant', 'hola')])).toBe('');
  });
});
