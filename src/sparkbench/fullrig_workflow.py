"""Explicit full-rig acquire -> measure -> compare. Never uploads firmware."""
import argparse
import json
from pathlib import Path

from .fullrig_verify import analyze, frozen_inputs
from .vision import digest, save


def execute(artifact, tracker, policy, spec, output, *, source_run=None, port=None,
            device_id=None, execute_sequence=False):
    if source_run is None and execute_sequence is not True:
        raise ValueError("Explicit execution opt-in required; no hardware/API I/O performed")
    plan, _, calibration, _, _, _, _ = frozen_inputs(artifact, tracker, policy, spec)
    if source_run is None and (not port or device_id != calibration["geometry"]["camera_id"]):
        raise ValueError("Fresh port and exact calibrated camera required")
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    frozen = {str(Path(p).resolve()): digest(p) for p in (tracker, policy, spec)}
    report = {"schema_version": 1, "status": "incomplete", "firmware_uploaded": False,
              "servo_actuation_requested": False, "full_behavior_verification": "incomplete"}
    save(output/"workflow.json", report)
    try:
        if source_run is None:
            from .fullrig_capture import acquire
            source_run = output/"capture"
            captured = acquire(port, device_id, artifact, source_run, execute_sequence=True)
            report["servo_actuation_requested"] = captured.get("servo_actuation_requested", False)
            if captured["status"] != "completed": raise ValueError("Acquisition incomplete")
        if any(digest(p) != sha for p, sha in frozen.items()): raise ValueError("Frozen inputs changed during acquisition")
        result = analyze(source_run, artifact, tracker, policy, spec, output/"analysis")
        report.update(status=result["status"], full_behavior_verification=result["status"],
                      source_run=str(Path(source_run).resolve()), verification="analysis/verification.json")
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="incomplete", error=str(exc), full_behavior_verification="incomplete")
    finally:
        save(output/"workflow.json", report)
        save(output/"integrity.json", {"sha256": {str(p.relative_to(output)): digest(p)
            for p in sorted(output.rglob('*')) if p.is_file() and p.name != "integrity.json"}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("artifact", "tracker", "policy", "spec", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--run", type=Path); parser.add_argument("--port"); parser.add_argument("--device-id")
    parser.add_argument("--execute-sequence", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args.artifact, args.tracker, args.policy, args.spec, args.output,
                         source_run=args.run, port=args.port, device_id=args.device_id, execute_sequence=args.execute_sequence)
    except (OSError, ValueError, KeyError, TypeError) as exc: parser.exit(2, str(exc)+"\n")
    print(json.dumps(result, indent=2)); return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
