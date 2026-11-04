'use strict';

{
 const button = $('idea-voice'), discard = $('idea-voice-cancel');
 const status = $('idea-voice-status'), idea = $('home-idea');
 let current = null;

 function say(message) {
  status.textContent = message;
  status.hidden = !message;
 }

 function controls(label = 'Record idea', busy = false) {
  button.textContent = label;
  button.disabled = busy;
  discard.hidden = !current || current.uploading;
 }

 function release(run) {
  clearTimeout(run.timeout);
  run.stream?.getTracks().forEach(track => track.stop());
  run.node?.port.close();
  if (run.context && run.context.state !== 'closed') run.context.close().catch(() => {});
  run.context = run.stream = run.node = null;
 }

 function reset(message = '') {
  const run = current;
  current = null;
  if (run) {
   release(run);
   run.abort?.abort();
  }
  controls();
  say(message);
 }

 function wav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
  const tag = (offset, value) => [...value].forEach((letter, i) => view.setUint8(offset + i, letter.charCodeAt(0)));
  tag(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); tag(8, 'WAVE');
  tag(12, 'fmt '); view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  tag(36, 'data'); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
   const s = Math.max(-1, Math.min(1, samples[i]));
   view.setInt16(44 + i * 2, s * (s < 0 ? 32768 : 32767), true);
  }
  return buffer;
 }

 async function transcribe(run) {
  if (!run.samples?.length) return reset('No audio was recorded. Try again or type your idea.');
  run.abort = new AbortController();
  run.uploading = true;
  controls('Transcribing…', true);
  say('Muse Voice is transcribing your recording.');
  try {
   const response = await fetch('/api/idea/transcribe', {
    method: 'POST',
    headers: {'Content-Type': 'audio/wav', 'X-SparkBench-Session': plannerSession.session_token},
    body: wav(run.samples, run.rate), signal: run.abort.signal
   });
   const result = await response.json();
   if (run !== current) return;
   if (!response.ok) throw new Error(result.error || 'Could not transcribe this recording.');
   const draft = idea.value.trimEnd();
   const prefix = draft ? draft + ' ' : '';
   const remaining = idea.maxLength - prefix.length;
   if (remaining <= 0) return reset('The idea box is full. Shorten your draft before adding a recording.');
   idea.value = prefix + result.transcript.slice(0, remaining);
   reset(result.transcript.length > remaining ? 'Added as much of the transcript as fits. Review your idea.' :
    'Transcript added. Review or edit your idea before planning.');
   idea.focus();
  } catch (error) {
   if (run === current) reset(error.message || 'Could not transcribe this recording.');
  }
 }

 async function record() {
  if (!plannerSession?.planning_available) return say('Connect the Meta API to record an idea, or type it here.');
  const run = current = {};
  controls('Opening microphone…', true);
  say('Allow microphone access to describe your project.');
  try {
   const context = run.context = new AudioContext({sampleRate: 24000});
   await context.resume();
   if (run !== current) return;
   const stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1}});
   if (run !== current) {
    stream.getTracks().forEach(track => track.stop());
    return;
   }
   run.stream = stream;
   run.rate = context.sampleRate;
   if (![16000, 24000].includes(run.rate)) throw new Error('This browser could not record at a supported sample rate.');
   await context.audioWorklet.addModule('/idea-recorder.js');
   if (run !== current) return;
   const recorder = run.node = new AudioWorkletNode(context, 'idea-recorder', {channelCount: 1});
   recorder.port.onmessage = ({data}) => {
    if (run !== current) return;
    run.samples = data;
    release(run);
    if (run.send) transcribe(run);
    else {
     controls('Transcribe recording');
     say('Reached the 30-second limit. Transcribe or discard this recording.');
    }
   };
   for (const track of stream.getAudioTracks()) track.addEventListener('ended', () => {
    if (run === current && run.stream) reset('The microphone disconnected. Try again or type your idea.');
   });
   context.createMediaStreamSource(stream).connect(recorder).connect(context.destination);
   run.timeout = setTimeout(() => reset('Recording did not finish. Try again or type your idea.'), 32000);
   controls('Stop and transcribe');
   say('Recording up to 30 seconds. Stop and transcribe sends the clip to Meta.');
  } catch (error) {
   if (run === current) reset(error.name === 'NotAllowedError' ?
    'Microphone access was denied. Allow it in the browser or type your idea.' :
    'Could not start recording. Check your microphone or type your idea.');
  }
 }

 if (navigator.mediaDevices?.getUserMedia && window.AudioContext && window.AudioWorkletNode) {
  button.hidden = $('idea-voice-help').hidden = false;
  button.addEventListener('click', () => {
   if (!current) return record();
   if (current.samples) return transcribe(current);
   if (!current.node) return;
   current.send = true;
   controls('Stopping…', true);
   clearTimeout(current.timeout);
   current.timeout = setTimeout(() => reset('Could not finish recording. Try again or type your idea.'), 2000);
   current.node.port.postMessage('stop');
  });
  discard.addEventListener('click', () => reset('Recording discarded.'));
  window.cancelIdeaVoice = () => reset();
  window.addEventListener('pagehide', () => reset());
 }
}
