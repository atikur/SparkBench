"""Capture a bounded heartbeat window after serial-open startup settles.

Some UART bridges reset/replay startup bytes on open even when this reader does
not explicitly pulse reset. Startup bytes are retained separately from the
measurement window; duplicates or resets inside the window still fail.
"""

import argparse
import json
import time
from pathlib import Path

import serial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--connection", choices=("native-usb", "uart"), default="native-usb")
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--settle-seconds", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=Path("runs/bringup/heartbeat.json"))
    args = parser.parse_args()
    if args.seconds <= 0 or args.seconds > 60:
        parser.error("--seconds must be greater than 0 and at most 60")
    if not 0 <= args.settle_seconds <= 5:
        parser.error("--settle-seconds must be between 0 and 5")
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2)
    connection.port = args.port
    # Native CDC needs host-present DTR. On UART boards, leave both auto-reset
    # control lines deasserted so the reader does not hold BOOT or RESET active.
    connection.dtr = args.connection == "native-usb"
    connection.rts = False
    lines = []
    ticks = []
    startup_lines = []
    try:
        connection.open()
        time.sleep(args.settle_seconds)
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
            if line.startswith("HEARTBEAT:"):
                value = line.partition(":")[2]
                if value.isdigit():
                    ticks.append(int(value))
    finally:
        connection.close()
    deltas = [second - first for first, second in zip(ticks, ticks[1:])]
    passed = len(ticks) >= 3 and all(900 <= delta <= 1500 for delta in deltas)
    result = {
        "status": "pass" if passed else "fail",
        "source": "live_serial",
        "port": args.port,
        "connection": args.connection,
        "startup_settle_seconds": args.settle_seconds,
        "startup_lines": startup_lines,
        "lines": lines,
        "heartbeat_ticks_ms": ticks,
        "heartbeat_deltas_ms": deltas,
        "scope": "USB serial and firmware heartbeat only; no physical rig tested",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
