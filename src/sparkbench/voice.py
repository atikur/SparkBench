"""Transcribe a short idea recording. The audio is never stored; the request, its settings and the
reply are, like every other Meta request, so the record can be inspected later."""
import hashlib
import io
import json
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

from .meta import BASE_URL, configuration

VOICE_MODEL = "muse-voice-transcribe-1.0"
MAX_VOICE_SECONDS = 30
MAX_VOICE_BYTES = 44 + 24_000 * 2 * MAX_VOICE_SECONDS


class VoiceServiceError(Exception):
    pass


def transcribe_idea(audio, *, config=None, post=None, output=None):
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
                "keywords": ["ESP32", "GPIO", "LED", "OLED", "SparkBench", "READY", "BUSY", "DONE", "START", "STOP", "GO", "WAIT"]}
    record = {"schema_version": 1, "model": VOICE_MODEL, "endpoint": BASE_URL + "/asr/transcribe", "settings": settings,
              "audio_bytes": len(audio), "audio_sha256": hashlib.sha256(audio).hexdigest(), "audio_stored": False,
              "started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "error", "transcript": None, "error": None}
    start = time.monotonic()
    try:
        return _transcribe(audio, config, settings, post, requests, record)
    finally:
        record["latency_seconds"] = round(time.monotonic() - start, 3)
        if output is not None:
            folder = Path(output)
            folder.mkdir(parents=True, exist_ok=False)
            (folder / "record.json").write_text(json.dumps(record, indent=2) + "\n")


def _transcribe(audio, config, settings, post, requests, record):
    try:
        reply = (post or requests.post)(
            BASE_URL + "/asr/transcribe",
            headers={"Authorization": "Bearer " + config.api_key, "Accept": "application/json"},
            files={"request": (None, json.dumps(settings), "application/json"),
                   "audio": ("idea.wav", audio, "audio/wav")},
            timeout=(5, 30), allow_redirects=False,
        )
    except requests.RequestException as exc:
        record["error"] = "connection"
        raise VoiceServiceError("Could not reach Muse Voice. Try again or type your idea.") from exc
    record["http_status"] = reply.status_code
    if reply.status_code != 200:
        record["error"] = "http_%s" % reply.status_code
        raise VoiceServiceError(f"Muse Voice could not transcribe this clip (HTTP {reply.status_code}).")
    try:
        transcript = reply.json()["transcript"]
    except (ValueError, KeyError, TypeError) as exc:
        record["error"] = "malformed_response"
        raise VoiceServiceError("Muse Voice did not return a transcript.") from exc
    if not isinstance(transcript, str) or not transcript.strip():
        record["error"] = "no_speech"
        raise VoiceServiceError("No speech was transcribed. Try again or type your idea.")
    # The service sometimes ends a sentence with an ideographic full stop; keep the text as typed English.
    text = " ".join(transcript.replace("\u3002", ".").replace("\uff0c", ",").split())
    record.update(status="transcribed", transcript=text)
    return {"transcript": text, "model": VOICE_MODEL}
