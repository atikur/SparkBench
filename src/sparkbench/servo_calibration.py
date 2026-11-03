"""Offline physical-angle calibration. No camera, serial, firmware or API I/O.

Independent protractor readings validate image geometry; commanded pulses never
become observed angles. Synthetic records exercise software only.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from .camera import ROOT
from .plans import canonical
from .servo_geometry import perspective, point, project
from .servo_preview import heading
from .vision import digest, finite, load, save

MAX_ERROR_DEG = 3.0  # Half of the original Behavior A/B six-degree tolerance.
MEASUREMENT_SOURCES = ("src/sparkbench/servo_calibration.py", "src/sparkbench/servo_geometry.py",
                       "src/sparkbench/servo_preview.py", "src/sparkbench/servo_tracking.py",
                       "tools/macos_servo_tracker/Tracker.swift", "tools/macos_servo_tracker/main.swift")


def measurement_sources():
    return {name: digest(ROOT/name) for name in MEASUREMENT_SOURCES}


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def angle_from_points(geometry, pivot, tip, camera_transform=None):
    plane = perspective(geometry.get("plane_reference"))
    zero = geometry.get("zero_reference")
    if (plane["image_to_plane"] is None or not isinstance(zero, dict)
            or zero.get("confirmed") is not True
            or zero.get("method") != "fixed_protractor_baseline"
            or type(zero.get("direction")) is not int or zero["direction"] not in (-1, 1)):
        raise ValueError("Confirmed horn-plane geometry and independent zero baseline required")
    # Undo the frozen tracker's reference-to-current camera similarity transform.
    def reference_point(value):
        x, y = point(value)
        if camera_transform is None:
            return [x, y]
        if (not isinstance(camera_transform, list) or len(camera_transform) != 6
                or not all(finite(v) for v in camera_transform)):
            raise ValueError("Invalid camera registration")
        a, b, c, d, e, f = camera_transform
        det = a*e-b*d
        if abs(det) < 1e-9:
            raise ValueError("Degenerate camera registration")
        return [(e*(x-c)-b*(y-f))/det, (-d*(x-c)+a*(y-f))/det]
    matrix = plane["image_to_plane"]
    baseline = zero.get("endpoints_px")
    if not isinstance(baseline, list) or len(baseline) != 2:
        raise ValueError("Two fixed zero-baseline endpoints required")
    a, b = [project(matrix, reference_point(p)) for p in (pivot, tip)]
    z = [project(matrix, p) for p in baseline]
    value = (zero["direction"]*(heading(a, b)-heading(*z))) % 360
    if value > 180 + 1e-6:
        raise ValueError("Observed horn lies outside the defined zero-to-180 degree sector")
    return min(value, 180.0)


def qualify(record):
    """Evaluate supplied evidence; flags/provenance are recorded, not authenticated."""
    if record.get("schema_version") != 1 or record.get("kind") not in ("physical", "synthetic"):
        raise ValueError("Explicit physical or synthetic calibration record required")
    geometry = record.get("geometry", {})
    uncertainty = record.get("independent_reader_uncertainty_deg")
    if not finite(uncertainty) or not 0 < uncertainty <= 1.5:
        raise ValueError("Independent reference reading uncertainty must be stated and <=1.5 degrees")
    if (not geometry.get("camera_id") or not geometry.get("tracker_settings_sha256")
            or not geometry.get("reference_frame") or not geometry.get("reference_sha256")):
        raise ValueError("Frozen camera, tracker and reference identity required")
    if digest(ROOT / geometry["reference_frame"]) != geometry["reference_sha256"]:
        raise ValueError("Calibration reference image changed")
    if record["kind"] == "physical" and (geometry.get("measurement_sources_sha256") != measurement_sources()
            or not geometry.get("tracker_temporal_policy_sha256")):
        raise ValueError("Physical calibration measurement source/policy changed or absent")
    bound = record.get("approved_pulse_bounds_us")
    if (not isinstance(bound, list) or len(bound) != 2 or any(type(v) is not int for v in bound)
            or not 500 <= bound[0] < bound[1] <= 2500):
        raise ValueError("Explicit bounded pulse envelope required; not an authorization to execute")
    rows = record.get("observations")
    if not isinstance(rows, list):
        raise ValueError("Independent fit and held-out validation observations required")
    results, seen, seen_hashes = [], set(), set()
    for row in rows:
        image = row.get("image")
        if (not isinstance(image, str) or not image or str((ROOT/image).resolve()) in seen
                or row.get("role") not in ("fit", "validation")
                or row.get("reference_kind") != "independent_protractor_reading"
                or type(row.get("pulse_us")) is not int or not bound[0] <= row["pulse_us"] <= bound[1]
                or not finite(row.get("reference_angle_deg")) or not 0 <= row["reference_angle_deg"] <= 180
                or not row.get("image_sha256") or row["image_sha256"] in seen_hashes):
            raise ValueError("Unique image-bound independent angle/pulse observations required")
        seen.add(str((ROOT/image).resolve())); seen_hashes.add(row["image_sha256"])
        if digest(ROOT / image) != row["image_sha256"]:
            raise ValueError("Calibration observation image changed")
        if record["kind"] == "physical":
            evidence = row.get("tracking_evidence")
            if not isinstance(evidence, dict) or not evidence.get("trace") or not evidence.get("trace_sha256"):
                raise ValueError("Physical camera validation requires frozen automatic tracker evidence")
            trace_path = ROOT / evidence["trace"]
            if evidence:
                if digest(trace_path) != evidence["trace_sha256"]:
                    raise ValueError("Calibration tracking evidence changed")
                tracker = load(trace_path.parent/"tracker-config.snapshot.json")
                preview = load(trace_path.parent/"preview-config.snapshot.json")
                if (fingerprint(tracker["settings"]) != geometry["tracker_settings_sha256"]
                        or fingerprint(tracker["temporal_policy"]) != geometry["tracker_temporal_policy_sha256"]
                        or preview["camera_id"] != geometry["camera_id"]
                        or preview["reference_sha256"] != geometry["reference_sha256"]):
                    raise ValueError("Calibration observation uses a different tracker/view")
                matches = [r for r in map(json.loads, trace_path.read_text().splitlines())
                           if r.get("file") == evidence.get("file")]
                if len(matches) != 1:
                    raise ValueError("Unique automatic calibration frame required")
                tracked = matches[0]
                if (tracked.get("status") != "tracked_unverified" or tracked.get("reasons")
                        or tracked.get("source_image_sha256") != row["image_sha256"]
                        or tracked.get("localized_points") != {"pivot_px": row.get("pivot_px"), "tip_px": row.get("tip_px")}
                        or (tracked.get("quality") or {}).get("camera_image_transform") != row.get("camera_transform")
                        or row.get("camera_transform") is None):
                    raise ValueError("Physical calibration points must come from accepted automatic image localization")
        measured = angle_from_points(geometry, row.get("pivot_px"), row.get("tip_px"), row.get("camera_transform"))
        error = abs(measured-row["reference_angle_deg"])
        if error + uncertainty > MAX_ERROR_DEG:
            raise ValueError("Camera/reference error plus reading uncertainty exceeds 3 degrees")
        results.append({**row, "camera_angle_deg": measured, "error_deg": error})
    fit = sorted((r for r in results if r["role"] == "fit"), key=lambda r: r["reference_angle_deg"])
    validation = [r for r in results if r["role"] == "validation"]
    if len(fit) < 3 or len(validation) < 3:
        raise ValueError("At least three fit and three separate validation images required")
    angles, pulses = [r["reference_angle_deg"] for r in fit], [r["pulse_us"] for r in fit]
    differences = [b-a for a, b in zip(pulses, pulses[1:])]
    if (any(b-a < 10 for a, b in zip(angles, angles[1:]))
            or not (all(v > 0 for v in differences) or all(v < 0 for v in differences))):
        raise ValueError("Fit needs separated angles and a strictly monotonic pulse mapping")
    # Require held-out checks close to both endpoints and the middle, so a narrow
    # validation cluster cannot qualify an entire range.
    for target in (angles[0], (angles[0]+angles[-1])/2, angles[-1]):
        if not any(abs(r["reference_angle_deg"]-target) <= 5 for r in validation):
            raise ValueError("Held-out validation must cover both fit endpoints and midpoint")
    for row in validation:
        predicted = interpolate(row["reference_angle_deg"], fit)
        # Convert pulse discrepancy to local degrees using neighboring fit points.
        segment = next((a, b) for a, b in zip(fit, fit[1:])
                       if a["reference_angle_deg"] <= row["reference_angle_deg"] <= b["reference_angle_deg"])
        a, b = segment
        error = abs(row["pulse_us"]-predicted)*abs((b["reference_angle_deg"]-a["reference_angle_deg"])/(b["pulse_us"]-a["pulse_us"]))
        if error + uncertainty > MAX_ERROR_DEG:
            raise ValueError("Held-out pulse/angle repeatability exceeds error budget")
    return {"schema_version": 1, "status": "qualified_record" if record["kind"] == "physical" else "synthetic_software_only",
            "eligible_for_hardware": record["kind"] == "physical", "kind": record["kind"],
            "record_sha256": fingerprint(record), "angle_range_deg": [angles[0], angles[-1]],
            "fit": fit, "validation": validation, "geometry": geometry,
            "approved_pulse_bounds_us": bound, "maximum_error_budget_deg": MAX_ERROR_DEG,
            "scope": "Image-angle and pulse mapping for this frozen view/range only; supplied reference readings are not authenticated, no electrical waveform or continuous-motion qualification"}


def interpolate(angle, fit):
    if not finite(angle):
        raise ValueError("Finite target angle required")
    for a, b in zip(fit, fit[1:]):
        lo, hi = a["reference_angle_deg"], b["reference_angle_deg"]
        if lo <= angle <= hi:
            return a["pulse_us"]+(angle-lo)/(hi-lo)*(b["pulse_us"]-a["pulse_us"])
    raise ValueError("Target outside measured calibration range; extrapolation prohibited")


def pending_template(tracker_path):
    tracker = load(tracker_path)
    preview = load(ROOT / tracker["preview_config"])
    return {"schema_version": 1, "kind": "physical", "status": "pending_physical_measurements",
            "approved_pulse_bounds_us": [1300, 1700], "independent_reader_uncertainty_deg": None,
            "geometry": {"camera_id": preview["camera_id"], "reference_frame": preview["reference_frame"],
                         "reference_sha256": preview["reference_sha256"],
                         "tracker_settings_sha256": fingerprint(tracker["settings"]),
                         "tracker_temporal_policy_sha256": fingerprint(tracker["temporal_policy"]),
                         "measurement_sources_sha256": measurement_sources(),
                         "plane_reference": None, "zero_reference": None},
            "observations": [], "eligible_for_hardware": False,
            "note": "Fill from independent physical observations. Never derive reference angles from commands or expected behavior. Existing approved envelope is not new movement authorization."}


def add_observation(record, trace_path, file, role, pulse_us, reference_angle_deg):
    """Join a supplied independent scale reading to frozen automatic image points."""
    trace_path = Path(trace_path).resolve()
    tracker = load(trace_path.parent/"tracker-config.snapshot.json")
    preview = load(trace_path.parent/"preview-config.snapshot.json")
    if (fingerprint(tracker["settings"]) != record["geometry"]["tracker_settings_sha256"]
            or fingerprint(tracker["temporal_policy"]) != record["geometry"]["tracker_temporal_policy_sha256"]
            or preview["camera_id"] != record["geometry"]["camera_id"]
            or preview["reference_sha256"] != record["geometry"]["reference_sha256"]):
        raise ValueError("Observation uses a different frozen tracker/view")
    matches = [r for r in map(json.loads, trace_path.read_text().splitlines()) if r.get("file") == file]
    if len(matches) != 1 or matches[0].get("status") != "tracked_unverified" or matches[0].get("reasons"):
        raise ValueError("A uniquely accepted automatic tracked frame is required")
    row = matches[0]; image = (ROOT/tracker["source_capture"]/file).resolve()
    if image.name != file or digest(image) != row["source_image_sha256"]:
        raise ValueError("Unsafe or changed observation image")
    if (role not in ("fit", "validation") or type(pulse_us) is not int
            or not record["approved_pulse_bounds_us"][0] <= pulse_us <= record["approved_pulse_bounds_us"][1]
            or not finite(reference_angle_deg) or not 0 <= reference_angle_deg <= 180):
        raise ValueError("Explicit role, bounded pulse and independent scale reading required")
    observation = {"role": role, "image": str(image), "image_sha256": digest(image),
                   "reference_kind": "independent_protractor_reading", "reference_angle_deg": reference_angle_deg,
                   "pulse_us": pulse_us, **row["localized_points"],
                   "camera_transform": (row.get("quality") or {}).get("camera_image_transform"),
                   "tracking_evidence": {"trace": str(trace_path), "trace_sha256": digest(trace_path), "file": file}}
    if any(r["image"] == str(image) for r in record["observations"]): raise ValueError("Observation image already used")
    result = {**record, "observations": record["observations"]+[observation]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template")
    template.add_argument("--tracker", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--record", type=Path, required=True)
    add = commands.add_parser("add-observation", help="Attach an independently read angle to automatic image points")
    add.add_argument("--record", type=Path, required=True); add.add_argument("--trace", type=Path, required=True)
    add.add_argument("--file", required=True); add.add_argument("--role", choices=("fit", "validation"), required=True)
    add.add_argument("--pulse-us", type=int, required=True); add.add_argument("--reference-angle-deg", type=float, required=True)
    for command in (template, check, add):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "template": result = pending_template(args.tracker)
        elif args.command == "check": result = qualify(load(args.record))
        else: result = add_observation(load(args.record), args.trace, args.file, args.role, args.pulse_us, args.reference_angle_deg)
        with args.output.open("x") as stream:
            stream.write(json.dumps(result, indent=2)+"\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
