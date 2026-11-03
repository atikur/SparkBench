import argparse
import json
import sys
from pathlib import Path

from .doctor import readiness
from .verify import verify_trace


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "dashboard":
        from .dashboard.server import main as dashboard_main
        return dashboard_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "passive":
        from .passive import main as passive_main
        return passive_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in ("build", "generate", "workflow", "discover", "replay"):
        from .control import main as control_main
        return control_main(sys.argv[1:])
    parser = argparse.ArgumentParser(description="SparkBench bring-up tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report local readiness without touching hardware")
    commands.add_parser("dashboard", help="Open the local read-only recorded evidence dashboard")
    commands.add_parser("passive", help="Camera-only capture, tracking and session quality report")
    for name, help_text in (("build", "Compile a restricted plan; no upload"),
                            ("generate", "Generate/repair a plan through Meta; no hardware"),
                            ("workflow", "Capture, measure and compare LED/OLED"),
                            ("discover", "Bounded GPIO25/26 camera probes"),
                            ("replay", "Offline evidence regression; no API")):
        commands.add_parser(name, help=help_text)
    camera = commands.add_parser("camera", help="List cameras or capture local evidence on macOS")
    camera_commands = camera.add_subparsers(dest="camera_command", required=True)
    camera_commands.add_parser("list", help="List devices without recording or opening a camera")
    camera_commands.add_parser("authorize", help="Request macOS camera permission without recording")
    capture = camera_commands.add_parser("capture", help="Save a bounded set of timestamped frames")
    capture.add_argument("--device-id", required=True, help="Exact ID from camera list; no automatic fallback")
    capture.add_argument("--seconds", type=float, default=10)
    capture.add_argument("--fps", type=float, default=5, help="Saved frame sampling rate, 1–10")
    capture.add_argument("--output", type=Path, help="New directory; existing evidence is never overwritten")
    verify = commands.add_parser("verify", help="Check a recorded measurement trace")
    verify.add_argument("--spec", type=Path, required=True)
    verify.add_argument("--trace", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps(readiness(), indent=2))
        return 0
    if args.command == "camera":
        from .camera import authorize_camera, capture_frames, list_cameras
        import subprocess
        try:
            if args.camera_command == "list":
                report = list_cameras()
            elif args.camera_command == "authorize":
                report = authorize_camera()
            else:
                report = capture_frames(args.device_id, args.seconds, args.fps, args.output)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            print("Camera error: %s" % exc, file=sys.stderr)
            return 2
        print(json.dumps(report, indent=2))
        return 0
    try:
        with args.spec.open() as stream:
            spec = json.load(stream)
        with args.trace.open() as stream:
            trace = json.load(stream)
        if not isinstance(spec, dict) or not isinstance(trace, dict):
            raise ValueError("Spec and trace must be JSON objects")
        report = verify_trace(spec, trace)
    except (OSError, ValueError) as exc:
        print("Invalid input: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return {"pass": 0, "fail": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
