"""Camera setup orchestration using synthetic pixels and mocked interpretation.

These tests exercise persistence, ownership and HTTP boundaries. They provide no
physical calibration evidence and never access a real camera, board or model.
"""
import base64
import copy
import hashlib
import http.client
import json
import struct
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from sparkbench.dashboard.evidence import EvidenceStore
from sparkbench.dashboard.execution import ExecutionService
from sparkbench.dashboard.planning import BusyError
from sparkbench.dashboard.server import DashboardServer
from sparkbench.intent import save
from sparkbench.vision import digest


PLAN = "a" * 32
OTHER = "b" * 32
REPAIR = "c" * 32
CAMERA = "synthetic-iphone"


def jpeg(tag=b"fixture"):
    # A bounded SOF header for transport/dimension validation. Pixel decoding is
    # intentionally mocked below; this is not a photograph.
    return (b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", 240, 320)
            + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00" + tag + b"\xff\xd9")


class CameraSetupFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / "hardware").mkdir()
        (self.root / "reference.jpg").write_bytes(jpeg())
        self.base = self.root / "hardware/oled-reader.policy.json"
        self.calibration = self.root / "calibration.json"
        geometry = {"image_width": 320, "image_height": 240,
            "reference_frame": str(self.root / "reference.jpg"),
            "leds": {"red": {"center_x": 235, "center_y": 70, "radius": 9},
                     "green": {"center_x": 280, "center_y": 70, "radius": 9}},
            "oled_corners": [[30, 40], [180, 40], [180, 150], [30, 150]],
            "minimum_border_support": .85, "label_crop": [16, 132, 992, 256],
            "maximum_registration_shift_pixels": 80, "minimum_registration_scale": .88,
            "maximum_registration_scale": 1.12, "registration_translation_pixels": 12,
            "maximum_registration_error": 35}
        save(self.calibration, {"camera_id": CAMERA, "geometry": geometry,
            "thresholds": {name: {"off_threshold": 100, "on_threshold": 180}
                           for name in ("red", "green")},
            "source_kind": "synthetic_fixture", "source_run": "synthetic",
            "native_reader_source_sha256": "f" * 64, "macos": "synthetic"})
        save(self.base, {"calibration": str(self.calibration), "calibration_sha256": digest(self.calibration)})
        self.planner = Mock(directory=self.root / "plans")
        self.planner.get.side_effect = self.proposal
        self.builder, self.installer, self.runner = Mock(), Mock(), Mock()
        self.identity = Mock()
        self.reader = Mock(side_effect=self.read_images)
        self.label = Mock(return_value={"status": "read", "text": "READY"})
        self.sam = Mock(side_effect=self.suggest)
        self.capture = Mock(side_effect=self.capture_frames)
        self.registration = Mock(side_effect=ValueError("No automatic alignment in this fixture"))
        self.patches = [patch("sparkbench.dashboard.camera_flow.capture_frames", self.capture),
                        patch("sparkbench.dashboard.camera_flow.register_setup", self.registration)]
        for module in ("camera_flow", "camera_setup", "execution"):
            self.patches.append(patch("sparkbench.dashboard." + module + ".check_policy", side_effect=self.check_policy))
        for item in self.patches:
            item.start()
        self.services = []
        self.service = self.new_service()

    def tearDown(self):
        for service in self.services:
            service.shutdown()
            if service.thread:
                service.thread.join(5)
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def proposal(self, proposal_id):
        if proposal_id not in (PLAN, OTHER, REPAIR):
            raise KeyError("Unknown proposal")
        result = {"id": proposal_id, "status": "ready", "plan_sha256": "d" * 64,
                  "review_status": "reviewed"}
        if proposal_id == REPAIR:
            result.update(origin="mapping_repair", parent_id=PLAN)
        return result

    def check_policy(self, path):
        policy = json.loads(Path(path).read_text())
        calibration = Path(policy["calibration"])
        self.assertEqual(digest(calibration), policy["calibration_sha256"])
        return policy, calibration

    def new_service(self):
        service = ExecutionService(self.root, self.planner, EvidenceStore(self.root, ()),
            builder=self.builder, installer=self.installer, runner=self.runner,
            identity_checker=self.identity, view_reader=self.reader, label_reader=self.label,
            enumerate_devices=lambda: {"ports": [], "cameras": [{"id": CAMERA}]},
            region_proposer=self.sam)
        self.services.append(service)
        return service

    def capture_frames(self, camera, *, output, **kwargs):
        self.assertEqual(camera, CAMERA)
        output.mkdir(parents=True)
        rows = []
        serial = self.capture.call_count
        for index in range(1, 5):
            name = "frame-%06d.jpg" % index
            (output / name).write_bytes(jpeg(("synthetic-%d-%d" % (serial, index)).encode()))
            rows.append({"frame": index, "file": name, "width": 320, "height": 240,
                         "sample_pts_seconds": serial * 10 + index / 2,
                         "host_uptime_seconds": serial * 10 + index / 2 + .1})
        (output / "frames.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        save(output / "capture.json", {"status": "captured", "source": "live_camera",
             "camera": {"id": camera}, "frame_count": len(rows), "fixture": "synthetic"})

    def suggest(self, body):
        regions = ({"red": [220, 55, 250, 85], "green": [265, 55, 295, 85]}
                   if body["points"] else {"oled": [20, 30, 190, 160]})
        return {"model": "sam-3.1", "regions": regions,
                "image_sha256": hashlib.sha256(base64.b64decode(body["image"]["data"])).hexdigest()}

    def read_images(self, run, geometry, frames, output, **kwargs):
        self.assertFalse(kwargs["read_labels"])
        return {row["file"]: {"status": "measured", "oled_border_support": [1, 1, 1, 1],
                "leds": {name: {"mean_luma_srgb": 70} for name in ("red", "green")},
                "label_crop": "label.png"} for row in frames}

    def body(self, proposal_id=PLAN):
        return {"proposal_id": proposal_id, "device_id": CAMERA, "request_id": uuid.uuid4().hex}

    def wait(self, job_id):
        for _ in range(500):
            result = self.service.get(job_id)
            if result["status"] != "running" and self.service.active is None:
                return result
            time.sleep(.01)
        self.fail("Synthetic camera setup worker timed out")

    def start(self):
        result = self.wait(self.service.start_camera_setup(self.body()))
        self.assertEqual(result["status"], "setup_review", result)
        return result

    def confirmation(self, job):
        return {"image_sha256": job["image_sha256"],
                "regions": {"oled": [20, 30, 190, 160], "red": [220, 55, 250, 85],
                            "green": [265, 55, 295, 85]},
                "sources": {name: "sam-3.1" for name in ("oled", "red", "green")},
                "points": {"red": [235, 70], "green": [280, 70]},
                "oled_corners": [[30, 40], [180, 40], [180, 150], [30, 150]]}

    def activate(self):
        job = self.start()
        return self.wait(self.service.confirm_camera_setup(job["id"], self.confirmation(job)))


class CameraSetupFlowTests(CameraSetupFixture):
    def automatic_fixture(self):
        self.registration.side_effect = None
        self.registration.return_value = {
            "landmarks": [[30, 40], [180, 40], [180, 150], [30, 150], [235, 70], [280, 70]],
            "lens_similarity": [.98, .97]}
        def sam(body):
            result = self.suggest(body)
            if body["points"]:
                result["regions"] = {"red": [220, 55, 250, 85], "green": [265, 55, 295, 85]}
            return result
        self.sam.side_effect = sam

    def test_automatic_reference_activates_without_operator_confirmation(self):
        self.automatic_fixture()
        job = self.wait(self.service.start_camera_setup(self.body()))
        self.assertEqual(job["status"], "setup_ready", job)
        self.assertEqual(job["setup_mode"], "automatic")
        self.assertEqual(job["meta_requests"], 3)
        self.assertEqual(self.capture.call_count, 2)
        self.assertNotIn("confirmation", job)
        policy = self.service._camera_policy_path(PLAN)
        self.assertEqual(policy.parent.name, job["automatic_candidate_id"])
        record = json.loads((policy.parent / "review.json").read_text())
        self.assertEqual(record["selection_method"], "registered_and_sam_checked")
        self.runner.assert_not_called()

    def test_sam_boxes_are_published_as_each_call_returns(self):
        self.automatic_fixture()
        sam = self.sam.side_effect
        seen = []
        def spying(body):
            seen.append(copy.deepcopy(next(iter(self.service.jobs.values())).get("proposed_regions")))
            return sam(body)
        self.sam.side_effect = spying
        job = self.wait(self.service.start_camera_setup(self.body()))
        self.assertEqual(job["status"], "setup_ready", job)
        self.assertIsNone(seen[0])
        self.assertEqual(set(seen[1]), {"oled"})
        self.assertEqual(set(job["proposed_regions"]), {"oled", "red", "green"})
        self.assertEqual(job["latest_frame"]["file"], job["source_file"])
        self.assertTrue(self.service.image(job["id"], job["source_file"]).startswith(b"\xff\xd8\xff"))

    def test_changed_view_uses_current_frame_before_asking_for_manual_setup(self):
        self.automatic_fixture()
        self.registration.side_effect = [
            ValueError("The saved view no longer aligns"),
            {**self.registration.return_value, "method": "current_frame_color_and_border"},
        ]
        job = self.wait(self.service.start_camera_setup(self.body()))
        self.assertEqual(job["status"], "setup_ready", job)
        self.assertEqual(job["setup_mode"], "automatic")
        self.assertEqual(self.registration.call_args.kwargs["screen"], [20, 30, 190, 160])
        self.assertEqual(self.capture.call_count, 2)
        policy = self.service._camera_policy_path(PLAN)
        record = json.loads((policy.parent / "review.json").read_text())
        self.assertEqual(record["selection_method"], "located_and_sam_checked")
        self.runner.assert_not_called()

    def test_automatic_validation_failure_allows_separate_manual_candidate(self):
        self.automatic_fixture()
        self.label.return_value = {"status": "unknown"}
        job = self.start()
        self.assertIn("could not qualify a reference", job["setup_note"])
        self.assertEqual(self.service._camera_policy_path(PLAN), self.base)
        self.label.return_value = {"status": "read", "text": "READY"}
        manual = self.wait(self.service.confirm_camera_setup(job["id"], self.confirmation(job)))
        self.assertEqual(manual["setup_mode"], "manual")
        self.assertEqual(self.capture.call_count, 3)
        self.assertEqual(self.service._camera_policy_path(PLAN).parent.name, job["id"])

    def test_sam_lens_disagreement_is_advisory_and_the_validation_capture_decides(self):
        self.automatic_fixture()
        automatic_sam = self.sam.side_effect
        def sam(body):
            result = automatic_sam(body)
            if body["points"]:
                result["regions"].pop("red")
            return result
        self.sam.side_effect = sam
        job = self.wait(self.service.start_camera_setup(self.body()))
        self.assertEqual(job["status"], "setup_ready", job)
        self.assertFalse(job["sam_lens_agreement"])
        self.assertEqual(job["sources"], {"oled": "sam-3.1", "red": "local-vision", "green": "local-vision"})
        record = json.loads((self.service._camera_policy_path(PLAN).parent / "review.json").read_text())
        self.assertEqual(record["selection_method"], "registered_and_sam_checked_sam_unconfirmed")
        self.assertIn("isolate both LED lenses", record["registration"]["sam_lens_note"])

    def test_alignment_tries_older_frames_before_a_second_capture(self):
        self.automatic_fixture()
        good = self.registration.return_value
        self.registration.side_effect = [ValueError("blur"), ValueError("blur"), ValueError("blur"), ValueError("blur"), good]
        job = self.wait(self.service.start_camera_setup(self.body()))
        self.assertEqual(job["status"], "setup_ready", job)
        self.assertEqual(self.capture.call_count, 2)
        self.assertEqual(job["source_file"], "frame-000002.jpg")

    def test_second_capture_when_no_frame_of_the_first_is_usable(self):
        self.automatic_fixture()
        good = self.registration.return_value
        self.registration.side_effect = [ValueError("moving")] * 6 + [good]
        job = self.wait(self.service.start_camera_setup(self.body()))
        self.assertEqual(job["status"], "setup_ready", job)
        self.assertEqual(self.capture.call_count, 3)
        self.assertEqual(job["setup_attempt"], 2)

    def test_blocked_validation_is_retried_once_on_a_fresh_capture(self):
        self.automatic_fixture()
        good = self.reader.side_effect; calls = []
        def reader(run, geometry, frames, output, **kwargs):
            calls.append(run.name)
            if len(calls) == 1:
                return {row["file"]: {"status": "unknown", "error": "Static border pixels do not match reference"} for row in frames}
            return good(run, geometry, frames, output, **kwargs)
        self.reader.side_effect = reader
        job = self.wait(self.service.start_camera_setup(self.body()))
        self.assertEqual(job["status"], "setup_ready", job)
        self.assertEqual(self.capture.call_count, 3)
        self.assertEqual(calls, ["automatic-validation", "automatic-validation-2"])

    def test_nothing_usable_ends_in_review_with_every_attempt_recorded(self):
        self.automatic_fixture()
        self.registration.side_effect = ValueError("no landmarks")
        job = self.start()
        self.assertEqual(self.capture.call_count, 2)
        self.assertEqual(len(job["setup_attempts"]), 6)
        self.assertIn("2 captures", job["setup_note"])
        self.assertEqual(self.service._camera_policy_path(PLAN), self.base)

    def test_tested_plan_can_get_a_new_reference_and_each_test_keeps_its_own(self):
        self.service.jobs["a" * 32] = {"id": "a" * 32, "action": "test", "proposal_id": PLAN, "status": "pass"}
        self.automatic_fixture()
        job = self.wait(self.service.start_camera_setup(self.body()))
        self.assertEqual(job["status"], "setup_ready", job)
        self.assertEqual(job["tests_seen"], ["a" * 32])

    def test_fresh_capture_confirmation_and_independent_validation_persist(self):
        original = self.base.read_bytes()
        job = self.activate()
        self.assertEqual(job["status"], "setup_ready", job)
        self.assertEqual(self.capture.call_count, 3)
        *sources, validation = [call.kwargs["output"] for call in self.capture.call_args_list]
        source = sources[-1]
        self.assertNotEqual(source, validation)
        self.assertNotEqual(digest(source / "frame-000004.jpg"), digest(validation / "frame-000004.jpg"))
        self.assertEqual(job["physical_verification"], "not_performed")
        self.assertEqual(job["serial_commands_sent"], [])
        for action in (self.builder, self.installer, self.runner, self.identity):
            action.assert_not_called()
        self.assertEqual(self.sam.call_count, 6)
        self.label.assert_called_once()
        self.assertEqual(self.base.read_bytes(), original)
        path = self.service._camera_policy_path(PLAN)
        self.assertNotEqual(path, self.base)
        self.assertEqual(self.service._camera_policy_path(OTHER), self.base)
        restarted = self.new_service()
        self.assertEqual(restarted._camera_policy_path(PLAN), path)
        self.assertEqual(restarted.get(job["id"])["status"], "setup_ready")
        proof = json.loads((path.parent / "qualification.json").read_text())["validation"]
        self.assertEqual(proof["frames_checked"], 3)
        self.assertEqual(proof["thresholds"], "inherited_unchanged")

    def test_failed_readability_keeps_existing_profile_and_retains_candidate(self):
        self.label.return_value = {"status": "unknown", "text": None}
        job = self.activate()
        self.assertEqual(job["status"], "setup_blocked")
        self.assertEqual(self.service._camera_policy_path(PLAN), self.base)
        self.assertTrue((self.root / "runs/camera-setup" / job["id"] / "policy.json").is_file())
        self.assertFalse((self.root / "runs/camera-setup/proposals" / (PLAN + ".json")).exists())

    def test_cancel_during_oled_request_cannot_activate(self):
        def cancel_then_read(*args):
            self.service.cancel(self.service.active)
            return {"status": "read", "text": "READY"}
        self.label.side_effect = cancel_then_read
        job = self.activate()
        self.assertEqual(job["status"], "cancelled")
        self.assertEqual(self.service._camera_policy_path(PLAN), self.base)

    def test_cancel_while_waiting_for_confirmation_closes_that_review(self):
        job = self.start()
        self.assertEqual(self.service.cancel(job["id"])["status"], "cancelled")
        with self.assertRaisesRegex(ValueError, "new setup reference"):
            self.service.confirm_camera_setup(job["id"], self.confirmation(job))
        self.assertEqual(self.capture.call_count, 2)

    def test_unknown_native_geometry_stops_before_oled_request(self):
        self.reader.side_effect = lambda run, geometry, frames, output, **kwargs: {
            row["file"]: {"status": "unknown"} for row in frames}
        job = self.activate()
        self.assertEqual(job["status"], "setup_blocked")
        self.assertEqual(self.service._camera_policy_path(PLAN), self.base)
        self.label.assert_not_called()

    def test_test_started_while_dialog_open_blocks_confirmation(self):
        job = self.start()
        self.service.jobs["e" * 32] = {"id": "e" * 32, "action": "test", "proposal_id": PLAN, "status": "incomplete"}
        with self.assertRaisesRegex(ValueError, "after this setup capture"):
            self.service.confirm_camera_setup(job["id"], self.confirmation(job))
        self.assertEqual(self.capture.call_count, 2)
        self.assertFalse((self.root / "runs/camera-setup" / job["id"]).exists())

    def test_repair_cannot_recalibrate_and_uses_parent_reference(self):
        with self.assertRaisesRegex(ValueError, "not a repair"):
            self.service.start_camera_setup(self.body(REPAIR))
        self.capture.assert_not_called()
        self.assertEqual(self.activate()["status"], "setup_ready")
        self.assertEqual(self.service._camera_policy_path(REPAIR), self.service._camera_policy_path(PLAN))

    def test_foreign_frame_hash_and_test_job_cannot_be_confirmed(self):
        job = self.start()
        body = self.confirmation(job)
        body["image_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "confirmed image differs"):
            self.service.confirm_camera_setup(job["id"], body)
        self.service.jobs["f" * 32] = {"action": "test", "status": "fail"}
        with self.assertRaisesRegex(ValueError, "Unknown camera setup"):
            self.service.confirm_camera_setup("f" * 32, self.confirmation(job))
        self.assertEqual(self.capture.call_count, 2)

    def test_sam_failure_tries_every_frame_then_asks_for_review(self):
        self.sam.side_effect = ValueError("Synthetic unavailable model")
        job = self.start()
        self.assertEqual(job["regions"], {})
        self.assertIn("could not isolate the screen", job["setup_note"])
        self.assertEqual(self.sam.call_count, 6)
        self.assertEqual(self.capture.call_count, 2)

    def test_changed_saved_reference_fails_closed_after_restart(self):
        self.assertEqual(self.activate()["status"], "setup_ready")
        path = self.service._camera_policy_path(PLAN)
        (path.parent / "reference.jpg").write_bytes(jpeg(b"changed pixels"))
        with self.assertRaisesRegex(ValueError, "reference changed"):
            self.new_service()._camera_policy_path(PLAN)

    def test_guided_sam_owns_bench_counts_calls_and_retains_source_provenance(self):
        job = self.start()
        points = self.confirmation(job)["points"]
        def outline(body):
            self.assertEqual(self.service.active, job["id"])
            self.assertEqual(body["points"], points)
            self.assertEqual(hashlib.sha256(base64.b64decode(body["image"]["data"])).hexdigest(), job["image_sha256"])
            with self.assertRaises(BusyError):
                self.service.start_camera_setup(self.body(OTHER))
            return self.suggest(body)
        self.sam.side_effect = outline
        result = self.service.suggest_camera_setup(job["id"], {"points": points})
        self.assertEqual(set(result["regions"]), {"red", "green"})
        self.assertIsNone(self.service.active)
        saved = self.service.get(job["id"])
        self.assertEqual(saved["status"], "setup_review")
        self.assertEqual(saved["meta_requests"], 7)
        records = list(self.service._folder(job["id"]).glob("sam-*.json"))
        guided = [json.loads(path.read_text()) for path in records if path.name != "sam-suggestion.json"]
        self.assertEqual(len(guided), 1)
        self.assertEqual(guided[0]["points"], points)
        self.assertEqual(guided[0]["image_sha256"], job["image_sha256"])
        self.assertEqual(guided[0]["result"], result)
        ready = self.wait(self.service.confirm_camera_setup(job["id"], self.confirmation(job)))
        self.assertEqual(ready["status"], "setup_ready")
        self.assertEqual(ready["meta_requests"], 8)  # six screen calls, one guided lens call, one Muse label.
        self.assertEqual(self.sam.call_count, 7)

    def test_guided_sam_cancel_during_model_call_rejects_result_and_confirmation(self):
        job = self.start()
        def cancel_and_return(body):
            self.service.cancel(job["id"])
            return self.suggest(body)
        self.sam.side_effect = cancel_and_return
        with self.assertRaisesRegex(ValueError, "suggestion cancelled"):
            self.service.suggest_camera_setup(job["id"], {"points": self.confirmation(job)["points"]})
        self.assertEqual(self.service.get(job["id"])["status"], "cancelled")
        self.assertIsNone(self.service.active)
        records = [path for path in self.service._folder(job["id"]).glob("sam-*.json")
                   if path.name != "sam-suggestion.json"]
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text())
        self.assertIn("cancelled", record["error"])
        self.assertNotIn("result", record)
        with self.assertRaisesRegex(ValueError, "new setup reference"):
            self.service.confirm_camera_setup(job["id"], self.confirmation(job))

    def test_guided_sam_rejects_invalid_points_and_mutated_source_before_call(self):
        job = self.start()
        invalid = [{"red": [235, 70]}, {"red": [True, 70], "green": [280, 70]},
                   {"red": [320, 70], "green": [280, 70]},
                   {"red": [280, 70], "green": [280, 70]}]
        for points in invalid:
            with self.subTest(points=points), self.assertRaises(ValueError):
                self.service.suggest_camera_setup(job["id"], {"points": points})
        self.assertEqual(self.sam.call_count, 6)
        source = self.service._folder(job["id"]) / "workflow" / job["source_path"]
        source.write_bytes(jpeg(b"changed source"))
        with self.assertRaisesRegex(ValueError, "source image changed"):
            self.service.suggest_camera_setup(job["id"], {"points": self.confirmation(job)["points"]})
        self.assertEqual(self.sam.call_count, 6)

    def test_guided_sam_wrong_image_result_is_retained_as_error(self):
        job = self.start()
        self.sam.side_effect = lambda body: {**self.suggest(body), "image_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "different source image"):
            self.service.suggest_camera_setup(job["id"], {"points": self.confirmation(job)["points"]})
        self.assertEqual(self.service.get(job["id"])["status"], "setup_review")
        self.assertEqual(self.service.get(job["id"])["meta_requests"], 7)
        self.assertIsNone(self.service.active)


class CameraSetupHTTPTests(CameraSetupFixture):
    def setUp(self):
        super().setUp()
        self.server = DashboardServer(0, EvidenceStore(self.root, ()), self.planner,
                                      self.service, Mock())
        self.http_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.http_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.http_thread.join(2)
        super().tearDown()

    def request(self, path, body=None, authorized=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers.update(Origin="http://127.0.0.1:" + str(self.server.server_port))
            headers["X-SparkBench-Session"] = self.server.session_token
        connection.request("POST" if body is not None else "GET", path,
                           json.dumps(body) if body is not None else None, headers)
        reply = connection.getresponse()
        status, value = reply.status, reply.read()
        connection.close()
        return status, value

    def test_http_setup_and_confirmation_require_local_session(self):
        for route in ("/api/camera/setup", "/api/camera/setup/" + "d" * 32 + "/confirm",
                      "/api/camera/setup/" + "d" * 32 + "/regions"):
            with self.subTest(route=route):
                self.assertEqual(self.request(route, {}, authorized=False)[0], 403)
        self.capture.assert_not_called()

    def test_http_rejects_injected_source_and_ignores_no_test_evidence(self):
        request = self.body()
        request["source_job_id"] = "f" * 32
        status, _ = self.request("/api/camera/setup", request)
        self.assertEqual(status, 400)
        self.capture.assert_not_called()
        status, value = self.request("/api/camera/setup", self.body())
        self.assertEqual(status, 202)
        job = self.wait(json.loads(value)["id"])
        confirmation = self.confirmation(job)
        confirmation["source_path"] = "/tmp/failed-test/frame-000001.jpg"
        self.assertEqual(self.request("/api/camera/setup/" + job["id"] + "/confirm", confirmation)[0], 400)
        self.assertEqual(self.capture.call_count, 2)
        self.assertEqual(self.service._camera_policy_path(PLAN), self.base)

    def test_http_confirmation_routes_to_fresh_validation(self):
        status, value = self.request("/api/camera/setup", self.body())
        self.assertEqual(status, 202)
        job = self.wait(json.loads(value)["id"])
        status, value = self.request("/api/camera/setup/" + job["id"] + "/confirm", self.confirmation(job))
        self.assertEqual(status, 202)
        self.assertEqual(self.wait(json.loads(value)["id"])["status"], "setup_ready")
        status, image = self.request("/api/camera/reference/" + PLAN)
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(image).hexdigest(), job["image_sha256"])

    def test_http_guided_sam_uses_saved_source_and_rejects_supplied_image(self):
        job = self.start()
        path = "/api/camera/setup/" + job["id"] + "/regions"
        body = {"points": self.confirmation(job)["points"]}
        injected = {**body, "image": {"name": "failed-test.jpg", "data": base64.b64encode(jpeg()).decode()}}
        self.assertEqual(self.request(path, injected)[0], 400)
        self.assertEqual(self.sam.call_count, 6)
        status, value = self.request(path, body)
        self.assertEqual(status, 200)
        result = json.loads(value)
        self.assertEqual(result["image_sha256"], job["image_sha256"])
        self.assertEqual(set(result["regions"]), {"red", "green"})
        self.assertEqual(self.service.get(job["id"])["meta_requests"], 7)
        self.assertEqual(self.capture.call_count, 2)


if __name__ == "__main__":
    unittest.main()
