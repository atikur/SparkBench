"""Full acquisition lifecycle against simulated devices only. No physical proof."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sparkbench import fullrig_capture as runner
from sparkbench.fullrig import calibration_plan


class Clock:
    def __init__(self): self.now = 100.
    def __call__(self): return self.now


class Wire:
    def __init__(self, clock, plan, fault):
        self.clock, self.plan, self.fault = clock, plan, fault
        self.queue, self.written = [], []; self.start = None; self.step = 0; self.is_open = False
    @property
    def in_waiting(self): return 4096
    def open(self): self.is_open = True
    def close(self): self.is_open = False
    def write(self, data):
        cmd = data.decode().strip(); self.written.append(cmd)
        if cmd == "ID":
            identity = runner.identity(self.plan)
            if self.fault == "identity": identity = identity.replace("AVAILABLE:1", "AVAILABLE:0")
            self.queue += [identity, "FULL_ALIVE UPTIME_MS:2000 MODE:IDLE PWM:OFF", "FULL_ALIVE UPTIME_MS:3000 MODE:IDLE PWM:OFF"]
        if cmd == "CALIBRATE": self.start = self.clock()
        if cmd == "STOP":
            self.start = None
            if self.fault == "stop_write": raise OSError("fake disconnect")
            if self.fault != "stop_ack": self.queue += ["FULL_STOPPED REASON:STOP PWM:OFF UPTIME_MS:20000"]
        return len(data)
    def read(self, count):
        self.clock.now += .05
        if self.start is not None:
            elapsed = self.clock()-self.start
            if self.fault == "reset" and elapsed > .3:
                self.queue.append("SPARKBENCH FULL_RUNTIME BOOT PWM:OFF"); self.start = None
            elif self.fault == "driver" and elapsed > .3:
                self.queue.append("FULL_STOPPED REASON:WRITE_ERROR PWM:FAULT UPTIME_MS:3400"); self.start = None
            elif self.fault != "silent":
                while self.step < 4 and elapsed >= 3*self.step:
                    pulse = self.plan["steps"][self.step]["pulse_us"]
                    if self.fault == "pulse": pulse += 1
                    self.queue.append(f"FULL_STEP:{self.step+1} PULSE_US:{pulse} UPTIME_MS:{3000+3000*self.step}"); self.step += 1
                if elapsed >= 12:
                    self.queue.append("FULL_STOPPED REASON:COMPLETE PWM:OFF UPTIME_MS:15000"); self.start = None
        return (self.queue.pop(0)+"\n").encode() if self.queue else b""


class Camera:
    def __init__(self, clock, directory, wire, fault):
        self.clock, self.directory, self.wire, self.fault = clock, directory, wire, fault
        self.started = clock(); self.returncode = None; directory.mkdir()
        for i in range(1,4): (directory/f"frame-{i:06d}.jpg").write_bytes(b"fake image, no physical evidence")
    def poll(self):
        if self.fault != "hang_camera" and self.clock()-self.started >= 18:
            self.returncode = 0
            (self.directory/"capture.json").write_text(json.dumps({"status": "captured", "frame_count": 3}))
            return 0
        if self.fault == "camera" and self.wire.start is not None: self.returncode = 2
        now = self.clock()-(2 if self.fault == "stale" else 0)
        (self.directory/"capture.json").write_text(json.dumps({"source": "live_camera", "status": "recording", "camera": {"id": "iphone"}}))
        rows = [{"frame": i+1, "file": f"frame-{i+1:06d}.jpg", "host_uptime_seconds": now-.4+i*.2, "sample_pts_seconds": now-.45+i*.2} for i in range(3)]
        (self.directory/"frames.jsonl").write_text(''.join(json.dumps(r)+'\n' for r in rows))
        return self.returncode
    def wait(self, timeout): return self.returncode
    def terminate(self): self.returncode = -15
    def kill(self): self.returncode = -9


class AcquisitionLifecycleTests(unittest.TestCase):
    def exercise(self, fault=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); clock = Clock(); plan = calibration_plan([1500,1300,1700,1500])
            artifact = {"firmware_sha256": "a"*64}; wire = Wire(clock, plan, fault); cameras = []
            helper = root/"helper"; helper.write_bytes(b"fake helper")
            def launch(args, **kwargs):
                camera = Camera(clock, Path(args[3]), wire, fault); cameras.append(camera); return camera
            port = SimpleNamespace(device="/fake/cp2102", vid=0x10c4, pid=0xea60, hwid="SYNTHETIC")
            with patch("serial.Serial", return_value=wire), patch("serial.tools.list_ports.comports", return_value=[port]), \
                    patch.object(runner, "load_artifact", return_value=(plan, artifact)), \
                    patch.object(runner, "list_cameras", return_value={"devices": [{"id": "iphone", "connected": True}]}), \
                    patch.object(runner, "build_helper", return_value=helper), patch.object(runner.subprocess, "Popen", side_effect=launch), \
                    patch.object(runner.time, "monotonic", side_effect=clock):
                report = runner.acquire(port.device, "iphone", root/"artifact", root/"run", execute_sequence=True)
            self.assertFalse(wire.is_open); self.assertTrue(all(c.returncode is not None for c in cameras))
            self.assertTrue(set(wire.written) <= {"ID", "CALIBRATE", "PING", "STOP"})
            self.assertFalse(report["firmware_uploaded"]); self.assertIsNone(report["angle_deg"])
            return report, wire.written

    def test_complete_capture_is_uart_only_and_one_start(self):
        report, commands = self.exercise()
        self.assertEqual(report["status"], "completed"); self.assertEqual(commands.count("CALIBRATE"), 1)
        self.assertEqual(commands[-1], "STOP"); self.assertTrue(report["stop_acknowledged_uart_only"])
        self.assertEqual(report["automatic_physical_verification"], "not performed")

    def test_wrong_identity_or_stale_camera_never_starts(self):
        for fault in ("identity", "stale"):
            report, commands = self.exercise(fault)
            self.assertEqual(report["status"], "incomplete"); self.assertNotIn("CALIBRATE", commands)
            if fault == "identity": self.assertEqual(commands, ["ID"])

    def test_failure_cleanup_and_deadlines(self):
        for fault in ("camera", "reset", "driver", "pulse", "silent", "stop_write", "stop_ack", "hang_camera"):
            with self.subTest(fault=fault):
                report, commands = self.exercise(fault)
                self.assertEqual(report["status"], "incomplete"); self.assertEqual(commands.count("CALIBRATE"), 1)
                self.assertEqual(commands[-1], "STOP")


if __name__ == "__main__": unittest.main()
