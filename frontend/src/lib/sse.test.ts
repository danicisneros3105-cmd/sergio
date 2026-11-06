import { afterEach, describe, expect, it, vi } from 'vitest';
import { IncompleteChatStreamError, readSSE, streamChat, streamResearch } from './sse';

function streamOf(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { headers: { 'content-type': 'text/event-stream' } });
}

describe('readSSE', () => {
  it('parses events split across chunks and skips bad ones', async () => {
    const seen: unknown[] = [];
    await readSSE(
      streamOf(['data: {"stage":"plan"}\n\nda', 'ta: {"stage":"call","n":1}\n\n', 'data: {oops}\n\n', 'data: {"stage":"answer"}\n\n']),
      (e) => seen.push(e),
    );
    expect(seen).toEqual([{ stage: 'plan' }, { stage: 'call', n: 1 }, { stage: 'answer' }]);
  });

  it('handles a split CRLF, comments and multiple data lines', async () => {
    const seen: unknown[] = [];
    await readSSE(streamOf([': ping\r\ndata:{\r', '\ndata: "value": 2}\r\n\r', '\n']), (e) => seen.push(e));
    expect(seen).toEqual([{ value: 2 }]);
  });

  it('does not swallow consumer errors', async () => {
    await expect(readSSE(streamOf(['data: {}\n\n']), () => {
      throw new Error('Consumer failed');
    })).rejects.toThrow('Consumer failed');
  });

  it('handles accents split inside a multi-byte character', async () => {
    const bytes = new TextEncoder().encode('data: {"answer":"llegó"}\n\n');
    const cut = bytes.length - 6;
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes.slice(0, cut));
        c.enqueue(bytes.slice(cut));
        c.close();
      },
    });
    const seen: { answer: string }[] = [];
    await readSSE<{ answer: string }>(new Response(body), (e) => seen.push(e));
    expect(seen[0].answer).toBe('llegó');
  });
});


describe('streamChat', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('signals an interrupted answer instead of reporting completion', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamOf(['data: {"text":"parcial"}\n\n'])));
    const stream = streamChat({ model: 'test', messages: [], stream: true });
    await expect(stream.next()).resolves.toMatchObject({ value: { data: '{"text":"parcial"}' }, done: false });
    await expect(stream.next()).rejects.toBeInstanceOf(IncompleteChatStreamError);
  });

  it('keeps the event type across chunks and accepts CRLF framing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamOf([
      'event: phase\n', 'data: {"x":1}\n\n',
      'event: token\r\n', 'data: {"text":"ho', 'la"}\r\n\r\n', 'data: [DONE]\r\n\r\n',
    ])));
    const seen = [];
    for await (const event of streamChat({ model: 'test', messages: [], stream: true })) seen.push(event);
    expect(seen).toEqual([{ event: 'phase', data: '{"x":1}' }, { event: 'token', data: '{"text":"hola"}' }]);
  });
});

describe('streamResearch', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('reads CRLF events and stops at completion', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamOf([
      'data: null\r\n\r\ndata:{"type":"done"}\r', '\n\r\ndata: {"type":"extra"}\n\n',
    ])));
    const seen = [];
    for await (const event of streamResearch('prueba')) seen.push(event);
    expect(seen).toEqual([{ type: 'done' }]);
  });
});
