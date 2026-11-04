import io
import json
import unittest
import wave
from unittest.mock import Mock

from sparkbench.meta import Config
from sparkbench.voice import VoiceServiceError, transcribe_idea


def recording(frames=2400, rate=24000, channels=1):
    output = io.BytesIO()
    with wave.open(output, "wb") as clip:
        clip.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        clip.writeframes(bytes(frames * channels * 2))
    return output.getvalue()


class IdeaVoiceTests(unittest.TestCase):
    def test_sends_wav_with_voice_model_and_returns_only_transcript(self):
        audio = recording()
        reply = Mock(status_code=200)
        reply.json.return_value = {"transcript": "  Make the green LED blink.  ", "sessionId": "internal"}
        post = Mock(return_value=reply)
        result = transcribe_idea(audio, config=Config("fixture"), post=post)
        self.assertEqual(result, {"transcript": "Make the green LED blink.",
                                  "model": "muse-voice-transcribe-1.0"})
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.meta.ai/v1/asr/transcribe")
        self.assertEqual(kwargs["files"]["audio"][1], audio)
        self.assertEqual(json.loads(kwargs["files"]["request"][1])["model"], result["model"])
        self.assertFalse(kwargs["allow_redirects"])

    def test_bad_or_oversized_audio_never_reaches_meta(self):
        post = Mock()
        for audio in (b"not a wav" * 6, recording()[:-2], recording(rate=44100),
                      recording(channels=2), recording(frames=16000 * 30 + 1, rate=16000)):
            with self.subTest(size=len(audio)), self.assertRaises(ValueError):
                transcribe_idea(audio, config=Config("fixture"), post=post)
        post.assert_not_called()

    def test_blank_transcript_and_provider_errors_do_not_return_a_draft(self):
        for status in (200, 403, 429):
            reply = Mock(status_code=status)
            reply.json.return_value = {"transcript": " "}
            with self.subTest(status=status), self.assertRaises(VoiceServiceError):
                transcribe_idea(recording(), config=Config("fixture"), post=Mock(return_value=reply))
