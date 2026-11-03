"""Refresh the frozen camera reference after the rig or the phone moved, keeping validated LED thresholds.

First supervise `hardware/vision.geometry.json` on a saved frame of the new view: set `reference_frame`,
the two LED circle centres and the four OLED border corners. Then run this tool. It checks the new
geometry on real frames with the native reader (border support and LED scores against the previous
thresholds), writes a calibration that carries those thresholds, and writes a policy candidate.
`--promote` installs the candidate as `hardware/oled-reader.policy.json` once `check_policy` passes.
It makes no Meta request and touches no hardware. The new geometry is a registration refresh, not a
new LED threshold fit: every checked frame must read as LEDs off, or the refresh is refused.
"""
import argparse
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sparkbench.vision import ROOT, digest, geometry_valid, load, read_images, save, validate_capture  # noqa: E402
from sparkbench.policy import check_policy  # noqa: E402


def classify(score, thresholds):
    if score <= thresholds["off_threshold"]:
        return "off"
    if score >= thresholds["on_threshold"]:
        return "on"
    return "uncertain"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", type=Path, required=True, help="Run directory holding run.json and camera/ for the new view")
    parser.add_argument("--previous-calibration", type=Path, required=True, help="Calibration whose LED thresholds are carried over")
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    parser.add_argument("--every", type=int, default=12, help="Check every Nth frame in addition to the reference frame")
    parser.add_argument("--supervision", type=Path, nargs="*", default=[], help="Overlay images that show the supervised geometry; copied as evidence")
    parser.add_argument("--promote", action="store_true", help="Install the policy candidate as hardware/oled-reader.policy.json")
    args = parser.parse_args()

    capture = args.capture.resolve()
    output = args.output.resolve()
    policy_path = ROOT / "hardware/oled-reader.policy.json"
    if args.promote and (output / "policy.candidate.json").is_file():
        shutil.copy2(policy_path, output / "policy.previous.json")
        shutil.copy2(output / "policy.candidate.json", policy_path)
        check_policy(policy_path)
        print("promoted existing candidate:", load(policy_path)["calibration"])
        return 0
    geometry_path = ROOT / "hardware/vision.geometry.json"
    geometry = load(geometry_path)
    previous = load(args.previous_calibration.resolve())
    frames = validate_capture(capture)
    reference = (ROOT / geometry["reference_frame"]).resolve()
    if reference.parent != capture / "camera" or not reference.is_file():
        raise SystemExit("hardware/vision.geometry.json must reference a frame inside the given capture")
    reference_name = reference.name
    # The first frame of a capture is camera startup and is treated as unknown elsewhere; skip it here too.
    chosen = [row for i, row in enumerate(frames) if row["file"] == reference_name or (i > 0 and i % args.every == 0)]
    output.mkdir(parents=True, exist_ok=False)

    (output / "reader").mkdir()
    native = read_images(capture, geometry, chosen, output / "reader", read_labels=False)
    rows = []
    for row in chosen:
        native_row = native[row["file"]]
        leds = native_row.get("leds", {}) if native_row.get("status") == "measured" else {}
        scores = {c: leds.get(c, {}).get("mean_luma_srgb") for c in ("red", "green")}
        rows.append({"frame": row["file"], "geometry_supported": geometry_valid(native_row, geometry),
                     "border_support": native_row.get("oled_border_support"),
                     "led_scores": scores,
                     "led_reading": {c: (classify(s, previous["thresholds"][c]) if s is not None else None) for c, s in scores.items()}})
    unsupported = [r["frame"] for r in rows if not r["geometry_supported"]]
    not_off = [(r["frame"], c, r["led_reading"][c]) for r in rows for c in ("red", "green") if r["led_reading"][c] != "off"]
    check = {"frames_checked": len(rows), "first_frame_skipped_as_startup": True, "geometry_unsupported": unsupported, "led_not_off": not_off, "rows": rows}
    save(output / "geometry-check.json", check)
    for r in rows:
        print("%-18s geometry %-5s border %s red %6.1f %-9s green %6.1f %s" % (
            r["frame"], "ok" if r["geometry_supported"] else "NO", [round(v, 3) for v in (r["border_support"] or [])],
            r["led_scores"]["red"] or -1, r["led_reading"]["red"], r["led_scores"]["green"] or -1, r["led_reading"]["green"]))
    if unsupported or not_off:
        raise SystemExit("Refresh refused: geometry unsupported on %s; LED not off on %s" % (unsupported, not_off))

    camera = load(capture / "camera/capture.json")["camera"]
    calibration = {**previous,
                   "source_kind": "prior_validated_thresholds_with_new_supervised_reference",
                   "source_run": str(capture), "source_review_sha256": None,
                   "source_frames_sha256": {r["frame"]: digest(capture / "camera" / r["frame"]) for r in rows},
                   "geometry": geometry, "geometry_sha256": digest(geometry_path),
                   "reference_image_sha256": digest(reference),
                   "camera_id": camera["id"], "camera_name": camera.get("name"),
                   "native_reader_source_sha256": digest(ROOT / "tools/macos_vision/main.swift"),
                   "thresholds": previous["thresholds"],
                   "threshold_source_calibration": str(args.previous_calibration), "threshold_source_calibration_sha256": digest(args.previous_calibration.resolve()),
                   "macos": platform.mac_ver()[0],
                   "geometry_refresh_scope": "New reference frame, LED circles and OLED border corners supervised on a saved frame of the new view; thresholds, radius, rejection and temporal limits unchanged; checked frames all read LEDs off; a fresh independent camera test is still required",
                   "refreshed_at_utc": datetime.now(timezone.utc).isoformat()}
    save(output / "calibration.json", calibration)
    supervision = output / "supervision"
    for image in args.supervision:
        supervision.mkdir(exist_ok=True)
        shutil.copy2(image, supervision / Path(image).name)
    policy = load(policy_path)
    relative = (output / "calibration.json").relative_to(ROOT)
    candidate = {**policy, "calibration": str(relative), "calibration_sha256": digest(output / "calibration.json"),
                 "scope": "Frozen after supervised geometry refresh of the new view; no limits or reader changes; thresholds carried from the previous validated calibration"}
    save(output / "policy.candidate.json", candidate)
    check_policy(output / "policy.candidate.json")
    freeze = {"status": "candidate_frozen_before_new_capture", "policy_sha256": digest(output / "policy.candidate.json"),
              "previous_policy_sha256": digest(policy_path), "previous_calibration": policy["calibration"],
              "new_capture_required": True, "not_independent_acceptance": True, "meta_requests": 0, "hardware_actions": []}
    save(output / "freeze.json", freeze)
    print("calibration:", relative)
    if args.promote:
        shutil.copy2(policy_path, output / "policy.previous.json")
        shutil.copy2(output / "policy.candidate.json", policy_path)
        check_policy(policy_path)
        print("promoted: hardware/oled-reader.policy.json now points at", relative)
    else:
        print("candidate written; rerun with --promote to install it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
