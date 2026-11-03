"""Synthetic offline regressions. No camera, serial port, API or physical proof."""
import copy
import io
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sparkbench.camera import ROOT
from sparkbench.fullrig import (behavior_plan, build, calibration_plan, generate, load_artifact,
                               render_header, requested_behavior, validate_model_data, validate_plan)
from sparkbench.fullrig_capture import FullJournal, acquire, drive, identity, stop_and_confirm, verify_idle
from sparkbench.fullrig_verify import angles_from_trace, compare_full, require_coverage, windows
from sparkbench.meta import Config
from sparkbench.servo_calibration import angle_from_points, fingerprint, interpolate, qualify
from sparkbench.vision import digest, load, save

SPEC = load(ROOT/"specs/behavior_a.json")
MAPPING = {"red": 25, "green": 26}


def synthetic_calibration(root):
    root = Path(root); reference = root/"reference.jpg"; reference.write_bytes(b"synthetic reference, not a JPEG")
    geometry = {"camera_id": "synthetic-camera", "tracker_settings_sha256": "a"*64,
                "reference_frame": str(reference), "reference_sha256": digest(reference),
                "plane_reference": {"dimensions_confirmed": True, "plane_relation_confirmed": True,
                                    "relation_to_horn_plane": "same_plane", "provenance": "synthetic geometry",
                                    "plane_size": [100, 100], "corners_px": [[0, 0], [100, 0], [100, 100], [0, 100]]},
                "zero_reference": {"confirmed": True, "method": "fixed_protractor_baseline",
                                   "direction": 1, "endpoints_px": [[0, 0], [100, 0]]}}
    observations = []
    for role in ("fit", "validation"):
        for angle, pulse in ((40, 1300), (90, 1500), (140, 1700)):
            image = root/(role+str(angle)+".jpg"); image.write_bytes((role+str(angle)).encode())
            rad = math.radians(angle)
            observations.append({"role": role, "image": str(image), "image_sha256": digest(image),
                "reference_kind": "independent_protractor_reading", "reference_angle_deg": angle,
                "pulse_us": pulse, "pivot_px": [50, 50], "tip_px": [50+30*math.cos(rad), 50+30*math.sin(rad)]})
    return {"schema_version": 1, "kind": "synthetic", "approved_pulse_bounds_us": [1300, 1700],
            "independent_reader_uncertainty_deg": 1, "geometry": geometry, "observations": observations}


class CalibrationTests(unittest.TestCase):
    def test_geometry_and_independent_heldout_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            cal = synthetic_calibration(directory); result = qualify(cal)
            self.assertEqual(result["angle_range_deg"], [40, 140])
            self.assertFalse(result["eligible_for_hardware"])
            self.assertAlmostEqual(interpolate(65, result["fit"]), 1400)
            with self.assertRaises(ValueError): interpolate(150, result["fit"])

    def test_missing_plane_zero_measurement_or_uncertainty_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            original = synthetic_calibration(directory)
            for field in ("plane_reference", "zero_reference"):
                cal = copy.deepcopy(original); cal["geometry"][field] = None
                with self.assertRaises(ValueError): qualify(cal)
            for value in (None, True, float("nan"), 0, 2):
                cal = copy.deepcopy(original); cal["independent_reader_uncertainty_deg"] = value
                with self.assertRaises(ValueError): qualify(cal)

    def test_commands_cannot_replace_observations_or_heldout_images(self):
        with tempfile.TemporaryDirectory() as directory:
            original = synthetic_calibration(directory)
            for modification in ("command", "reuse", "no_holdout", "narrow_holdout", "bad_mapping", "bad_camera", "bad_repeatability"):
                cal = copy.deepcopy(original)
                if modification == "command": cal["observations"][0]["reference_kind"] = "uart_command"
                if modification == "reuse": cal["observations"][3]["image"] = cal["observations"][0]["image"]
                if modification == "no_holdout": cal["observations"] = cal["observations"][:3]
                if modification == "narrow_holdout":
                    for row in cal["observations"][3:]:
                        row.update(reference_angle_deg=90, pivot_px=[50, 50], tip_px=[50, 80], pulse_us=1500)
                if modification == "bad_mapping": cal["observations"][1]["pulse_us"] = 1700
                if modification == "bad_camera": cal["observations"][0]["tip_px"] = [50, 80]
                if modification == "bad_repeatability": cal["observations"][3]["pulse_us"] = 1400
                with self.subTest(modification=modification), self.assertRaises(ValueError): qualify(cal)

    def test_observation_and_reference_hashes_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            cal = synthetic_calibration(directory)
            Path(cal["observations"][2]["image"]).write_text("changed")
            with self.assertRaises(ValueError): qualify(cal)

    def test_physical_record_requires_automatic_image_bound_localization(self):
        with tempfile.TemporaryDirectory() as directory:
            cal = synthetic_calibration(directory); cal["kind"] = "physical"
            with self.assertRaises(ValueError): qualify(cal)

    def test_camera_transform_is_undone_before_angle(self):
        with tempfile.TemporaryDirectory() as directory:
            cal = synthetic_calibration(directory); g = cal["geometry"]
            self.assertAlmostEqual(angle_from_points(g, [60, 70], [60, 100], [1, 0, 10, 0, 1, 20]), 90)
            with self.assertRaises(ValueError): angle_from_points(g, [0, 0], [1, 1], [0]*6)


class FullPlanTests(unittest.TestCase):
    def test_model_cannot_choose_pulses_source_or_durations(self):
        original = requested_behavior(SPEC, MAPPING)
        for key, value in (("pulse_us", 2500), ("source", "bad"), ("duration_ms", 100000)):
            data = copy.deepcopy(original); data["steps"][0][key] = value
            with self.assertRaises(ValueError): validate_model_data(data)
        for angle in (True, float("nan"), 181):
            data = copy.deepcopy(original); data["steps"][0]["angle_deg"] = angle
            with self.assertRaises(ValueError): validate_model_data(data)
        for text in ('X"}; bad;', "A\n", "", "A"*17):
            data = copy.deepcopy(original); data["steps"][0]["text"] = text
            with self.assertRaises(ValueError): validate_model_data(data)

    def test_calibrated_pulses_are_local_and_spec_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            cal = synthetic_calibration(directory); data = requested_behavior(SPEC, MAPPING)
            plan = behavior_plan(data, SPEC, cal)
            self.assertEqual(plan["steps"][0]["pulse_us"], 1320)
            self.assertEqual(plan["steps"][-1]["pulse_us"], 1680)
            data["steps"][0]["angle_deg"] = 46
            with self.assertRaises(ValueError): behavior_plan(data, SPEC, cal)

    def test_pending_or_insufficient_range_blocks_before_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cal = synthetic_calibration(root)
            for row in cal["observations"]:
                angle = 80+(row["reference_angle_deg"]-40)/5
                row["reference_angle_deg"] = angle
                rad = math.radians(angle); row["tip_px"] = [50+30*math.cos(rad), 50+30*math.sin(rad)]
            save(root/"cal.json", cal); post = Mock()
            with self.assertRaises(ValueError):
                generate(ROOT/"specs/behavior_a.json", MAPPING, root/"cal.json", root/"out", post=post)
            post.assert_not_called()

    def test_synthetic_artifact_is_disabled_and_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cal = synthetic_calibration(root)
            plan = behavior_plan(requested_behavior(SPEC, MAPPING), SPEC, cal)
            result = build(plan, root/"artifact", cal, False)
            self.assertFalse(result["eligible_for_hardware"])
            self.assertIn("kEnabled = false", (root/"artifact/project/include/plan_data.h").read_text())
            self.assertEqual(load_artifact(root/"artifact", require_compiled=False, for_hardware=False)[0], plan)
            with self.assertRaises(ValueError): load_artifact(root/"artifact", require_compiled=False)
            source = root/"artifact/project/src/main.cpp"; source.write_text(source.read_text()+"\n// changed\n")
            meta = load(root/"artifact/artifact.json"); meta["inputs_sha256"]["project/src/main.cpp"] = digest(source)
            meta["trusted_runtime_sha256"]["src/main.cpp"] = digest(source); save(root/"artifact/artifact.json", meta)
            with self.assertRaises(ValueError): load_artifact(root/"artifact", require_compiled=False, for_hardware=False)

    def test_manual_pulse_tampering_and_bounds_changes_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cal = synthetic_calibration(root)
            plan = behavior_plan(requested_behavior(SPEC, MAPPING), SPEC, cal)
            plan["steps"][0]["pulse_us"] += 1
            with self.assertRaises(ValueError): build(plan, root/"bad", cal, False)
            for pulses, bounds in (([True], [1300,1700]), ([1200], [1300,1700]), ([1500]*9, [1300,1700]), ([1500], [0,3000])):
                with self.assertRaises(ValueError): calibration_plan(pulses, bounds)

    def test_meta_only_repair_budget_and_secret_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cal = synthetic_calibration(root); save(root/"cal.json", cal)
            good = requested_behavior(SPEC, MAPPING); bad = copy.deepcopy(good); bad["mapping"] = {"red": 26, "green": 25}
            def response(data, status=200):
                return Mock(status_code=status, json=Mock(return_value={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(data)}}]}))
            post = Mock(side_effect=[response(bad), response(good)])
            result = generate(ROOT/"specs/behavior_a.json", MAPPING, root/"cal.json", root/"out",
                              config=Config("private-test-key", "muse-spark-1.3-contributor"), post=post, compile_firmware=False)
            self.assertEqual(result["status"], "rendered"); self.assertEqual(post.call_count, 2)
            self.assertFalse(post.call_args.kwargs["allow_redirects"])
            self.assertEqual(post.call_args.kwargs["json"]["model"], "muse-spark-1.3-contributor")
            for file in (root/"out").rglob("*.json"): self.assertNotIn("private-test-key", file.read_text())
            post = Mock(return_value=response({}, 429))
            generate(ROOT/"specs/behavior_a.json", MAPPING, root/"cal.json", root/"rate", config=Config("key"), post=post, compile_firmware=False)
            self.assertEqual(post.call_count, 1)

    def test_synthetic_calibration_never_makes_a_real_paid_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cal=synthetic_calibration(root);save(root/"cal.json",cal)
            with patch("requests.post") as post:
                with self.assertRaisesRegex(ValueError,"no paid Meta"):
                    generate(ROOT/"specs/behavior_a.json",MAPPING,root/"cal.json",root/"out")
                post.assert_not_called()


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now


class CaptureTests(unittest.TestCase):
    def test_import_and_missing_optin_do_not_access_hardware(self):
        with patch("serial.Serial") as serial, patch("sparkbench.fullrig_capture.list_cameras") as camera:
            with self.assertRaises(ValueError): acquire("port", "camera", "artifact", "output")
            serial.assert_not_called(); camera.assert_not_called()

    def test_start_once_partial_write_and_no_run(self):
        serial = Mock(); serial.write.side_effect = lambda data: len(data)
        j = FullJournal(serial, io.StringIO(), "EXECUTE")
        for cmd in ("RUN", "CALIBRATE", "EXECUTE", "PING", "STOP"):
            with self.assertRaises(ValueError): j.send(cmd)
        j.verified = j.camera_ready = True
        serial.write.return_value = 1; serial.write.side_effect = None
        with self.assertRaises(ValueError): j.send("EXECUTE")
        with self.assertRaises(ValueError): j.send("EXECUTE")
        self.assertTrue(j.started)

    def test_sequence_and_faults_with_fake_clock_and_no_hardware(self):
        for fault, reason in ((None, "COMPLETE"), ("stop", "STOP"), ("lease", "LEASE_EXPIRED")):
            clock = Clock(); serial = Mock(); serial.write.side_effect = lambda data: len(data)
            journal = FullJournal(serial, io.StringIO(), "CALIBRATE", clock); journal.verified = True
            def read():
                clock.now += .2
                if not hasattr(clock, "first"):
                    clock.first = True; return ["FULL_STEP:1 PULSE_US:1500 UPTIME_MS:1000"]
                end = 3.2 if fault is None else 2.2
                return [f"FULL_STOPPED REASON:{reason} PWM:OFF UPTIME_MS:4000"] if clock.now >= end else []
            journal.read = read
            result = drive(journal, [1500], lambda: True, fault=fault, clock=clock)
            self.assertEqual(result["stop_reason"], reason)

    def test_stale_camera_and_reset_abort(self):
        clock = Clock(); serial = Mock(); serial.write.side_effect = lambda data: len(data)
        journal = FullJournal(serial, io.StringIO(), "EXECUTE", clock); journal.verified = True
        with self.assertRaises(ValueError): drive(journal, [1500], lambda: False, clock=clock)
        self.assertFalse(journal.started)
        journal.read = lambda: ["SPARKBENCH FULL_RUNTIME BOOT PWM:OFF"]
        with self.assertRaises(ValueError): drive(journal, [1500], lambda: True, clock=clock)

    def test_wrong_identity_and_stop_confirmation_time_out(self):
        clock = Clock(); serial = Mock(); serial.write.side_effect = lambda data: len(data)
        j = FullJournal(serial, io.StringIO(), "EXECUTE", clock)
        def read(): clock.now += .5; return ["SPARKBENCH SERVO_GUARDED V:1"]
        j.read = read
        with self.assertRaises(ValueError): verify_idle(j, calibration_plan([1500]), clock)
        self.assertFalse(j.verified)
        j.verified = True
        self.assertFalse(stop_and_confirm(j, clock))


def measured_windows(spec=SPEC):
    result = []
    for row in spec["steps"]:
        start = row["step"]*4
        result.append({"step": row["step"], "start": start, "end": start+1.8,
                       "measurements": [{"file": f"{row['step']}-{i}.jpg", "sample_pts_seconds": start+i*.3,
                                         "red": row["red"], "green": row["green"], "oled_text": row["oled_text"],
                                         "angle_deg": row["expected_angle"]} for i in range(7)]})
    return result


class FullVerifierTests(unittest.TestCase):
    def test_error_budget_cannot_silently_extend_original_tolerance(self):
        measured = measured_windows(); row = measured[0]["measurements"][0]
        row["angle_error_budget_deg"] = 3
        row["angle_deg"] = 49
        self.assertEqual(compare_full(SPEC, measured)["status"], "incomplete")
        row["angle_deg"] = 55
        self.assertEqual(compare_full(SPEC, measured)["status"], "fail")
        row["angle_deg"] = 47
        self.assertEqual(compare_full(SPEC, measured)["status"], "pass")
    def test_both_original_specs_and_real_missing_wrong_controls(self):
        for spec in (SPEC, load(ROOT/"specs/behavior_b.json")):
            measured = measured_windows(spec); self.assertEqual(compare_full(spec, measured)["status"], "pass")
            for channel, value, status in (("angle_deg", None, "incomplete"), ("angle_deg", 200, "fail"),
                                          ("red", None, "incomplete"), ("oled_text", "WRONG", "fail")):
                changed = copy.deepcopy(measured); changed[0]["measurements"][0][channel] = value
                self.assertEqual(compare_full(spec, changed)["status"], status)
            measured[0]["measurements"][0]["sample_pts_seconds"] += .7
            self.assertEqual(compare_full(spec, measured)["status"], "incomplete")

    def test_synthetic_calibration_cannot_emit_physical_angles(self):
        with tempfile.TemporaryDirectory() as directory:
            cal = synthetic_calibration(directory)
            trace = [{"file": "a.jpg", "status": "tracked_unverified", "reasons": [],
                      "localized_points": {"pivot_px": [50,50], "tip_px": [50,80]},
                      "quality": {"camera_image_transform": [1,0,0,0,1,0]}}]
            self.assertIsNone(angles_from_trace(trace, cal)["a.jpg"])

    def test_timing_uses_uart_ids_never_uart_as_angles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = calibration_plan([1500])
            events = [{"kind": "tx", "command": "CALIBRATE"},
                      {"kind": "rx_line", "line": "FULL_STEP:1 PULSE_US:1500 UPTIME_MS:1000", "host_uptime_seconds": 10},
                      {"kind": "rx_line", "line": "FULL_STOPPED REASON:COMPLETE PWM:OFF UPTIME_MS:4100", "host_uptime_seconds": 13.1}]
            (root/"uart.jsonl").write_text(''.join(json.dumps(r)+'\n' for r in events))
            frames = [{"sample_pts_seconds": 10.7+i*.3} for i in range(7)]
            result = windows(root, frames, plan, "CALIBRATE"); require_coverage(result)
            self.assertNotIn("angle_deg", result[0])
            events.insert(0, {"kind": "tx", "command": "RUN"})
            (root/"uart.jsonl").write_text(''.join(json.dumps(r)+'\n' for r in events))
            with self.assertRaises(ValueError): windows(root, frames, plan, "CALIBRATE")


class NativeFullRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "C++ unavailable")
    def test_actual_adapter_safety_against_fake_gpio_pwm_display(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cal = synthetic_calibration(root)
            behavior = behavior_plan(requested_behavior(SPEC, MAPPING), SPEC, cal)
            for plan, enabled in ((calibration_plan([1500,1300,1700,1500]), True), (behavior, True), (behavior, False)):
                (root/"plan_data.h").write_text(render_header(plan, enabled=enabled))
                compiled = subprocess.run(["c++", "-std=c++11", "-I"+str(ROOT/"tests/native_servo"), "-I"+str(ROOT/"tests/native"),
                                "-I"+str(ROOT/"firmware/full_runtime/src"), "-I"+str(root), str(ROOT/"tests/native_servo/full_runtime_test.cpp"),
                                "-o", str(root/"test")], capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                executed = subprocess.run([str(root/"test")], capture_output=True, text=True, timeout=10)
                self.assertEqual(executed.returncode, 0, executed.stderr)


if __name__ == "__main__": unittest.main()
