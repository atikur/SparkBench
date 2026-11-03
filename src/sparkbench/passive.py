"""Bounded camera-only session and post-capture readiness/recovery reporting.

No serial, firmware or model API imports. Session states qualify a preview only;
they never create calibrated angles or a physical behavior pass.
"""
import argparse
import copy
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .camera import ROOT, build_helper, capture_frames, list_cameras
from .servo_tracking import build_tracker, track_saved
from .vision import digest, finite, load, save


DEFAULT_POLICY = {"ready_good_frames": 3, "ready_span_seconds": 0.5,
                  "maximum_frame_gap_seconds": 1.0}


def session_quality(rows, tracking, policy=None):
    """Causal states on every row; no filtering, backdating or trace mutation."""
    policy = dict(DEFAULT_POLICY if policy is None else policy)
    if (type(policy.get("ready_good_frames")) is not int or policy["ready_good_frames"] < 2
            or not finite(policy.get("ready_span_seconds")) or policy["ready_span_seconds"] < 0
            or not finite(policy.get("maximum_frame_gap_seconds")) or policy["maximum_frame_gap_seconds"] <= 0):
        raise ValueError("Invalid readiness policy")
    if [r.get("frame") for r in rows] != list(range(1, len(rows)+1)):
        raise ValueError("Ordered consecutive source frame IDs required")
    allowed = tracking.get("status") == "unverified_tracking_available" and tracking.get("quality_controls") == "pass"
    trace, events, gaps, deltas = [], [], [], []
    state, ever_ready, streak, streak_pts = "starting", False, 0, None
    previous_pts, first_ready, losses, recoveries = None, None, 0, 0
    credited, unobserved = Counter(), 0.0
    for source in rows:
        row = copy.deepcopy(source)
        pts, host = row.get("sample_pts_seconds"), row.get("host_uptime_seconds")
        reasons = list(row.get("reasons", []))
        if not allowed:
            reasons.append("tracking_report_incomplete_or_controls_failed")
        if not finite(pts) or not finite(host) or not 0 <= host-pts <= 1:
            reasons.append("unsupported_camera_timestamp_alignment")
        if finite(pts) and finite(host):
            deltas.append(host-pts)
        if finite(pts) and previous_pts is not None:
            dt = pts-previous_pts
            if dt <= 0:
                reasons.append("nonincreasing_camera_timestamp")
            elif dt > policy["maximum_frame_gap_seconds"]:
                reasons.append("capture_gap")
                gaps.append({"frame": row["frame"], "seconds": dt})
                unobserved += dt
            elif trace:
                # Adjacent-sample accounting only; no claim about motion between frames.
                credited[trace[-1]["session_state"]] += dt
        if finite(pts):
            previous_pts = pts
        preview, points = row.get("preview_estimates"), row.get("localized_points")
        if row.get("status") != "tracked_unverified":
            reasons.append("source_tracking_unknown")
        if (not isinstance(preview, dict) or not finite(preview.get("apparent_image_heading_deg"))
                or not isinstance(points, dict) or any(not isinstance(points.get(k), list)
                    or len(points[k]) != 2 or not all(finite(v) for v in points[k]) for k in ("pivot_px", "tip_px"))):
            reasons.append("source_preview_unavailable")
        reasons = list(dict.fromkeys(reasons))
        good = not reasons
        before = state
        if not good:
            streak, streak_pts = 0, None
            if ever_ready:
                if state == "tracking":
                    losses += 1
                state = "lost"
            else:
                state = "starting"
        else:
            if streak == 0:
                streak_pts = pts
            streak += 1
            stable = streak >= policy["ready_good_frames"] and pts-streak_pts >= policy["ready_span_seconds"]
            if stable:
                if not ever_ready:
                    first_ready = {"frame": row["frame"], "sample_pts_seconds": pts}
                    ever_ready = True
                elif state != "tracking":
                    recoveries += 1
                state = "tracking"
            else:
                state = "recovering" if ever_ready else "starting"
        if state != before:
            events.append({"frame": row["frame"], "sample_pts_seconds": pts,
                           "from": before, "to": state, "reasons": reasons})
        row.update(session_state=state, session_input_reasons=reasons,
                   consecutive_good_frames=streak, preview_available=good and state == "tracking",
                   session_preview_estimates=preview if good and state == "tracking" else None,
                   angle_deg=None, eligible_for_verifier=False, calibrated_angle_verification=False)
        # Preserve original row status/points/preview in this copy for auditing;
        # the session_preview field alone is the readiness-qualified preview.
        trace.append(row)
    unknown_intervals = []
    for row in trace:
        if row["session_input_reasons"]:
            if not unknown_intervals or unknown_intervals[-1]["end_frame"] != row["frame"]-1:
                unknown_intervals.append({"start_frame": row["frame"], "end_frame": row["frame"],
                    "start_pts": row.get("sample_pts_seconds"), "end_pts": row.get("sample_pts_seconds"), "frames": 0})
            interval = unknown_intervals[-1]
            interval.update(end_frame=row["frame"], end_pts=row.get("sample_pts_seconds"), frames=interval["frames"]+1)
    for interval in unknown_intervals:
        a, b = interval["start_pts"], interval["end_pts"]
        interval["sampled_span_seconds"] = b-a if finite(a) and finite(b) and b >= a else None
    counts = Counter(r["session_state"] for r in trace)
    tracked = sum(r.get("status") == "tracked_unverified" for r in trace)
    qualified = sum(r["preview_available"] for r in trace)
    pts = [r.get("sample_pts_seconds") for r in trace]
    monotonic = all(finite(p) for p in pts) and all(b > a for a, b in zip(pts, pts[1:]))
    span = pts[-1]-pts[0] if len(pts) > 1 and monotonic else None
    good_headings = [r["session_preview_estimates"]["apparent_image_heading_deg"] for r in trace if r["preview_available"]]
    report = {"schema_version": 1, "status": "preview_intervals_available" if qualified else "no_ready_interval",
        "scope": "Post-capture static unverified preview quality; no live readiness gate or physical behavior pass",
        "policy": policy, "frames": len(trace), "raw_tracked_frames": tracked,
        "raw_unknown_frames": len(trace)-tracked, "session_preview_frames": qualified,
        "raw_localization_fraction": tracked/len(trace) if trace else None,
        "session_preview_fraction": qualified/len(trace) if trace else None,
        "state_counts": {s: counts[s] for s in ("starting", "tracking", "lost", "recovering")},
        "first_ready": first_ready, "tracking_losses": losses, "recoveries": recoveries,
        "final_state": state, "events": events, "unknown_intervals": unknown_intervals,
        "reason_counts": dict(Counter(s for r in trace for s in r["session_input_reasons"])),
        "sample_pts_span_seconds": span, "observed_sample_fps": (len(trace)-1)/span if span else None,
        "timestamp_host_minus_pts_range_seconds": [min(deltas), max(deltas)] if deltas else None,
        "capture_gaps": gaps, "unobserved_gap_seconds": unobserved,
        "adjacent_sample_interval_seconds_by_previous_state": dict(credited),
        "duration_scope": "Adjacent sample intervals only; gaps above policy limit uncredited, no extrapolation before first/after last sample; between-frame behavior unverified",
        "apparent_static_heading_span_deg": max(good_headings)-min(good_headings) if good_headings else None,
        "heading_scope": "Static image repeatability only, not physical angular accuracy",
        "angle_deg": None, "eligible_for_verifier": False,
        "full_behavior_verification": "incomplete_required_servo_measurements_missing"}
    return trace, report


def write_quality(analysis, output, policy):
    rows = [json.loads(line) for line in (analysis/"trace.jsonl").read_text().splitlines()]
    trace, report = session_quality(rows, load(analysis/"tracking.json"), policy)
    (output/"session-trace.jsonl").write_text("".join(json.dumps(r)+"\n" for r in trace))
    save(output/"quality.json", report)
    lines = ["# Passive camera session", "", "Unverified static preview only. Actual shaft angles remain unknown.", "",
        f"- Source frames: {report['frames']}; localized: {report['raw_tracked_frames']}; unknown: {report['raw_unknown_frames']}.",
        f"- Readiness-qualified preview frames: {report['session_preview_frames']}. All frames remain in the trace.",
        f"- States: {report['state_counts']}; final state: {report['final_state']}.",
        f"- Tracking losses: {report['tracking_losses']}; recoveries: {report['recoveries']}.",
        f"- First ready: {report['first_ready']}.",
        f"- Timestamp host-minus-PTS range: {report['timestamp_host_minus_pts_range_seconds']} seconds.",
        f"- Gaps above the frozen limit: {len(report['capture_gaps'])}.", "",
        "Readiness is reported after capture, not used to control hardware. Startup/lost/recovering frames never display a session preview.",
        "Raw analysis, source images, timestamps and unknowns are retained. No interpolation or carried-forward preview occurs.", "",
        "## Unknown intervals", "", "| First frame | Last frame | Samples | Sampled span (s) |", "| ---: | ---: | ---: | ---: |"]
    lines += [f"| {v['start_frame']} | {v['end_frame']} | {v['frames']} | {v['sampled_span_seconds']} |" for v in report["unknown_intervals"]]
    lines += ["", "These are sampled spans, not measured physical outage durations. Full details: quality.json and session-trace.jsonl.", ""]
    (output/"report.md").write_text("\n".join(lines))
    return report


def run_session(config_path, device_id, output, seconds=60, fps=5):
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Exact camera ID required")
    if not finite(seconds) or not 1 <= seconds <= 60 or not finite(fps) or not 1 <= fps <= 10:
        raise ValueError("Bounded capture requires 1–60 seconds and 1–10 FPS")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"schema_version": 1, "status": "incomplete", "phase": "preflight",
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "camera_id": device_id,
        "requested_seconds": seconds, "requested_fps": fps, "servo_actuation": False,
        "serial_commands_sent": [], "model_api_requests": 0, "firmware_uploaded": False,
        "angle_deg": None, "eligible_for_verifier": False,
        "full_behavior_verification": "incomplete_required_servo_measurements_missing"}
    save(output/"session.json", record)
    try:
        config = load(config_path)
        preview_path = ROOT/config["preview_config"]
        preview = load(preview_path)
        reference = ROOT/preview["reference_frame"]
        if (config.get("mode") != "unverified_passive_tracking" or preview.get("camera_id") != device_id
                or digest(preview_path) != config["preview_config_sha256"]
                or digest(reference) != preview["reference_sha256"]):
            raise ValueError("Camera/reference identity mismatch; no fallback or capture")
        inputs = output/"inputs"
        inputs.mkdir()
        import shutil
        shutil.copy2(reference, inputs/"reference.jpg")
        preview["reference_frame"] = str(inputs/"reference.jpg")
        save(inputs/"preview.json", preview)
        save(inputs/"original-config.json", config)
        config.update(preview_config=str(inputs/"preview.json"), preview_config_sha256=digest(inputs/"preview.json"),
                      source_capture=str(output/"camera"))
        save(inputs/"tracker.frozen.json", config)
        policy = dict(DEFAULT_POLICY, maximum_frame_gap_seconds=config["temporal_policy"]["maximum_frame_gap_seconds"])
        save(inputs/"session-policy.json", policy)
        sources = ["src/sparkbench/passive.py", "src/sparkbench/__main__.py", "src/sparkbench/camera.py",
                   "src/sparkbench/servo_tracking.py", "src/sparkbench/servo_preview.py",
                   "tools/macos_camera/main.swift", "tools/macos_camera/Info.plist",
                   "tools/macos_servo_tracker/Tracker.swift", "tools/macos_servo_tracker/main.swift"]
        hashes = {}
        for name in sources:
            path = ROOT/name
            target = inputs/"source"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            hashes[name] = digest(path)
        helpers = {"camera": digest(build_helper()), "tracker": digest(build_tracker())}
        enumeration = list_cameras()
        save(output/"camera-enumeration.json", enumeration)
        selected = [d for d in enumeration.get("devices", []) if d.get("id") == device_id and d.get("connected")]
        if len(selected) != 1:
            raise ValueError("Selected camera absent/denied in this execution context; inspect saved permission/enumeration. No fallback. Sandbox denial does not prove host unavailability.")
        frozen = {"source_sha256": hashes, "locally_built_helper_sha256": helpers,
                  "tracker_config_sha256": digest(inputs/"tracker.frozen.json"),
                  "session_policy_sha256": digest(inputs/"session-policy.json"),
                  "camera": selected[0], "frozen_at_utc": datetime.now(timezone.utc).isoformat()}
        save(output/"preflight.json", frozen)
        record["phase"] = "capture"
        save(output/"session.json", record)
        capture = capture_frames(device_id, seconds, fps, output/"camera")
        record["capture"] = capture
        if (any(digest(ROOT/n) != h for n, h in hashes.items())
                or digest(inputs/"tracker.frozen.json") != frozen["tracker_config_sha256"]
                or digest(inputs/"session-policy.json") != frozen["session_policy_sha256"]):
            raise ValueError("Source/settings changed after freeze; raw capture retained, analysis incomplete")
        record["phase"] = "analysis"
        save(output/"session.json", record)
        tracking = track_saved(inputs/"tracker.frozen.json", output/"analysis")
        record["tracking"] = tracking
        if "error" in tracking or not (output/"analysis/trace.jsonl").is_file():
            raise ValueError("Tracking analysis incomplete: "+str(tracking.get("error", tracking["status"])))
        quality = write_quality(output/"analysis", output, policy)
        record.update(status=quality["status"], phase="complete", frames=quality["frames"],
                      raw_tracked_frames=quality["raw_tracked_frames"], raw_unknown_frames=quality["raw_unknown_frames"],
                      session_preview_frames=quality["session_preview_frames"], source_unchanged_since_freeze=True)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        record["error"] = str(exc)
    finally:
        record["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        save(output/"session.json", record)
        save(output/"integrity.json", {"sha256": {str(p.relative_to(output)): digest(p)
            for p in sorted(output.rglob("*")) if p.is_file() and p != output/"integrity.json"}})
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", required=True, help="Exact ID matching the initialized reference; no fallback")
    parser.add_argument("--config", type=Path, default=ROOT/"hardware/servo.tracker.subpixel.pending.json")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--fps", type=float, default=5)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    args = parser.parse_args(argv)
    try:
        report = run_session(args.config, args.device_id, args.output, args.seconds, args.fps)
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc)+"\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "preview_intervals_available" else 2


if __name__ == "__main__":
    raise SystemExit(main())
