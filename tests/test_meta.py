"""No network: assert blindness, unknown handling and credential hygiene."""
import json
import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sparkbench.meta import Config, PROMPT, is_truncated, parse_reading, payload, read_label


class MetaReaderTests(unittest.TestCase):
    def test_request_has_no_expected_answers_or_uart_and_key_is_not_in_body(self):
        request = payload(b"image", "muse-spark-1.3")
        self.assertEqual(request["messages"][0]["content"][0]["text"], PROMPT)
        self.assertNotIn("enum", json.dumps(request["response_format"]))
        self.assertNotIn("Authorization", json.dumps(request))
        self.assertIn("base64,", request["messages"][0]["content"][1]["image_url"]["url"])

    def test_wrong_visible_text_is_retained_not_corrected(self):
        body = {"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"readable": True, "text": "D4RK"})}}]}
        self.assertEqual(parse_reading(body), ("D4RK", None))
        body["choices"][0]["finish_reason"] = "length"
        self.assertIsNone(parse_reading(body)[0])

    def test_unreadable_malformed_or_empty_text_is_unknown(self):
        for value in ({"readable": False, "text": None}, {"readable": True, "text": ""},
                      {"readable": 1, "text": "GUESS"}, {"text": "GUESS"}):
            body = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}
            self.assertIsNone(parse_reading(body)[0])
        self.assertIsNone(parse_reading({})[0])

    def test_retry_eligibility_is_truncation_never_wrong_or_unreadable_answer(self):
        self.assertTrue(is_truncated({"choices": [{"finish_reason": "length"}]}))
        for reason in ("stop", "content_filter", None):
            self.assertFalse(is_truncated({"choices": [{"finish_reason": reason}]}))
        self.assertFalse(is_truncated({}))

    def test_auth_failure_is_unknown_no_fallback_and_secret_not_written(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "crop.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
            response = Mock(status_code=401)
            response.json.return_value = {"error": {"message": "invalid private-test-key"}}
            post = Mock(return_value=response)
            result = read_label(image, Path(folder)/"result", Config("private-test-key"), post, prepare_image=False)
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["error"], "authentication_or_access")
            self.assertEqual(post.call_count, 1)
            self.assertFalse(post.call_args.kwargs["allow_redirects"])
            self.assertNotIn("private-test-key", repr(Config("private-test-key")))
            for path in (Path(folder)/"result").glob("*.json"):
                self.assertNotIn("private-test-key", path.read_text())

    def test_prepared_pixels_and_source_hash_are_auditable(self):
        with tempfile.TemporaryDirectory() as folder:
            source = b"\x89PNG\r\n\x1a\nsource"
            prepared = b"\x89PNG\r\n\x1a\ntrimmed"
            image = Path(folder)/"crop.png"
            image.write_bytes(source)
            def preparation(input_path, output_path):
                output_path.write_bytes(prepared)
                return {"pixel_operation": "rectangle crop only"}
            response = Mock(status_code=200)
            response.json.return_value = {"choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"readable": True, "text": "TEST"})}}]}
            post = Mock(return_value=response)
            with patch("sparkbench.meta.prepare_label", side_effect=preparation):
                result = read_label(image,Path(folder)/"result",Config("private-test-key"),post)
            url = post.call_args.kwargs["json"]["messages"][0]["content"][1]["image_url"]["url"]
            self.assertEqual(base64.b64decode(url.split(",",1)[1]), prepared)
            self.assertEqual(result["source_image_sha256"],hashlib.sha256(source).hexdigest())
            self.assertEqual(result["image_sha256"],hashlib.sha256(prepared).hexdigest())

    def test_preparation_failure_is_unknown_without_api_request(self):
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/"crop.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
            post=Mock()
            with patch("sparkbench.meta.prepare_label",side_effect=ValueError("invalid crop")):
                result=read_label(image,Path(folder)/"result",Config("private-test-key"),post)
            self.assertEqual(result["status"],"unknown")
            self.assertFalse(result["api_request_sent"])
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
