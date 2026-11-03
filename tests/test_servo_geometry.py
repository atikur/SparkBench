"""Synthetic geometry regressions; no hardware, capture, network or angle claims."""
import math
import unittest

from sparkbench.servo_geometry import body_coordinates, homography, perspective, project


class ServoGeometryTests(unittest.TestCase):
    def test_body_reference_moves_origin_and_rotates_axis_without_metric_claim(self):
        h=body_coordinates([1200,700],[1300,900],[1280,1000])
        self.assertAlmostEqual(project(h,[1200,700])[0],0)
        self.assertAlmostEqual(project(h,[1200,700])[1],0)
        a,b=project(h,[1300,900]),project(h,[1280,1000])
        self.assertAlmostEqual(a[0],b[0]);self.assertGreater(b[1],a[1])

    def test_projective_correction_recovers_independent_interior_points(self):
        physical=[[0,0],[2,0],[2,1],[0,1]]
        camera=[[230,13,1200],[-17,170,600],[.08,.12,1]]
        source=[project(camera,p) for p in physical]
        inverse=homography(source,physical)
        for p in ([.2,.3],[1,.5],[1.7,.8]):
            corrected=project(inverse,project(camera,p))
            self.assertAlmostEqual(corrected[0],p[0],places=8)
            self.assertAlmostEqual(corrected[1],p[1],places=8)

    def test_correct_aspect_is_needed_for_angles(self):
        source=[[100,100],[500,130],[470,330],[110,310]]
        metric=homography(source,[[0,0],[2,0],[2,1],[0,1]])
        square=homography(source,[[0,0],[1,0],[1,1],[0,1]])
        # Four corners alone cannot select between these valid maps.
        p=[source[0][0]+100,source[0][1]+100]
        a,b=project(metric,p),project(square,p)
        self.assertNotAlmostEqual(math.atan2(a[1],a[0]),math.atan2(b[1],b[0]))

    def test_unknown_dimensions_plane_or_provenance_cannot_calibrate(self):
        for reference in (None,{}, {"dimensions_confirmed":True},
                          {"dimensions_confirmed":True,"plane_relation_confirmed":True,
                           "relation_to_horn_plane":"different_plane","provenance":"unverified body silhouette"}):
            result=perspective(reference)
            self.assertIsNone(result["image_to_plane"])
            self.assertIsNone(result["angle_deg"])
            self.assertFalse(result["calibrated_angle_verification"])

    def test_known_plane_defines_map_but_never_claims_accuracy_or_servo_zero(self):
        result=perspective({"dimensions_confirmed":True,"plane_relation_confirmed":True,
            "relation_to_horn_plane":"same_plane","provenance":"synthetic square fixture, not physical evidence",
            "plane_size":[1,1],"corners_px":[[100,100],[300,120],[280,300],[110,290]]})
        self.assertIsNotNone(result["image_to_plane"])
        self.assertIsNone(result["angle_deg"])
        self.assertFalse(result["calibrated_angle_verification"])

    def test_invalid_or_self_crossing_geometry_is_rejected(self):
        for points in ([[0,0],[1,0],[2,0],[3,0]], [[0,0],[1,1],[1,0],[0,1]],
                       [[0,0],[1,0],[float('nan'),1],[0,1]]):
            with self.assertRaises(ValueError):homography(points,[[0,0],[1,0],[1,1],[0,1]])
        with self.assertRaises(ValueError):project([[1,0,0],[0,1,0],[0,0,0]],[1,1])
        with self.assertRaises(ValueError):body_coordinates([0,0],[1,1],[1,1])


if __name__=="__main__":unittest.main()
