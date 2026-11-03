"""Passive orchestration/state tests. Hardware and capture boundaries are mocked."""
import copy
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from sparkbench.passive import DEFAULT_POLICY, run_session, session_quality
from sparkbench.vision import digest, save


TRACKING = {"status": "unverified_tracking_available", "quality_controls": "pass"}


def frames(pattern):
    return [{"frame": i, "file": "frame-%06d.jpg" % i, "sample_pts_seconds": 10+i*.3,
        "host_uptime_seconds": 10.1+i*.3, "status": "tracked_unverified" if good else "unknown",
        "reasons": [] if good else ["body_patch_disagreement"],
        "preview_estimates": {"apparent_image_heading_deg": 100+i*.1} if good else None,
        "localized_points": {"pivot_px": [10, 10], "tip_px": [20, 20]} if good else None,
        "angle_deg": None, "eligible_for_verifier": False} for i, good in enumerate(pattern, 1)]


class PassiveQualityTests(unittest.TestCase):
    def test_startup_is_causal_and_preserves_every_original_row(self):
        rows = frames([False, True, True, True, True]); original = copy.deepcopy(rows)
        trace, report = session_quality(rows, TRACKING)
        self.assertEqual([r["session_state"] for r in trace], ["starting"]*3+["tracking"]*2)
        self.assertEqual([r["preview_available"] for r in trace], [False]*3+[True]*2)
        self.assertEqual(rows, original)
        self.assertEqual(report["frames"], 5); self.assertEqual(report["raw_unknown_frames"], 1)
        self.assertEqual(report["session_preview_frames"], 2)
        self.assertEqual(report["first_ready"]["frame"], 4)
        self.assertTrue(all(r["angle_deg"] is None and not r["eligible_for_verifier"] for r in trace))

    def test_loss_immediately_hides_preview_and_recovery_requires_new_streak(self):
        trace, report = session_quality(frames([True]*3+[False, True, False]+[True]*3), TRACKING)
        self.assertEqual([r["session_state"] for r in trace],
            ["starting", "starting", "tracking", "lost", "recovering", "lost", "recovering", "recovering", "tracking"])
        self.assertTrue(all(r["session_preview_estimates"] is None for r in trace[3:8]))
        self.assertEqual(report["tracking_losses"], 1); self.assertEqual(report["recoveries"], 1)
        self.assertEqual(report["unknown_intervals"][0]["start_frame"], 4)
        self.assertEqual(report["unknown_intervals"][1]["end_frame"], 6)

    def test_frame_count_alone_cannot_satisfy_minimum_ready_duration(self):
        rows = frames([True]*3)
        for i, r in enumerate(rows):
            r.update(sample_pts_seconds=10+i*.1, host_uptime_seconds=10.05+i*.1)
        trace, report = session_quality(rows, TRACKING)
        self.assertEqual(report["status"], "no_ready_interval")
        self.assertTrue(all(not r["preview_available"] for r in trace))

    def test_timestamp_error_and_gap_lose_tracking_without_crediting_gap(self):
        rows = frames([True]*8)
        for r in rows[3:]:
            r["sample_pts_seconds"] += 2; r["host_uptime_seconds"] += 2
        rows[6]["host_uptime_seconds"] = rows[6]["sample_pts_seconds"]-0.1
        trace, report = session_quality(rows, TRACKING)
        self.assertEqual(trace[3]["session_state"], "lost")
        self.assertEqual(trace[6]["session_state"], "lost")
        self.assertIsNone(trace[6]["session_preview_estimates"])
        self.assertAlmostEqual(report["unobserved_gap_seconds"], 2.3)
        self.assertEqual(report["capture_gaps"][0]["frame"], 4)
        self.assertLess(sum(report["adjacent_sample_interval_seconds_by_previous_state"].values()), report["sample_pts_span_seconds"])

    def test_failed_controls_and_missing_points_never_create_preview(self):
        for tracking in ({"status": "incomplete", "quality_controls": "pass"},
                         {"status": "unverified_tracking_available", "quality_controls": "fail"}):
            trace, report = session_quality(frames([True]*5), tracking)
            self.assertEqual(report["session_preview_frames"], 0)
        rows = frames([True]*4); rows[0]["localized_points"] = None
        trace, _ = session_quality(rows, TRACKING)
        self.assertIsNone(trace[0]["session_preview_estimates"])
        self.assertIn("source_preview_unavailable", trace[0]["session_input_reasons"])

    def test_invalid_order_policy_and_empty_input(self):
        rows = frames([True]*3); rows[1]["frame"] = 1
        with self.assertRaises(ValueError): session_quality(rows, TRACKING)
        with self.assertRaises(ValueError): session_quality([], TRACKING, dict(DEFAULT_POLICY, ready_good_frames=True))
        trace, report = session_quality([], TRACKING)
        self.assertEqual(trace, []); self.assertIsNone(report["raw_localization_fraction"])
        self.assertEqual(report["status"], "no_ready_interval")


class PassiveCommandTests(unittest.TestCase):
    def inputs(self, root):
        reference = root/"reference.jpg"; reference.write_bytes(b"saved reference fixture")
        helper = root/"helper"; helper.write_bytes(b"mock helper")
        preview = root/"preview.json"
        save(preview, {"camera_id": "selected-iphone", "reference_frame": str(reference),
                       "reference_sha256": digest(reference)})
        config = root/"config.json"
        save(config, {"mode": "unverified_passive_tracking", "preview_config": str(preview),
            "preview_config_sha256": digest(preview), "temporal_policy": {"maximum_frame_gap_seconds": 1}})
        return config, helper

    def test_capture_and_tracking_create_self_contained_frozen_report(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve(); config, helper = self.inputs(root); output = root/"session"
            stack.enter_context(patch("sparkbench.passive.build_helper", return_value=helper))
            stack.enter_context(patch("sparkbench.passive.build_tracker", return_value=helper))
            stack.enter_context(patch("sparkbench.passive.list_cameras", return_value={"devices": [
                {"id": "selected-iphone", "connected": True}]}))
            def capture(identifier, seconds, fps, path):
                self.assertEqual(identifier, "selected-iphone")
                path.mkdir(); save(path/"capture.json", {"status": "captured"})
                return {"status": "captured"}
            stack.enter_context(patch("sparkbench.passive.capture_frames", side_effect=capture))
            def track(frozen, analysis):
                c = json.loads(frozen.read_text()); self.assertEqual(c["source_capture"], str(output/"camera"))
                p = json.loads(Path(c["preview_config"]).read_text())
                self.assertEqual(Path(p["reference_frame"]).parent, output/"inputs")
                analysis.mkdir(); save(analysis/"tracking.json", TRACKING)
                (analysis/"trace.jsonl").write_text("".join(json.dumps(r)+"\n" for r in frames([True]*4)))
                return TRACKING
            stack.enter_context(patch("sparkbench.passive.track_saved", side_effect=track))
            report = run_session(config, "selected-iphone", output, 2, 5)
            self.assertEqual(report["status"], "preview_intervals_available")
            self.assertEqual(report["frames"], 4)
            self.assertTrue((output/"quality.json").is_file()); self.assertTrue((output/"report.md").is_file())
            self.assertEqual(report["serial_commands_sent"], []); self.assertFalse(report["servo_actuation"])
            preflight = json.loads((output/"preflight.json").read_text())
            self.assertEqual(preflight["tracker_config_sha256"], digest(output/"inputs/tracker.frozen.json"))

    def test_identity_mismatch_never_builds_or_captures_and_retains_incomplete_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config, _ = self.inputs(root)
            with patch("sparkbench.passive.build_helper") as helper, patch("sparkbench.passive.capture_frames") as capture:
                report = run_session(config, "wrong-camera", root/"session")
                helper.assert_not_called(); capture.assert_not_called()
            self.assertEqual(report["status"], "incomplete"); self.assertIn("identity mismatch", report["error"])
            self.assertTrue((root/"session/integrity.json").is_file())

    def test_denied_enumeration_never_substitutes_a_camera(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config, helper = self.inputs(root)
            with patch("sparkbench.passive.build_helper", return_value=helper), \
                 patch("sparkbench.passive.build_tracker", return_value=helper), \
                 patch("sparkbench.passive.list_cameras", return_value={"camera_permission": "denied", "devices": []}), \
                 patch("sparkbench.passive.capture_frames") as capture:
                report = run_session(config, "selected-iphone", root/"session")
                capture.assert_not_called()
            self.assertEqual(report["status"], "incomplete"); self.assertIn("Sandbox denial", report["error"])

    def test_bounds_and_existing_output_fail_without_hardware(self):
        with tempfile.TemporaryDirectory() as directory, patch("sparkbench.passive.list_cameras") as enumeration:
            root = Path(directory)
            for seconds in (0, 61, float("nan"), True):
                with self.assertRaises(ValueError): run_session(root/"missing", "id", root/"new", seconds)
            with self.assertRaises(FileExistsError): run_session(root/"missing", "id", root)
            enumeration.assert_not_called()

    def test_failed_capture_retains_partial_evidence_and_does_not_track(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); config, helper = self.inputs(root); output = root/"session"
            def failed_capture(identifier, seconds, fps, path):
                path.mkdir(); (path/"frame-000001.jpg").write_bytes(b"partial mock frame")
                raise ValueError("mock capture failed")
            with patch("sparkbench.passive.build_helper", return_value=helper), \
                 patch("sparkbench.passive.build_tracker", return_value=helper), \
                 patch("sparkbench.passive.list_cameras", return_value={"devices": [{"id": "selected-iphone", "connected": True}]}), \
                 patch("sparkbench.passive.capture_frames", side_effect=failed_capture), \
                 patch("sparkbench.passive.track_saved") as track:
                report = run_session(config, "selected-iphone", output, 2)
                track.assert_not_called()
            self.assertEqual(report["status"], "incomplete"); self.assertEqual(report["phase"], "capture")
            self.assertTrue((output/"camera/frame-000001.jpg").is_file())
            self.assertIn("camera/frame-000001.jpg", json.loads((output/"integrity.json").read_text())["sha256"])

    def test_policy_change_after_freeze_aborts_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); config, helper = self.inputs(root); output = root/"session"
            def changed_policy(identifier, seconds, fps, path):
                save(output/"inputs/session-policy.json", {"changed": True})
                return {"status": "captured"}
            with patch("sparkbench.passive.build_helper", return_value=helper), \
                 patch("sparkbench.passive.build_tracker", return_value=helper), \
                 patch("sparkbench.passive.list_cameras", return_value={"devices": [{"id": "selected-iphone", "connected": True}]}), \
                 patch("sparkbench.passive.capture_frames", side_effect=changed_policy), \
                 patch("sparkbench.passive.track_saved") as track:
                report = run_session(config, "selected-iphone", output, 2)
                track.assert_not_called()
            self.assertEqual(report["status"], "incomplete"); self.assertIn("changed after freeze", report["error"])


if __name__ == "__main__":
    unittest.main()
