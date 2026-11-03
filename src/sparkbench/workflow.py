"""One-command acquisition/measurement/comparison with frozen settings."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .camera import ROOT
from .policy import check_integrity, check_policy
from .vision import analyze, compare, digest, load, save, validate_capture, windows


def require_coverage(run, expected):
    """Reject known timing gaps before paying for any OLED model requests."""
    frames = validate_capture(run)
    for window in windows(run, frames, [s["step"] for s in expected]):
        pts = [f["sample_pts_seconds"] for f in window["frames"]]
        if (len(pts) < 5 or pts[0]-window["start"] > .55 or window["end"]-pts[-1] > .55
                or any(b-a > .65 for a,b in zip(pts,pts[1:]))):
            raise ValueError("step %d: insufficient temporal coverage; no Meta requests sent" % window["step"])


def execute(port, device_id, output, policy_path, spec_path, artifact_path=None, source_run=None,
            cancel=None, on_stage=None, analyzer=None):
    # Check all dependencies/settings before accessing hardware or spending API tokens.
    policy, calibration = check_policy(policy_path)
    spec = load(spec_path)
    from .plans import expected_plan, validate_against_spec
    if artifact_path:
        from .artifacts import load_artifact
        plan, artifact = load_artifact(artifact_path)
        validate_against_spec(plan, spec, plan["mapping"])
        if source_run:
            saved = load(Path(source_run) / "run.json")
            from .runtime_io import identity
            if (saved.get("plan_sha256") != artifact["plan_sha256"]
                    or saved.get("firmware_sha256") != artifact["firmware_sha256"]
                    or saved.get("identity") != identity(artifact["plan_sha256"])
                    or saved.get("action") != "VISUAL"):
                raise ValueError("Saved run is not bound to this runtime artifact; old diagnostic evidence cannot verify generated firmware")
    else:
        from .plans import validate_against_spec as validate
        installed = expected_plan(load(ROOT / "specs/led_oled_only.json"), {"red": 25, "green": 26})
        validate(installed, spec, {"red": 25, "green": 26})
    if source_run is None and (not port or not device_id):
        raise ValueError("Live capture requires explicit port and camera ID")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    policy_hash, spec_hash = digest(policy_path), digest(spec_path)
    save(output / "reader-policy.snapshot.json", policy)
    save(output / "spec.snapshot.json", spec)
    report = {"schema_version": 1, "status": "incomplete", "servo_actuation": False,
              "firmware_uploaded": False, "full_behavior_verification": "incomplete_required_servo_measurements_missing",
              "reader_model": policy["model"], "reader_policy_sha256": policy_hash,
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "LED/OLED sampled settled windows only"}
    if artifact_path:
        report["runtime_artifact"] = {"directory": str(Path(artifact_path).resolve()),
            "plan_sha256": artifact["plan_sha256"], "expected_firmware_sha256": artifact["firmware_sha256"],
            "hash_scope": "Local compiled artifact; not independent readback of installed binary"}
    save(output / "workflow.json", report)
    try:
        if cancel is not None and cancel.is_set():
            raise ValueError("Cancelled before acquisition")
        if source_run:
            run = Path(source_run).resolve()
            report["acquisition"] = "existing saved run; new analysis uses Meta API"
        else:
            run = output / "capture"
            if artifact_path:
                from .runtime_io import acquire
                if on_stage: on_stage("capture")
                capture = acquire(port, device_id, artifact_path, run, **({"cancel":cancel} if cancel is not None else {}))
            else:
                from .led_oled import run as acquire
                capture = acquire(port, device_id, run)
            report["acquisition"] = capture["status"]
            if capture["status"] != "completed":
                raise ValueError("Acquisition incomplete; no automatic behavior pass")
        check_policy(policy_path)
        if digest(policy_path) != policy_hash or digest(spec_path) != spec_hash:
            raise ValueError("Policy or specification changed during acquisition")
        require_coverage(run, spec["steps"])
        if cancel is not None and cancel.is_set():
            raise ValueError("Cancelled before analysis; no model requests sent")
        if on_stage: on_stage("analysis")
        result = (analyzer or analyze)(run, calibration, output / "spec.snapshot.json", output / "analysis")
        check_policy(policy_path)
        if digest(policy_path) != policy_hash:
            raise ValueError("Policy changed during analysis")
        report.update(status=result["status"], verification="analysis/verification.json",
                      source_run=str(run), failures=len(result["failures"]), unknowns=len(result["unknowns"]))
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="incomplete", error=str(exc))
    finally:
        report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        save(output / "workflow.json", report)
        save(output / "integrity.json", {"sha256": {str(p.relative_to(output)): digest(p)
            for p in sorted(output.rglob("*")) if p.is_file() and p != output / "integrity.json"}})
    return report


def replay(analysis, output):
    """No camera, serial or API: recheck recorded measurements and controls."""
    analysis, output = Path(analysis).resolve(), Path(output).resolve()
    entries = check_integrity(analysis)
    if not {"verification.json", "spec.snapshot.json", "reader.jsonl", "calibration.snapshot.json"} <= set(entries):
        raise ValueError("Replay requires integrity-covered verification, spec, reader and calibration")
    result = load(analysis / "verification.json")
    spec = load(analysis / "spec.snapshot.json")
    # Reconstruct values from independent raw pixel/Meta records, not cached assertions.
    from .vision import geometry_valid, led_state, oled_text
    calibration = load(analysis / "calibration.snapshot.json")
    raw = [json.loads(line) for line in (analysis / "reader.jsonl").read_text().splitlines()]
    by_id = {r["id"]: r for r in raw}
    if len(by_id) != len(raw):
        raise ValueError("Duplicate independent reader IDs")
    import copy
    windows = copy.deepcopy(result["windows"])
    wanted = []
    for window in windows:
        for frame in window["measurements"]:
            wanted.append(frame["native_result_id"])
            row = by_id.get(frame["native_result_id"], {})
            valid = geometry_valid(row, calibration["geometry"])
            for c in ("red", "green"):
                frame[c] = led_state(row.get("leds", {}).get(c, {}).get("mean_luma_srgb"), calibration["thresholds"][c]) if valid else None
            frame["oled_text"] = oled_text(row) if valid else None
    if len(set(wanted)) != len(wanted) or set(wanted) != set(by_id):
        raise ValueError("Missing/extra measured frame IDs in replay")
    rechecked = compare(spec["steps"], windows)
    controls = {}
    for kind in (("wrong_led", "wrong_oled", "missing_reading") if rechecked["status"] == "pass" else ()):
        expected, measured = copy.deepcopy(spec["steps"]), copy.deepcopy(windows)
        if kind == "wrong_led":
            expected[0]["red"] = not expected[0]["red"]
        elif kind == "wrong_oled":
            expected[0]["oled_text"] = "DELIBERATELY WRONG"
        else:
            measured[0]["measurements"][0]["oled_text"] = None
        controls[kind] = compare(expected, measured)["status"]
    controls_ok = (rechecked["status"] != "pass" or controls == {
        "wrong_led": "fail", "wrong_oled": "fail", "missing_reading": "incomplete"})
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "status": "pass" if rechecked == {k: result[k] for k in ("status", "failures", "unknowns")} and controls_ok else "fail",
              "source": "offline_replay_of_saved_measurements", "source_analysis": str(analysis),
              "comparison": rechecked, "digital_controls": controls,
              "physical_fault_injection": False, "new_camera_or_meta_requests": False,
              "note": "Replay regression only; no new physical acceptance evidence"}
    save(output / "replay.json", report)
    return report
