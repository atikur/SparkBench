"""Repair orchestration with synthetic bench adapters; no physical or model proof.

Real proposal/contract, artifact and workflow integrity code runs in temporary
directories. Hardware capture, image interpretation, compilation, installation
and Contributor transport are explicitly mocked.
"""
import copy
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from sparkbench.artifacts import build_artifact, load_artifact
from sparkbench.dashboard.execution import ExecutionService
from sparkbench.dashboard.planning import BusyError, PlanningService
from sparkbench.intent import fingerprint, save
from sparkbench.mapping_repair import propose_mapping
from sparkbench.meta import Config
from sparkbench.runtime_io import identity
from sparkbench.vision import digest
from test_mapping_repair import NORMAL, SWAPPED, discovery, reply, response


PARENT = "a" * 32
PORT = "/dev/synthetic-repair"
CAMERA = "synthetic-iphone"
PLAN = {"schema_version": 1, "mapping": NORMAL, "steps": [
    {"red": False, "green": True, "text": "READY"},
    {"red": True, "green": False, "text": "BUSY"},
    {"red": False, "green": False, "text": "DONE"},
]}


def seal(folder):
    save(folder / "integrity.json", {"sha256": {
        str(p.relative_to(folder)): digest(p) for p in sorted(folder.rglob("*"))
        if p.is_file() and p != folder / "integrity.json"}})


class MappingRepairExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.planner = PlanningService(self.root / "plans")
        parent = self.planner.directory / PARENT
        parent.mkdir(parents=True)
        save(parent / "plan.json", PLAN)
        save(parent / "result.json", {"status": "ready", "instruction": "READY green, BUSY red, DONE off",
             "proposal": {"decision": "ready", "summary": "Three status steps", "question": None,
                          "steps": copy.deepcopy(PLAN["steps"])},
             "plan_sha256": fingerprint(PLAN), "review_status": "pending"})
        seal(parent)
        self.planner.review(PARENT, fingerprint(PLAN))
        (self.root / "hardware").mkdir()
        (self.root / "old.bin").write_bytes(b"synthetic prior firmware")
        save(self.root / "hardware/board.json", {"active_firmware": {
            "application_binary": "old.bin", "firmware_sha256": digest(self.root / "old.bin")}})
        self.policy_path = self.root / "hardware/oled-reader.policy.json"
        self.calibration = self.root / "calibration.json"
        save(self.policy_path, {"calibration": "calibration.json", "test_fixture": "synthetic reader policy"})
        save(self.calibration, {"camera_id": CAMERA, "fixture": "synthetic geometry"})
        self.patches = [patch("sparkbench.dashboard.repair.check_policy", side_effect=self.policy),
                        patch("sparkbench.dashboard.execution.check_policy", side_effect=self.policy)]
        for item in self.patches: item.start()
        self.store = Mock(catalog={})
        self.runs = {}
        self.store.load.side_effect = lambda name: copy.deepcopy(self.runs[name])
        self.builder = Mock(side_effect=self.build)
        self.installer = Mock(side_effect=self.install)
        self.runner = Mock(side_effect=self.capture_test)
        self.probe_runner = Mock(side_effect=self.capture_probe)
        self.probe_analyzer = Mock(side_effect=self.analyze_probe)
        self.meta_post = Mock(return_value=response())
        self.mapping_proposer = Mock(side_effect=lambda current, data, out: propose_mapping(
            current, data, out, config=Config("synthetic-private-key", "muse-spark-1.3-contributor"), post=self.meta_post))
        self.probe_data = discovery()
        self.test_verdict = "fail"
        self.test_contracts = []
        self.service = ExecutionService(self.root, self.planner, self.store,
            builder=self.builder, installer=self.installer, runner=self.runner,
            enumerate_devices=lambda: {"ports": [{"id": PORT}], "cameras": [{"id": CAMERA}]},
            identity_checker=Mock(return_value={"status": "pass", "scope": "synthetic UART only"}),
            probe_runner=self.probe_runner, probe_analyzer=self.probe_analyzer,
            mapping_proposer=self.mapping_proposer)
        self.service._repair_preflight = Mock()
        self.build_job = self.run_action("compile")
        self.assertEqual(self.build_job["status"], "compiled")
        self.assertEqual(self.run_action("install", build=self.build_job)["status"], "installed")
        self.failed = self.run_action("test", build=self.build_job)
        self.assertEqual(self.failed["status"], "fail")

    def tearDown(self):
        self.service.shutdown()
        if self.service.thread: self.service.thread.join(5)
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def policy(self, path):
        return json.loads(Path(path).read_text()), self.calibration

    def build(self, plan, out):
        artifact = build_artifact(plan, out, compile_firmware=False)
        binary = out / "project/.pio/build/classic-led-oled-runtime/firmware.bin"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"synthetic binary for " + fingerprint(plan).encode())
        artifact.update(status="compiled", firmware=str(binary.relative_to(out)),
                        firmware_sha256=digest(binary), firmware_bytes=binary.stat().st_size)
        save(out / "artifact.json", artifact)
        return artifact

    def install(self, artifact_path, port, previous, previous_sha, out):
        self.assertEqual(port, PORT)
        self.assertEqual(digest(previous), previous_sha)
        _, artifact = load_artifact(artifact_path)
        out.mkdir()
        (out / "application.bin").write_bytes((artifact_path / artifact["firmware"]).read_bytes())
        save(out / "installation.json", {"status": "installed_hash_verified", "fixture": "mock installation"})
        return {"status": "installed_hash_verified"}

    def capture_test(self, port, camera, out, policy, spec, *, artifact_path, cancel, on_stage, analyzer):
        self.assertEqual((port, camera), (PORT, CAMERA))
        on_stage("capture")
        contract = json.loads(spec.read_text())
        self.test_contracts.append(copy.deepcopy(contract))
        _, artifact = load_artifact(artifact_path)
        (out / "analysis").mkdir(parents=True)
        (out / "capture").mkdir()
        save(out / "spec.snapshot.json", contract)
        save(out / "reader-policy.snapshot.json", json.loads(policy.read_text()))
        save(out / "analysis/calibration.snapshot.json", json.loads(self.calibration.read_text()))
        save(out / "analysis/verification.json", {"status": self.test_verdict, "fixture": "mock camera verifier"})
        save(out / "capture/run.json", {"action": "VISUAL", "source": "live_hardware", "fixture": "synthetic adapter",
            "status": "completed", "plan_sha256": artifact["plan_sha256"], "firmware_sha256": artifact["firmware_sha256"],
            "device_id": camera, "port": port, "identity": identity(artifact["plan_sha256"]), "servo_actuation": False,
            "sequence_started": True, "stop_acknowledged_uart_only": True})
        frames = []
        for step in contract["steps"]:
            expected = {k: step[k] for k in ("red", "green", "oled_text")}
            observed = dict(expected)
            if self.test_verdict == "fail": observed.update(red=expected["green"], green=expected["red"])
            frames.append({"evaluated": True, "geometry_supported": True, "expected": expected, "observed": observed})
        self.runs["test-" + out.parent.name] = {"behavior_verdict": self.test_verdict, "frames": frames}
        seal(out)
        return {"status": self.test_verdict, "failures": 4 if self.test_verdict == "fail" else 0, "unknowns": 0}

    def capture_probe(self, port, camera, artifact_path, out, *, action, cancel):
        self.assertEqual((port, camera, action), (PORT, CAMERA, "DISCOVER"))
        out.mkdir(parents=True)
        _, artifact = load_artifact(artifact_path)
        result = {"status": "completed", "source": "live_hardware", "fixture": "synthetic probe",
                  "action": action, "device_id": camera, "plan_sha256": artifact["plan_sha256"],
                  "port": port, "identity": identity(artifact["plan_sha256"]), "servo_actuation": False,
                  "firmware_sha256": artifact["firmware_sha256"], "sequence_started": True,
                  "stop_acknowledged_uart_only": True}
        save(out / "run.json", result)
        return result

    def analyze_probe(self, capture, policy, out):
        out.mkdir(parents=True)
        value = copy.deepcopy(self.probe_data)
        value.update(source_run=str(capture.resolve()), calibration_sha256=digest(self.calibration))
        save(out / "discovery.json", value)
        seal(out)
        return value

    def wait(self, job_id):
        for _ in range(500):
            result = self.service.get(job_id)
            if result["status"] != "running":
                if self.service.thread: self.service.thread.join(5)
                return self.service.get(job_id)
            time.sleep(.005)
        self.fail("Synthetic job did not finish")

    def run_action(self, action, *, proposal=None, build=None):
        proposal = proposal or self.planner.get(PARENT)
        body = {"proposal_id": proposal["id"], "plan_sha256": proposal["plan_sha256"], "request_id": uuid.uuid4().hex}
        if action != "compile": body.update(build_id=build["id"], port=PORT)
        if action == "test": body["device_id"] = CAMERA
        return self.wait(self.service.start(action, body))

    def repair_body(self):
        return {"source_test_id": self.failed["id"], "port": PORT, "device_id": CAMERA, "request_id": uuid.uuid4().hex}

    def repair(self):
        return self.wait(self.service.start_repair(self.repair_body()))

    def approve(self, repair):
        return self.service.approve_repair(repair["id"], {"plan_sha256": repair["candidate_plan_sha256"]})

    def test_full_chain_requires_approval_and_retests_same_contract_with_new_binary(self):
        contract_bytes = (self.planner.directory / PARENT / "contract.json").read_bytes()
        old_hash = self.build_job["firmware_sha256"]
        repair = self.repair()
        self.assertEqual(repair["status"], "repair_ready", repair.get("error"))
        self.assertEqual(self.builder.call_count, 1)
        self.assertEqual(self.installer.call_count, 1)
        self.assertEqual(self.runner.call_count, 1)
        self.assertEqual(self.meta_post.call_count, 1)
        candidate = self.planner.get(repair["candidate_proposal_id"])
        self.assertEqual(candidate["review_status"], "pending")
        self.assertEqual(candidate["mapping"], SWAPPED)
        self.assertEqual(candidate["contract_sha256"], self.failed["contract_sha256"])
        self.assertEqual((self.planner.directory / candidate["id"] / "contract.json").read_bytes(), contract_bytes)
        self.assertEqual(candidate["proposal"]["steps"], PLAN["steps"])
        with self.assertRaises(ValueError): self.run_action("compile", proposal=candidate)
        approved = self.approve(repair)
        self.assertEqual(self.installer.call_count, 1, "Approval itself cannot install")
        new_build = self.run_action("compile", proposal=approved)
        self.assertEqual(new_build["status"], "compiled", new_build.get("error"))
        self.assertNotEqual(new_build["firmware_sha256"], old_hash)
        installation = self.run_action("install", proposal=approved, build=new_build)
        self.assertEqual(installation["status"], "installed", installation.get("error"))
        self.assertEqual(installation["physical_verification"], "not_performed")
        self.test_verdict = "pass"
        test = self.run_action("test", proposal=approved, build=new_build)
        self.assertEqual(test["status"], "pass", test.get("error"))
        self.assertTrue(test["repair_verified"])
        self.assertEqual(test["source_test_id"], self.failed["id"])
        self.assertEqual(test["contract_sha256"], self.failed["contract_sha256"])
        self.assertEqual(self.test_contracts[0], self.test_contracts[1])
        self.assertEqual(self.service.get(self.failed["id"])["status"], "fail")

    def test_generic_proposal_review_cannot_bypass_mapping_approval(self):
        repair = self.repair()
        candidate = self.planner.review(repair["candidate_proposal_id"], repair["candidate_plan_sha256"])
        self.assertEqual(candidate["review_status"], "reviewed")
        with self.assertRaisesRegex(ValueError, "Approve the mapping repair"):
            self.run_action("compile", proposal=candidate)
        self.assertEqual(self.builder.call_count, 1)
        self.assertEqual(self.installer.call_count, 1)

    def test_unchanged_mapping_produces_no_candidate_or_install(self):
        self.probe_data = discovery(NORMAL)
        self.meta_post.return_value = response(reply(NORMAL))
        result = self.repair()
        self.assertEqual(result["status"], "no_change")
        self.assertNotIn("candidate_proposal_id", result)
        self.assertEqual(self.installer.call_count, 1)
        self.assertEqual(self.meta_post.call_count, 1)

    def test_incomplete_probe_never_calls_model_or_builds_candidate(self):
        self.probe_data["windows"][1]["measurements"][0]["green"] = None
        result = self.repair()
        self.assertEqual(result["status"], "incomplete")
        self.mapping_proposer.assert_not_called()
        self.meta_post.assert_not_called()
        self.assertNotIn("candidate_proposal_id", result)
        self.assertEqual(self.builder.call_count, 1)
        self.assertEqual(self.installer.call_count, 1)

    def test_blocked_preflight_never_probes_or_requests_model(self):
        self.service._repair_preflight.side_effect = ValueError("Camera preflight blocked")
        result = self.repair()
        self.assertEqual(result["status"], "incomplete")
        self.probe_runner.assert_not_called()
        self.mapping_proposer.assert_not_called()
        self.assertIsNone(self.service.active)

    def test_cancelled_probe_releases_lock_without_model_or_candidate(self):
        entered = threading.Event()
        def probe(*args, **kwargs):
            entered.set()
            self.assertTrue(kwargs["cancel"].wait(3))
            return self.capture_probe(*args, **kwargs)
        self.probe_runner.side_effect = probe
        job_id = self.service.start_repair(self.repair_body())
        self.assertTrue(entered.wait(2))
        with self.assertRaises(BusyError): self.run_action("compile")
        self.service.cancel(job_id)
        result = self.wait(job_id)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["shutdown"], "acknowledged_uart_only")
        self.mapping_proposer.assert_not_called()
        self.assertIsNone(self.service.active)
        self.assertEqual(self.run_action("compile")["status"], "compiled")

    def test_single_attempt_and_request_deduplication_survive_reload(self):
        body = self.repair_body()
        job_id = self.service.start_repair(body)
        self.assertEqual(self.service.start_repair(body), job_id)
        self.assertEqual(self.wait(job_id)["status"], "repair_ready")
        self.assertEqual(self.service.start_repair(body), job_id)
        with self.assertRaisesRegex(ValueError, "already recorded"):
            self.service.start_repair(self.repair_body())
        with self.assertRaisesRegex(ValueError, "already used"):
            self.service.start_repair({**body, "device_id": "different-camera"})
        self.assertEqual(self.probe_runner.call_count, 1)
        self.assertEqual(self.meta_post.call_count, 1)
        fresh = ExecutionService(self.root, self.planner, self.store, enumerate_devices=Mock())
        self.assertEqual(fresh.start_repair(body), job_id)
        self.assertIsNone(fresh.active)
        self.assertFalse(fresh.repair_eligibility(self.failed["id"])["eligible"])

    def test_unknown_led_geometry_and_oled_only_failure_cannot_trigger_probe(self):
        original = copy.deepcopy(self.runs["test-" + self.failed["id"]])
        for case in ("unknown", "geometry", "oled_only"):
            with self.subTest(case=case):
                run = copy.deepcopy(original)
                if case == "unknown": run["frames"][0]["observed"]["red"] = None
                elif case == "geometry": run["frames"][0]["geometry_supported"] = False
                else:
                    for row in run["frames"]:
                        row["observed"] = {**row["expected"], "oled_text": "WRONG"}
                self.runs["test-" + self.failed["id"]] = run
                self.assertFalse(self.service.repair_eligibility(self.failed["id"])["eligible"])
                with self.assertRaises(ValueError): self.service.start_repair(self.repair_body())
        self.probe_runner.assert_not_called()
        self.mapping_proposer.assert_not_called()

    def test_changed_policy_blocks_approval_and_keeps_original_failed_result(self):
        repair = self.repair()
        policy = json.loads(self.policy_path.read_text())
        policy["changed"] = True
        save(self.policy_path, policy)
        with self.assertRaisesRegex(ValueError, "policy or calibration changed"):
            self.approve(repair)
        self.assertEqual(self.installer.call_count, 1)
        self.assertEqual(self.service.get(self.failed["id"])["status"], "fail")

    def test_source_test_bytes_and_parent_plan_changes_block_approval(self):
        repair = self.repair()
        source_file = self.service._folder(self.failed["id"]) / "workflow/analysis/verification.json"
        source_file.write_text('{"status":"pass"}')
        with self.assertRaisesRegex(ValueError, "Evidence changed"):
            self.approve(repair)
        self.assertEqual(self.installer.call_count, 1)
        parent_plan = self.planner.directory / PARENT / "plan.json"
        plan = json.loads(parent_plan.read_text()); plan["steps"][0]["text"] = "CHANGED"
        save(parent_plan, plan)
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.approve(repair)

    def test_newer_original_test_or_changed_installed_image_invalidates_failure(self):
        self.test_verdict = "pass"
        newer = self.run_action("test", build=self.build_job)
        self.assertEqual(newer["status"], "pass")
        with self.assertRaisesRegex(ValueError, "newer test"):
            self.service.start_repair(self.repair_body())
        self.service.jobs.pop(newer["id"])
        board_path = self.root / "hardware/board.json"
        board = json.loads(board_path.read_text())
        board["active_firmware"].update(application_binary="old.bin", firmware_sha256=digest(self.root / "old.bin"))
        save(board_path, board)
        with self.assertRaisesRegex(ValueError, "installed firmware changed"):
            self.service.start_repair(self.repair_body())
        self.probe_runner.assert_not_called()

    def test_model_disagreement_never_produces_an_approvable_candidate(self):
        self.meta_post.return_value = response(reply(NORMAL))
        result = self.repair()
        self.assertEqual(result["status"], "invalid_response")
        self.assertNotIn("candidate_proposal_id", result)
        self.assertEqual(self.installer.call_count, 1)

    def test_approved_candidate_still_rechecks_policy_before_compilation(self):
        repair = self.repair(); approved = self.approve(repair)
        calibration = json.loads(self.calibration.read_text()); calibration["changed"] = True
        save(self.calibration, calibration)
        with self.assertRaisesRegex(ValueError, "policy or calibration changed"):
            self.run_action("compile", proposal=approved)
        self.assertEqual(self.builder.call_count, 1)

    def test_resealed_failed_capture_cannot_cross_device_action_or_firmware_boundaries(self):
        workflow = self.service._folder(self.failed["id"]) / "workflow"
        capture_path = workflow / "capture/run.json"
        original = json.loads(capture_path.read_text())
        changes = {"status": "incomplete", "source": "synthetic", "action": "DISCOVER",
                   "servo_actuation": True, "identity": identity("e" * 64), "port": "/dev/another-board",
                   "device_id": "another-camera", "plan_sha256": "e" * 64, "firmware_sha256": "f" * 64}
        for key, value in changes.items():
            with self.subTest(key=key):
                save(capture_path, {**original, key: value})
                seal(workflow)  # Valid checksums alone do not establish correct capture binding.
                with self.assertRaisesRegex(ValueError, "Capture is not bound"):
                    self.service.start_repair(self.repair_body())
        save(capture_path, original); seal(workflow)
        self.assertTrue(self.service.repair_eligibility(self.failed["id"])["eligible"])
        self.probe_runner.assert_not_called()
        self.mapping_proposer.assert_not_called()

    def test_crossbound_probe_capture_stops_before_analysis_or_model(self):
        def wrong_camera(*args, **kwargs):
            capture = self.capture_probe(*args, **kwargs)
            capture["device_id"] = "different-camera"
            save(args[3] / "run.json", capture)
            return capture
        self.probe_runner.side_effect = wrong_camera
        result = self.repair()
        self.assertEqual(result["status"], "incomplete")
        self.assertIn("Capture is not bound", result["error"])
        self.probe_analyzer.assert_not_called()
        self.mapping_proposer.assert_not_called()

    def test_discovery_from_another_capture_cannot_request_model(self):
        def wrong_source(*args):
            result = self.analyze_probe(*args)
            result["source_run"] = str(self.root / "another-capture")
            save(args[2] / "discovery.json", result); seal(args[2])
            return result
        self.probe_analyzer.side_effect = wrong_source
        result = self.repair()
        self.assertEqual(result["status"], "incomplete")
        self.assertIn("does not match this capture", result["error"])
        self.mapping_proposer.assert_not_called()

    def test_discovery_from_another_calibration_cannot_request_model(self):
        def wrong_calibration(*args):
            result = self.analyze_probe(*args)
            result["calibration_sha256"] = "9" * 64
            save(args[2] / "discovery.json", result); seal(args[2])
            return result
        self.probe_analyzer.side_effect = wrong_calibration
        result = self.repair()
        self.assertEqual(result["status"], "incomplete")
        self.assertIn("does not match this capture", result["error"])
        self.mapping_proposer.assert_not_called()

    def test_resealed_probe_capture_cannot_be_rebound_before_approval(self):
        repair = self.repair()
        folder = self.service._folder(repair["id"]) / "repair"
        capture_path = folder / "capture/run.json"
        capture = json.loads(capture_path.read_text())
        capture["port"] = "/dev/different-board"
        save(capture_path, capture); seal(folder)
        with self.assertRaisesRegex(ValueError, "Capture is not bound"):
            self.approve(repair)
        self.assertEqual(self.installer.call_count, 1)

    def test_nonobject_failed_capture_is_refused_without_worker_or_probe(self):
        workflow = self.service._folder(self.failed["id"]) / "workflow"
        capture_path = workflow / "capture/run.json"
        for value in (None, []):
            with self.subTest(value=value):
                save(capture_path, value); seal(workflow)
                self.assertFalse(self.service.repair_eligibility(self.failed["id"])["eligible"])
                with self.assertRaises(ValueError): self.service.start_repair(self.repair_body())
                self.assertIsNone(self.service.active)
        self.probe_runner.assert_not_called()

    def test_nonobject_probe_journal_stops_and_releases_the_bench(self):
        def malformed_probe(*args, **kwargs):
            self.capture_probe(*args, **kwargs)
            save(args[3] / "run.json", None)
            return None
        self.probe_runner.side_effect = malformed_probe
        result = self.repair()
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(self.service.active)
        self.mapping_proposer.assert_not_called()
        self.assertEqual(self.run_action("compile")["status"], "compiled")


if __name__ == "__main__": unittest.main()
