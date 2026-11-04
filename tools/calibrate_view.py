"""Calibrate the camera for a new phone position from one saved test capture, with the LEDs lit.

Use this after the phone moved and a test ran in the new position. It copies the capture so the original
evidence stays untouched, sets the view from markers a person checked, and fits LED thresholds from frames
labelled by inspecting the frames, not from the plan. Without `--labels` it only prints scores, so the
markers and labels can be checked first. `--promote` installs the result. The next capture is the held-out test.

  tools/calibrate_view.py --capture runs/dashboard-execution/<job>/workflow/capture --output runs/live/<name> \\
    --reference frame-000140.jpg --red 1660 651 --green 1744 574 --oled 1039 831 1252 927 1209 1037 991 935 \\
    --probe 95 100 112 116 124 140 --labels 95:on:off 100:on:off 112:off:on 116:off:on 124:off:off 140:off:off --promote

Labels are frame:red:green. It makes no Meta request and touches no hardware.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sparkbench.policy import check_policy  # noqa: E402
from sparkbench.vision import ROOT, calibrate, digest, geometry_valid, load, read_images, save, validate_capture  # noqa: E402


def frame_name(number):
    return "frame-%06d.jpg" % number


def parse_label(text):
    number, red, green = text.split(":")
    if red not in ("on", "off") or green not in ("on", "off"):
        raise argparse.ArgumentTypeError("Labels are frame:on|off:on|off")
    return {"frame": frame_name(int(number)), "red": red == "on", "green": green == "on"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", required=True, help="Frame name in the capture, in the final phone position")
    parser.add_argument("--red", type=int, nargs=2, required=True, metavar=("X", "Y"))
    parser.add_argument("--green", type=int, nargs=2, required=True, metavar=("X", "Y"))
    parser.add_argument("--oled", type=int, nargs=8, required=True, help="Drawn OLED border: top-left, top-right, bottom-right, bottom-left")
    parser.add_argument("--label-crop", type=int, nargs=4, metavar=("X", "Y", "W", "H"), help="OLED text area in the rectified image, when the firmware layout changed")
    parser.add_argument("--probe", type=int, nargs="+", required=True, help="Frame numbers to score")
    parser.add_argument("--labels", type=parse_label, nargs="*", default=[])
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()

    output = args.output.resolve()
    capture = output / "capture"
    geometry_path = ROOT / "hardware/vision.geometry.json"
    policy_path = ROOT / "hardware/oled-reader.policy.json"
    if not capture.exists():
        capture.mkdir(parents=True)
        shutil.copy2(args.capture / "run.json", capture / "run.json")
        shutil.copytree(args.capture / "camera", capture / "camera")
    if not (output / "geometry.previous.json").exists():
        shutil.copy2(geometry_path, output / "geometry.previous.json")
        shutil.copy2(policy_path, output / "policy.previous.json")
    geometry = load(geometry_path)
    geometry["reference_frame"] = str((capture / "camera" / args.reference).relative_to(ROOT))
    geometry["leds"]["red"].update(center_x=args.red[0], center_y=args.red[1])
    geometry["leds"]["green"].update(center_x=args.green[0], center_y=args.green[1])
    geometry["oled_corners"] = [args.oled[i:i+2] for i in range(0, 8, 2)]
    if args.label_crop:
        geometry["label_crop"] = args.label_crop
    candidate_geometry = output / "geometry.candidate.json"
    save(candidate_geometry, geometry)

    wanted = {frame_name(n) for n in args.probe}
    chosen = [row for row in validate_capture(capture) if row["file"] in wanted]
    probe = output / "probe"
    shutil.rmtree(probe, ignore_errors=True)
    probe.mkdir()
    native = read_images(capture, geometry, chosen, probe, read_labels=False)
    for row in chosen:
        item = native[row["file"]]
        leds = item.get("leds", {})
        print(row["file"], "geometry", "ok" if geometry_valid(item, geometry) else "NO", item.get("error") or "",
              "red", leds.get("red", {}).get("mean_luma_srgb"), "green", leds.get("green", {}).get("mean_luma_srgb"))
    if not args.labels:
        print("Scores only. Check %s/crops, then rerun with --labels." % probe)
        return 0

    save(capture / "visual_review.json", {"source": "agent_visual_inspection_of_saved_live_camera_frames",
                                          "scope": "Labels come from inspecting the LED area of each frame, not from the plan.",
                                          "observations": args.labels})
    calibration_dir = output / "calibration"
    if calibration_dir.exists():
        raise SystemExit("Calibration already exists: " + str(calibration_dir))
    calibrate(capture, candidate_geometry, calibration_dir)
    calibration_path = calibration_dir / "calibration.json"
    policy = load(policy_path)
    candidate = {**policy, "calibration": str(calibration_path.relative_to(ROOT)), "calibration_sha256": digest(calibration_path),
                 "scope": "Frozen after a supervised view and LED calibration from labelled frames of one capture; reader, prompt and limits unchanged; the next capture is held out"}
    save(output / "policy.candidate.json", candidate)
    check_policy(output / "policy.candidate.json")
    if args.promote:
        shutil.copy2(candidate_geometry, geometry_path)
        shutil.copy2(output / "policy.candidate.json", policy_path)
        check_policy(policy_path)
        print("Installed:", policy_path, "now points at", candidate["calibration"])
    else:
        print("Candidate written; rerun with --promote in a new output directory to install it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
