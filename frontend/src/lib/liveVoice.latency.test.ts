// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { VoiceCall } from './liveVoice';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('streams 20 ms microphone chunks, ends silence promptly and cancels playback', async () => {
  let now = 1000;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const sockets: Socket[] = [];
  class Socket {
    static OPEN = 1;
    readyState = 1;
    bufferedAmount = 0;
    sent: (string | ArrayBuffer)[] = [];
    onopen: (() => void) | null = null;
    onmessage: ((e: { data: string | ArrayBuffer }) => void) | null = null;
    constructor() { sockets.push(this); }
    send(data: string | ArrayBuffer) { this.sent.push(data); }
    close() {}
  }
  const worklets: Worklet[] = [];
  class Worklet {
    port: { onmessage: ((e: { data: Float32Array }) => void) | null } = { onmessage: null };
    constructor() { worklets.push(this); }
    connect() {}
    disconnect() {}
  }
  const stopVoice = vi.fn();
  const contexts: unknown[] = [];
  class Audio {
    sampleRate = 48000;
    currentTime = 0;
    destination = {};
    audioWorklet = { addModule: async () => {} };
    constructor(options: unknown) { contexts.push(options); }
    createMediaStreamSource() { return { connect() {} }; }
    resume() { return Promise.resolve(); }
    close() { return Promise.resolve(); }
    createBuffer(_channels: number, length: number, rate: number) {
      return { copyToChannel() {}, duration: length / rate };
    }
    createBufferSource() { return { connect() {}, start() {}, stop: stopVoice }; }
  }
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('AudioContext', Audio);
  vi.stubGlobal('AudioWorkletNode', Worklet);
  const stopMic = vi.fn();
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
    getUserMedia: async () => ({ getTracks: () => [{ stop: stopMic }] }),
  } });
  const latency = vi.fn();
  const call = new VoiceCall({ onState: vi.fn(), onHeard: vi.fn(), onSaid: vi.fn(),
    onLevel: vi.fn(), onError: vi.fn(), onLatency: latency });
  try {
    await call.start();
    const ws = sockets[0];
    ws.onopen?.();
    ws.onmessage?.({ data: JSON.stringify({ type: 'ready' }) });
    await vi.waitFor(() => expect(worklets[0]?.port.onmessage).toBeTypeOf('function'));
    expect(contexts).toEqual([{ latencyHint: 'interactive' }, { sampleRate: 24000, latencyHint: 'interactive' }]);
    const feed = (value: number) => worklets[0].port.onmessage?.({ data: new Float32Array(960).fill(value) });
    feed(0.1);
    now = 1390; feed(0);
    expect(ws.sent.filter(x => typeof x === 'string' && x.includes('audio_end'))).toHaveLength(0);
    now = 1420; feed(0);
    now = 1450; feed(0);
    expect(ws.sent.filter(x => typeof x === 'string' && x.includes('audio_end'))).toHaveLength(1);
    expect(ws.sent.filter(x => x instanceof ArrayBuffer).map(x => x.byteLength)).toEqual([640, 640]);
    ws.onmessage?.({ data: new ArrayBuffer(960) });
    ws.onmessage?.({ data: JSON.stringify({ type: 'interrupted' }) });
    expect(stopVoice).toHaveBeenCalledOnce();
    ws.onmessage?.({ data: JSON.stringify({ type: 'latency', server_end_to_first_audio_ms: 85 }) });
    expect(latency).toHaveBeenCalledWith(85);
  } finally { call.stop(); }
  expect(stopMic).toHaveBeenCalledOnce();
});
