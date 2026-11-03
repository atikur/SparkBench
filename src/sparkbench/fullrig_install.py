"""Application-only full-runtime installation with verified rollback.

Explicit CLI only. No runtime commands, camera, actuation or model operation.
Disconnect the external servo supply before invoking this installer.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .camera import ROOT
from .fullrig import ENVIRONMENT, load_artifact
from .vision import digest, save


def install(artifact_path, port, previous_application, previous_sha256, output, *, servo_power_off=False):
    if servo_power_off is not True:
        raise ValueError("Explicit external servo power-off confirmation required; no hardware I/O performed")
    plan, artifact = load_artifact(artifact_path)
    previous_application = Path(previous_application).resolve()
    if digest(previous_application) != previous_sha256: raise ValueError("Previous application hash mismatch")
    from serial.tools import list_ports
    ports = [p for p in list_ports.comports() if p.device == port]
    if len(ports) != 1 or (ports[0].vid, ports[0].pid) != (0x10C4, 0xEA60):
        raise ValueError("Fresh CP2102 enumeration required")
    reference = ROOT/"runs/firmware/led-oled-installed-2026-10-30"
    build = Path(artifact_path)/"project/.pio/build"/ENVIRONMENT
    for name in ("bootloader.bin", "partitions.bin"):
        if digest(build/name) != digest(reference/name): raise ValueError("Existing boot layout differs; application-only install refused")
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(previous_application, output/"previous-application.bin")
    shutil.copyfile(Path(artifact_path)/artifact["firmware"], output/"application.bin")
    for name in ("bootloader.bin", "partitions.bin", "boot_app0.bin"): shutil.copyfile(reference/name, output/name)
    report = {"schema_version": 1, "status": "prepared", "profile": plan["profile"],
              "port": port, "usb_hwid": ports[0].hwid, "plan_sha256": artifact["plan_sha256"],
              "firmware_sha256": artifact["firmware_sha256"], "previous_firmware_sha256": previous_sha256,
              "application_offset": "0x10000", "boot_partition_nvs_written": False,
              "servo_actuation": False, "serial_runtime_commands": [], "commands": []}
    save(output/"installation.json", report)
    prefix = [sys.executable, "-m", "esptool", "--chip", "esp32", "--port", port, "--baud", "115200"]
    def command(name, arguments):
        cmd = prefix+arguments; report["commands"].append(cmd); save(output/"installation.json", report)
        with (output/(name+".log")).open("x") as log:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        if result.returncode: raise ValueError(name+" failed")
    def verify_image(application):
        return ["verify-flash", "0x1000", str(output/"bootloader.bin"), "0x8000", str(output/"partitions.bin"),
                "0xe000", str(output/"boot_app0.bin"), "0x10000", str(output/application)]
    wrote = False
    try:
        command("01-verify-previous", verify_image("previous-application.bin"))
        report["previous_installed_bytes_verified"] = True; wrote = True
        command("02-write-application", ["write-flash", "0x10000", str(output/"application.bin")])
        command("03-verify-installed-and-boot", verify_image("application.bin"))
        report.update(status="installed_hash_verified", uploaded=True)
    except (OSError, ValueError, subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        report.update(status="incomplete", error=str(exc))
        if wrote:
            try:
                command("04-restore-previous", ["write-flash", "0x10000", str(output/"previous-application.bin")])
                command("05-verify-restored-and-boot", verify_image("previous-application.bin"))
                report["recovery"] = "previous_application_restored_hash_verified"
            except (OSError, ValueError, subprocess.TimeoutExpired, KeyboardInterrupt) as restore:
                report["recovery"] = "incomplete: "+str(restore)
    finally:
        save(output/"installation.json", report)
        save(output/"integrity.json", {"sha256": {str(p.relative_to(output)): digest(p)
            for p in sorted(output.rglob('*')) if p.is_file() and p.name != "integrity.json"}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True); parser.add_argument("--port", required=True)
    parser.add_argument("--previous-application", type=Path, required=True); parser.add_argument("--previous-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--servo-power-off", action="store_true")
    args = parser.parse_args()
    try:
        result = install(args.artifact, args.port, args.previous_application, args.previous_sha256, args.output,
                         servo_power_off=args.servo_power_off)
    except (OSError, ValueError, KeyError, TypeError) as exc: parser.exit(2, str(exc)+"\n")
    print(json.dumps(result, indent=2)); return 0 if result["status"] == "installed_hash_verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
