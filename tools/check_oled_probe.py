"""Capture the three address-only OLED scans; this does not verify pixels."""
import argparse
import json
import re
import time
from pathlib import Path

import serial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2)
    connection.port = args.port
    connection.dtr = False
    connection.rts = False
    lines = []
    try:
        connection.open()
        started = time.monotonic()
        while time.monotonic() - started < 30:
            line = connection.readline().decode('utf-8', errors='replace').strip()
            if line:
                lines.append(line)
            if line == 'I2C_PROBE:DONE BUS_RELEASED':
                break
    finally:
        connection.close()
    # Use only the latest complete firmware run, discarding bridge replay.
    headers = [i for i, line in enumerate(lines) if line.startswith('SPARKBENCH OLED I2C PROBE')]
    run = lines[headers[-1]:] if headers else []
    scans = {}
    addresses = {}
    for line in run:
        match = re.fullmatch(r'I2C_SCAN:(\d+) END FOUND:(\d+) ERRORS:(\d+)', line)
        if match:
            scans[int(match[1])] = {'found': int(match[2]), 'errors': int(match[3])}
        match = re.fullmatch(r'I2C_SCAN:(\d+) ACK_7BIT:(0x[0-9A-F]+)', line)
        if match:
            addresses.setdefault(int(match[1]), []).append(match[2])
    passed = (
        'I2C_PROBE:DONE BUS_RELEASED' in run
        and set(scans) == {1, 2, 3}
        and all(s['found'] == 1 and s['errors'] == 0 for s in scans.values())
        and all(addresses.get(i) == addresses.get(1) for i in (2, 3))
        and addresses.get(1) in (['0x3C'], ['0x3D'])
    )
    result = {
        'status': 'pass' if passed else 'needs_inspection',
        'source': 'live_serial', 'port': args.port,
        'sda_gpio': 21, 'scl_gpio': 22,
        'scans': scans, 'ack_7bit_addresses_by_scan': addresses,
        'lines': lines,
        'scope': 'I2C address response only; controller identity and visible output unverified',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
