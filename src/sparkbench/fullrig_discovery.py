"""Saved full-runtime LED probe inference; camera pixels only, no model/serial."""
import argparse
import json
import platform
from pathlib import Path

from .camera import ROOT
from .discovery import infer
from .fullrig import load_artifact, requested_behavior
from .fullrig_capture import identity
from .fullrig_verify import require_coverage, windows
from .policy import check_integrity, check_policy
from .vision import digest, geometry_valid, led_state, load, read_images, save, validate_capture


def analyze(run, artifact_path, policy_path, output, spec_path=None):
    run, output = Path(run).resolve(), Path(output).resolve()
    plan, artifact = load_artifact(artifact_path)
    policy = load(policy_path); _, calibration_path = check_policy(policy_path, model=policy["model"])
    calibration = load(calibration_path); policy_hash = digest(policy_path)
    if (calibration["macos"] != platform.mac_ver()[0]
            or calibration["native_reader_source_sha256"] != digest(ROOT/"tools/macos_vision/main.swift")
            or calibration["reference_image_sha256"] != digest(ROOT/calibration["geometry"]["reference_frame"])):
        raise ValueError("Frozen LED calibration no longer matches")
    check_integrity(run); frames = validate_capture(run); saved = load(run/"run.json")
    action = saved.get("action")
    if (action not in ("DISCOVER", "LEDS") or saved.get("servo_actuation_requested") is not False
            or saved.get("qualification_fault") is not None or saved.get("identity") != identity(plan)
            or saved.get("plan_sha256") != artifact["plan_sha256"]
            or saved.get("firmware_sha256") != artifact["firmware_sha256"]
            or saved.get("device_id") != calibration["camera_id"]
            or saved.get("stop_acknowledged_uart_only") is not True):
        raise ValueError("Saved run is not a complete bound servo-free full-runtime probe")
    expected = None
    if action == "LEDS":
        if plan["profile"] != "behavior" or spec_path is None:
            raise ValueError("LEDS check requires bound behavior specification")
        expected = requested_behavior(load(spec_path), plan["mapping"])
        actual = {"schema_version": 1, "mapping": plan["mapping"], "steps": [
            {k: s[k] for k in ("angle_deg", "red", "green", "text")} for s in plan["steps"]]}
        if actual != expected: raise ValueError("LEDS artifact differs from independent specification")
    selected = windows(run, frames, plan, action); require_coverage(selected)
    output.mkdir(parents=True, exist_ok=False)
    save(output/"policy.snapshot.json", policy); save(output/"calibration.snapshot.json", calibration)
    save(output/"plan.snapshot.json", plan)
    if spec_path is not None: save(output/"spec.snapshot.json", load(spec_path))
    raw = read_images(run, calibration["geometry"], [f for w in selected for f in w["frames"]], output, read_labels=False)
    measured = []
    for window in selected:
        readings = []
        for frame in window["frames"]:
            row = raw[frame["file"]]; valid = geometry_valid(row, calibration["geometry"])
            readings.append({"file": frame["file"], "sample_pts_seconds": frame["sample_pts_seconds"],
                "sha256": digest(run/"camera"/frame["file"]),
                **{c: led_state(row.get("leds", {}).get(c, {}).get("mean_luma_srgb"), calibration["thresholds"][c]) if valid else None for c in ("red", "green")}})
        measured.append({k: v for k, v in window.items() if k != "frames"})
        measured[-1]["measurements"] = readings
    if digest(policy_path) != policy_hash: raise ValueError("Reader policy changed during discovery")
    check_policy(policy_path, model=policy["model"]); check_integrity(run)
    if action == "DISCOVER":
        result = infer(measured, "saved_live_camera_frames")
    else:
        unknowns, failures = [], []
        for step, window in zip(expected["steps"], measured):
            for row in window["measurements"]:
                for color in ("red", "green"):
                    if type(row[color]) is not bool: unknowns.append(row["file"]+" "+color)
                    elif row[color] != step[color]: failures.append(row["file"]+" "+color)
        result = {"status": "fail" if failures else "incomplete" if unknowns else "pass", "failures": failures,
                  "unknowns": unknowns, "scope": "Sampled LED states only; OLED and servo not measured", "servo_actuation": False}
    result = {**result, "windows": measured,
              "source_run": str(run), "policy_sha256": policy_hash, "model_api_requests": 0,
              "blind_trial": "Not established by inference; ground truth must stay hidden until this report is frozen"}
    save(output/("discovery.json" if action == "DISCOVER" else "led-verification.json"), result)
    save(output/"integrity.json", {"sha256": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "artifact", "policy", "output"): parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--spec", type=Path)
    args = parser.parse_args()
    try: result = analyze(args.run, args.artifact, args.policy, args.output, args.spec)
    except (OSError, ValueError, KeyError, TypeError) as exc: parser.exit(2, str(exc)+"\n")
    print(json.dumps({**result, "windows": "See saved discovery.json"}, indent=2))
    return 0 if result["status"] in ("mapped", "pass") else 1 if result["status"] == "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
