import copy
import json
import unittest
from pathlib import Path

from sparkbench.verify import verify_trace

ROOT = Path(__file__).resolve().parents[1]


class PhysicalAssertionTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "specs/behavior_a.json").read_text())
        self.trace = json.loads((ROOT / "examples/synthetic_behavior_a.json").read_text())

    def test_reference_measurements_pass_and_retain_synthetic_label(self):
        result = verify_trace(self.spec, self.trace)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reported_provenance"]["kind"], "synthetic")

    def test_led_swap_fails_leds_without_failing_angles(self):
        for row in self.trace["measurements"]:
            row["red"], row["green"] = row["green"], row["red"]
        result = verify_trace(self.spec, self.trace)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(len(result["failures"]), 14)
        self.assertFalse(any("angle" in failure for failure in result["failures"]))

    def test_stall_fails_position_without_diagnosing_a_cause(self):
        for row in self.trace["measurements"][3:]:
            row["angle_deg"] = 80
        result = verify_trace(self.spec, self.trace)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(len(result["failures"]), 4)
        self.assertTrue(all("angle" in failure for failure in result["failures"]))

    def test_missing_oled_reading_cannot_pass(self):
        self.trace["measurements"][0]["oled_text"] = None
        self.assertEqual(verify_trace(self.spec, self.trace)["status"], "incomplete")

    def test_nonfinite_or_boolean_angle_cannot_pass(self):
        for angle in (float("nan"), float("inf"), True):
            with self.subTest(angle=angle):
                trace = copy.deepcopy(self.trace)
                trace["measurements"][0]["angle_deg"] = angle
                self.assertEqual(verify_trace(self.spec, trace)["status"], "incomplete")

    def test_out_of_order_measurements_fail(self):
        self.trace["measurements"].reverse()
        self.assertEqual(verify_trace(self.spec, self.trace)["status"], "fail")

    def test_missing_step_cannot_pass(self):
        self.trace["measurements"].pop()
        self.assertNotEqual(verify_trace(self.spec, self.trace)["status"], "pass")

    def test_duplicate_measurement_rejected(self):
        self.trace["measurements"].append(self.trace["measurements"][0])
        with self.assertRaises(ValueError):
            verify_trace(self.spec, self.trace)

    def test_second_behavior_uses_same_engine(self):
        spec = json.loads((ROOT / "specs/behavior_b.json").read_text())
        trace = {"schema_version": 1, "provenance": {"kind": "synthetic"},
                 "measurements": [
                     {"step": 1, "angle_deg": 134, "red": True, "green": False, "oled_text": "HIGH"},
                     {"step": 2, "angle_deg": 91, "red": True, "green": True, "oled_text": "MID"},
                     {"step": 3, "angle_deg": 46, "red": False, "green": True, "oled_text": "LOW"},
                 ]}
        self.assertEqual(verify_trace(spec, trace)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
