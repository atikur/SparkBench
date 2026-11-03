"""GPIO25/26 probe inference from calibrated camera pixels, with no pin guesses."""
import json
from pathlib import Path

from .policy import check_policy
from .vision import (digest, finite, geometry_valid, led_state, load, read_images,
                     save, validate_capture)

PHASES = (None, 25, None, 26, None)


def infer(windows, source):
    """Pure inference; synthetic/replayed inputs retain their source label."""
    unknowns, responses = [], {}
    if [w.get("step") for w in windows] != list(range(1, 6)):
        unknowns.append("Missing, duplicate or out-of-order probe phases")
    for phase, window in enumerate(windows):
        if phase >= len(PHASES):
            break
        rows = window.get("measurements", [])
        pts = [r.get("sample_pts_seconds") for r in rows]
        start, end = window.get("start"), window.get("end")
        valid_times = (finite(start) and finite(end) and start < end and len(pts) >= 5
                       and all(finite(t) and start <= t <= end for t in pts))
        if (not valid_times or pts != sorted(set(pts)) or pts[0] - start > .55
                or end - pts[-1] > .55 or any(b-a > .65 for a, b in zip(pts, pts[1:]))):
            unknowns.append("phase %d: insufficient settled temporal coverage" % (phase + 1))
        if not rows or any(type(r.get(c)) is not bool for r in rows for c in ("red", "green")):
            unknowns.append("phase %d: missing/uncertain camera LED measurement" % (phase + 1))
            continue
        states = {(r["red"], r["green"]) for r in rows}
        pin = PHASES[phase]
        if pin is None:
            if states != {(False, False)}:
                unknowns.append("phase %d: off baseline did not settle off" % (phase + 1))
        elif states == {(True, False)}:
            responses[pin] = "red"
        elif states == {(False, True)}:
            responses[pin] = "green"
        else:
            unknowns.append("GPIO%d: response missing, unstable, or multiple LEDs active" % pin)
    mapping = None
    if set(responses) == {25, 26} and set(responses.values()) == {"red", "green"} and not unknowns:
        mapping = {color: pin for pin, color in responses.items()}
    else:
        unknowns.append("A unique complete one-to-one mapping is not supported")
    return {"schema_version": 1, "status": "mapped" if mapping else "incomplete",
            "mapping": mapping, "unknowns": unknowns, "source": source,
            "automatic_camera_mapping": bool(mapping and source == "saved_live_camera_frames"),
            "approved_gpio": [25, 26], "oled_bus": "fixed SDA21/SCL22 at 0x3C; not discovered",
            "servo_angle_deg": None, "servo_actuation": False,
            "full_behavior_verification": "incomplete_required_servo_measurements_missing"}


def probe_windows(run, frames):
    events = [json.loads(line) for line in (run / "uart.jsonl").read_text().splitlines()]
    starts = [i for i, row in enumerate(events) if row.get("kind") == "tx" and row.get("command") == "DISCOVER"]
    if len(starts) != 1:
        raise ValueError("Exactly one fresh DISCOVER command required")
    if any(r.get("command") not in ("ID", "DISCOVER", "PING", "STOP")
           for r in events if r.get("kind") == "tx"):
        raise ValueError("Unexpected serial command in discovery evidence")
    from .led_oled import STEP
    import re
    markers, stops = [], []
    for event in events[starts[0]+1:]:
        if event.get("kind") != "rx_line":
            continue
        line = event.get("line", "")
        if "ERROR" in line or re.search(r"\bBOOT\b", line):
            raise ValueError("Runtime error/reset in discovery evidence")
        match = STEP.fullmatch(line)
        if match:
            markers.append((int(match[1]), event["host_uptime_seconds"]))
        if line.startswith("VISUAL_STOPPED STATUS:COMPLETE "):
            stops.append(event["host_uptime_seconds"])
    if [i for i, _ in markers] != list(range(1, 6)) or len(stops) != 1:
        raise ValueError("Missing/duplicate discovery timing markers")
    times = [t for _, t in markers] + stops
    if not all(finite(t) for t in times) or not all(3 <= b-a <= 4 for a, b in zip(times, times[1:])):
        raise ValueError("Unsupported probe timing")
    return [{"step": i + 1, "start": times[i] + .65, "end": times[i+1] - .45,
             "frames": [f for f in frames if times[i] + .65 <= f["sample_pts_seconds"] <= times[i+1] - .45]}
            for i in range(5)]


def analyze_probes(run, policy_path, output):
    run, output = Path(run), Path(output)
    policy = load(policy_path)
    # Discovery needs no key or text requests: only calibrated LED pixel states.
    _, calibration_path = check_policy(policy_path, model=policy["model"])
    calibration = load(calibration_path)
    import platform
    if (calibration["native_reader_source_sha256"] != digest(Path(__file__).resolve().parents[2] / "tools/macos_vision/main.swift")
            or calibration["macos"] != platform.mac_ver()[0]
            or calibration["camera_id"] != load(run / "camera/capture.json")["camera"]["id"]):
        raise ValueError("Discovery calibration source/macOS/camera changed")
    from .camera import ROOT
    if calibration["reference_image_sha256"] != digest(ROOT / calibration["geometry"]["reference_frame"]):
        raise ValueError("Discovery reference frame changed")
    frames = validate_capture(run)
    windows = probe_windows(run, frames)
    output.mkdir(parents=True, exist_ok=False)
    save(output / "policy.snapshot.json", policy)
    selected = [f for w in windows for f in w["frames"]]
    raw = read_images(run, calibration["geometry"], selected, output, read_labels=False)
    measured = []
    for window in windows:
        readings = []
        for frame in window["frames"]:
            row = raw[frame["file"]]
            valid = geometry_valid(row, calibration["geometry"])
            readings.append({"file": frame["file"], "sample_pts_seconds": frame["sample_pts_seconds"],
                "sha256": digest(run / "camera" / frame["file"]),
                **{c: led_state(row.get("leds", {}).get(c, {}).get("mean_luma_srgb"), calibration["thresholds"][c])
                   if valid else None for c in ("red", "green")}})
        measured.append({k: v for k, v in window.items() if k != "frames"})
        measured[-1]["measurements"] = readings
    result = {**infer(measured, "saved_live_camera_frames"), "windows": measured,
              "source_run": str(run.resolve()), "calibration_sha256": digest(calibration_path)}
    check_policy(policy_path, model=policy["model"])
    save(output / "discovery.json", result)
    save(output / "integrity.json", {"sha256": {str(p.relative_to(output)): digest(p)
        for p in sorted(output.rglob("*")) if p.is_file()}})
    return result
