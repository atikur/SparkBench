"""Synthetic regressions for fault timing and unknown-preserving camera checks."""
import unittest

from sparkbench.qualification import evaluate
from sparkbench.runtime_io import acquire
from sparkbench.workflow import require_coverage
from unittest.mock import patch


def fixture(case):
    trigger = 13.6 if case == "lease" else 14.9
    end = 15.0 if case == "lease" else 15.05
    rows = [{"kind":"tx", "command":"DISCOVER", "host_uptime_seconds":10.0},
            {"kind":"rx_line", "line":"VISUAL_STEP:2 RED:1 GREEN:0 TEXT:P25 UPTIME_MS:1", "host_uptime_seconds":13.0},
            {"kind":"tx", "command":"PING", "host_uptime_seconds":13.4 if case == "lease" else 14.8},
            {"kind":"fault_trigger", "case":case, "host_uptime_seconds":trigger}]
    if case == "stop": rows.append({"kind":"tx", "command":"STOP", "host_uptime_seconds":trigger})
    rows.append({"kind":"rx_line", "line":"VISUAL_STOPPED STATUS:"+("LEASE_EXPIRED" if case == "lease" else "STOPPED")+" RED:0 GREEN:0", "host_uptime_seconds":end})
    frames = [{"file":f"frame-{i:06d}.jpg", "sample_pts_seconds":13+i*.1} for i in range(60)]
    values = {r["file"]:{"red":r["sample_pts_seconds"] < end-.2, "green":False} for r in frames}
    return rows, frames, values


class QualificationTests(unittest.TestCase):
    def test_measured_energized_and_off_windows_plus_uart_timing(self):
        for case in ("stop", "lease"):
            self.assertEqual(evaluate(*fixture(case), case)["status"], "pass")

    def test_uart_alone_cannot_verify_shutdown(self):
        events, frames, _ = fixture("lease")
        self.assertEqual(evaluate(events, frames, {}, "lease")["status"], "incomplete")

    def test_led_still_on_after_reported_shutdown_fails(self):
        events, frames, values = fixture("stop")
        for value in values.values(): value["red"] = True
        self.assertEqual(evaluate(events, frames, values, "stop")["status"], "fail")

    def test_no_energized_evidence_cannot_pass(self):
        events, frames, values = fixture("lease")
        for value in values.values(): value["red"] = False
        self.assertEqual(evaluate(events, frames, values, "lease")["status"], "fail")

    def test_normal_step_change_cannot_be_mislabeled_as_timeout(self):
        events, frames, values = fixture("lease")
        events.append({"kind":"rx_line", "line":"VISUAL_STEP:3 RED:0 GREEN:0 TEXT:DARK UPTIME_MS:2", "host_uptime_seconds":14.0})
        with self.assertRaises(ValueError): evaluate(events, frames, values, "lease")

    def test_forbidden_fault_arguments_fail_before_hardware_access(self):
        for case, action in (("servo", "DISCOVER"), ("lease", "VISUAL")):
            with self.assertRaises(ValueError): acquire("unused", "explicit", "unused", "unused", action, fault=case)

    def test_sampling_gap_is_rejected_before_meta(self):
        from pathlib import Path
        with patch("sparkbench.workflow.validate_capture",return_value=[]), \
                patch("sparkbench.workflow.windows",return_value=[{
                    "step":1,"start":0,"end":2,"frames":[{"sample_pts_seconds":t} for t in (0,.2,.4,1.1,1.3,1.5,1.8,2)]}]):
            with self.assertRaisesRegex(ValueError,"no Meta requests"):
                require_coverage(Path("unused"),[{"step":1}])


if __name__ == "__main__": unittest.main()
