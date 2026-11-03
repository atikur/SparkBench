"""Unverified previews cannot become physical-angle evidence."""
import copy
import json
import unittest

from sparkbench.camera import ROOT
from sparkbench.servo_geometry import perspective
from sparkbench.servo_preview import estimates
from sparkbench.verify import verify_trace


def fixture():
    return {"mode":"unverified_static_preview",
        "body_reference":{"shaft_center_px":[150,150],"axis_endpoints_px":[[150,170],[150,210]]},
        "horn_tip_px":[175,175],
        "preview_card":{"corners_px":[[100,100],[300,100],[300,300],[100,300]],
                        "illustrative_width_to_height_ratios":[1.25,1.5,2]},
        "plane_reference":None}


class ServoPreviewTests(unittest.TestCase):
    def test_separates_image_heading_from_true_servo_angle(self):
        r=estimates(fixture())
        self.assertEqual(r["preview_estimates"]["apparent_image_heading_deg"],45)
        self.assertIsNone(r["angle_deg"])
        self.assertIsNone(r["measured_angle_calibration"])
        self.assertFalse(r["eligible_for_verifier"])
        self.assertFalse(r["calibrated_angle_verification"])

    def test_assumptions_change_result_without_becoming_error_bounds(self):
        r=estimates(fixture())["preview_estimates"]
        values=[v["unverified_heading_from_card_top_edge_deg"] for v in r["card_ratio_scenarios"]]
        self.assertEqual(len(set(values)),3)
        self.assertFalse(r["scenarios_are_confidence_or_error_bounds"])

    def test_extrapolation_is_explicit(self):
        c=fixture();c["body_reference"]["shaft_center_px"]=[50,50];c["horn_tip_px"]=[60,70]
        self.assertTrue(estimates(c)["preview_estimates"]["horn_points_extrapolated_beyond_card"])

    def test_invalid_assumptions_and_missing_opt_in_fail(self):
        for ratios in ([0],[True],[float('nan')],[1,1],[],[100]):
            c=fixture();c["preview_card"]["illustrative_width_to_height_ratios"]=ratios
            with self.assertRaises(ValueError):estimates(c)
        c=fixture();c.pop("mode")
        with self.assertRaises(ValueError):estimates(c)

    def test_preview_never_relaxes_strict_metric_plane_or_behavior_verifier(self):
        c=fixture();r=estimates(c)
        self.assertIsNone(perspective(c["plane_reference"])["image_to_plane"])
        spec=json.loads((ROOT/"specs/behavior_a.json").read_text())
        trace=json.loads((ROOT/"examples/synthetic_behavior_a.json").read_text())
        for row in trace["measurements"]:
            row["angle_deg"]=None
            row["preview_estimates"]=copy.deepcopy(r["preview_estimates"])
        self.assertEqual(verify_trace(spec,trace)["status"],"incomplete")

    def test_nominal_printed_square_preserves_user_report_without_metric_upgrade(self):
        c=fixture();c["preview_card"].update(reference_kind="nominal_printed_square",
            illustrative_width_to_height_ratios=[1.0],dimensions_confirmed=False,
            plane_relation_confirmed=True)
        r=estimates(c)
        self.assertIn("unmeasured",r["assumptions"][0])
        self.assertIn("User confirms flat parallel",r["assumptions"][1])
        self.assertIsNone(r["angle_deg"]);self.assertFalse(r["eligible_for_verifier"])
        self.assertIsNone(perspective(c["plane_reference"])["image_to_plane"])

    def test_image_only_has_no_invented_plane_or_calibrated_angle(self):
        c=fixture();c.update(geometry_mode="image_only",preview_card=None)
        r=estimates(c)
        self.assertEqual(r["preview_estimates"]["apparent_image_heading_deg"],45)
        self.assertEqual(r["preview_estimates"]["card_ratio_scenarios"],[])
        self.assertIsNone(r["preview_estimates"]["horn_points_extrapolated_beyond_card"])
        self.assertIsNone(r["angle_deg"])
        self.assertFalse(r["eligible_for_verifier"])
        self.assertIn("No usable planar reference",r["assumptions"][0])
        c.pop("geometry_mode")
        with self.assertRaises(ValueError):estimates(c)
        c=fixture();c["geometry_mode"]="image_only"
        with self.assertRaises(ValueError):estimates(c)

    def test_old_card_reference_notes_remain_conservative(self):
        r=estimates(fixture())
        self.assertIn("Card ratio is unknown",r["assumptions"][0])
        self.assertIn("only approximately parallel",r["assumptions"][1])

    def test_reported_grid_with_possible_tilt_never_claims_parallel_confirmation(self):
        c=fixture();c["preview_card"].update(reference_kind="reported_square_grid",
            illustrative_width_to_height_ratios=[1.0],plane_relation_confirmed=False,
            plane_alignment_report="Paper flat; horn could tilt downward at front")
        r=estimates(c)
        self.assertIn("50 x 50 mm reference grid",r["assumptions"][0])
        self.assertIn("parallelism unconfirmed",r["assumptions"][1])
        self.assertIn("tilt downward",r["assumptions"][1])
        self.assertNotIn("User confirms flat parallel",r["assumptions"][1])
        self.assertIsNone(r["angle_deg"])
        self.assertFalse(r["eligible_for_verifier"])
        self.assertIsNone(perspective(c["plane_reference"])["image_to_plane"])


if __name__=="__main__":unittest.main()
