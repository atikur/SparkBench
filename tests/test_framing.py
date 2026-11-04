"""Mocked Meta responses for the camera frame check; these are not model or physical results."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from sparkbench.framing import inspect_frame, validate_reply
from sparkbench.meta import Config

JPEG = b"\xff\xd8\xffsynthetic"
REPLY = {"oled": "partly_visible", "red_led": "fully_visible", "green_led": "not_visible", "oled_legible": False, "fix": "Tilt the phone down."}


def response(value=REPLY, status=200, finish="stop"):
    return Mock(status_code=status, json=Mock(return_value={"choices": [{"finish_reason": finish, "message": {"content": json.dumps(value)}}], "usage": {"total_tokens": 10}}))


class FramingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.out = Path(self.temp.name) / "out"
        self.config = Config("private-key", "muse-spark-1.3-contributor")
    def tearDown(self): self.temp.cleanup()

    def test_one_request_keeps_audit_without_image_bytes_or_key(self):
        post = Mock(return_value=response())
        result = inspect_frame(JPEG, JPEG, self.out, config=self.config, post=post)
        self.assertEqual((result["status"], result["inspection"]["oled"], result["advisory"]), ("inspected", "partly_visible", True))
        post.assert_called_once()
        saved = (self.out / "request.json").read_text()
        self.assertNotIn("private-key", saved); self.assertNotIn("base64,", saved)

    def test_invalid_refused_or_failed_replies_give_no_inspection_and_no_retry(self):
        cases = [response({**REPLY, "oled": "maybe"}), response({**REPLY, "passed": True}), response(finish="length"), response(status=500)]
        for i, reply in enumerate(cases):
            post = Mock(return_value=reply)
            result = inspect_frame(JPEG, JPEG, self.out / str(i), config=self.config, post=post)
            self.assertIsNone(result["inspection"]); post.assert_called_once()

    def test_reply_and_image_limits(self):
        with self.assertRaises(ValueError): validate_reply({**REPLY, "oled_legible": "no"})
        with self.assertRaises(ValueError): validate_reply({**REPLY, "fix": " "})
        with self.assertRaises(ValueError): inspect_frame(b"not a jpeg", JPEG, self.out, config=self.config, post=Mock())


if __name__ == "__main__":
    unittest.main()
