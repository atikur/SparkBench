"""Trusted renderer/compiler. Compile-only: this module has no upload path."""
import json
import os
import shutil
import subprocess
from pathlib import Path

from .camera import ROOT
from .plans import plan_hash, render_header, validate_plan
from .vision import digest, save

TRUSTED_FILES = ("platformio.ini", "include/engine.h", "src/main.cpp")


def build_artifact(plan, output, compile_firmware=True):
    validate_plan(plan)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    save(output / "plan.json", plan)
    project = output / "project"
    for name in TRUSTED_FILES:
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "firmware/runtime" / name, target)
    (project / "include/plan_data.h").write_text(render_header(plan))
    report = {"schema_version": 1, "status": "rendered", "plan_sha256": plan_hash(plan),
              "trusted_runtime_sha256": {n: digest(ROOT / "firmware/runtime" / n) for n in TRUSTED_FILES},
              "inputs_sha256": {str(p.relative_to(output)): digest(p)
                                for p in sorted(output.rglob("*")) if p.is_file()},
              "environment": "classic-led-oled-runtime", "uploaded": False,
              "physical_verification": "not performed", "servo_actuation": False}
    save(output / "artifact.json", report)
    if compile_firmware:
        # Reuse pinned library source already built on this Mac, never binaries.
        cached = ROOT/"runs/live/qualification-2026-10-30-v1/11-discovered-generation/attempt-01/artifact/project/.pio/libdeps/classic-led-oled-runtime/U8g2"
        if cached.is_dir():
            dependency = project/".pio/libdeps/classic-led-oled-runtime/U8g2"
            shutil.copytree(cached, dependency)
            report["dependency_sources_sha256"] = {str(p.relative_to(output)):digest(p)
                for p in sorted(dependency.rglob('*')) if p.is_file()}
        env = dict(os.environ, PLATFORMIO_CORE_DIR=str(ROOT / ".platformio"),
                   PLATFORMIO_SETTING_ENABLE_TELEMETRY="no")
        command = [str(ROOT / ".venv/bin/pio"), "run", "--project-dir", str(project),
                   "--environment", "classic-led-oled-runtime"]
        try:
            with (output / "compile.log").open("x") as log:
                result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
            binary = project / ".pio/build/classic-led-oled-runtime/firmware.bin"
            report["status"] = "compiled" if result.returncode == 0 and binary.is_file() else "compile_failed"
            report["compiler_returncode"] = result.returncode
            if report["status"] == "compiled":
                report["firmware"] = str(binary.relative_to(output))
                report["firmware_sha256"] = digest(binary)
                report["firmware_bytes"] = binary.stat().st_size
        except (OSError, subprocess.TimeoutExpired) as exc:
            report.update(status="compile_failed", error=type(exc).__name__)
        save(output / "artifact.json", report)
    return report


def runtime_current(path):
    """False when a saved build holds an older trusted runtime, so it can no longer be installed."""
    try:
        record = json.loads((Path(path) / "artifact.json").read_text())["trusted_runtime_sha256"]
        return all(record.get(n) == digest(ROOT / "firmware/runtime" / n) for n in TRUSTED_FILES)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def load_artifact(path, require_compiled=True):
    path = Path(path).resolve()
    record = json.loads((path / "artifact.json").read_text())
    plan = validate_plan(json.loads((path / "plan.json").read_text()))
    if record["plan_sha256"] != plan_hash(plan):
        raise ValueError("Artifact plan changed")
    expected_files = {"plan.json", "project/include/plan_data.h"} | {
        "project/" + n for n in TRUSTED_FILES}
    if set(record["inputs_sha256"]) != expected_files:
        raise ValueError("Unexpected artifact write set")
    for name, sha in record["inputs_sha256"].items():
        file = path / name
        if file.is_symlink() or digest(file) != sha:
            raise ValueError("Artifact input changed: " + name)
    if (path / "project/include/plan_data.h").read_text() != render_header(plan):
        raise ValueError("Artifact data header does not match validated plan")
    for name in TRUSTED_FILES:
        sha = digest(ROOT / "firmware/runtime" / name)
        if record["trusted_runtime_sha256"].get(name) != sha or digest(path / "project" / name) != sha:
            raise ValueError("Artifact does not contain current trusted runtime: " + name)
    if require_compiled:
        binary_name = "project/.pio/build/classic-led-oled-runtime/firmware.bin"
        if (record.get("status") != "compiled" or record.get("firmware") != binary_name
                or digest(path / binary_name) != record.get("firmware_sha256")):
            raise ValueError("A compiled, unchanged runtime artifact is required")
        for name, sha in record.get("dependency_sources_sha256", {}).items():
            relative = Path(name)
            if (relative.is_absolute() or ".." in relative.parts
                    or not name.startswith("project/.pio/libdeps/classic-led-oled-runtime/U8g2/")
                    or (path/relative).is_symlink() or digest(path/relative) != sha):
                raise ValueError("Compiled dependency source changed")
    return plan, record
