"""CLI for bounded software stages. No command flashes firmware."""
import argparse
import json
from pathlib import Path

from .camera import ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Validate a JSON plan and compile trusted runtime; no upload")
    build.add_argument("--plan", type=Path, required=True)
    build.add_argument("--render-only", action="store_true")
    generate = commands.add_parser("generate", help="Meta-only bounded plan generation and compile; no hardware")
    generate.add_argument("--spec", type=Path, default=ROOT / "specs/led_oled_only.json")
    generate.add_argument("--mapping", type=Path, required=True)
    generate.add_argument("--max-repairs", type=int, default=1)
    workflow = commands.add_parser("workflow", help="Capture, measure with Meta, compare and report; no upload")
    workflow.add_argument("--port")
    workflow.add_argument("--device-id")
    workflow.add_argument("--run", type=Path, help="Analyze an existing run instead of new acquisition; calls Meta")
    workflow.add_argument("--artifact", type=Path, help="Require installed protected-runtime identity/plan hash")
    workflow.add_argument("--spec", type=Path, default=ROOT / "specs/led_oled_only.json")
    discover = commands.add_parser("discover", help="Bounded runtime probes and camera-only LED mapping; no Meta requests")
    discover.add_argument("--port")
    discover.add_argument("--device-id")
    discover.add_argument("--artifact", type=Path)
    discover.add_argument("--run", type=Path, help="Analyze a saved DISCOVER run without hardware access")
    replay = commands.add_parser("replay", help="Offline regression using saved real measurements; no API or hardware")
    replay.add_argument("--analysis", type=Path, required=True)
    for command in (workflow, discover):
        command.add_argument("--policy", type=Path, default=ROOT / "hardware/oled-reader.policy.json")
    for command in (build, generate, workflow, discover, replay):
        command.add_argument("--output", type=Path, required=True, help="New directory; existing evidence rejected")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            from .artifacts import build_artifact
            report = build_artifact(json.loads(args.plan.read_text()), args.output, not args.render_only)
        elif args.command == "generate":
            from .generation import generate
            record = json.loads(args.mapping.read_text())
            if "mapping" in record:
                if record.get("status") != "mapped":
                    raise ValueError("Discovery record is incomplete; no guessed mapping permitted")
                record = record["mapping"]
            report = generate(args.spec, record, args.output, args.max_repairs)
        elif args.command == "workflow":
            from .workflow import execute
            report = execute(args.port, args.device_id, args.output, args.policy, args.spec, args.artifact, args.run)
        elif args.command == "replay":
            from .workflow import replay
            report = replay(args.analysis, args.output)
        else:
            from .discovery import analyze_probes
            from .policy import check_policy
            from .vision import digest, load, save
            policy = load(args.policy)
            check_policy(args.policy, model=policy["model"])
            if not args.run and not (args.port and args.device_id and args.artifact):
                raise ValueError("Live discovery requires explicit port, camera ID and compiled runtime artifact")
            args.output.mkdir(parents=True, exist_ok=False)
            save(args.output / "policy.snapshot.json", policy)
            initial_hash = digest(args.policy)
            report = {"status": "incomplete", "mapping": None, "servo_actuation": False,
                      "firmware_uploaded": False, "meta_requests": 0}
            try:
                run = args.run
                if run is None:
                    from .runtime_io import acquire
                    run = args.output / "capture"
                    capture = acquire(args.port, args.device_id, args.artifact, run, "DISCOVER")
                    if capture["status"] != "completed":
                        raise ValueError("Probe acquisition incomplete")
                if digest(args.policy) != initial_hash:
                    raise ValueError("Policy changed during probe acquisition")
                report.update(analyze_probes(run, args.policy, args.output / "analysis"))
                if digest(args.policy) != initial_hash:
                    raise ValueError("Policy changed during probe analysis")
            except (Exception, KeyboardInterrupt) as exc:
                report.update(status="incomplete", mapping=None, error=str(exc), automatic_camera_mapping=False)
            finally:
                save(args.output / "discovery.json", report)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "incomplete", "error": str(exc)}))
        return 2
    print(json.dumps({**report, "output_directory": str(args.output.resolve())}, indent=2))
    return 0 if report["status"] in ("pass", "mapped", "compiled", "rendered") else 1 if report["status"] == "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
