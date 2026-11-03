"""Offline, synthetic control-layer regressions. No hardware/API access."""
import copy
import io
import json
import shutil
import subprocess
import tempfile
import unittest
import itertools
import importlib.util
import platform
from pathlib import Path
from unittest.mock import Mock, patch

from sparkbench.artifacts import build_artifact, load_artifact
from sparkbench.camera import ROOT
from sparkbench.discovery import infer, probe_windows
from sparkbench.generation import generate
from sparkbench.meta import Config
from sparkbench.plans import expected_plan, render_header, validate_against_spec, validate_plan
from sparkbench.policy import check_policy
from sparkbench.runtime_io import RuntimeJournal
from sparkbench.workflow import execute
from sparkbench.verify import verify_trace

SPEC = json.loads((ROOT / "specs/led_oled_only.json").read_text())
MAPPING = {"red": 25, "green": 26}
PLAN = expected_plan(SPEC, MAPPING)


class PlanTests(unittest.TestCase):
    def test_no_extra_code_paths_pins_or_durations(self):
        bad = []
        for key, value in (("source", "digitalWrite(27,HIGH)"), ("duration_ms", 999999), ("servo", True)):
            p = copy.deepcopy(PLAN); p[key] = value; bad.append(p)
        for mapping in ({"red": 27, "green": 26}, {"red": 25, "green": 25}, {"red": True, "green": 26}):
            p = copy.deepcopy(PLAN); p["mapping"] = mapping; bad.append(p)
        for text in ('X"}; system("bad");', "A\nRUN", "A" * 17, "", "ümlaut", "A\n"):
            p = copy.deepcopy(PLAN); p["steps"][0]["text"] = text; bad.append(p)
        p = copy.deepcopy(PLAN); p["steps"] *= 2; bad.append(p)
        p = copy.deepcopy(PLAN); p["steps"][0]["red"] = 1; bad.append(p)
        for plan in bad:
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                validate_plan(plan)

    def test_wrong_behavior_is_rejected_separately_from_schema(self):
        p = copy.deepcopy(PLAN); p["steps"][1]["text"] = "WRONG"
        validate_plan(p)
        with self.assertRaises(ValueError):
            validate_against_spec(p, SPEC, MAPPING)
        with self.assertRaises(ValueError):
            expected_plan(json.loads((ROOT / "specs/behavior_a.json").read_text()), MAPPING)

    def test_mapping_changes_rendered_physical_pins_without_changing_spec(self):
        p = copy.deepcopy(PLAN); p["mapping"] = {"red": 26, "green": 25}
        self.assertIn('{false, true, "RED"}', render_header(p))
        self.assertIn('{true, false, "GREEN"}', render_header(p))

    def test_artifact_rejects_tampered_header_and_trusted_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"artifact"
            build_artifact(PLAN, path, False)
            self.assertEqual(load_artifact(path, False)[0], PLAN)
            with self.assertRaises(ValueError):
                load_artifact(path)  # Rendered does not imply compiled.
            (path/"project/include/plan_data.h").write_text("untrusted code")
            with self.assertRaises(ValueError):
                load_artifact(path, False)

    def test_rehashing_modified_trusted_source_does_not_make_it_acceptable(self):
        from sparkbench.vision import digest
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"artifact"; build_artifact(PLAN, path, False)
            source = path/"project/src/main.cpp"
            source.write_text(source.read_text()+"\n// unauthorized runtime edit\n")
            record = json.loads((path/"artifact.json").read_text())
            record["inputs_sha256"]["project/src/main.cpp"] = digest(source)
            record["trusted_runtime_sha256"]["src/main.cpp"] = digest(source)
            (path/"artifact.json").write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                load_artifact(path, False)

    def test_full_behavior_cannot_pass_without_measured_servo_angles(self):
        spec = json.loads((ROOT/"specs/behavior_a.json").read_text())
        trace = json.loads((ROOT/"examples/synthetic_behavior_a.json").read_text())
        for step in trace["measurements"]:
            step["angle_deg"] = None
        self.assertEqual(verify_trace(spec, trace)["status"], "incomplete")


def response(plan, status=200):
    reply = Mock(status_code=status)
    reply.json.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(plan)}}]}
    return reply


class GenerationTests(unittest.TestCase):
    def test_wrong_behavior_then_bounded_repair_and_original_preserved(self):
        wrong = copy.deepcopy(PLAN); wrong["steps"][0]["red"] = True
        post = Mock(side_effect=[response(wrong), response(PLAN)])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"generation"
            result = generate(ROOT/"specs/led_oled_only.json", MAPPING, output, config=Config("private-test-key", "muse-spark-1.3-contributor"), post=post, compile_firmware=False)
            self.assertEqual(result["status"], "rendered")
            self.assertEqual(post.call_count, 2)
            self.assertEqual(result["attempts"][0]["status"], "rejected")
            self.assertEqual(json.loads((output/"attempt-01/response.json").read_text())["choices"][0]["message"]["content"], json.dumps(wrong))
            self.assertFalse(post.call_args.kwargs["allow_redirects"])
            for file in output.rglob("*.json"):
                self.assertNotIn("private-test-key", file.read_text())

    def test_invalid_forever_stops_at_budget_and_service_errors_never_retry(self):
        for status, expected_calls in ((200, 2), (401, 1), (429, 1), (500, 1), (302, 1)):
            with tempfile.TemporaryDirectory() as directory:
                post = Mock(return_value=response({"source": "bad"}, status))
                result = generate(ROOT/"specs/led_oled_only.json", MAPPING, Path(directory)/"out", config=Config("key"), post=post, compile_firmware=False)
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(post.call_count, expected_calls)

    def test_unsupported_spec_and_unbounded_budget_make_no_request(self):
        post = Mock()
        with tempfile.TemporaryDirectory() as directory:
            for spec, budget in ((ROOT/"specs/behavior_a.json", 1), (ROOT/"specs/led_oled_only.json", 3)):
                with self.assertRaises(ValueError):
                    generate(spec, MAPPING, Path(directory)/"out", max_repairs=budget, config=Config("key"), post=post)
        post.assert_not_called()


def windows(mapping=MAPPING):
    result = []
    for i, pin in enumerate((None, 25, None, 26, None)):
        result.append({"step": i+1, "start": 10*i, "end": 10*i+2,
            "measurements": [{"sample_pts_seconds": 10*i+j*.4,
                              **{c: mapping[c] == pin for c in ("red", "green")}}
                             for j in range(6)]})
    return result


class DiscoveryTests(unittest.TestCase):
    def test_infers_both_mappings_from_responses_not_expected_wiring(self):
        for mapping in (MAPPING, {"red": 26, "green": 25}):
            result = infer(windows(mapping), "synthetic")
            self.assertEqual(result["mapping"], mapping)
            self.assertFalse(result["automatic_camera_mapping"])

    def test_unknown_unstable_missing_temporal_gap_baseline_and_crosstalk_never_guess(self):
        cases = []
        w = windows(); w[1]["measurements"][0]["red"] = None; cases.append(w)
        w = windows(); w[1]["measurements"][0]["red"] = False; cases.append(w)
        w = windows(); w[0]["measurements"][0]["green"] = True; cases.append(w)
        w = windows(); w[1]["measurements"][0]["green"] = True; cases.append(w)
        w = windows(); w[2]["measurements"] = []; cases.append(w)
        w = windows(); w[2]["measurements"][1]["sample_pts_seconds"] += .9; cases.append(w)
        cases.append(windows()[:-1])
        for w in cases:
            with self.subTest(w=w):
                result = infer(w, "synthetic")
                self.assertIsNone(result["mapping"])
                self.assertEqual(result["status"], "incomplete")

    def test_uart_values_do_not_supply_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            rows = [{"kind": "tx", "command": "DISCOVER"}]
            rows += [{"kind": "rx_line", "line": f"VISUAL_STEP:{i+1} RED:1 GREEN:1 TEXT:WRONG UPTIME_MS:1", "host_uptime_seconds": 10+i*3.2} for i in range(5)]
            rows += [{"kind": "rx_line", "line": "VISUAL_STOPPED STATUS:COMPLETE RED:0 GREEN:0", "host_uptime_seconds": 26}]
            (run/"uart.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
            self.assertEqual(len(probe_windows(run, [])), 5)
            rows.insert(0, {"kind": "tx", "command": "RUN"})
            (run/"uart.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
            with self.assertRaises(ValueError):
                probe_windows(run, [])


class AcquisitionTests(unittest.TestCase):
    def test_runtime_start_gate_allowlist_and_once_only(self):
        connection = Mock(); journal = RuntimeJournal(connection, io.StringIO(), "DISCOVER")
        for command in ("RUN", "VISUAL", "DISCOVER", "PING", "DISCOVER\nRUN"):
            with self.assertRaises(ValueError):
                journal.send(command)
        connection.write.assert_not_called()
        journal.verified = journal.camera_ready = True
        journal.send("DISCOVER"); journal.send("PING"); journal.send("STOP")
        with self.assertRaises(ValueError):
            journal.send("DISCOVER")

    def test_changed_policy_fails_before_any_capture_or_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"policy.json"
            policy = json.loads((ROOT/"hardware/oled-reader.policy.json").read_text())
            policy["analyzer_source_sha256"] = "changed"; path.write_text(json.dumps(policy))
            with patch("sparkbench.led_oled.run") as acquire, patch("sparkbench.workflow.analyze") as analyze:
                with self.assertRaises(ValueError):
                    execute("port", "camera", Path(directory)/"out", path, ROOT/"specs/led_oled_only.json")
            acquire.assert_not_called(); analyze.assert_not_called()

    @unittest.skipUnless((ROOT / "runs/vision/calibration-meta-2026-10-30-v3/calibration.json").is_file(),
                         "Private camera calibration is not included in source-only snapshots")
    def test_real_frozen_policy_still_matches_without_credential_read(self):
        policy, calibration = check_policy(ROOT/"hardware/oled-reader.policy.json", model="muse-spark-1.3-contributor")
        self.assertTrue(calibration.is_file())

    def test_wrong_runtime_identity_cannot_start_camera_or_outputs(self):
        from sparkbench.runtime_io import acquire
        port = Mock(device="/dev/test", vid=0x10C4, pid=0xEA60, hwid="synthetic")
        connection = Mock(is_open=True, in_waiting=1)
        connection.read.return_value = b"SPARKBENCH RIG_TEST MODE:IDLE OLED:ACK\nVISUAL_ALIVE UPTIME_MS:1000 MODE:IDLE\n"
        with tempfile.TemporaryDirectory() as directory, \
                patch("serial.tools.list_ports.comports", return_value=[port]), \
                patch("serial.Serial", return_value=connection), \
                patch("sparkbench.runtime_io.load_artifact", return_value=(PLAN, {"plan_sha256": "a"*64, "firmware_sha256": "b"*64})), \
                patch("sparkbench.runtime_io.build_helper", return_value=Path("helper")), \
                patch("sparkbench.runtime_io.time.monotonic", side_effect=itertools.count(0, .2)), \
                patch("sparkbench.runtime_io.subprocess.Popen") as camera:
            result = acquire("/dev/test", "explicit-camera", Path("artifact"), Path(directory)/"out")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["serial_commands_sent"], ["ID"])
        connection.write.assert_called_once_with(b"ID\n")
        camera.assert_not_called()

    def test_combined_workflow_uses_frozen_spec_and_preserves_missing_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Different whitespace must not be mistaken for spec mutation.
            spec_path = root/"spec.json"; spec_path.write_text(json.dumps(SPEC, separators=(",", ":")))
            def analysis(run, calibration, spec, output):
                self.assertEqual(json.loads(spec.read_text()), SPEC)
                output.mkdir()
                return {"status": "incomplete", "failures": [], "unknowns": ["missing text"]}
            with patch("sparkbench.workflow.check_policy", return_value=({"model": "muse-spark-1.3-contributor"}, root/"calibration.json")), \
                    patch("sparkbench.workflow.require_coverage"), \
                    patch("sparkbench.workflow.analyze", side_effect=analysis), \
                    patch("sparkbench.led_oled.run") as hardware:
                result = execute(None, None, root/"out", ROOT/"hardware/oled-reader.policy.json", spec_path, source_run=Path("saved-run"))
            hardware.assert_not_called()
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["unknowns"], 1)
            self.assertFalse(result["firmware_uploaded"])
            self.assertIn("servo", result["full_behavior_verification"])

    def test_old_diagnostic_capture_cannot_verify_a_new_runtime_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"run.json").write_text(json.dumps({"status": "completed", "source": "live_hardware"}))
            with patch("sparkbench.workflow.check_policy", return_value=({"model": "muse-spark-1.3-contributor"}, root/"calibration")), \
                    patch("sparkbench.artifacts.load_artifact", return_value=(PLAN, {"plan_sha256": "a"*64, "firmware_sha256": "b"*64})), \
                    patch("sparkbench.workflow.analyze") as analysis:
                with self.assertRaises(ValueError):
                    execute(None, None, root/"out", ROOT/"hardware/oled-reader.policy.json", ROOT/"specs/led_oled_only.json", root/"artifact", root)
            analysis.assert_not_called()

    @unittest.skipUnless((ROOT/"runs/vision/contributor-validation-2026-10-30-v1/reader.jsonl").is_file()
                         and platform.system() == "Darwin", "Private Mac capture fixture omitted")
    def test_whole_workflow_with_recorded_independent_readings_no_api_or_hardware(self):
        rows = [json.loads(line) for line in (ROOT/"runs/vision/contributor-validation-2026-10-30-v1/reader.jsonl").read_text().splitlines()]
        readings = {r["id"]+".jpg": r for r in rows}
        calibration = json.loads((ROOT/"runs/vision/contributor-validation-2026-10-30-v1/calibration.snapshot.json").read_text())
        if platform.mac_ver()[0] != calibration["macos"]:
            self.skipTest("Private calibration belongs to a different macOS build")
        with tempfile.TemporaryDirectory() as directory, \
                patch("sparkbench.vision.read_images", return_value=readings) as reader, \
                patch("sparkbench.led_oled.run") as acquire:
            result = execute(None, None, Path(directory)/"out", ROOT/"runs/vision/contributor-validation-2026-10-30-v1/reader-policy.snapshot.json",
                ROOT/"specs/led_oled_only.json", source_run=ROOT/"runs/led-oled/20261030T061710.065777Z")
            verification = json.loads((Path(directory)/"out/analysis/verification.json").read_text())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(sum(len(w["measurements"]) for w in verification["windows"]), 47)
        reader.assert_called_once(); acquire.assert_not_called()


class HandoverTests(unittest.TestCase):
    @staticmethod
    def packager():
        spec = importlib.util.spec_from_file_location("sparkbench_packager", ROOT/"tools/package_handover.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def test_configured_meta_key_is_detected_without_being_included(self):
        tool = self.packager()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory); (path/".env").write_text('META_API_KEY="private-test-credential-123456"\n')
            with patch.object(tool, "ROOT", path), patch.dict("os.environ", {"META_API_KEY": "environment-credential-123456"}):
                secrets = tool.configured_secrets()
                self.assertIn(b"private-test-credential-123456", secrets)
                self.assertIn(b"environment-credential-123456", secrets)
                self.assertNotIn(path/".env", tool.payload_files())

    def test_omitted_calibration_and_reference_are_explicit(self):
        tool = self.packager()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory); (path/"hardware").mkdir()
            (path/"hardware/oled-reader.policy.json").write_text(json.dumps({"calibration": "calibration.json"}))
            (path/"calibration.json").write_text(json.dumps({"geometry": {"reference_frame": "private.jpg"}}))
            (path/"private.jpg").write_bytes(b"synthetic fixture")
            with patch.object(tool, "ROOT", path):
                omitted = {r["path"]: r for r in tool.omitted_evidence()}
            self.assertFalse(omitted["private.jpg"]["bundled"])
            self.assertFalse(omitted["calibration.json"]["bundled"])


class NativeRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "Native C++ compiler unavailable")
    def test_actual_adapter_lease_stop_command_rejection_probes_and_rollover(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output/"plan_data.h").write_text(render_header(PLAN))
            subprocess.run(["c++", "-std=c++11", "-I"+str(ROOT/"tests/native"),
                "-I"+str(ROOT/"firmware/runtime/include"), "-I"+str(ROOT/"firmware/runtime/src"),
                "-I"+str(output), str(ROOT/"tests/native/runtime_test.cpp"), "-o", str(output/"runtime-test")], check=True, capture_output=True, timeout=30)
            subprocess.run([str(output/"runtime-test")], check=True, capture_output=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
