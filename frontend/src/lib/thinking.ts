import type { ChatMessage } from '../types';

// The WebSocket that streams deep-thinking steps (server/thinking_routes.py).
export function thinkingUrl(base: string, origin: string): string {
  const url = new URL('/v1/thinking/stream', base || origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export function lastUserQuestion(messages: ChatMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === 'user' && messages[i].content.trim()) return messages[i].content.trim();
  }
  return '';
}
