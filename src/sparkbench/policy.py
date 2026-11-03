"""Check frozen measurement settings without changing the calibrated reader."""
import hashlib
import json
from pathlib import Path

from .camera import ROOT
from .meta import MAX_COMPLETION_TOKENS, PROMPT, configuration
from .vision import digest


def check_policy(path, model=None):
    path = Path(path)
    policy = json.loads(path.read_text())
    files = {"meta_reader_source_sha256": "src/sparkbench/meta.py",
             "preparer_source_sha256": "tools/macos_vision/prepare_label.swift",
             "preparer_wrapper_sha256": "src/sparkbench/label_crop.py",
             "analyzer_source_sha256": "src/sparkbench/vision.py"}
    for field, name in files.items():
        if policy.get(field) != digest(ROOT / name):
            raise ValueError("Frozen reader policy differs: " + field)
    if (policy.get("model") != (model or configuration().model)
            or policy.get("prompt_sha256") != hashlib.sha256(PROMPT.encode()).hexdigest()
            or policy.get("max_completion_tokens") != MAX_COMPLETION_TOKENS
            or policy.get("reasoning_effort") != "minimal"):
        raise ValueError("Frozen reader model/prompt/token settings differ")
    calibration = (ROOT / policy["calibration"]).resolve()
    if digest(calibration) != policy.get("calibration_sha256"):
        raise ValueError("Frozen LED calibration differs")
    return policy, calibration


def check_integrity(directory):
    directory = Path(directory)
    entries = json.loads((directory / "integrity.json").read_text())["sha256"]
    if not entries:
        raise ValueError("Empty evidence integrity manifest")
    for name, sha in entries.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe integrity manifest path")
        path = directory / relative
        if path.is_symlink() or digest(path) != sha:
            raise ValueError("Evidence changed: " + name)
    return entries
