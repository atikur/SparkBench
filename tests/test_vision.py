"""Measurement safeguards; synthetic numbers here are not physical evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from sparkbench.vision import (compare, fit_threshold, geometry_valid, led_state,
                               oled_text, windows)


class VisionMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.expected = [{"step": 1, "red": True, "green": False, "oled_text": "TEST"}]
        self.window = {"step": 1, "start": 10, "end": 12,
                       "measurements": [{"file": "frame-%06d.jpg" % i,
                           "sample_pts_seconds": 10.2 + i*.35,
                           "red": True, "green": False, "oled_text": "TEST"}
                           for i in range(5)]}

    def test_calibration_has_separation_and_preserves_unknown_band(self):
        thresholds = fit_threshold([70, 80], [190, 200])
        self.assertFalse(led_state(80, thresholds))
        self.assertTrue(led_state(190, thresholds))
        self.assertIsNone(led_state(135, thresholds))
        for value in (None, True, float("nan"), float("inf"), -1, 256):
            self.assertIsNone(led_state(value, thresholds))

    def test_overlapping_or_insufficient_calibration_is_rejected(self):
        for off, on in (([80, 100], [90, 110]), ([80, 85], [90, 95]),
                        ([80], [190, 200]), ([70, True], [190, 200])):
            with self.assertRaises(ValueError):
                fit_threshold(off, on)

    def test_meta_reading_does_not_correct_answers_toward_expected_vocabulary(self):
        def reading(text):
            return {"meta_oled": {"source": "meta_api", "status": "read", "text": text}}
        self.assertEqual(oled_text(reading("  wrong   label ")), "WRONG LABEL")
        self.assertEqual(oled_text(reading("D4RK")), "D4RK")
        for row in ({}, {"ocr": [{"text": "TEST", "confidence": 1}]},
                    {"meta_oled": {"source": "meta_api", "status": "unknown", "text": "GUESS"}},
                    reading("")):
            self.assertIsNone(oled_text(row))

    def test_missing_or_shifted_border_is_unknown_geometry(self):
        geometry = {"minimum_border_support": .85}
        self.assertTrue(geometry_valid({"status": "measured", "oled_border_support": [1]*4}, geometry))
        for row in ({"status": "unknown"},
                    {"status": "measured", "oled_border_support": [1, 1, .4, 1]},
                    {"status": "measured", "oled_border_support": [1, 1, 1, float("nan")]}):
            self.assertFalse(geometry_valid(row, geometry))

    def test_all_settled_frames_must_match_not_just_majority(self):
        self.assertEqual(compare(self.expected, [self.window])["status"], "pass")
        self.window["measurements"][2]["red"] = False
        result = compare(self.expected, [self.window])
        self.assertEqual(result["status"], "fail")
        self.assertIn("red", result["failures"][0])

    def test_oled_mismatch_fails_and_missing_reading_is_incomplete(self):
        self.window["measurements"][2]["oled_text"] = "WRONG"
        self.assertEqual(compare(self.expected, [self.window])["status"], "fail")
        self.window["measurements"][2]["oled_text"] = None
        self.assertEqual(compare(self.expected, [self.window])["status"], "incomplete")

    def test_missing_samples_gaps_and_nonboolean_leds_cannot_pass(self):
        for change in ("missing", "gap", "nonboolean", "duplicate_time", "nan_time", "outside_window"):
            window = copy.deepcopy(self.window)
            if change == "missing":
                window["measurements"].pop()
            elif change == "gap":
                window["end"] = 15
            elif change == "nonboolean":
                window["measurements"][0]["green"] = 0
            elif change == "duplicate_time":
                window["measurements"][1]["sample_pts_seconds"] = window["measurements"][0]["sample_pts_seconds"]
            elif change == "nan_time":
                window["measurements"][0]["sample_pts_seconds"] = float("nan")
            else:
                window["measurements"][0]["sample_pts_seconds"] = 9
            self.assertEqual(compare(self.expected, [window])["status"], "incomplete")

    def test_empty_or_malformed_spec_cannot_manufacture_a_pass(self):
        for expected in ([], self.expected*2, [{"step": 1}],
                         [{"step": 1, "red": 1, "green": False, "oled_text": "TEST"}]):
            with self.assertRaises(ValueError):
                compare(expected, [])

    def test_step_marker_values_never_become_visual_measurements(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            # Deliberately wrong state/text in UART; only its time/ID is used.
            events = [
                {"kind": "rx_line", "host_uptime_seconds": 1, "line": "VISUAL_STEP:1 RED:1 GREEN:1 TEXT:OLD"},
                {"kind": "tx", "host_uptime_seconds": 9.9, "command": "VISUAL"},
                {"kind": "rx_line", "host_uptime_seconds": 10, "line": "VISUAL_STEP:1 RED:1 GREEN:1 TEXT:UNTRUSTED"},
                {"kind": "rx_line", "host_uptime_seconds": 13.1, "line": "VISUAL_STOPPED STATUS:COMPLETE RED:0 GREEN:0"}]
            (path / "uart.jsonl").write_text("\n".join(json.dumps(row) for row in events))
            frames = [{"file": "actual.jpg", "sample_pts_seconds": 11.5}]
            selected = windows(path, frames, [1])
            self.assertEqual(selected[0]["frames"], frames)
            self.assertNotIn("red", selected[0])
            self.assertNotIn("oled_text", selected[0])
            events.insert(3, {"kind": "rx_line", "line": "SPARKBENCH LED_OLED_TEST BOOT", "host_uptime_seconds": 11})
            (path / "uart.jsonl").write_text("\n".join(json.dumps(row) for row in events))
            with self.assertRaises(ValueError):
                windows(path, frames, [1])


if __name__ == "__main__":
    unittest.main()
