"""Run the explicit LED/OLED diagnostic with separate camera and UART journals.

This orchestrator never uploads firmware. The camera helper still has no serial
access. UART acknowledgements are not treated as visual measurements.
"""

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .camera import ROOT, build_helper

IDENTITY = "SPARKBENCH LED_OLED_TEST MODE:IDLE OLED:ACK SERVO:UNUSED"
STEP = re.compile(r"VISUAL_STEP:(\d+) RED:([01]) GREEN:([01]) TEXT:(.*?) UPTIME_MS:(\d+)")


def ready_identity(line):
    return line == IDENTITY


def check_sequence(lines, expected):
    steps = []
    for line in lines:
        match = STEP.fullmatch(line)
        if match:
            steps.append({"step": int(match[1]), "red": match[2] == "1",
                          "green": match[3] == "1", "oled_text": match[4],
                          "uptime_ms": int(match[5])})
    observed = [{k: v for k, v in row.items() if k != "uptime_ms"} for row in steps]
    deltas = [b["uptime_ms"] - a["uptime_ms"] for a, b in zip(steps, steps[1:])]
    complete = (observed == expected and "VISUAL_DONE" in lines
                and any(line.startswith("VISUAL_STOPPED STATUS:COMPLETE RED:0 GREEN:0")
                        for line in lines)
                and all(3000 <= delta <= 4000 for delta in deltas)
                and not any("ERROR" in line or re.search(r"\bBOOT\b", line)
                            for line in lines))
    return {"status": "pass" if complete else "incomplete", "steps": steps,
            "step_deltas_ms": deltas,
            "scope": "UART-reported sequence only; no physical behavior assertions"}


class Journal:
    def __init__(self, connection, stream):
        self.connection, self.stream = connection, stream
        self.pending = b""
        self.lines = []
        self.verified = False
        self.camera_ready = False
        self.started = False

    def event(self, kind, **fields):
        row = {"kind": kind, "host_uptime_seconds": time.monotonic(),
               "host_unix_seconds": time.time(), **fields}
        self.stream.write(json.dumps(row) + "\n")
        self.stream.flush()
        return row

    def read(self):
        raw = self.connection.read(min(self.connection.in_waiting or 1, 8192))
        if not raw:
            return []
        event = self.event("rx_bytes", hex=raw.hex())
        self.pending += raw
        fresh = []
        while b"\n" in self.pending:
            line, self.pending = self.pending.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").rstrip("\r")
            self.lines.append(text)
            fresh.append(text)
            self.stream.write(json.dumps({**event, "kind": "rx_line", "line": text,
                                          "hex": line.hex()}) + "\n")
        self.stream.flush()
        return fresh

    def send(self, command):
        if command not in ("ID", "VISUAL", "STOP"):
            raise ValueError("Command outside LED/OLED allowlist")
        if command == "VISUAL":
            if not self.verified or not self.camera_ready or self.started:
                raise ValueError("VISUAL requires fresh idle identity and live camera frames, once only")
            self.started = True
        self.event("tx", command=command)
        self.connection.write((command + "\n").encode("ascii"))
        self.connection.flush()


def frame_rows(path):
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            break  # Writer may currently be appending the final row.
    return rows


def run(port, device_id, output):
    import serial
    from serial.tools import list_ports

    if not device_id.strip():
        raise ValueError("Select the exact camera ID explicitly")
    ports = [p for p in list_ports.comports() if p.device == port]
    if len(ports) != 1 or (ports[0].vid, ports[0].pid) != (0x10C4, 0xEA60):
        raise ValueError("Selected port is not a freshly enumerated CP2102 10C4:EA60")
    helper = build_helper()
    expected = json.loads((ROOT / "specs/led_oled_only.json").read_text())["steps"]
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "status": "recording", "source": "live_hardware",
              "port": port, "usb_hwid": ports[0].hwid, "device_id": device_id,
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "camera_directory": "camera", "uart_journal": "uart.jsonl",
              "serial_commands_sent": [], "servo_actuation": False,
              "servo_angle_deg": None, "firmware_uploaded_by_runner": False,
              "automatic_physical_verification": "not performed",
              "full_behavior_verification": "incomplete; required servo measurements missing",
              "timing_note": "UART receipt and camera host uptime use seconds since boot; receipt is not exposure time. Keep raw PTS and exclude transition windows."}
    report_path = output / "run.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.1)
    connection.port, connection.dtr, connection.rts = port, False, False
    camera = None
    journal = None
    with (output / "uart.jsonl").open("x") as stream, \
            (output / "camera.stdout.json").open("x") as camera_stdout, \
            (output / "camera.stderr.log").open("x") as camera_stderr:
        try:
            connection.open()
            journal = Journal(connection, stream)
            journal.event("serial_open", note="Startup and replay bytes retained; no input reset")
            settle = time.monotonic() + 2
            while time.monotonic() < settle:
                journal.read()
            journal.event("settled")
            journal.send("ID")
            identity = False
            ticks = []
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                for line in journal.read():
                    identity = identity or ready_identity(line)
                    match = re.fullmatch(r"VISUAL_ALIVE UPTIME_MS:(\d+) MODE:IDLE", line)
                    if match:
                        ticks.append(int(match[1]))
                if identity and len(ticks) >= 2 and ticks[-1] > ticks[-2]:
                    break
            else:
                raise ValueError("Fresh LED_OLED_TEST idle identity/OLED ACK and increasing heartbeats not received; no start command sent")
            journal.verified = True
            report["identity"] = IDENTITY
            journal.event("identity_verified")
            camera = subprocess.Popen([str(helper), "capture", device_id,
                                       str(output / "camera"), "25", "5"],
                                      stdout=camera_stdout, stderr=camera_stderr)
            camera_deadline = time.monotonic() + 40
            while time.monotonic() < camera_deadline:
                journal.read()
                if camera.poll() is not None:
                    raise ValueError("Camera stopped before start gate; no VISUAL command sent")
                rows = frame_rows(output / "camera/frames.jsonl")
                if len(rows) >= 3 and 0 <= time.monotonic() - rows[-1]["host_uptime_seconds"] < 1.5:
                    if not all((output / "camera" / row["file"]).is_file() for row in rows[-3:]):
                        continue
                    break
            else:
                raise ValueError("Camera did not deliver fresh frames; no VISUAL command sent")
            journal.camera_ready = True
            journal.event("camera_frames_ready", frame=rows[-1]["frame"])
            start_index = len(journal.lines)
            journal.send("VISUAL")
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline and camera.poll() is None:
                journal.read()
            if camera.poll() is None:
                raise ValueError("Bounded camera process exceeded deadline")
            # Drain final serial bytes; all five steps normally finish well before capture.
            journal.read()
            report["serial_sequence"] = check_sequence(journal.lines[start_index:], expected)
            camera_report = json.loads((output / "camera/capture.json").read_text())
            report["camera_status"] = camera_report["status"]
            report["frame_count"] = camera_report.get("frame_count", 0)
            report["status"] = ("completed" if camera.returncode == 0
                                and camera_report["status"] == "captured"
                                and report["serial_sequence"]["status"] == "pass" else "incomplete")
        except (Exception, KeyboardInterrupt) as exc:
            report["status"], report["error"] = "incomplete", str(exc)
            if journal is not None and journal.verified and connection.is_open:
                try:
                    journal.send("STOP")
                except Exception as stop_error:
                    report["stop_error"] = str(stop_error)
        finally:
            if camera is not None and camera.poll() is None:
                camera.terminate()
                try:
                    camera.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    camera.kill()
                    camera.wait(timeout=5)
            if journal is not None and journal.pending:
                journal.event("rx_partial", hex=journal.pending.hex())
            connection.close()
            stream.flush()
            report["serial_commands_sent"] = [json.loads(line)["command"] for line in
                (output / "uart.jsonl").read_text().splitlines() if json.loads(line)["kind"] == "tx"]
            report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
            report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "runs/led-oled" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    report = run(args.port, args.device_id, output.resolve())
    print(json.dumps({**report, "output_directory": str(output.resolve())}, indent=2))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
