"""Explicit one-shot full-runtime acquisition. Importing performs no I/O.

No flash/model operation. Fresh acquisition is not a live visual/mount gate.
"""
import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .camera import ROOT, build_helper, list_cameras
from .fullrig import load_artifact
from .servo_calibration import fingerprint
from .servo_capture import GuardJournal, camera_fresh
from .vision import digest, load, save

STEP = re.compile(r"FULL_STEP:(\d+) PULSE_US:(\d+) UPTIME_MS:(\d+)")
STOP = re.compile(r"FULL_STOPPED REASON:(\w+) PWM:(\w+) UPTIME_MS:(\d+)")


def identity(plan):
    return ("SPARKBENCH FULL_RUNTIME V:1 PLAN:%s CAL:%s PROFILE:%s MODE:IDLE OLED:ACK PWM:OFF AVAILABLE:1"
            % (fingerprint(plan), plan["calibration_sha256"] or "NONE", plan["profile"].upper()))


def clean(lines):
    if any("ERROR" in line or "FAULT" in line or re.search(r"\bBOOT\b", line) for line in lines):
        raise ValueError("Full runtime error, reset or PWM fault")


class FullJournal(GuardJournal):
    def __init__(self, connection, stream, action, clock=time.monotonic):
        super().__init__(connection, stream, clock)
        if action not in ("CALIBRATE", "EXECUTE", "DISCOVER", "LEDS"):
            raise ValueError("Unsupported compiled runtime action")
        self.action = action

    def send(self, command):
        if command not in ("ID", "STOP", "PING", self.action):
            raise ValueError("Command outside full-runtime allowlist")
        if command == self.action:
            if not self.verified or not self.camera_ready or self.started:
                raise ValueError("Fresh exact identity and camera required, once only")
            self.started = True  # Latch before write, including partial/error writes.
        if command in ("STOP", "PING") and not self.verified:
            raise ValueError("Unverified runtime")
        if command == "PING" and not self.started:
            raise ValueError("Sequence not started")
        self.event("tx", command=command); self.commands.append(command)
        data = (command+"\n").encode("ascii")
        if self.connection.write(data) != len(data):
            raise ValueError("Incomplete serial write")


def verify_idle(journal, plan, clock=time.monotonic):
    journal.send("ID"); seen = False; ticks = []; deadline = clock()+8
    while clock() < deadline:
        lines = journal.read(); clean(lines)
        for line in lines:
            seen |= line == identity(plan)
            match = re.fullmatch(r"FULL_ALIVE UPTIME_MS:(\d+) MODE:IDLE PWM:OFF", line)
            if match: ticks.append(int(match[1]))
        if seen and len(ticks) >= 2 and ticks[-1] > ticks[-2]:
            journal.verified = True; journal.event("identity_verified", identity=identity(plan)); return
    raise ValueError("Exact available full-runtime identity and fresh heartbeats absent")


def drive(journal, pulses, healthy_camera, *, fault=None, clock=time.monotonic):
    if fault not in (None, "stop", "lease"):
        raise ValueError("Unsupported fault case")
    if not healthy_camera(): raise ValueError("Camera not fresh at start")
    journal.camera_ready = True; journal.send(journal.action)
    start = clock(); deadline = start+30; next_ping = start; rows = []; fault_at = None
    while clock() < deadline:
        if not healthy_camera(): raise ValueError("Camera stopped or frames stale")
        now = clock()
        if fault and fault_at is None and rows and now-start >= (1.9 if fault == "stop" else .8):
            fault_at = now; journal.event("fault_trigger", case=fault)
            if fault == "stop": journal.send("STOP")
        if now >= next_ping and not (fault_at is not None):
            journal.send("PING"); next_ping = clock()+.4
        lines = journal.read(); clean(lines)
        for line in lines:
            match = STEP.fullmatch(line)
            if match:
                index, pulse, uptime = map(int, match.groups())
                if index != len(rows)+1 or index > len(pulses) or pulse != pulses[index-1]:
                    raise ValueError("Unexpected UART step/pulse sequence")
                if rows and not 3000 <= (uptime-rows[-1]["uptime_ms"]) % 2**32 <= 4000:
                    raise ValueError("UART step timing outside bound")
                rows.append({"step": index, "pulse_us": pulse, "uptime_ms": uptime})
            match = STOP.fullmatch(line)
            if match:
                reason, pwm, uptime = match.groups()
                expected = {None: "COMPLETE", "stop": "STOP", "lease": "LEASE_EXPIRED"}[fault]
                if reason != expected or pwm != "OFF" or (fault and fault_at is None):
                    raise ValueError("Unexpected shutdown reason or PWM fault")
                if fault is None and (len(rows) != len(pulses)
                        or not 3000 <= (int(uptime)-rows[-1]["uptime_ms"]) % 2**32 <= 4000):
                    raise ValueError("Incomplete UART sequence or final dwell")
                if fault and len(rows) != 1:
                    raise ValueError("Fault did not stop within first dwell")
                return {"status": "complete_uart_only", "steps": rows, "stop_reason": reason,
                        "scope": "Command/timing telemetry only; not angle, LED, OLED or waveform evidence"}
    raise ValueError("Host motion deadline expired")


def stop_and_confirm(journal, clock=time.monotonic):
    journal.send("STOP"); deadline = clock()+1
    while clock() < deadline:
        lines = journal.read(); clean(lines)
        if any(re.fullmatch(r"FULL_STOPPED REASON:STOP PWM:OFF UPTIME_MS:\d+", line) for line in lines):
            return True
    return False


def acquire(port, device_id, artifact_path, output, *, execute_sequence=False, action=None, fault=None):
    if execute_sequence is not True:
        raise ValueError("Explicit execute_sequence opt-in required; no I/O performed")
    plan, artifact = load_artifact(artifact_path)
    action = action or ("CALIBRATE" if plan["profile"] == "calibration" else "EXECUTE")
    allowed = ("DISCOVER", "CALIBRATE") if plan["profile"] == "calibration" else ("DISCOVER", "EXECUTE", "LEDS")
    if action not in allowed:
        raise ValueError("Action does not match compiled profile")
    if fault not in (None, "stop", "lease") or not port or not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Explicit port/camera and supported fault case required")
    if plan["profile"] == "behavior":
        cal = load(Path(artifact_path)/"calibration.json")
        if cal["geometry"]["camera_id"] != device_id:
            raise ValueError("Camera differs from angle calibration")
    import serial
    from serial.tools import list_ports
    ports = [p for p in list_ports.comports() if p.device == port]
    if len(ports) != 1 or (ports[0].vid, ports[0].pid) != (0x10C4, 0xEA60):
        raise ValueError("Fresh CP2102 enumeration required")
    enumeration = list_cameras()
    if len([d for d in enumeration.get("devices", []) if d.get("id") == device_id and d.get("connected")]) != 1:
        raise ValueError("Explicit camera absent; no fallback")
    helper = build_helper(); output = Path(output); output.mkdir(parents=True, exist_ok=False)
    save(output/"camera-enumeration.json", enumeration); save(output/"plan.snapshot.json", plan)
    save(output/"artifact.snapshot.json", artifact)
    report = {"schema_version": 1, "status": "incomplete", "source": "live_hardware", "device_id": device_id,
              "port": port, "usb_hwid": ports[0].hwid, "identity": identity(plan), "action": action,
              "plan_sha256": fingerprint(plan), "firmware_sha256": artifact["firmware_sha256"],
              "firmware_hash_scope": "Expected local artifact only, not installed flash readback",
              "calibration_sha256": plan["calibration_sha256"], "servo_actuation_requested": False,
              "firmware_uploaded": False, "model_api_requests": 0, "angle_deg": None,
              "automatic_physical_verification": "not performed", "qualification_fault": fault,
              "camera_gate_scope": "Fresh acquisition only; not live pixel quality/mount verification",
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    save(output/"run.json", report)
    connection = serial.Serial(port=None, baudrate=115200, timeout=.05, write_timeout=.25)
    connection.port, connection.dtr, connection.rts = port, False, False
    camera = journal = None
    with (output/"uart.jsonl").open("x") as stream, (output/"camera.stdout.json").open("x") as stdout, (output/"camera.stderr.log").open("x") as stderr:
        try:
            connection.open(); journal = FullJournal(connection, stream, action, clock=time.monotonic)
            deadline = time.monotonic()+2
            while time.monotonic() < deadline: journal.read()
            verify_idle(journal, plan, clock=time.monotonic)
            seconds = 10 if fault else min(40, len(plan["steps"])*3.4+10) if action != "DISCOVER" else 28
            camera = subprocess.Popen([str(helper), "capture", device_id, str(output/"camera"), str(seconds), "5"], stdout=stdout, stderr=stderr)
            healthy = lambda: camera_fresh(camera, output/"camera", device_id, time.monotonic())
            deadline = time.monotonic()+12
            while time.monotonic() < deadline:
                clean(journal.read())
                if healthy(): break
                if camera.poll() is not None: raise ValueError("Camera ended before start")
            else: raise ValueError("Fresh camera gate timed out")
            pulses = [0]*5 if action == "DISCOVER" else [0]*len(plan["steps"]) if action == "LEDS" else [s["pulse_us"] for s in plan["steps"]]
            report["uart_sequence"] = drive(journal, pulses, healthy, fault=fault, clock=time.monotonic)
            report["status"] = "sequence_complete_capture_pending"
        except (Exception, KeyboardInterrupt) as exc:
            report["error"] = str(exc)
        finally:
            if journal:
                report["servo_actuation_requested"] = journal.started and action not in ("DISCOVER", "LEDS")
                if journal.verified:
                    try: report["stop_acknowledged_uart_only"] = stop_and_confirm(journal, clock=time.monotonic)
                    except (Exception, KeyboardInterrupt) as exc: report["stop_error"] = str(exc)
                report["serial_commands_sent"] = journal.commands
            try:
                if report["status"] == "sequence_complete_capture_pending":
                    if not report.get("stop_acknowledged_uart_only"): raise ValueError("Cleanup STOP not acknowledged")
                    deadline = time.monotonic()+45
                    while camera.poll() is None and time.monotonic() < deadline: clean(journal.read())
                    if camera.poll() is None: raise ValueError("Camera drain deadline expired")
                    clean(journal.read()); captured = load(output/"camera/capture.json")
                    report["status"] = "completed" if camera.returncode == 0 and captured.get("status") == "captured" else "incomplete"
                    report["frame_count"] = captured.get("frame_count", 0)
            except (Exception, KeyboardInterrupt) as exc:
                report.update(status="incomplete", cleanup_error=str(exc))
            finally:
                try:
                    if camera and camera.poll() is None:
                        camera.terminate()
                        try: camera.wait(timeout=3)
                        except subprocess.TimeoutExpired: camera.kill(); camera.wait(timeout=3)
                finally:
                    try: connection.close()
                    except Exception as exc: report.update(status="incomplete", serial_close_error=str(exc))
                    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
                    save(output/"run.json", report)
                    save(output/"integrity.json", {"sha256": {str(p.relative_to(output)): digest(p)
                        for p in sorted(output.rglob('*')) if p.is_file() and p.name != "integrity.json"}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True); parser.add_argument("--device-id", required=True)
    parser.add_argument("--artifact", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-sequence", action="store_true")
    parser.add_argument("--action", choices=("CALIBRATE", "EXECUTE", "DISCOVER", "LEDS"))
    parser.add_argument("--fault", choices=("stop", "lease"))
    args = parser.parse_args()
    try:
        report = acquire(args.port, args.device_id, args.artifact, args.output,
                         execute_sequence=args.execute_sequence, action=args.action, fault=args.fault)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc)+"\n")
    print(json.dumps(report, indent=2)); return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
