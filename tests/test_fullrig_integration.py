"""Synthetic integration fixtures with mocked pixel/model adapters. Not hardware evidence."""
import copy
import json
import math
import platform
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sparkbench import fullrig_discovery, fullrig_install, fullrig_shutdown, fullrig_verify, fullrig_workflow
from sparkbench.camera import ROOT
from sparkbench.fullrig import behavior_plan, calibration_plan, requested_behavior
from sparkbench.fullrig_capture import identity
from sparkbench.servo_calibration import fingerprint, measurement_sources
from sparkbench.vision import digest, load, save
from test_fullrig import MAPPING, synthetic_calibration


def physical_branch_fixture(root):
    """Simulate physical-record structure to test its code path, never a real calibration."""
    cal = synthetic_calibration(root); cal["kind"] = "physical"
    settings = {"synthetic_fixture": True}; cal["geometry"]["tracker_settings_sha256"] = fingerprint(settings)
    cal["geometry"]["tracker_temporal_policy_sha256"] = fingerprint({})
    cal["geometry"]["measurement_sources_sha256"] = measurement_sources()
    for i, row in enumerate(cal["observations"]):
        output = root/("fake-tracking-%d" % i); output.mkdir()
        save(output/"tracker-config.snapshot.json", {"settings": settings, "temporal_policy": {}})
        save(output/"preview-config.snapshot.json", {"camera_id": cal["geometry"]["camera_id"], "reference_sha256": cal["geometry"]["reference_sha256"]})
        row["camera_transform"] = [1,0,0,0,1,0]
        trace = {"file": Path(row["image"]).name, "status": "tracked_unverified", "reasons": [],
                 "source_image_sha256": row["image_sha256"],
                 "localized_points": {"pivot_px": row["pivot_px"], "tip_px": row["tip_px"]},
                 "quality": {"camera_image_transform": row["camera_transform"]}}
        (output/"trace.jsonl").write_text(json.dumps(trace)+'\n')
        row["tracking_evidence"] = {"trace": str(output/"trace.jsonl"), "trace_sha256": digest(output/"trace.jsonl"), "file": trace["file"]}
    return cal


class MeasurementIntegrationTests(unittest.TestCase):
    def exercise(self, defect=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cal = physical_branch_fixture(root)
            spec = load(ROOT/"specs/behavior_b.json")
            plan = behavior_plan(requested_behavior(spec, MAPPING), spec, cal)
            artifact = {"firmware_sha256": "a"*64}; run = root/"run"; (run/"camera").mkdir(parents=True)
            geometry = {"minimum_border_support": .5}
            leds = {"geometry": geometry, "thresholds": {c: {"off_threshold": 10, "on_threshold": 20} for c in ("red", "green")}}
            action = "LEDS" if defect in ("leds", "leds_wrong") else "DISCOVER" if defect == "discover" else "EXECUTE"
            frames, events, traces, pixels = [], [{"kind": "tx", "command": action}], [], {}
            sequence = spec["steps"] if action != "DISCOVER" else [
                {"expected_angle": 90, "red": a, "green": b, "oled_text": text}
                for a,b,text in ((False,False,"DARK"),(True,False,"P25"),(False,False,"DARK"),(False,True,"P26"),(False,False,"DARK END"))]
            for i, step in enumerate(sequence):
                start = 10+i*3.1
                pulse = plan['steps'][i]['pulse_us'] if action == "EXECUTE" else 0
                events.append({"kind": "rx_line", "line": f"FULL_STEP:{i+1} PULSE_US:{pulse} UPTIME_MS:{1000+i*3100}", "host_uptime_seconds": start})
                for j in range(7):
                    number = len(frames)+1; name = f"frame-{number:06d}.jpg"; pts = start+.7+j*.3
                    (run/"camera"/name).write_bytes(("synthetic camera fixture "+name).encode())
                    frames.append({"frame": number, "file": name, "sample_pts_seconds": pts, "host_uptime_seconds": pts+.05})
                    angle = 70 if defect == "wrong_angle" and number == 1 else step["expected_angle"]
                    rad = math.radians(angle)
                    traces.append({"file": name, "status": "tracked_unverified", "reasons": [],
                        "source_image_sha256": digest(run/"camera"/name),
                        "localized_points": {"pivot_px": [50,50], "tip_px": [50+30*math.cos(rad),50+30*math.sin(rad)]},
                        "quality": {"camera_image_transform": [1,0,0,0,1,0]}})
                    if defect == "unknown_angle" and number == 1:
                        traces[-1].update(status="unknown", reasons=["occluded"], localized_points=None)
                    pixels[name] = {"id": Path(name).stem, "status": "measured", "oled_border_support": [1]*4,
                        "leds": {c: {"mean_luma_srgb": 30 if step[c] else 0} for c in ("red", "green")},
                        "meta_oled": {"source": "meta_api", "status": "read", "text": step["oled_text"]}}
                    if defect == "wrong_text" and number == 1: pixels[name]["meta_oled"]["text"] = "WRONG"
                    if defect == "leds_wrong" and number == 1:
                        pixels[name]["leds"]["red"]["mean_luma_srgb"] = 0 if step["red"] else 30
            events.append({"kind": "rx_line", "line": f"FULL_STOPPED REASON:COMPLETE PWM:OFF UPTIME_MS:{1000+len(sequence)*3100}", "host_uptime_seconds": 10+len(sequence)*3.1})
            shutdown = defect in ("shutdown_stop", "shutdown_lease", "shutdown_wrong", "shutdown_unknown")
            case = "lease" if defect == "shutdown_lease" else "stop"
            if shutdown:
                stop = 12 if case == "lease" else 11.95
                events = [{"kind": "tx", "command": "EXECUTE", "host_uptime_seconds": 9.9},
                          {"kind": "rx_line", "line": f"FULL_STEP:1 PULSE_US:{plan['steps'][0]['pulse_us']} UPTIME_MS:1000", "host_uptime_seconds": 10},
                          {"kind": "tx", "command": "PING", "host_uptime_seconds": 10.3},
                          {"kind": "fault_trigger", "case": case, "host_uptime_seconds": 10.8 if case == "lease" else 11.9}]
                if case == "stop": events.append({"kind": "tx", "command": "STOP", "host_uptime_seconds": 11.9})
                events.append({"kind": "rx_line", "line": f"FULL_STOPPED REASON:{'LEASE_EXPIRED' if case == 'lease' else 'STOP'} PWM:OFF UPTIME_MS:2950", "host_uptime_seconds": stop})
                frames, traces, pixels = [], [], {}
                samples = [(p, True) for p in (10.7,11,11.3,11.6,11.75)] + [(stop+.7+i*.3,False) for i in range(7)]
                for number, (pts, before) in enumerate(samples,1):
                    name=f"frame-{number:06d}.jpg"; (run/"camera"/name).write_bytes(("synthetic shutdown fixture "+name).encode())
                    frames.append({"frame": number, "file": name, "sample_pts_seconds": pts, "host_uptime_seconds": pts+.05})
                    rad=math.radians(135)
                    traces.append({"file": name, "status": "tracked_unverified", "reasons": [], "source_image_sha256": digest(run/"camera"/name),
                        "localized_points": {"pivot_px": [50,50], "tip_px": [50+30*math.cos(rad),50+30*math.sin(rad)]},
                        "quality": {"camera_image_transform": [1,0,0,0,1,0]}})
                    if defect == "shutdown_unknown" and number == 6: traces[-1].update(status="unknown", reasons=["occluded"], localized_points=None)
                    pixels[name]={"id": Path(name).stem, "status": "measured", "oled_border_support": [1]*4,
                                  "leds": {"red": {"mean_luma_srgb": 30 if before or defect == "shutdown_wrong" else 0}, "green": {"mean_luma_srgb": 0}}}
            save(run/"run.json", {"status": "completed", "source": "live_hardware", "device_id": cal["geometry"]["camera_id"],
                "plan_sha256": fingerprint(plan), "firmware_sha256": artifact["firmware_sha256"], "identity": identity(plan),
                "action": action, "servo_actuation_requested": action == "EXECUTE",
                "qualification_fault": case if shutdown else None,
                "calibration_sha256": plan["calibration_sha256"], "stop_acknowledged_uart_only": True})
            save(run/"camera/capture.json", {"status": "captured", "source": "live_camera", "camera": {"id": cal["geometry"]["camera_id"]}, "frame_count": len(frames)})
            (run/"camera/frames.jsonl").write_text(''.join(json.dumps(r)+'\n' for r in frames))
            (run/"uart.jsonl").write_text(''.join(json.dumps(r)+'\n' for r in events))
            save(run/"integrity.json", {"sha256": {str(p.relative_to(run)): digest(p) for p in run.rglob('*') if p.is_file()}})
            artifact_path = root/"artifact"; artifact_path.mkdir()
            save(artifact_path/"artifact.json", artifact); save(artifact_path/"calibration.json", cal)
            for name in ("tracker", "policy", "spec"): save(root/(name+".json"), {})
            def tracker(config, output):
                output.mkdir(); (output/"trace.jsonl").write_text(''.join(json.dumps(r)+'\n' for r in traces))
                return {"status": "unverified_tracking_available", "quality_controls": "fail" if defect == "controls" else "pass"}
            inputs = (plan, artifact, cal, {}, {"model": "synthetic-mocked-meta"}, leds, spec)
            if shutdown:
                with patch.object(fullrig_shutdown, "frozen_inputs", return_value=inputs), \
                        patch.object(fullrig_shutdown, "track_saved", side_effect=tracker), \
                        patch.object(fullrig_shutdown, "read_images", return_value=pixels) as reader:
                    report=fullrig_shutdown.analyze(run,artifact_path,root/"tracker.json",root/"policy.json",root/"spec.json",root/"out")
                self.assertFalse(reader.call_args.kwargs["read_labels"])
                return report,reader.call_count
            if action in ("LEDS", "DISCOVER"):
                leds.update(macos=platform.mac_ver()[0], native_reader_source_sha256=digest(ROOT/"tools/macos_vision/main.swift"),
                            camera_id=cal["geometry"]["camera_id"], reference_image_sha256=cal["geometry"]["reference_sha256"])
                leds["geometry"]["reference_frame"] = cal["geometry"]["reference_frame"]
                save(root/"leds.json", leds); save(root/"spec.json", spec); save(root/"policy.json", {"model": "synthetic-mocked-meta"})
                with patch.object(fullrig_discovery, "load_artifact", return_value=(plan, {**artifact, "plan_sha256": fingerprint(plan)})), \
                        patch.object(fullrig_discovery, "check_policy", return_value=({}, root/"leds.json")), \
                        patch.object(fullrig_discovery, "read_images", return_value=pixels) as reader:
                    report = fullrig_discovery.analyze(run, artifact_path, root/"policy.json", root/"out", root/"spec.json")
                self.assertFalse(reader.call_args.kwargs["read_labels"])
                return report, reader.call_count
            with patch.object(fullrig_verify, "frozen_inputs", return_value=inputs), \
                    patch.object(fullrig_verify, "track_saved", side_effect=tracker), \
                    patch.object(fullrig_verify, "read_images", return_value=pixels) as reader:
                report = fullrig_verify.analyze(run, artifact_path, root/"tracker.json", root/"policy.json", root/"spec.json", root/"out")
            return report, reader.call_count

    def test_composition_with_mocked_readers_and_original_spec(self):
        report, reads = self.exercise()
        self.assertEqual(report["status"], "pass"); self.assertEqual(reads, 1)
        self.assertEqual(sum(len(w["measurements"]) for w in report["windows"]), 21)

    def test_servo_free_led_check_and_discovery_never_request_text(self):
        for defect, status in (("leds", "pass"), ("leds_wrong", "fail"), ("discover", "mapped")):
            with self.subTest(defect=defect):
                report, reads = self.exercise(defect)
                self.assertEqual(report["status"], status); self.assertEqual(report["model_api_requests"], 0)
                self.assertEqual(reads, 1)
                if defect == "discover": self.assertEqual(report["mapping"], MAPPING)

    def test_shutdown_composition_keeps_camera_and_uart_scopes_separate(self):
        for defect, status in (("shutdown_stop", "pass"), ("shutdown_lease", "pass"), ("shutdown_wrong", "fail"), ("shutdown_unknown", "incomplete")):
            with self.subTest(defect=defect):
                report, reads=self.exercise(defect)
                self.assertEqual(report["status"],status,report)
                self.assertEqual(report["model_api_requests"],0);self.assertEqual(reads,1)

    def test_wrong_angle_or_text_fails_and_missing_angle_skips_meta(self):
        for defect in ("wrong_angle", "wrong_text", "unknown_angle", "controls"):
            with self.subTest(defect=defect):
                report, reads = self.exercise(defect)
                self.assertEqual(report["status"], "incomplete" if defect in ("unknown_angle", "controls") else "fail")
                self.assertEqual(reads, 0 if defect in ("unknown_angle", "controls", "wrong_angle") else 1)

    def test_workflow_missing_optin_refuses_before_inputs_or_io(self):
        with patch.object(fullrig_workflow, "frozen_inputs") as inputs:
            with self.assertRaises(ValueError): fullrig_workflow.execute("a", "t", "p", "s", "o")
            inputs.assert_not_called()


class FullInstallerTests(unittest.TestCase):
    def exercise(self, codes):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); artifact = root/"artifact"; build = artifact/"project/.pio/build/classic-full-runtime"; build.mkdir(parents=True)
            reference = root/"runs/firmware/led-oled-installed-2026-10-30"; reference.mkdir(parents=True)
            for name in ("bootloader.bin", "partitions.bin", "boot_app0.bin"):
                (reference/name).write_bytes(name.encode()); (build/name).write_bytes(name.encode())
            (build/"firmware.bin").write_bytes(b"synthetic new firmware")
            previous = root/"previous.bin"; previous.write_bytes(b"synthetic previous firmware")
            record = {"firmware": "project/.pio/build/classic-full-runtime/firmware.bin", "firmware_sha256": digest(build/"firmware.bin"), "plan_sha256": "a"*64}
            port = Mock(device="/fake", vid=0x10c4, pid=0xea60, hwid="SYNTHETIC")
            with patch.object(fullrig_install, "ROOT", root), patch.object(fullrig_install, "load_artifact", return_value=(calibration_plan([1500]), record)), \
                    patch("serial.tools.list_ports.comports", return_value=[port]), \
                    patch.object(fullrig_install.subprocess, "run", side_effect=[Mock(returncode=c) for c in codes]) as commands:
                result = fullrig_install.install(artifact, "/fake", previous, digest(previous), root/"out", servo_power_off=True)
            return result, [c.args[0] for c in commands.call_args_list]

    def test_application_only_and_boot_verification(self):
        result, commands = self.exercise([0,0,0])
        self.assertEqual(result["status"], "installed_hash_verified")
        writes = [c for c in commands if "write-flash" in c]
        self.assertEqual(len(writes), 1); self.assertEqual(writes[0][-2], "0x10000")
        self.assertIn("0x1000", commands[-1]); self.assertIn("0xe000", commands[-1])

    def test_write_failure_restores_and_preflight_failure_never_writes(self):
        result, commands = self.exercise([0,1,0,0])
        self.assertEqual(result["status"], "incomplete"); self.assertEqual(result["recovery"], "previous_application_restored_hash_verified")
        result, commands = self.exercise([1])
        self.assertEqual(result["status"], "incomplete"); self.assertFalse(any("write-flash" in c for c in commands))

    def test_power_off_flag_required_before_artifact_or_device_access(self):
        with patch.object(fullrig_install, "load_artifact") as load_artifact:
            with self.assertRaises(ValueError): fullrig_install.install("a", "p", "previous", "hash", "o")
            load_artifact.assert_not_called()


if __name__ == "__main__": unittest.main()
