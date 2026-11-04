"""Synthetic storage/geometry fixtures only; no camera, serial or Meta requests."""
import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sparkbench.dashboard.camera_setup import CameraSetupStore, image_dimensions, validate_regions
from sparkbench.vision import digest


PROPOSAL = "a" * 32
JOB = "b" * 32


def header_fixture(width=400, height=240):
    # Structurally valid size headers, deliberately no pixel scan. Used only to
    # test storage parsing, never as a photograph or native-reader qualification.
    components = b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    return (b"\xff\xd8\xff\xfe\x00\x0csynthetic!\xff\xc0\x00\x11\x08"
            + struct.pack(">HH", height, width) + b"\x03" + components + b"\xff\xd9")


class CameraSetupStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.planner = Mock()
        self.planner.get.return_value = {"status": "ready", "plan_sha256": "c" * 64}
        self.store = CameraSetupStore(self.root, self.planner)
        self.geometry = {
            "schema_version": 1, "image_width": 400, "image_height": 240,
            "coordinate_origin": "top_left", "reference_frame": "old-reference.jpg",
            "leds": {"red": {"center_x": 210, "center_y": 60, "radius": 9},
                     "green": {"center_x": 280, "center_y": 60, "radius": 9}},
            "oled_corners": [[20, 20], [140, 20], [140, 100], [20, 100]],
            "rectified_width": 1024, "rectified_height": 512,
            "label_crop": [16, 132, 992, 256], "minimum_border_support": .85,
            "maximum_registration_shift_pixels": 80,
            "minimum_registration_scale": .88, "maximum_registration_scale": 1.12,
            "registration_translation_pixels": 12, "maximum_registration_error": 35,
        }
        self.calibration = {
            "schema_version": 1, "source_kind": "prior_real_inspection",
            "source_run": "old/run", "source_frames_sha256": {"frame.jpg": "d" * 64},
            "geometry": self.geometry, "geometry_sha256": "f" * 64,
            "reference_image_sha256": "e" * 64, "camera_id": "iphone",
            "thresholds": {"red": {"off_threshold": 120, "on_threshold": 210},
                           "green": {"off_threshold": 155, "on_threshold": 185}},
            "native_reader_source_sha256": "1" * 64, "macos": "test-platform",
            "limits": "fixed limits",
        }
        self.source = self.root / "runs/setup-capture/camera/frame-000010.jpg"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(header_fixture())
        self.base_calibration = self.root / "calibration.json"
        self.base_calibration.write_text(json.dumps(self.calibration))
        self.policy = {"calibration": str(self.base_calibration),
                       "calibration_sha256": digest(self.base_calibration),
                       "model": "muse-spark-1.3-contributor", "reader_hash": "2" * 64,
                       "missing_reading_policy": "unknown stays incomplete"}
        self.base_policy = self.root / "policy.json"
        self.base_policy.write_text(json.dumps(self.policy))
        self.body = {
            "image_sha256": digest(self.source),
            "regions": {"oled": [15, 15, 155, 115], "red": [200, 50, 240, 90], "green": [270, 50, 310, 90]},
            "sources": {"oled": "sam-3.1", "red": "sam-3.1", "green": "manual"},
            "points": {"red": [220, 70], "green": [290, 70]},
            "oled_corners": [[25, 25], [145, 35], [135, 105], [20, 95]],
        }
        self.validation_directory = self.root / "runs/fresh-validation"
        camera = self.validation_directory / "camera"
        camera.mkdir(parents=True)
        frames = {}
        for i in range(1, 4):
            path = camera / ("frame-%06d.jpg" % i)
            path.write_bytes(header_fixture())
            frames[path.name] = digest(path)
        (camera / "capture.json").write_text(json.dumps({"source": "synthetic_fixture", "frame_count": 3}))
        (camera / "frames.jsonl").write_text("".join(json.dumps({"file": f}) + "\n" for f in frames))
        manifest = self.validation_directory / "integrity.json"
        manifest.write_text(json.dumps({"sha256": {"camera/" + p.name: digest(p) for p in camera.iterdir()}}))
        self.validation = {"status": "view_ok", "source": "fresh_camera_only_validation", "device_id": "iphone",
                           "frames_checked": 3, "serial_commands_sent": [], "frames_sha256": frames,
                           "validation_directory": str(self.validation_directory),
                           "validation_integrity_sha256": digest(manifest)}
        self.patch = patch("sparkbench.dashboard.camera_setup.check_policy", side_effect=self.check_policy)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def check_policy(self, path):
        policy = json.loads(Path(path).read_text())
        calibration = Path(policy["calibration"])
        if digest(calibration) != policy["calibration_sha256"]:
            raise ValueError("Frozen LED calibration differs")
        return policy, calibration

    def prepare(self, body=None, job=JOB, device="iphone"):
        return self.store.prepare(job, PROPOSAL, device, self.source,
                                  self.body if body is None else body, self.base_policy)

    def test_confirmed_geometry_is_saved_without_activating_or_changing_reader_settings(self):
        result = self.prepare()
        self.assertEqual(self.store.policy_path(PROPOSAL, self.base_policy), self.base_policy)
        calibration = json.loads(result["calibration_path"].read_text())
        policy = json.loads(result["policy_path"].read_text())
        geometry = calibration["geometry"]
        self.assertEqual(calibration["thresholds"], self.calibration["thresholds"])
        self.assertEqual(geometry["leds"]["red"], {"center_x": 220, "center_y": 70, "radius": 9})
        self.assertEqual(geometry["oled_corners"], self.body["oled_corners"])
        for key in self.geometry.keys() - {"leds", "oled_corners", "reference_frame"}:
            self.assertEqual(geometry[key], self.geometry[key])
        for key in self.policy.keys() - {"calibration", "calibration_sha256"}:
            self.assertEqual(policy[key], self.policy[key])
        self.assertEqual(calibration["source_run"], str(self.source.parent.parent))
        self.assertNotIn("source_frames_sha256", calibration)
        self.assertEqual(calibration["inherited_thresholds"]["source"]["source_frames_sha256"], self.calibration["source_frames_sha256"])
        self.assertEqual(Path(geometry["reference_frame"]).read_bytes(), self.source.read_bytes())
        self.assertIn("behavior verification not performed", result["record"]["scope"])

    def test_only_qualified_reference_is_activated_and_survives_restart(self):
        result = self.prepare()
        for invalid in (None, {}, {"status": "view_blocked"}, {"status": "pass"}):
            with self.assertRaises(ValueError):
                self.store.activate(JOB, PROPOSAL, invalid)
        self.assertEqual(self.store.policy_path(PROPOSAL, self.base_policy), self.base_policy)
        validation = self.validation
        self.store.activate(JOB, PROPOSAL, validation)
        restart = CameraSetupStore(self.root, self.planner)
        self.assertEqual(restart.policy_path(PROPOSAL, self.base_policy), result["policy_path"])
        self.assertEqual(restart.policy_path("d" * 32, self.base_policy), self.base_policy)
        with self.assertRaisesRegex(ValueError, "already frozen"):
            restart.activate(JOB, PROPOSAL, {**validation, "note": "changed proof"})

    def test_every_activated_artifact_is_integrity_checked(self):
        result = self.prepare()
        self.store.activate(JOB, PROPOSAL, self.validation)
        folder = result["policy_path"].parent
        for name in ("reference.jpg", "review.json", "geometry.json", "calibration.json", "policy.json", "qualification.json"):
            path = folder / name
            old = path.read_bytes()
            path.write_bytes(old + b" ")
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.policy_path(PROPOSAL, self.base_policy)
            path.write_bytes(old)

    def test_resealed_changed_manifest_does_not_match_active_pointer(self):
        result = self.prepare()
        self.store.activate(JOB, PROPOSAL, self.validation)
        manifest = result["policy_path"].parent / "integrity.json"
        manifest.write_text(manifest.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.store.policy_path(PROPOSAL, self.base_policy)

    def test_source_change_resolution_and_camera_are_rejected_before_writing(self):
        wrong_hash = {**self.body, "image_sha256": "0" * 64}
        for body, device in ((wrong_hash, "iphone"), (self.body, "another-camera")):
            with self.assertRaises(ValueError):
                self.prepare(body, device=device)
        self.source.write_bytes(header_fixture(800, 480))
        with self.assertRaisesRegex(ValueError, "resolution"):
            self.prepare({**self.body, "image_sha256": digest(self.source)})
        self.assertFalse(self.store.directory.exists())

    def test_changed_proposal_cannot_reuse_reference(self):
        self.prepare()
        self.store.activate(JOB, PROPOSAL, self.validation)
        self.planner.get.return_value["plan_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "different proposal"):
            self.store.policy_path(PROPOSAL, self.base_policy)

    def test_candidate_cannot_be_rewritten_and_path_traversal_is_rejected(self):
        self.prepare()
        with self.assertRaises(FileExistsError):
            self.prepare()
        with self.assertRaises(ValueError):
            self.store.prepare("../escape", PROPOSAL, "iphone", self.source, self.body, self.base_policy)
        with self.assertRaises(ValueError):
            self.store.policy_path("../escape", self.base_policy)
        link = self.root / "source-link.jpg"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.store.prepare("c" * 32, PROPOSAL, "iphone", link, self.body, self.base_policy)

    def test_region_and_corner_rejections(self):
        mutations = [
            lambda b: b.update(unknown=True),
            lambda b: b["regions"]["red"].__setitem__(0, True),
            lambda b: b["regions"].update(red=[100, 50, 230, 100]),
            lambda b: b["regions"].update(red=[215, 65, 225, 75]),
            lambda b: b["regions"].update(green=[270, 50, 400, 90]),
            lambda b: b["points"].update(red=[220.0, 70]),
            lambda b: b["sources"].update(red="invented-model"),
            lambda b: b.update(oled_corners=[[25, 25], [135, 105], [145, 35], [20, 95]]),
            lambda b: b.update(oled_corners=[[145, 35], [135, 105], [20, 95], [25, 25]]),
            lambda b: b.update(oled_corners=[[25, 25], [35, 25], [35, 35], [25, 35]]),
            lambda b: b.update(oled_corners=[[10, 10], [145, 35], [135, 105], [20, 95]]),
            lambda b: b.update(oled_corners=[[25, 25], [145, 35], [80, 40], [20, 95]]),
        ]
        for i, mutate in enumerate(mutations):
            body = copy.deepcopy(self.body)
            mutate(body)
            with self.subTest(case=i), self.assertRaises(ValueError):
                validate_regions(body, self.geometry)

    def test_bad_image_headers_do_not_establish_dimensions(self):
        self.assertEqual(image_dimensions(header_fixture()), (400, 240))
        for bad in (b"not an image" * 4, header_fixture(4000, 240), header_fixture()[:-2], b"\xff\xd8\xff\xc0" + bytes(32) + b"\xff\xd9"):
            with self.assertRaises(ValueError):
                image_dimensions(bad)

    def test_qualification_requires_independent_camera_bound_retained_evidence(self):
        self.prepare()
        mutations = [
            lambda v: v.update(source="test_capture"),
            lambda v: v.update(device_id="other-camera"),
            lambda v: v.update(frames_checked=2),
            lambda v: v.update(validation_directory=str(self.source.parent.parent)),
            lambda v: v.update(validation_integrity_sha256="0" * 64),
            lambda v: v["frames_sha256"].update({"frame-000001.jpg": "0" * 64}),
        ]
        for i, mutate in enumerate(mutations):
            value = copy.deepcopy(self.validation)
            mutate(value)
            with self.subTest(case=i), self.assertRaises(ValueError):
                self.store.activate(JOB, PROPOSAL, value)
        self.assertEqual(self.store.policy_path(PROPOSAL, self.base_policy), self.base_policy)

    def test_changed_qualification_capture_cannot_be_reused(self):
        self.prepare()
        self.store.activate(JOB, PROPOSAL, self.validation)
        path = self.validation_directory / "camera/frame-000002.jpg"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "qualification evidence changed"):
            self.store.policy_path(PROPOSAL, self.base_policy)


if __name__ == "__main__":
    unittest.main()
