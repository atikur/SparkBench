"""Explicit runtime capture, with plan-hash identity and a bounded host lease.

No upload path. The installed diagnostic cannot satisfy this identity gate.
"""
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import load_artifact
from .camera import build_helper
from .led_oled import Journal, check_sequence, frame_rows
from .vision import save


class RuntimeJournal(Journal):
    def __init__(self, connection, stream, start_command):
        super().__init__(connection, stream)
        if start_command not in ("VISUAL", "DISCOVER"):
            raise ValueError("Unsupported runtime action")
        self.start_command = start_command

    def send(self, command):
        if command not in ("ID", "STOP", "PING", self.start_command):
            raise ValueError("Command outside protected runtime allowlist")
        if command == self.start_command:
            if not self.verified or not self.camera_ready or self.started:
                raise ValueError("Start requires exact fresh identity and camera frames, once only")
            self.started = True
        if command == "PING" and (not self.verified or not self.started):
            raise ValueError("PING requires verified, started runtime")
        self.event("tx", command=command)
        self.connection.write((command + "\n").encode("ascii"))
        self.connection.flush()


def identity(plan_sha):
    return "SPARKBENCH LED_OLED_RUNTIME V:1 PLAN:%s MODE:IDLE OLED:ACK SERVO:UNUSED" % plan_sha


def probe_expectations():
    # Telemetry describes physical pin25/pin26, never observed red/green lenses.
    return [{"step": i + 1, "red": a, "green": b, "oled_text": text}
            for i, (a, b, text) in enumerate(((False, False, "DARK"), (True, False, "P25"),
                (False, False, "DARK"), (False, True, "P26"), (False, False, "DARK END")))]


def acquire(port, device_id, artifact_path, output, action="VISUAL", fault=None, cancel=None):
    import serial
    from serial.tools import list_ports
    if cancel is not None and cancel.is_set():
        raise ValueError("Cancelled before hardware access")
    if not device_id.strip() or action not in ("VISUAL", "DISCOVER"):
        raise ValueError("Exact camera ID and supported runtime action required")
    if fault not in (None, "stop", "lease") or (fault and action != "DISCOVER"):
        raise ValueError("Qualification faults are limited to STOP/lease during approved LED probes")
    plan, artifact = load_artifact(artifact_path)
    ports = [p for p in list_ports.comports() if p.device == port]
    if len(ports) != 1 or (ports[0].vid, ports[0].pid) != (0x10C4, 0xEA60):
        raise ValueError("Selected port is not a freshly enumerated CP2102 10C4:EA60")
    helper = build_helper()
    expected_identity = identity(artifact["plan_sha256"])
    # UART check is telemetry only. Mapping may intentionally differ in probes.
    expected = probe_expectations() if action == "DISCOVER" else [
        {"step": i + 1, "red": s["red"] if plan["mapping"]["red"] == 25 else s["green"],
         "green": s["green"] if plan["mapping"]["green"] == 26 else s["red"], "oled_text": s["text"]}
        for i, s in enumerate(plan["steps"])]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "status": "recording", "source": "live_hardware",
              "device_id": device_id, "port": port, "usb_hwid": ports[0].hwid,
              "plan_sha256": artifact["plan_sha256"], "firmware_sha256": artifact["firmware_sha256"],
              "identity": expected_identity, "action": action, "servo_actuation": False,
              "firmware_hash_scope": "Expected local artifact hash; UART identity is not flash readback",
              "servo_angle_deg": None, "firmware_uploaded_by_runner": False,
              "automatic_physical_verification": "not performed",
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if fault:
        report["qualification_fault"] = fault
    save(output / "run.json", report)
    save(output / "artifact.snapshot.json", artifact)
    connection = serial.Serial(port=None, baudrate=115200, timeout=.05, write_timeout=.25)
    connection.port, connection.dtr, connection.rts = port, False, False
    camera = journal = None
    def check_cancel():
        if cancel is not None and cancel.is_set():
            report["cancelled"] = True
            raise ValueError("Camera test cancelled")
    with (output / "uart.jsonl").open("x") as stream, \
            (output / "camera.stdout.json").open("x") as stdout, \
            (output / "camera.stderr.log").open("x") as stderr:
        try:
            connection.open()
            journal = RuntimeJournal(connection, stream, action)
            journal.event("serial_open", note="Startup/replay retained")
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                check_cancel()
                journal.read()
            journal.send("ID")
            seen, ticks = False, []
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                check_cancel()
                for line in journal.read():
                    seen = seen or line == expected_identity
                    match = re.fullmatch(r"VISUAL_ALIVE UPTIME_MS:(\d+) MODE:IDLE", line)
                    if match:
                        ticks.append(int(match[1]))
                if seen and len(ticks) >= 2 and ticks[-1] > ticks[-2]:
                    break
            else:
                raise ValueError("Exact runtime plan identity/OLED ACK and fresh idle heartbeats absent; no start sent")
            journal.verified = True
            journal.event("identity_verified")
            seconds = 14 if fault else min(40, len(expected) * 3.3 + 8)
            camera = subprocess.Popen([str(helper), "capture", device_id, str(output / "camera"),
                                       str(seconds), "10" if fault else "5"], stdout=stdout, stderr=stderr)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                check_cancel()
                journal.read()
                if camera.poll() is not None:
                    raise ValueError("Camera stopped before start gate")
                rows = frame_rows(output / "camera/frames.jsonl")
                if (len(rows) >= 3 and 0 <= time.monotonic() - rows[-1]["host_uptime_seconds"] < 1.5
                        and all((output / "camera" / r["file"]).is_file() for r in rows[-3:])):
                    break
            else:
                raise ValueError("Fresh camera frames absent; no start sent")
            journal.camera_ready = True
            start = len(journal.lines)
            journal.send(action)
            next_ping = time.monotonic()
            bright_at = None
            fault_triggered = False
            deadline = time.monotonic() + seconds + 8
            while time.monotonic() < deadline and camera.poll() is None:
                check_cancel()
                fresh = frame_rows(output/"camera/frames.jsonl")
                if not fresh or time.monotonic()-fresh[-1]["host_uptime_seconds"] > 1.5:
                    raise ValueError("Camera frames became stale; stopping outputs")
                if (fault and bright_at is not None and not fault_triggered
                        and time.monotonic() - bright_at >= (.4 if fault == "lease" else 1.9)):
                    journal.event("fault_trigger", case=fault)
                    fault_triggered = True
                    if fault == "stop":
                        journal.send("STOP")
                if time.monotonic() >= next_ping and not (fault == "lease" and fault_triggered):
                    journal.send("PING")
                    next_ping = time.monotonic() + .4
                for line in journal.read():
                    if line.startswith("VISUAL_STEP:2 ") and bright_at is None:
                        bright_at = time.monotonic()
                    if fault == "lease" and fault_triggered and line == "VISUAL_ERROR LEASE_EXPIRED":
                        continue  # Explicitly induced and retained; never an ordinary sequence pass.
                    if "ERROR" in line or re.search(r"\bBOOT\b", line):
                        raise ValueError("Runtime error/reset; stopping capture")
            if camera.poll() is None:
                raise ValueError("Camera exceeded bounded deadline")
            journal.read()
            if fault:
                reason = "LEASE_EXPIRED" if fault == "lease" else "STOPPED"
                lines = journal.lines[start:]
                markers = [line for line in lines if line.startswith("VISUAL_STEP:")]
                report["serial_sequence"] = {"status": "pass" if fault_triggered
                    and len(markers) == 2 and any(line.startswith("VISUAL_STOPPED STATUS:" + reason + " ") for line in lines)
                    and "VISUAL_DONE" not in lines else "incomplete",
                    "scope": "Deliberate fault UART telemetry only; camera measurements required",
                    "expected_stop_reason": reason}
            else:
                report["serial_sequence"] = check_sequence(journal.lines[start:], expected)
            captured = json.loads((output / "camera/capture.json").read_text())
            report["frame_count"] = captured.get("frame_count", 0)
            report["status"] = "completed" if (camera.returncode == 0 and captured.get("status") == "captured"
                and report["serial_sequence"]["status"] == "pass") else "incomplete"
        except (Exception, KeyboardInterrupt) as exc:
            report.update(status="incomplete", error=str(exc))
        finally:
            # STOP even after normal completion; lease expiry is an independent fallback.
            if journal and journal.verified and connection.is_open:
                try:
                    before_stop = len(journal.lines)
                    journal.send("STOP")
                    deadline = time.monotonic()+1.0
                    acknowledged = False
                    while time.monotonic() < deadline:
                        journal.read()
                        if any(re.fullmatch(r"VISUAL_STOPPED STATUS:STOPPED RED:0 GREEN:0 UPTIME_MS:\d+", line)
                               for line in journal.lines[before_stop:]):
                            acknowledged = True
                            break
                    report["stop_acknowledged_uart_only"] = acknowledged
                    if not acknowledged:
                        report["status"] = "incomplete"
                        report["stop_error"] = "STOP acknowledgement absent"
                except Exception as exc:
                    report["stop_error"] = type(exc).__name__
                    report["status"] = "incomplete"
            if camera and camera.poll() is None:
                camera.terminate()
                try:
                    camera.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    camera.kill(); camera.wait(timeout=5)
            if journal and journal.pending:
                journal.event("rx_partial", hex=journal.pending.hex())
            connection.close()
            report["sequence_started"] = bool(journal and journal.started)
            report["serial_commands_sent"] = [json.loads(line)["command"] for line in
                (output / "uart.jsonl").read_text().splitlines() if json.loads(line)["kind"] == "tx"]
            report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
            save(output / "run.json", report)
    return report
