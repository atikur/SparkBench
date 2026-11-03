"""Camera qualification of explicit STOP and withheld-keepalive LED shutdown.

Only DISCOVER, ID, PING and STOP are sent by the existing gated runtime runner.
No Meta text requests, flashing, servo commands or electrical timing claims.
"""
import argparse
import json
import platform
from pathlib import Path

from .camera import ROOT
from .policy import check_policy
from .vision import (digest, finite, geometry_valid, led_state, load, read_images,
                     save, validate_capture)


def evaluate(events, frames, measurements, case):
    if case not in ("stop", "lease"):
        raise ValueError("Unsupported qualification case")
    triggers = [r for r in events if r.get("kind") == "fault_trigger" and r.get("case") == case]
    starts = [r for r in events if r.get("kind") == "tx" and r.get("command") == "DISCOVER"]
    if len(triggers) != 1 or len(starts) != 1:
        raise ValueError("Exactly one gated probe and fault trigger required")
    trigger = triggers[0]["host_uptime_seconds"]
    bright = [r for r in events if r.get("kind") == "rx_line"
              and r.get("line", "").startswith("VISUAL_STEP:2 ") and r["host_uptime_seconds"] > starts[0]["host_uptime_seconds"]]
    reason = "STOPPED" if case == "stop" else "LEASE_EXPIRED"
    stopped = [r for r in events if r.get("kind") == "rx_line" and r.get("line", "").startswith(
        "VISUAL_STOPPED STATUS:" + reason + " ") and r["host_uptime_seconds"] > trigger]
    if len(bright) != 1 or not stopped:
        raise ValueError("Missing bright-phase or expected shutdown marker")
    end = stopped[0]["host_uptime_seconds"]
    if not all(finite(t) for t in (trigger, end, bright[0]["host_uptime_seconds"])):
        raise ValueError("Invalid fault timestamps")
    if any(r.get("kind") == "tx" and r.get("command") not in ("ID", "DISCOVER", "PING", "STOP") for r in events):
        raise ValueError("Unexpected command in qualification")
    active_events = [r for r in events if starts[0]["host_uptime_seconds"] <= r["host_uptime_seconds"] < end]
    for r in active_events:
        if r.get("kind") == "rx_line":
            line = r.get("line", "")
            if " BOOT " in line or ("ERROR" in line and line != "VISUAL_ERROR LEASE_EXPIRED"):
                raise ValueError("Unexpected runtime reset/error")
            if line.startswith(("VISUAL_STEP:3 ", "VISUAL_STEP:4 ", "VISUAL_STEP:5 ")):
                raise ValueError("Shutdown did not precede the natural next probe phase")
    pings = [r["host_uptime_seconds"] for r in active_events if r.get("kind") == "tx" and r.get("command") == "PING"]
    if not pings:
        raise ValueError("No keepalive evidence")
    serial_delay = end - pings[-1] if case == "lease" else end - next(
        r["host_uptime_seconds"] for r in events if r.get("kind") == "tx" and r.get("command") == "STOP" and r["host_uptime_seconds"] >= trigger)
    serial_ok = 1.4 <= serial_delay <= 2.2 if case == "lease" else 0 <= serial_delay <= .7
    if case == "lease" and any(t > trigger for t in pings):
        raise ValueError("Keepalive was not actually withheld")
    selected = []
    unknowns, failures = [], []
    for name, start, stop, expected in (
            ("energized_before_shutdown", bright[0]["host_uptime_seconds"] + .65, end - .3, {"red": True, "green": False}),
            ("off_after_shutdown", end + .65, end + 2.65, {"red": False, "green": False})):
        readings = []
        for frame in frames:
            if start <= frame["sample_pts_seconds"] <= stop:
                value = measurements.get(frame["file"], {})
                readings.append({"file": frame["file"], "sample_pts_seconds": frame["sample_pts_seconds"],
                                 "red": value.get("red"), "green": value.get("green")})
        pts = [r["sample_pts_seconds"] for r in readings]
        if (len(pts) < 5 or pts != sorted(set(pts)) or pts[0]-start > .55 or stop-pts[-1] > .55
                or any(b-a > .65 for a,b in zip(pts,pts[1:]))):
            unknowns.append(name + ": insufficient settled camera coverage")
        for row in readings:
            for channel in ("red", "green"):
                if type(row[channel]) is not bool:
                    unknowns.append(name + " " + row["file"] + " " + channel + ": unknown")
                elif row[channel] != expected[channel]:
                    failures.append(name + " " + row["file"] + " " + channel + ": mismatch")
        selected.append({"name": name, "start": start, "end": stop, "measurements": readings})
    if not serial_ok:
        failures.append("UART shutdown receipt outside qualification bounds")
    return {"schema_version": 1, "status": "fail" if failures else "incomplete" if unknowns else "pass",
            "case": case, "source": "saved_live_camera_frames", "windows": selected,
            "failures": failures, "unknowns": unknowns, "uart_receipt_delay_seconds": serial_delay,
            "scope": "LED energized/off sampled windows plus UART shutdown timing; no GPIO waveform or exact electrical latency claim",
            "servo_angle_deg": None, "servo_actuation": False,
            "full_behavior_verification": "incomplete_required_servo_measurements_missing"}


def analyze_case(run, policy_path, output, case):
    run, output = Path(run), Path(output)
    policy = load(policy_path)
    _, calibration_path = check_policy(policy_path, model=policy["model"])
    calibration = load(calibration_path)
    if (calibration["native_reader_source_sha256"] != digest(ROOT / "tools/macos_vision/main.swift")
            or calibration["camera_id"] != load(run / "camera/capture.json")["camera"]["id"]
            or calibration["macos"] != platform.mac_ver()[0]
            or calibration["reference_image_sha256"] != digest(ROOT / calibration["geometry"]["reference_frame"])):
        raise ValueError("Frozen camera calibration no longer matches")
    frames = validate_capture(run)
    events = [json.loads(line) for line in (run / "uart.jsonl").read_text().splitlines()]
    # Derive only selection/timing first; unknown placeholder states cannot pass.
    selection = evaluate(events, frames, {}, case)
    names = {r["file"] for w in selection["windows"] for r in w["measurements"]}
    output.mkdir(parents=True, exist_ok=False)
    save(output / "policy.snapshot.json", policy)
    raw = read_images(run, calibration["geometry"], [f for f in frames if f["file"] in names], output, read_labels=False)
    measured = {}
    for name, row in raw.items():
        valid = geometry_valid(row, calibration["geometry"])
        measured[name] = {c: led_state(row.get("leds", {}).get(c, {}).get("mean_luma_srgb"), calibration["thresholds"][c]) if valid else None
                          for c in ("red", "green")}
    result = evaluate(events, frames, measured, case)
    for window in result["windows"]:
        for row in window["measurements"]:
            row["sha256"] = digest(run / "camera" / row["file"])
    result["source_run"] = str(run.resolve())
    check_policy(policy_path, model=policy["model"])
    save(output / "qualification.json", result)
    save(output / "integrity.json", {"sha256": {str(p.relative_to(output)): digest(p)
        for p in sorted(output.rglob('*')) if p.is_file()}})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--case", choices=("stop", "lease"), required=True)
    parser.add_argument("--policy", type=Path, default=ROOT/"hardware/oled-reader.policy.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy = load(args.policy)
    check_policy(args.policy, model=policy["model"])
    args.output.mkdir(parents=True, exist_ok=False)
    from .runtime_io import acquire
    capture = acquire(args.port, args.device_id, args.artifact, args.output/"capture", "DISCOVER", fault=args.case)
    result = {"status": "incomplete", "case": args.case}
    if capture["status"] == "completed":
        try:
            result = analyze_case(args.output/"capture", args.policy, args.output/"analysis", args.case)
        except (OSError, ValueError, KeyError) as exc:
            result["error"] = str(exc)
    else:
        result["error"] = capture.get("error", "Fault capture incomplete")
    save(args.output/"qualification.json", result)
    print(json.dumps({**result, "windows": "See saved per-frame evidence"}, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
