"""Explicit fixed guarded-servo capture. No firmware upload or model API.

Preparing/importing this module performs no I/O. Live execution requires its
explicit CLI flag, fresh CP2102/camera selection and exact idle firmware identity.
Camera freshness is an acquisition gate, not live visual tracking verification.
"""
import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .camera import build_helper, list_cameras
from .led_oled import frame_rows
from .vision import digest, load, save


IDENTITY = "SPARKBENCH SERVO_GUARDED V:1 MODE:IDLE PWM:OFF AVAILABLE:1 GPIO:27 RANGE_US:1300-1700"
HEARTBEAT = re.compile(r"SERVO_GUARD_ALIVE UPTIME_MS:(\d+) MODE:IDLE PWM:OFF")
STEP = re.compile(r"SERVO_GUARD_STEP:(\d+) PULSE_US:(\d+) UPTIME_MS:(\d+)")
STOP = re.compile(r"SERVO_GUARD_STOPPED REASON:(\w+) PWM:(\w+) UPTIME_MS:(\d+)")
PULSES = [1500, 1300, 1700, 1500]


class GuardJournal:
    def __init__(self, connection, stream, clock=time.monotonic):
        self.connection, self.stream, self.clock = connection, stream, clock
        self.pending = b""
        self.lines, self.commands = [], []
        self.verified = self.camera_ready = self.started = False

    def event(self, kind, **fields):
        self.stream.write(json.dumps({"kind": kind, "host_uptime_seconds": self.clock(),
                                     "host_unix_seconds": time.time(), **fields}) + "\n")
        self.stream.flush()

    def read(self):
        raw = self.connection.read(min(self.connection.in_waiting or 1, 4096))
        if not raw:
            return []
        self.event("rx_bytes", hex=raw.hex())
        self.pending += raw
        if len(self.pending) > 8192:
            raise ValueError("UART buffer exceeds bound")
        fresh = []
        while b"\n" in self.pending:
            line, self.pending = self.pending.split(b"\n", 1)
            text = line.decode("ascii", errors="replace").rstrip("\r")
            self.lines.append(text); fresh.append(text)
            self.event("rx_line", line=text)
        return fresh

    def send(self, command):
        if command not in ("ID", "STOP", "PING", "SERVO_TEST"):
            raise ValueError("Command outside fixed servo allowlist")
        if command == "SERVO_TEST":
            if not self.verified or not self.camera_ready or self.started:
                raise ValueError("Start requires fresh idle identity/camera, once only")
            # Latch before the write: a failed/partial write may have reached hardware.
            self.started = True
        if command in ("STOP", "PING") and not self.verified:
            raise ValueError("Unknown firmware; no control command sent")
        if command == "PING" and not self.started:
            raise ValueError("PING requires a started sequence")
        self.event("tx_attempt", command=command)
        self.commands.append(command)
        data = (command + "\n").encode("ascii")
        if self.connection.write(data) != len(data):
            raise ValueError("Incomplete serial write")
        # No unbounded flush: pyserial write_timeout bounds write itself.


def camera_fresh(camera, directory, device_id, now):
    if camera.poll() is not None:
        return False
    try:
        meta = load(directory / "capture.json")
        rows = frame_rows(directory / "frames.jsonl")[-3:]
        if (meta.get("source") != "live_camera" or meta.get("status") != "recording"
                or meta.get("camera", {}).get("id") != device_id or len(rows) != 3):
            return False
        pts = [r["sample_pts_seconds"] for r in rows]
        host = [r["host_uptime_seconds"] for r in rows]
        return (all(type(v) in (int, float) for v in pts + host)
                and all(b > a for a, b in zip(pts, pts[1:]))
                and all(b > a for a, b in zip(host, host[1:]))
                and all(0 <= h - t <= 1 for h, t in zip(host, pts))
                and 0 <= now - host[-1] <= 1
                and all(r["file"] == "frame-%06d.jpg" % r["frame"]
                        and (directory / r["file"]).is_file() for r in rows))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def clean_lines(lines):
    if any("ERROR" in line or "FAULT" in line or re.search(r"\bBOOT\b", line) for line in lines):
        raise ValueError("Firmware error, reset or driver fault")


def verify_idle(journal, clock=time.monotonic):
    journal.send("ID")
    seen, ticks = False, []
    deadline = clock() + 8
    while clock() < deadline:
        lines = journal.read()
        clean_lines(lines)
        for line in lines:
            seen = seen or line == IDENTITY
            tick = HEARTBEAT.fullmatch(line)
            if tick:
                ticks.append(int(tick[1]))
        if seen and len(ticks) >= 2 and ticks[-1] > ticks[-2]:
            journal.verified = True
            journal.event("identity_verified", identity=IDENTITY)
            return
    raise ValueError("Exact available idle identity and fresh heartbeats absent")


def drive_fixed_sequence(journal, healthy_camera, clock=time.monotonic):
    if not healthy_camera():
        raise ValueError("Camera not fresh at start")
    journal.camera_ready = True
    journal.send("SERVO_TEST")
    deadline, next_ping = clock() + 10, clock()
    steps = []
    while clock() < deadline:
        if not healthy_camera():
            raise ValueError("Camera ended or frames became stale")
        if clock() >= next_ping:
            journal.send("PING")
            next_ping = clock() + .4
        lines = journal.read()
        clean_lines(lines)
        for line in lines:
            step = STEP.fullmatch(line)
            if step:
                index, pulse, uptime = map(int, step.groups())
                if index != len(steps) + 1 or index > 4 or pulse != PULSES[index - 1]:
                    raise ValueError("Unexpected or repeated fixed sequence step")
                if steps and not 1900 <= (uptime - steps[-1]["uptime_ms"]) % (2**32) <= 2500:
                    raise ValueError("Step timing outside diagnostic bound")
                steps.append({"step": index, "pulse_us": pulse, "uptime_ms": uptime})
            stopped = STOP.fullmatch(line)
            if stopped:
                reason, pwm, uptime = stopped.groups()
                if (reason != "COMPLETE" or pwm != "OFF" or len(steps) != 4
                        or not 1900 <= (int(uptime) - steps[-1]["uptime_ms"]) % (2**32) <= 2500):
                    raise ValueError("Sequence stopped early or without complete PWM-off telemetry")
                return {"status": "complete_uart_only", "steps": steps,
                        "scope": "UART-reported commands/timing, not waveform, motion or measured angle"}
    raise ValueError("Host sequence deadline expired")


def stop_and_confirm(journal, clock=time.monotonic):
    journal.send("STOP")
    deadline = clock() + 1
    while clock() < deadline:
        lines = journal.read()
        clean_lines(lines)
        if any(re.fullmatch(r"SERVO_GUARD_STOPPED REASON:STOP PWM:OFF UPTIME_MS:\d+", line) for line in lines):
            return True
    return False


def acquire(port, device_id, config_path, output, *, execute_fixed_sequence=False):
    if execute_fixed_sequence is not True:
        raise ValueError("Explicit execute_fixed_sequence opt-in required; no I/O performed")
    if not port or not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Explicit port and camera ID required")
    import serial
    from serial.tools import list_ports
    config = load(config_path)
    from .camera import ROOT
    preview_path = ROOT / config["preview_config"]
    preview = load(preview_path)
    reference = ROOT / preview["reference_frame"]
    if (config.get("mode") != "unverified_passive_tracking" or preview.get("camera_id") != device_id
            or digest(preview_path) != config["preview_config_sha256"]
            or digest(reference) != preview["reference_sha256"]):
        raise ValueError("Camera/reference mismatch")
    ports = [p for p in list_ports.comports() if p.device == port]
    if len(ports) != 1 or (ports[0].vid, ports[0].pid) != (0x10C4, 0xEA60):
        raise ValueError("Fresh CP2102 enumeration required")
    enumeration = list_cameras()
    if len([d for d in enumeration.get("devices", []) if d.get("id") == device_id and d.get("connected")]) != 1:
        raise ValueError("Exact selected camera absent; no fallback")
    helper = build_helper()
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    save(output / "camera-enumeration.json", enumeration)
    save(output / "tracker-config.snapshot.json", config)
    save(output / "preview-config.snapshot.json", preview)
    save(output / "preflight.json", {"source_sha256": digest(Path(__file__)),
         "camera_helper_sha256": digest(helper), "config_sha256": digest(config_path),
         "reference_sha256": digest(reference), "usb_hwid": ports[0].hwid,
         "scope": "Local files and fresh enumeration; UART identity is not installed flash hash proof"})
    report = {"status": "incomplete", "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "camera_id": device_id, "port": port, "servo_actuation_requested": False,
        "actual_servo_motion_verified": False, "angle_deg": None, "eligible_for_verifier": False,
        "firmware_uploaded": False, "model_api_requests": 0, "serial_commands_sent": [],
        "camera_gate_scope": "Fresh image acquisition only, not live pixel tracking or mount verification"}
    save(output / "run.json", report)
    connection = serial.Serial(port=None, baudrate=115200, timeout=.05, write_timeout=.25)
    connection.port, connection.dtr, connection.rts = port, False, False
    camera = journal = None
    with (output / "uart.jsonl").open("x") as stream, (output / "camera.stdout.json").open("x") as stdout, (output / "camera.stderr.log").open("x") as stderr:
        try:
            connection.open()
            journal = GuardJournal(connection, stream, clock=time.monotonic)
            settle = time.monotonic() + 2
            while time.monotonic() < settle:
                journal.read()  # Retain reset/startup separately before fresh identity.
            verify_idle(journal, clock=time.monotonic)
            camera = subprocess.Popen([str(helper), "capture", device_id, str(output / "camera"), "30", "5"], stdout=stdout, stderr=stderr)
            healthy = lambda: camera_fresh(camera, output / "camera", device_id, time.monotonic())
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                clean_lines(journal.read())
                if healthy():
                    break
                if camera.poll() is not None:
                    raise ValueError("Camera exited before start")
            else:
                raise ValueError("Fresh camera gate timed out; no start")
            report["uart_sequence"] = drive_fixed_sequence(journal, healthy, clock=time.monotonic)
            report["status"] = "sequence_complete_capture_pending"
        except (Exception, KeyboardInterrupt) as exc:
            report["error"] = str(exc)
        finally:
            if journal:
                report["servo_actuation_requested"] = journal.started
                if journal.verified:
                    try:
                        report["stop_acknowledged_uart_only"] = stop_and_confirm(journal, clock=time.monotonic)
                    except (Exception, KeyboardInterrupt) as exc:
                        report["stop_error"] = str(exc)
                report["serial_commands_sent"] = journal.commands
            if report["status"] == "sequence_complete_capture_pending" and not report.get("stop_acknowledged_uart_only"):
                report.update(status="incomplete", error="STOP confirmation absent")
            try:
                if camera:
                    if report["status"] == "sequence_complete_capture_pending":
                        post_deadline = time.monotonic() + 35
                        while camera.poll() is None and time.monotonic() < post_deadline:
                            clean_lines(journal.read())
                        if camera.poll() is None:
                            raise ValueError("Camera post-capture deadline expired")
                        clean_lines(journal.read())
                        captured = load(output / "camera/capture.json")
                        report["status"] = "captured_uart_sequence_complete_unverified" if camera.returncode == 0 and captured.get("status") == "captured" else "incomplete"
                    if camera.poll() is None:
                        camera.terminate()
                        try:
                            camera.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            camera.kill(); camera.wait(timeout=3)
            except (Exception, KeyboardInterrupt) as exc:
                report.update(status="incomplete", camera_cleanup_error=str(exc))
                if camera and camera.poll() is None:
                    camera.kill(); camera.wait(timeout=3)
            finally:
                try:
                    connection.close()
                except Exception as exc:
                    report.update(status="incomplete", serial_close_error=str(exc))
                report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
                report["full_behavior_verification"] = "incomplete_required_servo_measurements_missing"
                save(output / "run.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-fixed-sequence", action="store_true")
    args = parser.parse_args()
    try:
        result = acquire(args.port, args.device_id, args.config, args.output,
                         execute_fixed_sequence=args.execute_fixed_sequence)
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "captured_uart_sequence_complete_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
