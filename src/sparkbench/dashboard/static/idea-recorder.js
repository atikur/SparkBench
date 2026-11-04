/* Runs on the audio thread. Keep at most 30 seconds of mono samples. */
class IdeaRecorder extends AudioWorkletProcessor {
 constructor() {
  super();
  this.samples = new Float32Array(sampleRate * 30);
  this.offset = 0;
  this.port.onmessage = () => this.finish();
 }
 finish() {
  if (!this.samples) return;
  this.port.postMessage(this.samples.subarray(0, this.offset), [this.samples.buffer]);
  this.samples = null;
 }
 process(inputs) {
  if (!this.samples) return false;
  const channel = inputs[0]?.[0];
  if (!channel) return true;
  const count = Math.min(channel.length, this.samples.length - this.offset);
  this.samples.set(channel.subarray(0, count), this.offset);
  this.offset += count;
  if (this.offset === this.samples.length) this.finish();
  return Boolean(this.samples);
 }
}
registerProcessor('idea-recorder', IdeaRecorder);
