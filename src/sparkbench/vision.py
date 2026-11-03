"""Fixed-camera LED/OLED measurements, with a spec-independent native reader.

Calibration uses previously inspected real frames. Held-out evaluation freezes
those thresholds. This module never accesses serial, captures or flashes.
"""
import argparse
import hashlib
import json
import math
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .camera import ROOT


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def load(path):
    return json.loads(Path(path).read_text())


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_expected(expected):
    if not isinstance(expected, list) or not expected:
        raise ValueError("Expected sequence must be nonempty")
    identifiers = []
    for row in expected:
        if (not isinstance(row, dict) or type(row.get("step")) is not int
                or row["step"] < 1 or type(row.get("red")) is not bool
                or type(row.get("green")) is not bool
                or not isinstance(row.get("oled_text"), str) or not row["oled_text"].strip()):
            raise ValueError("Each expected step needs a positive ID, boolean LED states and OLED text")
        identifiers.append(row["step"])
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate expected step ID")


def build_reader():
    if platform.system() != "Darwin" or not shutil.which("xcrun"):
        raise ValueError("Local image reader requires macOS and Xcode command-line tools")
    source = ROOT / "tools/macos_vision/main.swift"
    stamp = hashlib.sha256(source.read_bytes() + platform.machine().encode()
                           + platform.mac_ver()[0].encode()).hexdigest()
    folder = ROOT / ".cache/vision"
    folder.mkdir(parents=True, exist_ok=True)
    binary, fingerprint = folder / "SparkBenchVision", folder / "source.sha256"
    if not (binary.is_file() and fingerprint.is_file() and fingerprint.read_text() == stamp):
        result = subprocess.run(["xcrun", "swiftc", "-swift-version", "5", "-O",
            "-module-cache-path", str(folder / "swift-modules"), str(source), "-o", str(binary)],
            capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise ValueError("Local image reader build failed: " + result.stderr[-3000:])
        fingerprint.write_text(stamp)
    return binary


def read_images(run, geometry, frames, output, read_labels=True):
    """Native request contains only geometry and image paths, never the spec."""
    reader_geometry = dict(geometry)
    reference = Path(geometry["reference_frame"])
    reader_geometry["reference_frame"] = str((ROOT / reference).resolve())
    request = {"geometry": reader_geometry, "frames": [
        {"id": Path(row["file"]).stem, "path": str((run / "camera" / row["file"]).resolve())}
        for row in frames]}
    save(output / "reader.request.json", request)
    helper = build_reader()
    result = subprocess.run([str(helper), str(output / "reader.request.json"),
                             str(output / "crops")], capture_output=True, text=True, timeout=180)
    (output / "pixels.jsonl").write_text(result.stdout)
    (output / "reader.stderr.log").write_text(result.stderr)
    if result.returncode:
        raise ValueError("Local image reader failed; retain output and distinguish sandbox from host: "
                         + result.stderr[-2000:])
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids) or set(ids) != {Path(f["file"]).stem for f in frames}:
        raise ValueError("Image reader returned missing or duplicate frame IDs")
    if read_labels:
        from .meta import configuration, read_label
        config = configuration()
        service_error = None
        for row in rows:
            if service_error or not geometry_valid(row, geometry):
                row["meta_oled"] = {"source": "meta_api", "status": "unknown", "text": None,
                                    "error": service_error or "unsupported_geometry"}
                continue
            row["meta_oled"] = read_label(output / "crops" / row["label_crop"],
                                          output / "meta" / row["id"], config)
            if row["meta_oled"].get("error") in ("authentication_or_access", "rate_limit",
                    "service_error", "request_configuration", "connection_or_timeout"):
                service_error = row["meta_oled"]["error"]
    (output / "reader.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return {row["id"] + ".jpg": row for row in rows}


def validate_capture(run):
    report = load(run / "run.json")
    camera = load(run / "camera/capture.json")
    frames = [json.loads(line) for line in (run / "camera/frames.jsonl").read_text().splitlines()]
    if (report.get("status") != "completed" or camera.get("status") != "captured"
            or camera.get("source") != "live_camera"
            or camera.get("camera", {}).get("id") != report.get("device_id")
            or len(frames) != camera.get("frame_count") or not frames):
        raise ValueError("Completed live-camera run and consistent frame journal required")
    if [row["frame"] for row in frames] != list(range(1, len(frames)+1)):
        raise ValueError("Frame IDs missing or duplicated")
    previous = None
    for row in frames:
        name = row.get("file", "")
        if name != "frame-%06d.jpg" % row["frame"] or not (run / "camera" / name).is_file():
            raise ValueError("Missing frame or unsafe file name")
        pts, uptime = row.get("sample_pts_seconds"), row.get("host_uptime_seconds")
        if not finite(pts) or not finite(uptime) or not 0 <= uptime-pts <= 1:
            raise ValueError("Camera PTS and host uptime are not sufficiently aligned")
        if previous and (pts <= previous[0] or uptime <= previous[1]):
            raise ValueError("Non-increasing camera timestamps")
        previous = pts, uptime
    return frames


def windows(run, frames, identifiers):
    events = [json.loads(line) for line in (run / "uart.jsonl").read_text().splitlines()]
    starts_sent = [i for i, row in enumerate(events) if row.get("kind") == "tx"
                   and row.get("command") == "VISUAL"]
    if len(starts_sent) != 1:
        raise ValueError("Exactly one fresh VISUAL command event required")
    # Startup bytes may replay an old run. Only use markers after this start.
    events = events[starts_sent[0]+1:]
    starts, stops = [], []
    for event in events:
        if event.get("kind") != "rx_line":
            continue
        line = event.get("line", "")
        if "ERROR" in line or re.search(r"\bBOOT\b", line):
            raise ValueError("Board reset/error during capture; timing is unsupported")
        match = re.match(r"VISUAL_STEP:(\d+) ", line)
        if match:
            starts.append((int(match[1]), event["host_uptime_seconds"]))
        if line.startswith("VISUAL_STOPPED STATUS:COMPLETE "):
            stops.append(event["host_uptime_seconds"])
    if [i for i, _ in starts] != identifiers or len(stops) != 1:
        raise ValueError("Missing/duplicate UART timing markers; values are never used as visual readings")
    times = [time for _, time in starts] + stops
    if not all(finite(t) for t in times) or not all(3 <= b-a <= 4 for a, b in zip(times, times[1:])):
        raise ValueError("Invalid or discontinuous UART step timing")
    return [{"step": identifier, "start": times[i] + 0.65,
             "end": times[i+1] - 0.45,
             "frames": [row for row in frames if times[i]+0.65 <= row["sample_pts_seconds"] <= times[i+1]-0.45]}
            for i, identifier in enumerate(identifiers)]


def geometry_valid(row, geometry):
    values = row.get("oled_border_support", [])
    return (row.get("status") == "measured" and len(values) == 4
            and all(finite(v) and v >= geometry["minimum_border_support"] for v in values))


def fit_threshold(off, on):
    if len(off) < 2 or len(on) < 2 or not all(finite(v) and 0 <= v <= 255 for v in off+on):
        raise ValueError("At least two finite real off/on calibration readings are required")
    gap = min(on) - max(off)
    if gap < 15:
        raise ValueError("LED on/off calibration overlaps or has insufficient separation")
    return {"off_max": max(off), "on_min": min(on), "gap": gap,
            "off_threshold": max(off) + 0.30*gap,
            "on_threshold": max(off) + 0.70*gap,
            "off_samples": off, "on_samples": on}


def led_state(value, thresholds):
    if not finite(value) or not 0 <= value <= 255:
        return None
    if value <= thresholds["off_threshold"]:
        return False
    if value >= thresholds["on_threshold"]:
        return True
    return None


def oled_text(row):
    reading = row.get("meta_oled", {})
    if reading.get("source") != "meta_api" or reading.get("status") != "read":
        return None
    text = reading.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    # Whitespace/case only. No expected vocabulary, fuzzy matches or substitutions.
    return " ".join(text.upper().split())


def compare(expected, measured_windows):
    validate_expected(expected)
    failures, unknowns = [], []
    if [w["step"] for w in measured_windows] != [row["step"] for row in expected]:
        failures.append("Observed step timing sequence differs from specification")
    by_step = {w["step"]: w for w in measured_windows}
    if len(by_step) != len(measured_windows):
        raise ValueError("Duplicate measured step")
    for step in expected:
        window = by_step.get(step["step"])
        prefix = "step %s" % step["step"]
        if window is None:
            unknowns.append(prefix + ": missing window")
            continue
        frames = window["measurements"]
        if len(frames) < 5:
            unknowns.append(prefix + ": fewer than five settled frame readings")
        pts = [row["sample_pts_seconds"] for row in frames]
        valid_times = all(finite(t) and window["start"] <= t <= window["end"] for t in pts)
        if not valid_times:
            unknowns.append(prefix + ": invalid frame timestamps")
        elif pts and (pts != sorted(set(pts)) or pts[0]-window["start"] > .55
                    or window["end"]-pts[-1] > .55
                    or any(b-a > .65 for a, b in zip(pts, pts[1:]))):
            unknowns.append(prefix + ": insufficient temporal coverage")
        for row in frames:
            for channel in ("red", "green", "oled_text"):
                value = row.get(channel)
                known = type(value) is bool if channel != "oled_text" else isinstance(value, str)
                label = "%s %s %s" % (prefix, row["file"], channel)
                if not known:
                    unknowns.append(label + ": unknown")
                elif value != step[channel]:
                    failures.append(label + ": expected %r, measured %r" % (step[channel], value))
    return {"status": "fail" if failures else "incomplete" if unknowns else "pass",
            "failures": failures, "unknowns": unknowns}


def calibrate(run, geometry_path, output):
    frames = validate_capture(run)
    geometry = load(geometry_path)
    review_path = run / "visual_review.json"
    review = load(review_path)
    if review.get("source") != "agent_visual_inspection_of_saved_live_camera_frames":
        raise ValueError("Calibration needs prior explicit inspection of real camera frames")
    observations = review["observations"]
    names = [row["frame"] for row in observations]
    if len(set(names)) != len(names) or any(type(row.get(c)) is not bool for row in observations for c in ("red", "green")):
        raise ValueError("Calibration labels must be unambiguous independent visual observations")
    chosen = [row for row in frames if row["file"] in names]
    if len(chosen) != len(names):
        raise ValueError("Calibration references missing frames")
    output.mkdir(parents=True, exist_ok=False)
    native = read_images(run, geometry, chosen, output, read_labels=False)
    if any(not geometry_valid(row, geometry) for row in native.values()):
        raise ValueError("Calibration frame geometry is unsupported")
    thresholds = {}
    for channel in ("red", "green"):
        groups = {False: [], True: []}
        for row in observations:
            groups[row[channel]].append(native[row["frame"]]["leds"][channel]["mean_luma_srgb"])
        thresholds[channel] = fit_threshold(groups[False], groups[True])
    result = {"schema_version": 1, "source_kind": "supervised_prior_real_frame_inspection",
              "source_run": str(run.resolve()), "source_review_sha256": digest(review_path),
              "source_frames_sha256": {name: digest(run / "camera" / name) for name in names},
              "geometry": geometry, "geometry_sha256": digest(geometry_path),
              "reference_image_sha256": digest(ROOT / geometry["reference_frame"]),
              "camera_id": load(run / "camera/capture.json")["camera"]["id"],
              "native_reader_source_sha256": digest(ROOT / "tools/macos_vision/main.swift"),
              "thresholds": thresholds, "image_score": "mean Rec.709-weighted gamma-encoded sRGB JPEG bytes; not radiometric intensity",
              "macos": platform.mac_ver()[0], "text_reader": "Meta API only; not invoked to fit LED calibration",
              "limits": "Bounded pixel registration with frozen thresholds; uncertain score band yields null; border support guards geometry but does not authenticate scene identity"}
    save(output / "calibration.json", result)
    save(output / "geometry.snapshot.json", geometry)
    return result


def analyze(run, calibration_path, spec_path, output):
    frames = validate_capture(run)
    calibration, specification = load(calibration_path), load(spec_path)
    if calibration["native_reader_source_sha256"] != digest(ROOT / "tools/macos_vision/main.swift"):
        raise ValueError("Native reader changed since calibration; recalibrate explicitly")
    if (calibration["camera_id"] != load(run / "camera/capture.json")["camera"]["id"]
            or calibration["reference_image_sha256"] != digest(ROOT / calibration["geometry"]["reference_frame"])
            or calibration["macos"] != platform.mac_ver()[0]):
        raise ValueError("Camera/reference image/macOS changed since calibration")
    expected = specification["steps"]
    validate_expected(expected)
    selected_windows = windows(run, frames, [row["step"] for row in expected])
    output.mkdir(parents=True, exist_ok=False)
    save(output / "spec.snapshot.json", specification)
    save(output / "calibration.snapshot.json", calibration)
    selected = [row for window in selected_windows for row in window["frames"]]
    native = read_images(run, calibration["geometry"], selected, output)
    measured = []
    for window in selected_windows:
        rows = []
        for frame in window["frames"]:
            raw = native[frame["file"]]
            valid = geometry_valid(raw, calibration["geometry"])
            values = {channel: led_state(raw.get("leds", {}).get(channel, {}).get("mean_luma_srgb"), calibration["thresholds"][channel]) if valid else None for channel in ("red", "green")}
            rows.append({"file": frame["file"], "sample_pts_seconds": frame["sample_pts_seconds"],
                         "sha256": digest(run / "camera" / frame["file"]),
                         "red": values["red"], "green": values["green"],
                         "oled_text": oled_text(raw) if valid else None,
                         "geometry_supported": valid,
                         "native_result_id": Path(frame["file"]).stem})
        measured.append({"step": window["step"], "start": window["start"], "end": window["end"], "measurements": rows})
    result = {"schema_version": 1, **compare(expected, measured),
              "scope": "LED/OLED-only automatic measurements of sampled settled windows; no servo or full-rig pass",
              "source_run": str(run.resolve()), "source": "saved_live_camera_frames",
              "held_out_capture": run.resolve() != Path(calibration["source_run"]).resolve(),
              "calibration_sha256": digest(calibration_path), "spec_sha256": digest(spec_path),
              "reader_received_expected_labels": False,
              "text_reader": "Meta API; no local OCR fallback",
              "timing": {"start_guard_seconds": .65, "end_guard_seconds": .45,
                         "max_frame_gap_seconds": .65, "minimum_frames_per_step": 5,
                         "note": "UART receipt only supplies timing/step IDs, never observed states or OLED text. Transition and between-frame behavior not asserted."},
              "windows": measured, "servo_angle_deg": None,
              "full_behavior_verification": "incomplete_required_servo_measurements_missing"}
    save(output / "verification.json", result)
    save(output / "integrity.json", {"sha256": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return result


def resume_truncated(analysis, output):
    """Retry only transport-complete, server-truncated Meta output; never bad answers."""
    from .meta import PROMPT, configuration, is_truncated, read_label
    config = configuration()
    original = load(analysis / "verification.json")
    native = [json.loads(line) for line in (analysis / "reader.jsonl").read_text().splitlines()]
    # Verify preserved evidence before reuse. This is integrity, not authentication.
    for name, expected in load(analysis / "integrity.json")["sha256"].items():
        if digest(analysis / name) != expected:
            raise ValueError("Original analysis artifact changed: " + name)
    eligible = []
    for row in native:
        reading = row.get("meta_oled", {})
        response = analysis / "meta" / row["id"] / "response.json"
        if (reading.get("status") == "unknown" and response.is_file()
                and is_truncated(load(response))):
            request = load(response.with_name("request.json"))
            crop = Path(request["image_path"])
            if (reading.get("model") != config.model or digest(crop) != reading["image_sha256"]
                    or request["messages"][0]["content"][0]["text"] != PROMPT):
                raise ValueError("Model, prompt or crop differs from original truncated request")
            eligible.append((row, crop))
    if not eligible:
        raise ValueError("No server-truncated Meta responses to retry")
    output.mkdir(parents=True, exist_ok=False)
    for row, crop in eligible:
        row["meta_oled"] = read_label(crop, output / "meta" / row["id"], config, prepare_image=False)
    by_file = {row["id"] + ".jpg": row for row in native}
    measured = original["windows"]
    retried = {row["id"] + ".jpg" for row, _ in eligible}
    for window in measured:
        for row in window["measurements"]:
            if row["file"] in retried:
                row["oled_text"] = oled_text(by_file[row["file"]]) if row["geometry_supported"] else None
    specification = load(analysis / "spec.snapshot.json")
    result = {**original, **compare(specification["steps"], measured),
              "resumed_from": str(analysis), "resumed_report_sha256": digest(analysis / "verification.json"),
              "pixel_artifacts_directory": str(analysis),
              "retry_reason": "Server output truncation only; completed readings and prompt unchanged",
              "new_meta_requests": len(eligible), "reused_meta_readings": len(native)-len(eligible)}
    save(output / "verification.json", result)
    save(output / "spec.snapshot.json", specification)
    save(output / "calibration.snapshot.json", load(analysis / "calibration.snapshot.json"))
    (output / "reader.jsonl").write_text("".join(json.dumps(row) + "\n" for row in native))
    save(output / "integrity.json", {"sha256": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    calibration = commands.add_parser("calibrate")
    calibration.add_argument("--run", type=Path, required=True)
    calibration.add_argument("--geometry", type=Path, default=ROOT / "hardware/vision.geometry.json")
    check = commands.add_parser("analyze")
    check.add_argument("--run", type=Path, required=True)
    check.add_argument("--calibration", type=Path, required=True)
    check.add_argument("--spec", type=Path, default=ROOT / "specs/led_oled_only.json")
    resume = commands.add_parser("resume-truncated")
    resume.add_argument("--analysis", type=Path, required=True)
    for command in (calibration, check, resume):
        command.add_argument("--output", type=Path, required=True, help="New evidence directory")
    args = parser.parse_args()
    try:
        if args.command == "calibrate":
            result = calibrate(args.run.resolve(), args.geometry.resolve(), args.output.resolve())
            print(json.dumps({"status": "calibrated", "thresholds": result["thresholds"], "output": str(args.output)}, indent=2))
            return 0
        if args.command == "resume-truncated":
            result = resume_truncated(args.analysis.resolve(), args.output.resolve())
        else:
            result = analyze(args.run.resolve(), args.calibration.resolve(), args.spec.resolve(), args.output.resolve())
        summary = {k: v for k, v in result.items() if k not in ("windows", "failures", "unknowns")}
        summary.update({"failure_count": len(result["failures"]), "unknown_count": len(result["unknowns"]),
                        "failures": result["failures"][:5], "unknowns": result["unknowns"][:5]})
        print(json.dumps(summary, indent=2))
        return {"pass": 0, "fail": 1, "incomplete": 2}[result["status"]]
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "incomplete", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
