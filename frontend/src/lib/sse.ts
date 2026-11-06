import type { ResearchEvent, SSEEvent } from '../types';
import { getBase, authHeaders } from './api';

export interface ChatRequest {
  model: string;
  messages: Array<{ role: string; content: string }>;
  stream: true;
  temperature?: number;
  max_tokens?: number;
}

export class IncompleteChatStreamError extends Error {}

export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const base = getBase();
  const response = await fetch(`${base}/v1/chat/completions`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  for await (const event of eventFrames(response)) {
    if (event.data === '[DONE]') return;
    yield event;
  }
  throw new IncompleteChatStreamError('La respuesta se interrumpió antes de terminar. Puedes volver a intentarlo.');
}

export async function* streamResearch(
  query: string,
  model?: string,
  signal?: AbortSignal,
): AsyncGenerator<ResearchEvent> {
  // /api/research is mounted at the server root — strip any trailing /v1
  // from the base so configurations like "http://host:8000/v1" still resolve.
  const base = getBase().replace(/\/v1\/?$/, '');
  const response = await fetch(`${base}/api/research`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ query, ...(model ? { model } : {}) }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Research request failed: ${response.status}`);
  }

  for await (const event of eventFrames(response)) {
    if (event.data === '[DONE]') return;
    let parsed: ResearchEvent;
    try {
      parsed = JSON.parse(event.data) as ResearchEvent;
    } catch {
      continue;
    }
    if (!parsed || typeof parsed.type !== 'string') continue;
    yield parsed;
    if (parsed.type === 'done') return;
  }
}

// Parse complete SSE frames over fetch (POST bodies and auth headers).
// Keep a CR at the end of a chunk until we know whether an LF follows it.
async function* eventFrames(response: Response): AsyncGenerator<SSEEvent> {
  if (!response.body) throw new Error('Missing response body for event stream');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let event: string | undefined;
  let data: string[] = [];
  let ended = false;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      ended = done;
      buffer += decoder.decode(value, { stream: !done });

      let start = 0;
      for (const match of buffer.matchAll(/\r\n|[\r\n]/g)) {
        const at = match.index!;
        if (!done && match[0] === '\r' && at === buffer.length - 1) break;
        const line = buffer.slice(start, at);
        start = at + match[0].length;

        if (!line) {
          const frame = data.length ? { event, data: data.join('\n') } : undefined;
          event = undefined;
          data = [];
          if (frame) yield frame;
          continue;
        }
        const colon = line.indexOf(':');
        const field = colon < 0 ? line : line.slice(0, colon);
        const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
        if (field === 'data') data.push(value);
        else if (field === 'event') event = value || undefined;
      }
      buffer = buffer.slice(start);
      if (done) return;
    }
  } finally {
    // [DONE], cancellation or a consumer error may stop before the HTTP EOF.
    if (!ended) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function readSSE<T = unknown>(
  response: Response,
  onEvent: (event: T) => void,
): Promise<void> {
  for await (const event of eventFrames(response)) {
    if (event.data === '[DONE]') return;
    let parsed: T;
    try {
      parsed = JSON.parse(event.data) as T;
    } catch {
      continue;
    }
    onEvent(parsed);
  }
}
