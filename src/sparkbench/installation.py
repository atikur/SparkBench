"""Explicitly authorized application-only runtime installation with recovery.

The flash transaction is separate from capture and generation. A separate
identity check sends only ID; neither operation starts a behavior sequence.
"""
import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import load_artifact
from .camera import ROOT
from .vision import digest, save


def verify_identity(port, plan_sha256, output):
    """Read-only UART check. Sends one ID; never starts a sequence or PWM."""
    import serial
    from serial.tools import list_ports
    from .led_oled import Journal
    from .runtime_io import identity
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    expected=identity(plan_sha256)
    report={"status":"incomplete","scope":"UART identity only; not physical output verification",
            "port":port,"plan_sha256":plan_sha256,"expected":expected,"observed":None,
            "serial_commands_sent":[],"servo_actuation":False,"checked_at_utc":datetime.now(timezone.utc).isoformat()}
    connection=None
    try:
        ports=[p for p in list_ports.comports() if p.device==port]
        if len(ports)!=1 or (ports[0].vid,ports[0].pid)!=(0x10C4,0xEA60):raise ValueError('Selected CP2102 is absent from fresh enumeration')
        connection=serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=.25)
        connection.port=port;connection.dtr=False;connection.rts=False
        with (output/'uart.jsonl').open('x') as stream:
            connection.open();journal=Journal(connection,stream)
            startup=time.monotonic()+2
            while time.monotonic()<startup:journal.read()
            journal.send('ID');report['serial_commands_sent']=['ID']
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                fresh=journal.read()
                for line in fresh:
                    if line.startswith('SPARKBENCH LED_OLED_RUNTIME '):report['observed']=line
                    if line==expected:report['status']='pass';break
                if report['status']=='pass':break
            if report['status']!='pass':report['error']='Expected idle plan identity and OLED ACK were not confirmed'
    except (OSError,ValueError,serial.SerialException):report['error']='UART identity unavailable; inspect connection and retained journal'
    finally:
        if connection is not None and connection.is_open:connection.close()
        save(output/'identity.json',report)
        save(output/'integrity.json',{'sha256':{p.name:digest(p) for p in output.iterdir() if p.is_file() and p.name!='integrity.json'}})
    return report


def install(artifact_path, port, previous_application, previous_sha256, output):
    from serial.tools import list_ports
    plan, artifact = load_artifact(artifact_path)
    previous_application, output = Path(previous_application).resolve(), Path(output).resolve()
    if digest(previous_application) != previous_sha256:
        raise ValueError("Previous application does not match its installation record")
    ports = [p for p in list_ports.comports() if p.device == port]
    if len(ports) != 1 or (ports[0].vid, ports[0].pid) != (0x10C4, 0xEA60):
        raise ValueError("Fresh CP2102 enumeration required")
    # Retain the known partition/boot layout; only the application is written.
    reference = ROOT/"runs/firmware/led-oled-installed-2026-10-30"
    build = Path(artifact_path)/"project/.pio/build/classic-led-oled-runtime"
    for name in ("bootloader.bin", "partitions.bin"):
        if digest(build/name) != digest(reference/name):
            raise ValueError("Runtime boot layout differs; application-only installer refuses it")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(previous_application, output/"previous-application.bin")
    shutil.copyfile(Path(artifact_path)/artifact["firmware"], output/"application.bin")
    for name in ("bootloader.bin", "partitions.bin", "boot_app0.bin"):
        shutil.copyfile(reference/name, output/name)
    report = {"schema_version":1, "status":"prepared", "port":port, "usb_hwid":ports[0].hwid,
              "artifact":str(Path(artifact_path).resolve()), "plan_sha256":artifact["plan_sha256"],
              "firmware_sha256":artifact["firmware_sha256"], "previous_firmware_sha256":previous_sha256,
              "application_offset":"0x10000", "boot_partition_nvs_written":False,
              "servo_actuation":False, "commands":[], "started_at_utc":datetime.now(timezone.utc).isoformat()}
    save(output/"installation.json",report)
    prefix = [sys.executable,"-m","esptool","--chip","esp32","--port",port,"--baud","115200"]
    def command(name, arguments):
        cmd = prefix + arguments
        report["commands"].append(cmd)
        save(output/"installation.json",report)
        with (output/(name+".log")).open("x") as log:
            result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        if result.returncode:
            raise ValueError(name+" failed; inspect retained log")
    writes_started=False
    try:
        command("01-verify-previous",["verify-flash","0x1000",str(output/"bootloader.bin"),
            "0x8000",str(output/"partitions.bin"),"0xe000",str(output/"boot_app0.bin"),
            "0x10000",str(output/"previous-application.bin")])
        report["previous_installed_bytes_verified"]=True
        if previous_sha256 == artifact["firmware_sha256"]:
            report.update(status="installed_hash_verified", uploaded=False, reused_verified_application=True)
        else:
            writes_started=True
            command("02-write-application",["write-flash","0x10000",str(output/"application.bin")])
            command("03-verify-installed",["verify-flash","0x1000",str(output/"bootloader.bin"),
                "0x8000",str(output/"partitions.bin"),"0xe000",str(output/"boot_app0.bin"),
                "0x10000",str(output/"application.bin")])
            report.update(status="installed_hash_verified", uploaded=True)
    except (OSError,ValueError,subprocess.TimeoutExpired,KeyboardInterrupt) as exc:
        report.update(status="incomplete",error=str(exc))
        if writes_started:
            try:
                command("04-restore-previous",["write-flash","0x10000",str(output/"previous-application.bin")])
                command("05-verify-restored",["verify-flash","0x1000",str(output/"bootloader.bin"),
                    "0x8000",str(output/"partitions.bin"),"0xe000",str(output/"boot_app0.bin"),
                    "0x10000",str(output/"previous-application.bin")])
                report["recovery"]="previous_application_restored_hash_verified"
            except (OSError,ValueError,subprocess.TimeoutExpired) as restore:
                report["recovery"]="incomplete: "+str(restore)
    finally:
        report["ended_at_utc"]=datetime.now(timezone.utc).isoformat()
        save(output/"installation.json",report)
        save(output/"integrity.json",{"sha256":{str(p.relative_to(output)):digest(p)
            for p in sorted(output.rglob('*')) if p.is_file() and p.name!="integrity.json"}})
    return report


def main():
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact",type=Path,required=True)
    parser.add_argument("--port",required=True)
    parser.add_argument("--previous-application",type=Path,required=True)
    parser.add_argument("--previous-sha256",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report=install(args.artifact,args.port,args.previous_application,args.previous_sha256,args.output)
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="installed_hash_verified" else 2


if __name__=="__main__": raise SystemExit(main())
