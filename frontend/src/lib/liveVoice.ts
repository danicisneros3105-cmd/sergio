// Voice mode in the browser, like ChatGPT's: the same real-time call the
// desktop app makes (/v1/live, Gemini Live on the server, the key never
// leaves it). The microphone goes up as 16 kHz PCM; Sergio's voice comes back
// as 24 kHz PCM and is played as it arrives.

import { getBase } from './api';
import { buildWsProtocols } from './useAgentEvents';

export const IN_RATE = 16000;
export const OUT_RATE = 24000;
export const SILENCE_AFTER = 0.4; // seconds of quiet before explicitly ending input
const VOICE_LEVEL = 0.012; // RMS that counts as speech (after the browser's noise suppression)
const PREROLL = 3; // buffers kept from just before you start talking
// While Sergio talks, his own voice coming back or people nearby must not cut
// him off: only a voice clearly louder than that, kept up for 200 ms, does.
export const BARGE_LEVEL = 0.05;
export const BARGE_CHUNKS = 10; // 20 ms each

export interface Barge {
  /** Consecutive loud chunks heard while Sergio talks. */
  run: number;
  /** Smoothed level of what is NOT a deliberate interruption (echo, room). */
  echo: number;
}

/** One 20 ms chunk while Sergio is talking: has the owner really started to talk over him? */
export function nextBarge(state: Barge, level: number): { voiced: boolean; state: Barge } {
  const bar = Math.max(BARGE_LEVEL, state.echo * 2.5);
  if (level > bar) {
    const run = state.run + 1;
    return { voiced: run >= BARGE_CHUNKS, state: { run, echo: state.echo } };
  }
  return { voiced: false, state: { run: 0, echo: 0.95 * state.echo + 0.05 * level } };
}

export function liveUrl(base: string, origin: string): string {
  const url = new URL('/v1/live', base || origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

/** Float samples at *from* Hz -> 16-bit PCM at *to* Hz (averaging, so no aliasing hiss). */
export function downsample(input: Float32Array, from: number, to = IN_RATE): Int16Array {
  const ratio = from / to;
  const length = Math.floor(input.length / ratio);
  const out = new Int16Array(length);
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    const v = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
    out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  return out;
}

/** 16-bit PCM bytes -> float samples (an odd trailing byte is dropped). */
export function pcmToFloat(bytes: ArrayBuffer): Float32Array {
  const view = new DataView(bytes);
  const n = Math.floor(bytes.byteLength / 2);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = view.getInt16(i * 2, true) / 0x8000;
  return out;
}

export function rms(samples: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / Math.max(1, samples.length));
}

export type VoiceState = 'connecting' | 'listening' | 'thinking' | 'speaking' | 'ended' | 'error';

export interface VoiceCallbacks {
  onState: (s: VoiceState) => void;
  onHeard: (text: string) => void; // what Sergio understood you said
  onSaid: (text: string) => void; // what Sergio is saying
  onLevel: (level: number) => void; // 0..1, for the orb
  onError: (message: string) => void;
  onScreen?: (sharing: boolean) => void;
  /** Server input-end to first audio forwarded; excludes device/network playback. */
  onLatency?: (serverMs: number) => void;
  /** A finished exchange: what you said and what Sergio answered. */
  onTurn?: (heard: string, said: string) => void;
  /** Another window took the conversation: do not reconnect by yourself. */
  onReplaced?: () => void;
}

/** One voice-mode call. `start()` asks for the microphone and connects. */
export class VoiceCall {
  private ws: WebSocket | null = null;
  private mic: MediaStream | null = null;
  private input: AudioContext | null = null;
  private output: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private screen: MediaStream | null = null;
  private screenTimer: ReturnType<typeof setInterval> | null = null;
  private playing: AudioBufferSourceNode[] = [];
  private playAt = 0;
  private lastVoice = 0;
  private gated = true;
  private preroll: Int16Array[] = [];
  private heard = '';
  private said = '';
  private stopped = false;
  private barge: Barge = { run: 0, echo: 0.02 };
  private suspended = false;
  muted = false;

  constructor(
    private cb: VoiceCallbacks,
    private language = 'es',
  ) {}

  async start(): Promise<void> {
    this.cb.onState('connecting');
    try {
      this.mic = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch {
      this.fail('Necesito permiso para el micrófono.');
      return;
    }
    if (this.stopped) {
      // Closed while the browser was asking for the microphone.
      this.mic.getTracks().forEach((t) => t.stop());
      this.mic = null;
      return;
    }
    const ws = new WebSocket(liveUrl(getBase(), window.location.origin), buildWsProtocols());
    ws.binaryType = 'arraybuffer';
    this.ws = ws;
    ws.onopen = () =>
      // «addressed»: he answers only what is for him (his name, or a reply right
      // after he spoke), never a video or the TV playing near the microphone.
      ws.send(JSON.stringify({ type: 'start', voice: '', name: 'Sergio', language: this.language, context: '', tools: [], attention: 'addressed' }));
    ws.onmessage = (e) => this.receive(e.data);
    ws.onerror = () => this.fail('Se cortó la conexión con Sergio.');
    ws.onclose = () => {
      if (this.ws) this.stop();
    };
  }

  private async listen(): Promise<void> {
    if (!this.mic) return;
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.input = new Ctx({ latencyHint: 'interactive' });
    this.output = new Ctx({ sampleRate: OUT_RATE, latencyHint: 'interactive' });
    const source = this.input.createMediaStreamSource(this.mic);
    const context = this.input;
    // A real file from the same origin: bundlers inline small scripts as
    // data: URLs, which the page's security policy refuses for worklets.
    await context.audioWorklet.addModule(new URL('voice-capture.worklet.js', document.baseURI).toString());
    if (this.stopped) return;
    this.node = new AudioWorkletNode(context, 'sergio-capture');
    await Promise.all([context.resume(), this.output.resume()]);
    const rate = this.input.sampleRate;
    this.node.port.onmessage = (e: MessageEvent<Float32Array>) => {
      if (this.stopped) return;
      const samples = e.data;
      const level = rms(samples);
      const speaking = this.playing.length > 0;
      if (!speaking) this.cb.onLevel(Math.min(1, level * 12));
      const pcm = downsample(samples, rate);
      const now = performance.now() / 1000;
      const deaf = this.muted || this.suspended;
      let voiced = level > VOICE_LEVEL;
      if (speaking) {
        const next = nextBarge(this.barge, level);
        this.barge = next.state;
        voiced = next.voiced;
      } else {
        this.barge.run = 0;
      }
      if (!deaf && voiced) this.lastVoice = now;
      const open = !deaf && now - this.lastVoice < SILENCE_AFTER;
      if (open) {
        if (this.gated) {
          this.gated = false;
          for (const chunk of this.preroll) this.send(chunk.buffer as ArrayBuffer);
          this.preroll = [];
        }
        this.send(pcm.buffer as ArrayBuffer);
      } else {
        if (!this.gated) {
          this.gated = true;
          this.send(JSON.stringify({ type: 'audio_end' })); // your turn is over
        }
        if (!deaf) {
          this.preroll.push(pcm);
          // While he talks, keep the start of a deliberate interruption too.
          if (this.preroll.length > PREROLL + (speaking ? BARGE_CHUNKS : 0)) this.preroll.shift();
        } else this.preroll = [];
      }
    };
    source.connect(this.node);
    this.node.connect(context.destination);
  }

  private send(data: ArrayBuffer | string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      if (this.ws.bufferedAmount > 256000) {
        this.fail('La conexión no envía el audio a tiempo. Vuelva a conectar.');
        return;
      }
      this.ws.send(data);
    }
  }

  private receive(data: ArrayBuffer | string): void {
    if (typeof data !== 'string') {
      this.play(pcmToFloat(data));
      return;
    }
    let event: { type?: string; text?: string; message?: string; status?: string; server_end_to_first_audio_ms?: number };
    try {
      event = JSON.parse(data);
    } catch {
      return;
    }
    switch (event.type) {
      case 'ready':
        void this.listen().then(() => {
          if (!this.stopped) this.cb.onState('listening');
        }).catch(() => this.fail('No pude iniciar el audio en tiempo real.'));
        break;
      case 'heard':
        this.heard += event.text || '';
        this.said = '';
        this.cb.onHeard(this.heard.trim());
        break;
      case 'said':
        this.said += event.text || '';
        this.cb.onSaid(this.said.trim());
        break;
      case 'replaced':
        this.stop(false);
        this.cb.onReplaced?.();
        break;
      case 'interrupted':
        this.hush();
        this.said = '';
        this.cb.onState('listening');
        break;
      case 'turn_complete':
        if (this.heard.trim() || this.said.trim()) this.cb.onTurn?.(this.heard.trim(), this.said.trim());
        this.heard = '';
        this.said = '';
        break;
      case 'tool':
        if (event.status === 'running') this.cb.onState('thinking');
        break;
      case 'error':
        this.fail(event.message || 'La llamada falló.');
        break;
      case 'latency':
        if (typeof event.server_end_to_first_audio_ms === 'number' &&
            Number.isFinite(event.server_end_to_first_audio_ms) && event.server_end_to_first_audio_ms >= 0) {
          this.cb.onLatency?.(event.server_end_to_first_audio_ms);
        }
        break;
    }
  }

  private play(samples: Float32Array): void {
    const out = this.output;
    if (!out || !samples.length) return;
    const buffer = out.createBuffer(1, samples.length, OUT_RATE);
    buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0);
    const src = out.createBufferSource();
    src.buffer = buffer;
    src.connect(out.destination);
    this.playAt = Math.max(out.currentTime + 0.02, this.playAt);
    if (this.playAt - out.currentTime > 12) {
      this.fail('La reproducción quedó atrasada. Vuelva a iniciar la conversación.');
      return;
    }
    src.start(this.playAt);
    this.playAt += buffer.duration;
    this.playing.push(src);
    this.cb.onState('speaking');
    this.cb.onLevel(Math.min(1, rms(samples) * 6));
    src.onended = () => {
      this.playing = this.playing.filter((s) => s !== src);
      if (!this.playing.length) this.cb.onState('listening');
    };
  }

  /** Stop his voice at once (you started talking over him). */
  private hush(): void {
    for (const s of this.playing) {
      try {
        s.stop();
      } catch {
        // already stopped
      }
    }
    this.playing = [];
    this.playAt = 0;
  }

  /** Context for the voice without a reply (e.g. what was written in the chat). */
  sendNote(text: string): void {
    if (text.trim()) this.send(JSON.stringify({ type: 'note', text }));
  }

  /** Something to tell Sergio that he should answer out loud. */
  sendText(text: string): void {
    if (text.trim()) this.send(JSON.stringify({ type: 'text', text }));
  }

  /** Browsers start audio suspended until a click: wake it on the next one. */
  resumeAudio(): void {
    void this.input?.resume().catch(() => {});
    void this.output?.resume().catch(() => {});
  }

  get open(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    if (muted) this.closeGate();
  }

  /** The microphone is deaf for a while without the owner muting it (another voice is playing). */
  setSuspended(suspended: boolean): void {
    this.suspended = suspended;
    if (suspended) this.closeGate();
  }

  private closeGate(): void {
    this.preroll = [];
    if (!this.gated) this.send(JSON.stringify({ type: 'audio_end' }));
    this.gated = true;
    this.lastVoice = -Infinity;
  }

  /** The browser chooser grants access; stopping revokes the tracks immediately. */
  async shareScreen(): Promise<void> {
    if (this.screen) {
      this.stopScreen();
      return;
    }
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    if (this.stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
    this.screen = stream;
    const video = document.createElement('video');
    video.srcObject = stream;
    video.muted = true;
    await video.play();
    if (this.stopped || this.screen !== stream) { stream.getTracks().forEach((t) => t.stop()); return; }
    const canvas = document.createElement('canvas');
    const draw = canvas.getContext('2d');
    stream.getVideoTracks()[0].onended = () => this.stopScreen();
    this.cb.onScreen?.(true);
    this.screenTimer = setInterval(() => {
      if (!draw || !video.videoWidth || this.ws?.readyState !== WebSocket.OPEN || this.ws.bufferedAmount > 8000) return;
      canvas.width = Math.min(1280, video.videoWidth);
      canvas.height = Math.round(video.videoHeight * canvas.width / video.videoWidth);
      draw.drawImage(video, 0, 0, canvas.width, canvas.height);
      // Screenshots remain ephemeral; a congested socket skips frames instead of queuing them.
      this.ws.send(JSON.stringify({ type: 'image', source: 'pantalla', mime: 'image/jpeg',
        data: canvas.toDataURL('image/jpeg', 0.65).split(',')[1] }));
    }, 1000);
  }

  private stopScreen(): void {
    if (this.screenTimer) clearInterval(this.screenTimer);
    this.screenTimer = null;
    this.screen?.getTracks().forEach((t) => t.stop());
    this.screen = null;
    this.cb.onScreen?.(false);
  }

  private fail(message: string): void {
    this.cb.onError(message);
    this.cb.onState('error');
    this.stop(false);
  }

  stop(announce = true): void {
    this.stopped = true;
    const ws = this.ws;
    this.ws = null;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'end' }));
    ws?.close();
    this.hush();
    this.stopScreen();
    this.node?.disconnect();
    this.mic?.getTracks().forEach((t) => t.stop());
    void this.input?.close().catch(() => {});
    void this.output?.close().catch(() => {});
    this.node = null;
    this.mic = null;
    this.input = null;
    this.output = null;
    if (announce) this.cb.onState('ended');
  }
}
