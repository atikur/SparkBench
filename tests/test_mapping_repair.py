"""Synthetic probe fixtures and mocked Meta replies; no model or hardware proof."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from sparkbench.discovery import PHASES, infer
from sparkbench.mapping_repair import propose_mapping, verified_mapping
from sparkbench.meta import Config


NORMAL = {"red": 25, "green": 26}
SWAPPED = {"red": 26, "green": 25}


def discovery(mapping=SWAPPED):
    """Synthetic stand-in for a validated capture; integration validates provenance."""
    windows = []
    for phase, pin in enumerate(PHASES, 1):
        start = 100.0 + phase * 3
        rows = []
        for offset in range(5):
            index = (phase - 1) * 5 + offset + 1
            name = "frame-%06d.jpg" % index
            rows.append({"file": name, "sha256": hashlib.sha256(name.encode()).hexdigest(),
                         "sample_pts_seconds": start + offset * .5,
                         "red": pin == mapping["red"], "green": pin == mapping["green"]})
        windows.append({"step": phase, "start": start, "end": start + 2,
                        "measurements": rows})
    return {**infer(windows, "saved_live_camera_frames"), "windows": windows,
            "source_run": "/private/experiment/hidden-swapped-answer",
            "title": "Deliberately swapped", "fault_test": True}


def reply(mapping=SWAPPED):
    return {"mapping": dict(mapping),
            "explanation": "The measured green LED responds to GPIO25 and red responds to GPIO26. The off baseline is dark. This proposes a mapping correction; approval and a new camera test are still required.",
            "evidence": ["frame-000001.jpg", "frame-000006.jpg", "frame-000016.jpg"]}


def response(value=None, *, status=200, finish="stop", refusal=None):
    return Mock(status_code=status, json=Mock(return_value={
        "choices": [{"finish_reason": finish, "message": {
            "content": json.dumps(value if value is not None else reply()), "refusal": refusal}}],
        "usage": {"prompt_tokens": 300, "completion_tokens": 100, "total_tokens": 400}}))


class EvidenceTests(unittest.TestCase):
    def test_complete_observations_support_either_mapping_without_modifying_input(self):
        for mapping in (NORMAL, SWAPPED):
            record = discovery(mapping); before = copy.deepcopy(record)
            self.assertEqual(verified_mapping(record), mapping)
            self.assertEqual(record, before)

    def test_saved_mapping_cannot_override_the_measured_response(self):
        record = discovery()
        record["mapping"] = NORMAL
        with self.assertRaisesRegex(ValueError, "not supported"):
            verified_mapping(record)

    def test_uncertain_missing_multiple_or_unsettled_outputs_are_rejected(self):
        changes = [(1, "red", None), (1, "green", False), (1, "red", True), (0, "red", True)]
        for phase, key, value in changes:
            with self.subTest(phase=phase, key=key, value=value):
                record = discovery()
                for row in record["windows"][phase]["measurements"]:
                    row[key] = value
                with self.assertRaises(ValueError): verified_mapping(record)

    def test_synthetic_label_unknowns_and_unsupported_pins_are_rejected(self):
        changes = [("source", "synthetic"), ("status", "incomplete"),
                   ("automatic_camera_mapping", False), ("unknowns", ["missing"]),
                   ("servo_actuation", True), ("approved_gpio", [25, 27]),
                   ("mapping", {"red": 25, "green": 27})]
        for key, value in changes:
            with self.subTest(key=key):
                record = discovery(); record[key] = value
                with self.assertRaises(ValueError): verified_mapping(record)

    def test_missing_duplicate_unsafe_or_unhashed_frame_references_are_rejected(self):
        for change in ("duplicate", "unsafe", "hash", "missing", "phase"):
            with self.subTest(change=change):
                record = discovery(); windows = record["windows"]
                if change == "duplicate": windows[1]["measurements"][0]["file"] = windows[0]["measurements"][0]["file"]
                elif change == "unsafe": windows[0]["measurements"][0]["file"] = "../frame-000001.jpg"
                elif change == "hash": windows[0]["measurements"][0]["sha256"] = "not-a-hash"
                elif change == "missing": windows[1]["measurements"].pop()
                else: windows[1]["step"] = 1
                with self.assertRaises(ValueError): verified_mapping(record)

    def test_overlapping_phases_gaps_and_malformed_timestamps_are_rejected(self):
        for change in ("overlap", "gap", "nan", "text"):
            with self.subTest(change=change):
                record = discovery(); windows = record["windows"]
                if change == "overlap": windows[1]["start"] = windows[0]["end"]
                elif change == "gap": windows[1]["measurements"][2]["sample_pts_seconds"] += .4
                elif change == "nan": windows[0]["measurements"][0]["sample_pts_seconds"] = float("nan")
                else: windows[1]["start"] = "not-a-time"
                with self.assertRaises(ValueError): verified_mapping(record)


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config("private-mapping-key", "muse-spark-1.3-contributor")

    def tearDown(self): self.temp.cleanup()

    def propose(self, *, record=None, value=None, post=None, output="proposal", **kwargs):
        post = post if post is not None else Mock(return_value=response(value))
        result = propose_mapping(NORMAL, record if record is not None else discovery(), self.root / output,
                                 config=self.config, post=post, **kwargs)
        return result, post

    def test_matching_proposal_is_unapproved_unverified_and_saved_with_checksums(self):
        result, post = self.propose()
        self.assertEqual(result["status"], "proposed")
        self.assertEqual(result["mapping"], SWAPPED)
        self.assertTrue(result["approval_required"])
        self.assertEqual(result["hardware_actions"], [])
        self.assertEqual(result["physical_verification"], "not_performed")
        self.assertEqual(result["api_requests"], 1)
        self.assertEqual(result["usage"]["total_tokens"], 400)
        self.assertGreaterEqual(result["latency_seconds"], 0)
        self.assertIn("ended_at_utc", result)
        post.assert_called_once()
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 90))
        out = self.root / "proposal"
        manifest = json.loads((out / "integrity.json").read_text())["sha256"]
        self.assertEqual(set(manifest), {"result.json", "request.json", "response.json", "evidence.json"})
        for name, sha in manifest.items():
            self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), sha)
            self.assertNotIn(self.config.api_key, (out / name).read_text())

    def test_model_receives_measurements_and_assumption_without_inferred_answer_or_fault_label(self):
        _, post = self.propose()
        request = post.call_args.kwargs["json"]
        packet = json.loads(request["messages"][1]["content"])
        self.assertEqual(packet["current_firmware_assumption"], NORMAL)
        self.assertEqual([p["energized_gpio"] for p in packet["phases"]], list(PHASES))
        self.assertEqual(packet["phases"][1]["measurements"][0]["green"], True)
        text = json.dumps(packet)
        for hidden in ("hidden-swapped-answer", "Deliberately", "fault_test", "source_run", '"mapping"', "threshold", "unknowns"):
            self.assertNotIn(hidden, text)
        self.assertEqual(request["model"], self.config.model)
        self.assertTrue(request["response_format"]["json_schema"]["strict"])

    def test_unchanged_observed_mapping_returns_no_change(self):
        result, _ = self.propose(record=discovery(NORMAL), value=reply(NORMAL))
        self.assertEqual(result["status"], "no_change")
        self.assertEqual(result["mapping"], NORMAL)

    def test_incomplete_evidence_sends_no_request_and_needs_no_credentials(self):
        record = discovery(); record["windows"][1]["measurements"][0]["red"] = None
        post = Mock()
        with patch("sparkbench.mapping_repair.configuration", side_effect=AssertionError("must not request credentials")):
            result = propose_mapping(NORMAL, record, self.root / "incomplete", post=post)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["api_requests"], 0)
        self.assertIsNone(result["mapping"])
        post.assert_not_called()
        self.assertFalse((self.root / "incomplete/request.json").exists())

    def test_wrong_mapping_unapproved_pin_and_extra_behavior_fields_are_rejected(self):
        invalid = [reply(NORMAL), reply({"red": 25, "green": 27}),
                   reply({"red": 25, "green": 25}), {**reply(), "steps": []}]
        for i, value in enumerate(invalid):
            with self.subTest(i=i):
                result, post = self.propose(value=value, output="invalid-%d" % i)
                self.assertEqual(result["status"], "invalid_response")
                self.assertIsNone(result["mapping"])
                self.assertEqual(result["evidence"], [])
                post.assert_called_once()

    def test_citations_must_include_both_active_phases_and_off_baseline(self):
        invalid = [[], ["frame-999999.jpg", "frame-000006.jpg", "frame-000016.jpg"],
                   ["frame-000001.jpg", "frame-000002.jpg", "frame-000016.jpg"],
                   ["frame-000006.jpg", "frame-000007.jpg", "frame-000016.jpg"],
                   ["frame-000001.jpg", "frame-000006.jpg", "frame-000006.jpg"],
                   ["frame-000001.jpg says dark", "frame-000006.jpg", "frame-000016.jpg"]]
        for i, refs in enumerate(invalid):
            result, _ = self.propose(value={**reply(), "evidence": refs}, output="refs-%d" % i)
            self.assertEqual(result["status"], "invalid_response")
            self.assertIsNone(result["mapping"])

    def test_http_failures_refusals_and_truncation_never_retry(self):
        for i, resp in enumerate([response(status=429), response(status=503),
                                  response(finish="length"), response(refusal="Cannot answer")]):
            result, post = self.propose(post=Mock(return_value=resp), output="failure-%d" % i)
            self.assertIn(result["status"], ("error", "invalid_response"))
            self.assertIsNone(result["mapping"])
            post.assert_called_once()

    def test_network_error_does_not_serialize_exception_or_retry(self):
        result, post = self.propose(post=Mock(side_effect=requests.Timeout("private-mapping-key in URL")))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["api_requests"], 1)
        self.assertNotIn("private-mapping-key", json.dumps(result))
        post.assert_called_once()

    def test_response_credentials_are_redacted_before_persistence(self):
        result, _ = self.propose(value={**reply(), "explanation": "Response echoed private-mapping-key"})
        self.assertEqual(result["status"], "proposed")
        self.assertIn("[REDACTED]", result["explanation"])
        for file in (self.root / "proposal").glob("*.json"):
            self.assertNotIn("private-mapping-key", file.read_text())

    def test_other_provider_configuration_is_rejected_without_network(self):
        post = Mock()
        result = propose_mapping(NORMAL, discovery(), self.root / "other-model",
                                 config=Config("key", "other-model"), post=post)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["api_requests"], 0)
        post.assert_not_called()

    def test_malformed_response_never_creates_a_proposal(self):
        for i, body in enumerate([None, [], {"choices": []}, {"choices": [{}]}, {"usage": float("nan")} ]):
            post = Mock(return_value=Mock(status_code=200, json=Mock(return_value=body)))
            result, _ = self.propose(post=post, output="malformed-%d" % i)
            self.assertEqual(result["status"], "invalid_response")
            self.assertIsNone(result["mapping"])


if __name__ == "__main__": unittest.main()
