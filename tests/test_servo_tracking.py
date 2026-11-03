"""Passive tracking joins and quality handling; no hardware or network."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from sparkbench.camera import ROOT
from sparkbench.servo_tracking import joined_trace, heading_summary
from sparkbench.verify import verify_trace


def inputs():
    preview={"mode":"unverified_static_preview","body_reference":{"shaft_center_px":[150,150],"axis_endpoints_px":[[150,180],[150,220]]},"horn_tip_px":[175,175],
        "preview_card":{"corners_px":[[100,100],[300,100],[300,300],[100,300]],"illustrative_width_to_height_ratios":[1.25,1.5,2]}}
    frames=[{"frame":i,"file":"frame-%06d.jpg"%i,"sample_pts_seconds":10+i*.3,"host_uptime_seconds":10.1+i*.3} for i in range(1,4)]
    raw=[{"id":Path(f["file"]).stem,"status":"tracked_unverified","reasons":[],"pivot_px":[150,150],"tip_px":[175,175],"quality":{"body_shift_pixels":[0,0]}} for f in frames]
    return preview,frames,raw,{"maximum_frame_gap_seconds":1,"maximum_heading_jump_deg":45}


class ServoTrackingTests(unittest.TestCase):
    def test_circular_heading_coverage_handles_wrap_without_inventing_travel(self):
        r=heading_summary([179,-179,-175],True)
        self.assertAlmostEqual(r["apparent_image_heading_circular_span_deg"],6)
        self.assertIsNone(r["apparent_static_heading_span_deg"])
        self.assertIsNone(r["static_span_scope"])
        self.assertIn("not mechanical angle",r["circular_span_scope"])
        self.assertIn("not independent",r["evaluation_scope"])

    def test_static_summary_retains_legacy_metric_and_handles_empty_singleton(self):
        self.assertAlmostEqual(heading_summary([1,1.4])["apparent_static_heading_span_deg"],.4)
        self.assertIsNone(heading_summary([],True)["apparent_image_heading_circular_span_deg"])
        self.assertEqual(heading_summary([42],True)["apparent_image_heading_circular_span_deg"],0)

    def test_heading_summary_rejects_bad_context_or_nonfinite_direction(self):
        for flag in ("true",1,None):
            with self.assertRaises(ValueError):heading_summary([],flag)
        with self.assertRaises(ValueError):heading_summary([float("nan")],True)

    def test_timestamped_previews_have_arbitrary_relative_zero_and_no_measured_angle(self):
        config,frames,raw,policy=inputs();rows=joined_trace(frames,raw,config,policy)
        self.assertEqual(len(rows),3)
        for row in rows:
            self.assertEqual(row["status"],"tracked_unverified")
            self.assertEqual(row["preview_estimates"]["apparent_change_from_first_accepted_frame_deg"],0)
            self.assertFalse(row["preview_estimates"]["first_pose_is_mechanical_zero"])
            self.assertIsNone(row["angle_deg"]);self.assertFalse(row["eligible_for_verifier"])

    def test_image_only_registration_and_unknowns_preserve_null_plane(self):
        config,frames,raw,policy=inputs()
        config.update(geometry_mode="image_only",preview_card=None)
        for matrix in (False,True):
            for row in raw:
                row["quality"].update(camera_shift_pixels=[0,0])
                if matrix:
                    row["quality"].update(camera_image_transform=[1,0,0,0,1,0],body_residual_shift_pixels=[0,0])
            rows=joined_trace(frames,raw,config,policy)
            self.assertTrue(all(r["status"]=="tracked_unverified" for r in rows))
            self.assertTrue(all(r["preview_estimates"]["card_ratio_scenarios"]==[] for r in rows))
            self.assertTrue(all(r["angle_deg"] is None for r in rows))
        raw[1].update(status="unknown",reasons=["occluded"],pivot_px=None,tip_px=None)
        rows=joined_trace(frames,raw,config,policy)
        self.assertIsNone(rows[1]["preview_estimates"])
        self.assertIsNone(rows[1]["localized_points"])

    def test_rejected_frame_never_reuses_prior_points_or_angle(self):
        config,frames,raw,policy=inputs()
        raw[1].update(status="unknown",reasons=["blur_or_low_detail"],pivot_px=None,tip_px=None)
        rows=joined_trace(frames,raw,config,policy)
        self.assertEqual(rows[0]["status"],"tracked_unverified")
        self.assertEqual(rows[1]["status"],"unknown")
        self.assertIsNone(rows[1]["preview_estimates"]);self.assertIsNone(rows[1]["localized_points"])
        self.assertEqual(rows[2]["status"],"tracked_unverified")

    def test_missing_frame_remains_present_and_unknown(self):
        config,frames,raw,policy=inputs();raw.pop(1)
        rows=joined_trace(frames,raw,config,policy)
        self.assertEqual([r["frame"] for r in rows],[1,2,3])
        self.assertEqual(rows[1]["status"],"unknown");self.assertIsNone(rows[1]["preview_estimates"])

    def test_alignment_gap_and_nonincreasing_pts_are_rejected(self):
        for case in ("alignment","gap","reverse"):
            config,frames,raw,policy=inputs()
            if case=="alignment":frames[1]["host_uptime_seconds"]=frames[1]["sample_pts_seconds"]-.1
            elif case=="gap":frames[1].update(sample_pts_seconds=12,host_uptime_seconds=12.1)
            else:frames[1].update(sample_pts_seconds=10,host_uptime_seconds=10.1)
            row=joined_trace(frames,raw,config,policy)[1]
            self.assertEqual(row["status"],"unknown");self.assertIsNone(row["preview_estimates"])

    def test_heading_jump_and_invalid_native_points_are_unknown(self):
        for case in ("jump","nan"):
            config,frames,raw,policy=inputs()
            raw[1]["tip_px"]=[125,125] if case=="jump" else [float('nan'),175]
            self.assertEqual(joined_trace(frames,raw,config,policy)[1]["status"],"unknown")

    def test_duplicate_or_unexpected_native_frame_ids_rejected(self):
        config,frames,raw,policy=inputs()
        for altered in (raw+[copy.deepcopy(raw[0])],raw+[{"id":"foreign"}]):
            with self.assertRaises(ValueError):joined_trace(frames,altered,config,policy)

    def test_preview_trace_cannot_make_full_behavior_pass(self):
        config,frames,raw,policy=inputs();preview=joined_trace(frames,raw,config,policy)[0]["preview_estimates"]
        spec=json.loads((ROOT/"specs/behavior_a.json").read_text())
        trace=json.loads((ROOT/"examples/synthetic_behavior_a.json").read_text())
        for r in trace["measurements"]:r.update(angle_deg=None,preview_estimates=preview)
        self.assertEqual(verify_trace(spec,trace)["status"],"incomplete")

    def test_camera_shift_translates_card_and_body_geometry_consistently(self):
        config,frames,raw,policy=inputs()
        baseline=joined_trace(frames,raw,config,policy)
        for row in raw:
            row["pivot_px"]=[152,152];row["tip_px"]=[177,177]
            row["quality"].update(body_shift_pixels=[2,2],camera_shift_pixels=[2,2])
        translated=joined_trace(frames,raw,config,policy)
        self.assertEqual(translated[0]["preview_estimates"],baseline[0]["preview_estimates"] | {
            "card_ratio_scenarios":translated[0]["preview_estimates"]["card_ratio_scenarios"]})
        for a,b in zip(baseline[0]["preview_estimates"]["card_ratio_scenarios"],translated[0]["preview_estimates"]["card_ratio_scenarios"]):
            self.assertEqual(a["unverified_heading_from_card_top_edge_deg"],b["unverified_heading_from_card_top_edge_deg"])
        self.assertIsNone(translated[0]["angle_deg"])

    def test_invalid_camera_translation_never_produces_preview(self):
        config,frames,raw,policy=inputs()
        for value in ([float('nan'),0],[1],"2,2"):
            raw[0]["quality"]["camera_shift_pixels"]=value
            row=joined_trace(frames,raw,config,policy)[0]
            self.assertEqual(row["status"],"unknown")
            self.assertIsNone(row["preview_estimates"]);self.assertIsNone(row["localized_points"])

    def test_similarity_registration_preserves_corrected_geometry_and_null_angles(self):
        config,frames,raw,policy=inputs()
        expected=joined_trace(frames,raw,config,policy)[0]["preview_estimates"]
        # Exact small rotation around the origin plus translation. Synthetic only.
        import math
        a,b=math.cos(.003),math.sin(.003)
        def project(p):return [a*p[0]-b*p[1]+1,b*p[0]+a*p[1]-1]
        for row in raw:
            row["pivot_px"]=project([150,150]);row["tip_px"]=project([175,175])
            row["quality"].update(camera_image_transform=[a,-b,1,b,a,-1],body_residual_shift_pixels=[0,0])
        result=joined_trace(frames,raw,config,policy)[0]
        for x,y in zip(expected["card_ratio_scenarios"],result["preview_estimates"]["card_ratio_scenarios"]):
            self.assertEqual(x["unverified_heading_from_card_top_edge_deg"],y["unverified_heading_from_card_top_edge_deg"])
        self.assertEqual(result["preview_estimates"]["apparent_horn_vs_projected_case_axis_deg"],expected["apparent_horn_vs_projected_case_axis_deg"])
        self.assertIsNone(result["angle_deg"]);self.assertFalse(result["eligible_for_verifier"])
        raw[0]["quality"]["camera_image_transform"]=[1,0,float('nan'),0,1,0]
        self.assertIsNone(joined_trace(frames,raw,config,policy)[0]["localized_points"])

    @unittest.skipUnless(shutil.which("xcrun"),"Native Swift toolchain unavailable")
    def test_production_native_core_on_explicitly_synthetic_rgb_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            shutil.copyfile(ROOT/"tests/native/servo_tracker_test.swift",p/"main.swift")
            result=subprocess.run(["xcrun","swiftc","-O","-module-cache-path",str(ROOT/".cache/servo_tracker/test-modules"),str(ROOT/"tools/macos_servo_tracker/Tracker.swift"),str(p/"main.swift"),"-o",str(p/"test")],capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(p/"test")],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=="__main__":unittest.main()
