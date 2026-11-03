"""Saved full-rig STOP/lease sampled-window qualification; no Meta requests.

UART reports shutdown timing/PWM state. Camera independently measures LEDs and
post-shutdown angle stability; neither measures the electrical PWM waveform.
"""
import argparse
import copy
import json
from pathlib import Path

from .fullrig_capture import STEP, STOP, identity
from .fullrig_verify import angles_from_trace, frozen_inputs, require_coverage
from .policy import check_integrity
from .servo_calibration import fingerprint
from .servo_tracking import track_saved
from .vision import digest, finite, geometry_valid, led_state, load, read_images, save, validate_capture


def fault_windows(events, frames, plan, case):
    if case not in ("stop", "lease"): raise ValueError("Expected STOP or lease case")
    starts = [i for i,r in enumerate(events) if r.get("kind") == "tx" and r.get("command") == "EXECUTE"]
    if len(starts) != 1: raise ValueError("Exactly one fresh EXECUTE required")
    events = events[starts[0]+1:]
    if any(r.get("command") not in ("PING", "STOP") for r in events if r.get("kind") == "tx"):
        raise ValueError("Unexpected command in fault capture")
    triggers = [i for i,r in enumerate(events) if r.get("kind") == "fault_trigger" and r.get("case") == case]
    if len(triggers) != 1: raise ValueError("One explicit fault trigger required")
    markers, stopped = [], []
    expected_reason = "STOP" if case == "stop" else "LEASE_EXPIRED"
    for i, row in enumerate(events):
        if row.get("kind") != "rx_line": continue
        line = row.get("line", "")
        if "BOOT" in line or "ERROR" in line or "FAULT" in line: raise ValueError("Fault capture contains reset/driver error")
        match = STEP.fullmatch(line)
        if match: markers.append((int(match[1]), int(match[2]), row["host_uptime_seconds"]))
        match = STOP.fullmatch(line)
        if match:
            reason, pwm, _ = match.groups()
            if pwm != "OFF" or reason not in (expected_reason, "STOP"): raise ValueError("Unexpected shutdown marker")
            if reason == expected_reason and i > triggers[0]: stopped.append((i, row["host_uptime_seconds"]))
    if len(markers) != 1 or markers[0][:2] != (1, plan["steps"][0]["pulse_us"]) or not stopped:
        raise ValueError("Fault must stop during first compiled dwell")
    stop_index, stop_time = stopped[0]; start = markers[0][2]
    command = "STOP" if case == "stop" else "PING"
    prior = [r["host_uptime_seconds"] for r in events[:stop_index] if r.get("kind") == "tx" and r.get("command") == command]
    if not prior or not finite(stop_time): raise ValueError("Shutdown command/lease timing absent")
    delay = stop_time-prior[-1]
    if not (0 <= delay <= .75 if case == "stop" else 1.2 <= delay <= 2.5):
        raise ValueError("Shutdown receipt outside qualification timing bounds")
    selected = [{"step": 1, "name": "energized", "start": start+.65, "end": stop_time-.15},
                {"step": 2, "name": "shutdown", "start": stop_time+.65, "end": stop_time+2.65}]
    for window in selected:
        window["frames"] = [f for f in frames if window["start"] <= f["sample_pts_seconds"] <= window["end"]]
    require_coverage(selected)
    return selected, delay


def analyze(run, artifact, tracker, policy, spec, output):
    run, output = Path(run).resolve(), Path(output).resolve()
    plan, artifact_record, calibration, tracker_config, _, leds, _ = frozen_inputs(artifact, tracker, policy, spec)
    check_integrity(run); frames = validate_capture(run); saved = load(run/"run.json"); case = saved.get("qualification_fault")
    if (saved.get("identity") != identity(plan) or saved.get("plan_sha256") != fingerprint(plan)
            or saved.get("firmware_sha256") != artifact_record["firmware_sha256"]
            or saved.get("action") != "EXECUTE" or saved.get("stop_acknowledged_uart_only") is not True
            or saved.get("device_id") != calibration["geometry"]["camera_id"]):
        raise ValueError("Fault acquisition is not bound to calibrated full runtime")
    events = [json.loads(line) for line in (run/"uart.jsonl").read_text().splitlines()]
    selected, delay = fault_windows(events, frames, plan, case)
    output.mkdir(parents=True, exist_ok=False)
    frozen = {str(Path(p).resolve()): digest(p) for p in (tracker, policy, spec)}
    report = {"schema_version": 1, "status": "incomplete", "case": case, "model_api_requests": 0,
              "source": "saved_live_camera_frames", "uart_shutdown_receipt_delay_seconds": delay,
              "scope": "Sampled LED shutdown and 2-second post-shutdown angle stability; not electrical PWM-off, torque, exact stopping latency or continuous behavior"}
    try:
        config = copy.deepcopy(tracker_config); config.update(source_capture=str(run/"camera"), recorded_motion_analysis=True)
        save(output/"tracker.analysis.json", config)
        tracked = track_saved(output/"tracker.analysis.json", output/"tracking")
        if tracked.get("quality_controls") != "pass": raise ValueError("Tracker digital controls fail")
        trace = [json.loads(line) for line in (output/"tracking/trace.jsonl").read_text().splitlines()]
        angles = angles_from_trace(trace, calibration)
        trace_hash = {r["file"]: r["source_image_sha256"] for r in trace}
        (output/"reader").mkdir()
        raw = read_images(run, leds["geometry"], [f for w in selected for f in w["frames"]], output/"reader", read_labels=False)
        failures, unknowns, windows = [], [], []
        for window in selected:
            rows = []
            for frame in window["frames"]:
                name = frame["file"]; image_hash = digest(run/"camera"/name)
                if trace_hash.get(name) != image_hash: raise ValueError("Tracker/image evidence mismatch")
                native = raw[name]; valid = geometry_valid(native, leds["geometry"])
                row = {"file": name, "sha256": image_hash, "sample_pts_seconds": frame["sample_pts_seconds"], "angle_deg": angles.get(name)}
                for color in ("red", "green"):
                    value = led_state(native.get("leds", {}).get(color, {}).get("mean_luma_srgb"), leds["thresholds"][color]) if valid else None
                    row[color] = value
                    target = plan["steps"][0][color] if window["name"] == "energized" else False
                    if type(value) is not bool: unknowns.append(name+" "+color)
                    elif value != target: failures.append(name+" "+color)
                if not finite(row["angle_deg"]): unknowns.append(name+" angle")
                rows.append(row)
            windows.append({k:v for k,v in window.items() if k != "frames"}); windows[-1]["measurements"] = rows
        after = [r["angle_deg"] for r in windows[1]["measurements"] if finite(r["angle_deg"])]
        span = max(after)-min(after) if after else None
        if span is not None and span > 3: failures.append("Post-shutdown sampled angle span exceeds 3 degrees")
        if not any(plan["steps"][0][c] for c in ("red", "green")): unknowns.append("No energized LED before shutdown")
        if any(digest(p) != sha for p,sha in frozen.items()): raise ValueError("Frozen settings changed")
        check_integrity(run); frozen_inputs(artifact, tracker, policy, spec)
        report.update(status="fail" if failures else "incomplete" if unknowns else "pass", windows=windows,
                      failures=failures, unknowns=unknowns, post_shutdown_sampled_angle_span_deg=span)
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="incomplete", error=str(exc))
    finally:
        save(output/"qualification.json", report)
        save(output/"integrity.json", {"sha256": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name != "integrity.json"}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "artifact", "tracker", "policy", "spec", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    try: result = analyze(args.run, args.artifact, args.tracker, args.policy, args.spec, args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc: parser.exit(2, str(exc)+"\n")
    print(json.dumps({**result, "windows": "See saved qualification.json"}, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__": raise SystemExit(main())
