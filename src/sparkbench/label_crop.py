"""Deterministic label-margin trimming; no text recognition or model calls."""
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def prepare_label(source, output):
    if platform.system() != "Darwin" or not shutil.which("xcrun"):
        raise ValueError("Label preparation requires the local macOS image tool")
    swift = ROOT / "tools/macos_vision/prepare_label.swift"
    fingerprint = hashlib.sha256(swift.read_bytes() + platform.machine().encode()
                                 + platform.mac_ver()[0].encode()).hexdigest()
    folder = ROOT / ".cache/vision"
    binary, stamp = folder / "PrepareLabel", folder / "prepare-label.sha256"
    folder.mkdir(parents=True, exist_ok=True)
    if not (binary.is_file() and stamp.is_file() and stamp.read_text() == fingerprint):
        result = subprocess.run(["xcrun", "swiftc", "-O", "-module-cache-path",
            str(folder / "swift-modules"), str(swift), "-o", str(binary)],
            capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise ValueError("Label preparation build failed: " + result.stderr[-2000:])
        stamp.write_text(fingerprint)
    result = subprocess.run([str(binary), str(source), str(output)],
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError("Label preparation failed: " + result.stderr[-1000:])
    report = json.loads(result.stdout)
    report["source_sha256"] = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    report["output_sha256"] = hashlib.sha256(Path(output).read_bytes()).hexdigest()
    report["preparer_source_sha256"] = hashlib.sha256(swift.read_bytes()).hexdigest()
    return report
