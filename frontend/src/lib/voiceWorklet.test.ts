import { expect, it } from 'vitest';
import workletSource from '../../public/voice-capture.worklet.js?raw';

it.each([16000, 44100, 48000])('preserves sample order in 20 ms worklet packets at %i Hz', rate => {
  const packets: Float32Array[] = [];
  let Processor: new () => { process(inputs: Float32Array[][]): boolean };
  // Execute the shipped worklet with a recording AudioWorkletProcessor fixture.
  new Function('AudioWorkletProcessor', 'registerProcessor', 'sampleRate', workletSource)(
    class { port = { postMessage: (samples: Float32Array) => packets.push(samples) }; },
    (_name: string, type: typeof Processor) => { Processor = type; },
    rate,
  );
  const capture = new Processor!();
  for (let block = 0; block < 40; block++) {
    expect(capture.process([[Float32Array.from({ length: 128 }, (_, i) => block * 128 + i)]])).toBe(true);
  }
  expect(packets.length).toBeGreaterThan(0);
  expect(packets[0].length).toBe(Math.round(rate * 0.02));
  const values = packets.flatMap(chunk => Array.from(chunk));
  expect(values).toEqual(Array.from({ length: values.length }, (_, i) => i));
});
