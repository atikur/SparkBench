"""Transcribe a short idea recording without persisting its audio."""
import io
import json
import wave

from .meta import BASE_URL, configuration

VOICE_MODEL = "muse-voice-transcribe-1.0"
MAX_VOICE_SECONDS = 30
MAX_VOICE_BYTES = 44 + 24_000 * 2 * MAX_VOICE_SECONDS


class VoiceServiceError(Exception):
    pass


def transcribe_idea(audio, *, config=None, post=None):
    import requests

    if not 44 < len(audio) <= MAX_VOICE_BYTES:
        raise ValueError("Record an idea of up to 30 seconds.")
    try:
        with wave.open(io.BytesIO(audio), "rb") as recording:
            frames, rate = recording.getnframes(), recording.getframerate()
            if (recording.getnchannels() != 1 or recording.getsampwidth() != 2
                    or rate not in (16_000, 24_000)
                    or not 0 < frames <= rate * MAX_VOICE_SECONDS
                    or len(recording.readframes(frames)) != frames * 2):
                raise ValueError("Record a complete mono WAV clip of up to 30 seconds.")
    except (wave.Error, EOFError) as exc:
        raise ValueError("The recording is not a readable WAV clip.") from exc

    config = config or configuration()
    settings = {"model": VOICE_MODEL, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK",
                "keywords": ["ESP32", "GPIO", "LED", "OLED", "SparkBench"]}
    try:
        reply = (post or requests.post)(
            BASE_URL + "/asr/transcribe",
            headers={"Authorization": "Bearer " + config.api_key, "Accept": "application/json"},
            files={"request": (None, json.dumps(settings), "application/json"),
                   "audio": ("idea.wav", audio, "audio/wav")},
            timeout=(5, 30), allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise VoiceServiceError("Could not reach Muse Voice. Try again or type your idea.") from exc
    if reply.status_code != 200:
        raise VoiceServiceError(f"Muse Voice could not transcribe this clip (HTTP {reply.status_code}).")
    try:
        transcript = reply.json()["transcript"]
    except (ValueError, KeyError, TypeError) as exc:
        raise VoiceServiceError("Muse Voice did not return a transcript.") from exc
    if not isinstance(transcript, str) or not transcript.strip():
        raise VoiceServiceError("No speech was transcribed. Try again or type your idea.")
    return {"transcript": transcript.strip(), "model": VOICE_MODEL}
