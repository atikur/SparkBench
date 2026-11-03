"""Create a portable private source snapshot using an explicit inclusion list."""

import argparse
import hashlib
import json
import re
import os
import shlex
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FOLDERS = ("src", "tests", "firmware", "hardware", "tools", "docs", "specs", "examples")
ROOT_FILES = ("README.md", "HANDOVER.txt", "CONTINUE_PROMPT.txt", "pyproject.toml",
              "requirements-dev.txt", ".gitignore")
SKIP_PARTS = {".git", ".venv", ".platformio", ".pio", ".cache", "__pycache__"}
SOURCE_SUFFIXES = {".py", ".cpp", ".h", ".hpp", ".ini", ".csv", ".json", ".txt",
                   ".md", ".swift", ".plist", ".sh", ".svg", ".png", ".html", ".css", ".js"}
SECRET = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
                    rb"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{24,}|"
                    rb"github_pat_[A-Za-z0-9_]{24,}|AKIA[A-Z0-9]{16})\b")


def configured_secrets():
    """Scan for the actual configured Meta key without exposing or archiving it."""
    values = [os.environ.get("META_API_KEY", "")]
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            match = re.match(r"^\s*(?:export\s+)?META_API_KEY\s*=\s*(.*?)\s*$", line)
            if match:
                words = shlex.split(match[1], comments=True)
                values.extend(words if len(words) == 1 else [])
    return [v.encode() for v in values if len(v) >= 16]


def omitted_evidence():
    """Explicitly disclose private local dependencies of this source snapshot."""
    policy = json.loads((ROOT / "hardware/oled-reader.policy.json").read_text())
    names = {policy["calibration"], "runs/vision/contributor-validation-2026-10-30-v1/verification.json",
             "runs/software/status.json"}
    calibration = ROOT / policy["calibration"]
    if calibration.is_file():
        names.add(json.loads(calibration.read_text())["geometry"]["reference_frame"])
    camera = ROOT / "hardware/camera.json"
    if camera.is_file():
        target = json.loads(camera.read_text()).get("target_host", {})
        names.update(target[k] for k in ("latest_capture", "latest_review") if target.get(k))
    board = ROOT / "hardware/board.json"
    if board.is_file():
        active = json.loads(board.read_text()).get("active_firmware", {})
        names.update(active[k] for k in ("installation_record", "runtime_safety_qualification") if active.get(k))
    return [{"path": name, "bundled": False,
             "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest() if (ROOT / name).is_file() else None}
            for name in sorted(names)]


def payload_files():
    result = [ROOT / name for name in ROOT_FILES]
    for folder in SOURCE_FOLDERS:
        for path in (ROOT / folder).rglob("*"):
            relative = path.relative_to(ROOT)
            if (not path.is_file() or path.is_symlink()
                    or any(part in SKIP_PARTS or part.endswith(".egg-info") for part in relative.parts)
                    or path.name.startswith(".env") or path.suffix not in SOURCE_SUFFIXES):
                continue
            result.append(path)
    result.extend((ROOT / "runs" / "bringup").glob("*.json"))
    for pattern in ("*.json", "*.bin"):
        result.extend((ROOT / "runs" / "backups").glob(pattern))
    return sorted(set(result))


def verify_flash_backups():
    for path in (ROOT / "runs" / "backups").glob("manifest*.json"):
        record = json.loads(path.read_text())
        backup = ROOT / record["path"]
        data = backup.read_bytes()
        if (hashlib.sha256(data).hexdigest() != record["sha256"]
                or ("size_bytes" in record and len(data) != record["size_bytes"])):
            raise ValueError("Flash backup does not match its manifest: " + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Output ZIP already exists; choose a new path")
    verify_flash_backups()
    files = payload_files()
    entries = []
    local_secrets = configured_secrets()
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError("Missing file or unexpected symlink: " + str(path))
        data = path.read_bytes()
        if (any(secret in data for secret in local_secrets)
                or (path.suffix not in {".bin", ".png"} and SECRET.search(data))):
            raise ValueError("Possible credential in " + str(path.relative_to(ROOT))
                             + "; value withheld; archive was not created")
        entries.append({"path": path.relative_to(ROOT).as_posix(), "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {
        "schema_version": 1, "project": "SparkBench",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload_file_count": len(entries),
        "target": "MacBook Pro; native iPhone Continuity Camera captured and scoped LED/OLED verification recorded locally",
        "excludes": ["virtual environments", "toolchain/build caches", "credential files",
                     "compiled camera helper", "camera/video captures", "Git history"],
        "scope": "Source snapshot plus manual/serial evidence and original flash backups. Private camera/vision/software run evidence is omitted; referenced local results are not portable acceptance evidence.",
        "omitted_local_evidence": omitted_evidence(),
        "portability_note": "Rebuild tools and establish local permissions. Frozen camera calibration/reference images are omitted; migrate private evidence deliberately or recalibrate before camera verification.",
        "files": entries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, entry in zip(files, entries):
            info = zipfile.ZipInfo.from_file(path, "SparkBench/" + entry["path"])
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if path.suffix == ".sh" else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
        archive.writestr("SparkBench/HANDOVER_MANIFEST.json",
                         json.dumps(manifest, indent=2) + "\n")
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(checksum + "  " + output.name + "\n")
    print(json.dumps({"archive": str(output), "size_bytes": output.stat().st_size,
                      "payload_files": len(entries), "sha256": checksum,
                      "checksum_file": str(checksum_path)}, indent=2))


if __name__ == "__main__":
    main()
