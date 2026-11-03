"""Full-rig sampled-window measurement and comparison. No serial/flash access.

UART supplies timing only. Angles use independently validated geometry and
automatic image points; LEDs use camera pixels; OLED uses Meta API alone.
"""
import argparse
import copy
import json
import platform
import re
from pathlib import Path

from .camera import ROOT
from .fullrig import load_artifact, requested_behavior
from .fullrig_capture import STEP, STOP, identity
from .policy import check_integrity, check_policy
from .servo_calibration import MAX_ERROR_DEG, angle_from_points, fingerprint, qualify
from .servo_tracking import track_saved
from .verify import _check_spec
from .vision import compare, digest, finite, geometry_valid, led_state, load, oled_text, read_images, save, validate_capture


def windows(run, frames, plan, action="EXECUTE"):
    if action not in ("EXECUTE", "CALIBRATE", "DISCOVER", "LEDS"):
        raise ValueError("Unsupported full-runtime action")
    events = [json.loads(line) for line in (Path(run)/"uart.jsonl").read_text().splitlines()]
    starts = [i for i, r in enumerate(events) if r.get("kind") == "tx" and r.get("command") == action]
    if len(starts) != 1 or any(r.get("command") not in ("ID", action, "PING", "STOP")
                              for r in events if r.get("kind") == "tx"):
        raise ValueError("Exactly one fresh allowlisted sequence start required")
    markers, ends = [], []
    pulses = [0]*5 if action == "DISCOVER" else [0]*len(plan["steps"]) if action == "LEDS" else [s["pulse_us"] for s in plan["steps"]]
    for event in events[starts[0]+1:]:
        if event.get("kind") != "rx_line": continue
        line = event.get("line", "")
        if "ERROR" in line or "FAULT" in line or re.search(r"\bBOOT\b", line):
            raise ValueError("Board reset/error in full-runtime capture")
        match = STEP.fullmatch(line)
        if match:
            step, pulse, uptime = map(int, match.groups())
            if step != len(markers)+1 or step > len(pulses) or pulse != pulses[step-1]:
                raise ValueError("Unexpected UART sequence; telemetry is never an angle reading")
            markers.append((step, event.get("host_uptime_seconds"), uptime))
        stopped = STOP.fullmatch(line)
        if stopped:
            reason, pwm, uptime = stopped.groups()
            if pwm != "OFF" or reason not in ("COMPLETE", "STOP"):
                raise ValueError("Unexpected shutdown during normal sequence")
            if reason == "COMPLETE": ends.append((event.get("host_uptime_seconds"), int(uptime)))
            elif not ends: raise ValueError("Sequence stopped before completion")
    if len(markers) != len(pulses) or len(ends) != 1:
        raise ValueError("Missing or duplicate UART timing markers")
    times = [r[1] for r in markers]+[ends[0][0]]
    up = [r[2] for r in markers]+[ends[0][1]]
    if (not all(finite(t) for t in times) or not all(3 <= b-a <= 4 for a, b in zip(times, times[1:]))
            or not all(3000 <= (b-a) % 2**32 <= 4000 for a, b in zip(up, up[1:]))):
        raise ValueError("Unsupported UART receipt/firmware timing")
    return [{"step": i+1, "start": times[i]+.65, "end": times[i+1]-.45,
             "frames": [f for f in frames if times[i]+.65 <= f["sample_pts_seconds"] <= times[i+1]-.45]}
            for i in range(len(pulses))]


def require_coverage(selected_windows):
    for window in selected_windows:
        pts = [f["sample_pts_seconds"] for f in window["frames"]]
        if (len(pts) < 5 or pts[0]-window["start"] > .55 or window["end"]-pts[-1] > .55
                or any(b-a > .65 for a, b in zip(pts, pts[1:]))):
            raise ValueError("Insufficient settled temporal coverage; no Meta requests")


def compare_full(spec, measured):
    _check_spec(spec)
    result = compare(spec["steps"], measured)
    by_step = {w["step"]: w for w in measured}
    for step in spec["steps"]:
        for row in by_step.get(step["step"], {}).get("measurements", []):
            angle = row.get("angle_deg")
            budget = row.get("angle_error_budget_deg", 0)
            label = "step %d %s angle" % (step["step"], row["file"])
            if not finite(angle): result["unknowns"].append(label+": not measured")
            elif not finite(budget) or budget < 0:
                result["unknowns"].append(label+": missing measurement error budget")
            elif abs(angle-step["expected_angle"])-budget > spec["angle_tolerance_deg"]:
                result["failures"].append(label+": outside independent tolerance")
            elif abs(angle-step["expected_angle"])+budget > spec["angle_tolerance_deg"]:
                result["unknowns"].append(label+": error budget overlaps tolerance boundary")
    result["status"] = "fail" if result["failures"] else "incomplete" if result["unknowns"] else "pass"
    return result


def angles_from_trace(trace, calibration):
    qualified = qualify(calibration)
    result = {}
    for row in trace:
        name = row["file"]
        if name in result: raise ValueError("Duplicate tracked frame")
        angle = None
        if qualified["eligible_for_hardware"] and row.get("status") == "tracked_unverified" and not row.get("reasons"):
            points = row.get("localized_points") or {}
            transform = (row.get("quality") or {}).get("camera_image_transform")
            try:
                if transform is None: raise ValueError("Independent camera registration required")
                candidate = angle_from_points(qualified["geometry"], points.get("pivot_px"), points.get("tip_px"), transform)
                if not qualified["angle_range_deg"][0] <= candidate <= qualified["angle_range_deg"][1]:
                    raise ValueError("Observed angle outside validated measurement range")
                angle = candidate
            except (ValueError, KeyError, TypeError): pass
        result[name] = angle
    return result


def frozen_inputs(artifact_path, tracker_path, policy_path, spec_path):
    plan, artifact = load_artifact(artifact_path)
    if plan["profile"] != "behavior": raise ValueError("Calibration diagnostic cannot verify Behavior A/B")
    calibration = load(Path(artifact_path)/"calibration.json"); checked = qualify(calibration)
    if not checked["eligible_for_hardware"]: raise ValueError("Physical angle calibration required")
    spec = load(spec_path)
    data = {"schema_version": 1, "mapping": plan["mapping"],
            "steps": [{k: s[k] for k in ("angle_deg", "red", "green", "text")} for s in plan["steps"]]}
    if data != requested_behavior(spec, plan["mapping"]): raise ValueError("Artifact/spec behavior mismatch")
    tracker = load(tracker_path); preview = load(ROOT/tracker["preview_config"])
    geometry = checked["geometry"]
    if (fingerprint(tracker["settings"]) != geometry["tracker_settings_sha256"]
            or fingerprint(tracker["temporal_policy"]) != geometry["tracker_temporal_policy_sha256"]
            or preview["camera_id"] != geometry["camera_id"]
            or preview["reference_sha256"] != geometry["reference_sha256"]
            or digest(ROOT/preview["reference_frame"]) != geometry["reference_sha256"]
            or digest(ROOT/tracker["preview_config"]) != tracker["preview_config_sha256"]):
        raise ValueError("Tracker/view differs from independently calibrated geometry")
    policy, led_path = check_policy(policy_path)
    leds = load(led_path)
    if (leds["camera_id"] != geometry["camera_id"] or leds["macos"] != platform.mac_ver()[0]
            or leds["native_reader_source_sha256"] != digest(ROOT/"tools/macos_vision/main.swift")
            or digest(ROOT/leds["geometry"]["reference_frame"]) != leds["reference_image_sha256"]):
        raise ValueError("LED/OLED calibration camera/reference/macOS mismatch")
    return plan, artifact, calibration, tracker, policy, leds, spec


def analyze(run, artifact_path, tracker_path, policy_path, spec_path, output):
    run, output = Path(run).resolve(), Path(output).resolve()
    plan, artifact, calibration, tracker, policy, leds, spec = frozen_inputs(artifact_path, tracker_path, policy_path, spec_path)
    frozen = {str(Path(p).resolve()): digest(p) for p in (tracker_path, policy_path, spec_path, Path(artifact_path)/"artifact.json", Path(artifact_path)/"calibration.json")}
    check_integrity(run); frames = validate_capture(run); saved = load(run/"run.json")
    if (saved.get("plan_sha256") != fingerprint(plan) or saved.get("firmware_sha256") != artifact["firmware_sha256"]
            or saved.get("identity") != identity(plan) or saved.get("action") != "EXECUTE"
            or saved.get("qualification_fault") is not None
            or saved.get("calibration_sha256") != plan["calibration_sha256"]
            or saved.get("device_id") != calibration["geometry"]["camera_id"]
            or saved.get("stop_acknowledged_uart_only") is not True):
        raise ValueError("Saved acquisition does not match complete normal full-runtime behavior")
    selected = windows(run, frames, plan); require_coverage(selected)
    exposed = {r["image_sha256"] for r in calibration["observations"]}
    if any(digest(run/"camera"/f["file"]) in exposed for f in frames):
        raise ValueError("Calibration images cannot be reused as independent behavior evaluation")
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("spec", spec), ("angle-calibration", calibration), ("reader-policy", policy), ("led-calibration", leds)):
        save(output/(name+".snapshot.json"), value)
    report = {"schema_version": 1, "status": "incomplete", "source": "saved_live_camera_frames",
              "scope": "Sampled settled full-rig windows only; no continuous behavior or electrical waveform assertion",
              "source_run": str(run), "reader_received_expected_labels": False, "windows": [],
              "model_api_requests": 0, "firmware_uploaded": False, "servo_actuation_this_analysis": False}
    save(output/"verification.json", report)
    try:
        tracker = copy.deepcopy(tracker); tracker["source_capture"] = str(run/"camera")
        tracker["recorded_motion_analysis"] = True
        save(output/"tracker.analysis.json", tracker)
        tracked = track_saved(output/"tracker.analysis.json", output/"tracking")
        if tracked.get("status") != "unverified_tracking_available" or tracked.get("quality_controls") != "pass":
            raise ValueError("Automatic tracker baseline/digital controls did not pass; no Meta requests")
        trace = [json.loads(line) for line in (output/"tracking/trace.jsonl").read_text().splitlines()]
        hashes = {r["file"]: r["source_image_sha256"] for r in trace}
        if set(hashes) != {f["file"] for f in frames} or any(hashes[f["file"]] != digest(run/"camera"/f["file"]) for f in frames):
            raise ValueError("Tracking/image evidence mismatch")
        angles = angles_from_trace(trace, calibration)
        chosen = [f for w in selected for f in w["frames"]]
        # Fail early on missing angle/coverage to avoid spending on an already
        # incomplete capture. Never replace failed points with expected targets.
        angles_complete = all(finite(angles.get(f["file"])) for f in chosen)
        angles_acceptable = angles_complete and all(
            abs(angles[f["file"]]-step["expected_angle"])+MAX_ERROR_DEG <= spec["angle_tolerance_deg"]
            for step, window in zip(spec["steps"], selected) for f in window["frames"])
        raw = {}
        if angles_acceptable:
            (output/"reader").mkdir()
            raw = read_images(run, leds["geometry"], chosen, output/"reader")
            report["model_api_requests"] = len(list((output/"reader/meta").glob("*/request.json")))
        else:
            report["api_skipped_reason"] = "A required angle is missing, outside tolerance or overlaps its error-budget boundary"
        measured = []
        for window in selected:
            rows = []
            for frame in window["frames"]:
                row = raw.get(frame["file"], {}); valid = geometry_valid(row, leds["geometry"])
                values = {c: led_state(row.get("leds", {}).get(c, {}).get("mean_luma_srgb"), leds["thresholds"][c]) if valid else None for c in ("red", "green")}
                rows.append({"file": frame["file"], "sample_pts_seconds": frame["sample_pts_seconds"],
                             "sha256": hashes[frame["file"]], "angle_deg": angles.get(frame["file"]),
                             "angle_error_budget_deg": MAX_ERROR_DEG,
                             **values, "oled_text": oled_text(row) if valid else None})
            measured.append({k: v for k, v in window.items() if k != "frames"})
            measured[-1]["measurements"] = rows
        if any(digest(p) != sha for p, sha in frozen.items()): raise ValueError("Frozen input changed during analysis")
        check_integrity(run); frozen_inputs(artifact_path, tracker_path, policy_path, spec_path)
        report.update(compare_full(spec, measured)); report["windows"] = measured
        report["full_behavior_verification"] = report["status"]
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="incomplete", error=str(exc), full_behavior_verification="incomplete")
    finally:
        save(output/"verification.json", report)
        save(output/"integrity.json", {"sha256": {str(p.relative_to(output)): digest(p)
            for p in sorted(output.rglob('*')) if p.is_file() and p.name != "integrity.json"}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True); parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--tracker", type=Path, required=True); parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try: report = analyze(args.run, args.artifact, args.tracker, args.policy, args.spec, args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc: parser.exit(2, str(exc)+"\n")
    print(json.dumps({**report, "windows": "See saved verification.json"}, indent=2))
    return 0 if report["status"] == "pass" else 1 if report["status"] == "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
