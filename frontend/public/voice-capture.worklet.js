// Capture on the audio rendering thread. The main UI never supplies PCM timing.
class SergioCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunkSize = Math.max(1, Math.round(sampleRate * 0.02));
    this.samples = new Float32Array(this.chunkSize);
    this.used = 0;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (input) {
      for (let i = 0; i < input.length; i++) {
        this.samples[this.used++] = input[i];
        if (this.used === this.samples.length) {
          this.port.postMessage(this.samples, [this.samples.buffer]);
          this.samples = new Float32Array(this.chunkSize);
          this.used = 0;
        }
      }
    }
    return true; // output stays silent: no microphone echo
  }
}
registerProcessor('sergio-capture', SergioCapture);
