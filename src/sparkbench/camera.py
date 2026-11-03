"""Explicit-camera, bounded macOS acquisition using the native AVFoundation API.

List does not open cameras. Capture never sends commands to connected hardware.
Images stay local and are not automatically sent to any model or service.
"""

import hashlib
import json
import math
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build_helper():
    if platform.system() != "Darwin":
        raise ValueError("This camera backend requires macOS")
    compiler = shutil.which("xcrun")
    if not compiler:
        raise ValueError("Install Apple Command Line Tools to build the camera helper")
    sources = ROOT / "tools" / "macos_camera"
    source, info = sources / "main.swift", sources / "Info.plist"
    if not source.is_file() or not info.is_file():
        raise ValueError("Run from the source checkout; native camera sources are missing")
    fingerprint = hashlib.sha256(source.read_bytes() + info.read_bytes()
                                 + platform.machine().encode()
                                 + platform.mac_ver()[0].encode()).hexdigest()
    build = ROOT / ".cache" / "camera"
    binary, stamp = build / "SparkBenchCamera", build / "source.sha256"
    if binary.is_file() and stamp.is_file() and stamp.read_text() == fingerprint:
        return binary
    build.mkdir(parents=True, exist_ok=True)
    command = [compiler, "swiftc", "-swift-version", "5", "-O",
               "-module-cache-path", str(build / "swift-modules"), str(source),
               "-o", str(binary), "-Xlinker", "-sectcreate", "-Xlinker", "__TEXT",
               "-Xlinker", "__info_plist", "-Xlinker", str(info)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise ValueError("Camera helper build failed:\n" + result.stderr[-6000:])
    stamp.write_text(fingerprint)
    return binary


def run_helper(arguments, timeout=20):
    result = subprocess.run([str(build_helper()), *arguments], capture_output=True,
                            text=True, timeout=timeout)
    try:
        report = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError("Camera helper did not return JSON: " + result.stderr[-2000:]) from exc
    if result.returncode:
        raise ValueError(report.get("error") or "Camera capture incomplete: "
                         + json.dumps(report))
    return report


def list_cameras():
    return run_helper(["list"])


def authorize_camera():
    return run_helper(["authorize"], timeout=80)


def capture_frames(device_id, seconds=10, fps=5, output=None):
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Select a camera explicitly using its ID from camera list")
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 1 <= seconds <= 60):
        raise ValueError("Capture duration must be between 1 and 60 seconds")
    if (type(fps) not in (int, float) or not math.isfinite(fps) or not 1 <= fps <= 10):
        raise ValueError("Sample FPS must be between 1 and 10")
    if output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        output = ROOT / "runs" / "camera" / stamp
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output path already exists; choose a new directory")
    # The native helper also checks the path before creating it.
    return run_helper(["capture", device_id, str(output), str(seconds), str(fps)],
                      timeout=seconds + 100)
