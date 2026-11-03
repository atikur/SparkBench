"""Check firmware-reported LED transitions, not physical light output."""

import argparse
import json
import re
import time
from pathlib import Path

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error("--seconds must be greater than 0 and at most 60")

    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2)
    connection.port = args.port
    connection.dtr = False
    connection.rts = False
    events, lines, startup_lines = [], [], []
    try:
        connection.open()
        time.sleep(1)
        startup = connection.read(min(connection.in_waiting, 8192))
        startup_lines = startup.decode("utf-8", errors="replace").splitlines()
        connection.reset_input_buffer()
        started = time.monotonic()
        while time.monotonic() - started < args.seconds:
            raw = connection.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            lines.append(line)
            match = re.fullmatch(r"RED_LED:(ON|OFF) UPTIME_MS:(\d+)", line)
            if match:
                events.append({"state": match[1], "uptime_ms": int(match[2])})
    finally:
        connection.close()

    pairs = list(zip(events, events[1:]))
    deltas = [b["uptime_ms"] - a["uptime_ms"] for a, b in pairs]
    passed = (len(events) >= 4
              and all(a["state"] != b["state"] for a, b in pairs)
              and all(900 <= delta <= 1500 for delta in deltas))
    report = {
        "status": "pass" if passed else "fail",
        "source": "live_serial",
        "port": args.port,
        "scope": "Firmware-reported GPIO25 LED states and uptime spacing only",
        "physical_observation": "pending user confirmation; no camera measurement",
        "startup_settle_seconds": 1,
        "startup_lines": startup_lines,
        "lines": lines,
        "events": events,
        "event_deltas_ms": deltas,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    summary = {key: value for key, value in report.items()
               if key not in ("lines", "startup_lines")}
    summary["capture"] = str(args.output)
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
