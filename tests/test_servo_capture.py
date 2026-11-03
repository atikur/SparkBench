"""Fixed runner tests use simulated serial/camera/clock only; no hardware I/O."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sparkbench import servo_capture as runner
from sparkbench.vision import digest


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now


class Wire:
    def __init__(self, clock, fault=None):
        self.clock, self.fault, self.queue = clock, fault, []
        self.start = None; self.step = 0; self.is_open = False; self.written = []
    @property
    def in_waiting(self): return 4096
    def open(self): self.is_open = True
    def close(self): self.is_open = False
    def write(self, data):
        command = data.decode().strip(); self.written.append(command)
        if command == "ID":
            identity = runner.IDENTITY if self.fault != "identity" else runner.IDENTITY.replace("AVAILABLE:1", "AVAILABLE:0")
            self.queue += [identity, "SERVO_GUARD_ALIVE UPTIME_MS:2000 MODE:IDLE PWM:OFF", "SERVO_GUARD_ALIVE UPTIME_MS:3000 MODE:IDLE PWM:OFF"]
        if command == "SERVO_TEST": self.start = self.clock(); self.step = 0
        if command == "STOP":
            if self.fault == "stop_write": raise OSError("disconnected at STOP")
            self.start = None
            if self.fault != "stop_ack": self.queue.append("SERVO_GUARD_STOPPED REASON:STOP PWM:OFF UPTIME_MS:12000")
        return len(data)
    def read(self, count):
        self.clock.now += .05
        if self.start is not None:
            elapsed = self.clock() - self.start
            if self.fault == "reset" and elapsed > .3:
                self.queue.append("SPARKBENCH SERVO_GUARDED BOOT PWM:OFF"); self.start = None
            elif self.fault == "driver" and elapsed > .3:
                self.queue.append("SERVO_GUARD_STOPPED REASON:PWM_WRITE_ERROR PWM:FAULT UPTIME_MS:3400"); self.start = None
            elif self.fault != "silent":
                while self.step < 4 and elapsed >= 2 * self.step:
                    pulse = runner.PULSES[self.step]
                    if self.fault == "pulse": pulse = 1800
                    self.queue.append("SERVO_GUARD_STEP:%d PULSE_US:%d UPTIME_MS:%d" % (self.step+1,pulse,3000+2000*self.step)); self.step += 1
                if elapsed >= 8:
                    self.queue.append("SERVO_GUARD_STOPPED REASON:COMPLETE PWM:OFF UPTIME_MS:11000"); self.start = None
        return ((self.queue.pop(0)+"\n").encode() if self.queue else b"")


class Camera:
    def __init__(self, clock, directory, wire, fault=None):
        self.clock, self.directory, self.wire, self.fault = clock, directory, wire, fault
        self.started_at = clock()
        self.returncode = None; directory.mkdir()
        for i in range(1,4): (directory / ("frame-%06d.jpg" % i)).write_bytes(b"synthetic test fixture")
    def poll(self):
        if self.fault != "hang_camera" and self.clock() - self.started_at >= 12:
            self.wait(0)
            return self.returncode
        if self.fault == "camera" and self.wire.start is not None:
            self.returncode = 2
        now = self.clock() - (2 if self.fault == "stale" else 0)
        (self.directory / "capture.json").write_text(json.dumps({"source":"live_camera", "status":"recording", "camera":{"id":"iphone"}}))
        rows = [{"frame":i+1,"file":"frame-%06d.jpg"%(i+1),"host_uptime_seconds":now-.4+.2*i,"sample_pts_seconds":now-.45+.2*i} for i in range(3)]
        (self.directory / "frames.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
        return self.returncode
    def wait(self, timeout):
        if self.returncode is None:
            self.returncode = 0
            (self.directory / "capture.json").write_text(json.dumps({"status":"captured"}))
        return self.returncode
    def terminate(self): self.returncode = -15
    def kill(self): self.returncode = -9


class ServoCaptureTests(unittest.TestCase):
    def exercise(self, fault=None):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder); clock = Clock(); wire = Wire(clock,fault); cameras = []
            ref = p / "reference.jpg"; ref.write_bytes(b"synthetic fixture, not physical evidence")
            preview = p / "preview.json"
            preview.write_text(json.dumps({"camera_id":"iphone","reference_frame":str(ref),"reference_sha256":digest(ref)}))
            config = p / "config.json"
            config.write_text(json.dumps({"mode":"unverified_passive_tracking","preview_config":str(preview),"preview_config_sha256":digest(preview)}))
            helper = p / "helper"; helper.write_bytes(b"fake")
            def launch(args, **kwargs):
                cam = Camera(clock,Path(args[3]),wire,fault); cameras.append(cam); return cam
            port = SimpleNamespace(device="/fake/cp2102",vid=0x10c4,pid=0xea60,hwid="FAKE")
            with patch("serial.Serial", return_value=wire), patch("serial.tools.list_ports.comports",return_value=[port]), patch.object(runner,"list_cameras",return_value={"devices":[{"id":"iphone","connected":True}]}), patch.object(runner,"build_helper",return_value=helper), patch.object(runner.subprocess,"Popen",side_effect=launch), patch.object(runner.time,"monotonic",side_effect=clock):
                report = runner.acquire(port.device,"iphone",config,p/"run",execute_fixed_sequence=True)
            self.assertFalse(wire.is_open)
            self.assertTrue(all(c.returncode is not None for c in cameras))
            self.assertTrue(set(wire.written) <= {"ID","STOP","PING","SERVO_TEST"})
            self.assertIsNone(report["angle_deg"])
            self.assertFalse(report["eligible_for_verifier"])
            self.assertFalse(report["actual_servo_motion_verified"])
            self.assertFalse(report["firmware_uploaded"])
            return report,wire.written

    def test_default_opt_in_refuses_before_io(self):
        with patch.object(runner,"load") as load, patch.object(runner,"list_cameras") as camera:
            with self.assertRaises(ValueError): runner.acquire("p","c","config","output")
            load.assert_not_called(); camera.assert_not_called()

    def test_complete_fixed_sequence_is_uart_only_and_cleanup_stops(self):
        r,commands = self.exercise()
        self.assertEqual(r["status"],"captured_uart_sequence_complete_unverified")
        self.assertEqual([s["pulse_us"] for s in r["uart_sequence"]["steps"]],runner.PULSES)
        self.assertEqual(commands.count("SERVO_TEST"),1)
        self.assertGreater(commands.count("PING"),10)
        self.assertEqual(commands[-1],"STOP")
        self.assertTrue(r["stop_acknowledged_uart_only"])

    def test_wrong_or_consumed_identity_never_starts_or_sends_control(self):
        r,commands = self.exercise("identity")
        self.assertEqual(commands,["ID"])
        self.assertEqual(r["status"],"incomplete")
        self.assertFalse(r["servo_actuation_requested"])

    def test_stale_camera_never_starts(self):
        r,commands = self.exercise("stale")
        self.assertNotIn("SERVO_TEST",commands)
        self.assertEqual(commands[-1],"STOP")

    def test_camera_loss_reset_driver_wrong_pulse_and_deadline_stop(self):
        for fault in ("camera","reset","driver","pulse","silent"):
            with self.subTest(fault=fault):
                r,commands = self.exercise(fault)
                self.assertEqual(r["status"],"incomplete")
                self.assertEqual(commands.count("SERVO_TEST"),1)
                self.assertEqual(commands[-1],"STOP")
                self.assertTrue(r["servo_actuation_requested"])

    def test_stop_write_failure_or_missing_ack_cannot_pass(self):
        for fault in ("stop_write","stop_ack"):
            with self.subTest(fault=fault):
                r,commands = self.exercise(fault)
                self.assertEqual(r["status"],"incomplete")
                self.assertEqual(commands[-1],"STOP")

    def test_camera_hang_after_sequence_is_bounded_and_closed(self):
        r,commands = self.exercise("hang_camera")
        self.assertEqual(r["status"],"incomplete")
        self.assertIn("deadline",r["camera_cleanup_error"])
        self.assertEqual(commands[-1],"STOP")

    def test_camera_gate_rejects_wrong_id_stale_future_alignment_and_missing_image(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            camera=SimpleNamespace(poll=lambda:None)
            meta={"source":"live_camera","status":"recording","camera":{"id":"iphone"}}
            rows=[{"frame":i+1,"file":"frame-%06d.jpg"%(i+1),"host_uptime_seconds":99.4+.2*i,"sample_pts_seconds":99.3+.2*i} for i in range(3)]
            for row in rows:(p/row["file"]).write_bytes(b"fixture")
            def write():
                (p/"capture.json").write_text(json.dumps(meta))
                (p/"frames.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
            write();self.assertTrue(runner.camera_fresh(camera,p,"iphone",100))
            self.assertFalse(runner.camera_fresh(camera,p,"other",100))
            self.assertFalse(runner.camera_fresh(camera,p,"iphone",102))
            self.assertFalse(runner.camera_fresh(camera,p,"iphone",99))
            rows[-1]["sample_pts_seconds"]=float("nan");write()
            self.assertFalse(runner.camera_fresh(camera,p,"iphone",100))
            rows[-1]["sample_pts_seconds"]=99.7;write();(p/rows[0]["file"]).unlink()
            self.assertFalse(runner.camera_fresh(camera,p,"iphone",100))

    def test_allowlist_once_only_partial_write_and_buffer_bounds(self):
        clock=Clock(); wire=Wire(clock); journal=runner.GuardJournal(wire,io.StringIO(),clock)
        for command in ("RUN","CENTER","PULSE 1500","PING","STOP","SERVO_TEST"):
            with self.assertRaises(ValueError): journal.send(command)
        journal.verified=journal.camera_ready=True
        with patch.object(wire,"write",return_value=1):
            with self.assertRaises(ValueError): journal.send("SERVO_TEST")
        self.assertTrue(journal.started)
        with self.assertRaises(ValueError): journal.send("SERVO_TEST")
        with patch.object(wire,"read",return_value=b"x"*8193):
            with self.assertRaises(ValueError): journal.read()

    def test_duplicate_heartbeat_does_not_verify_idle(self):
        clock=Clock(); wire=Wire(clock); journal=runner.GuardJournal(wire,io.StringIO(),clock)
        with patch.object(wire,"write",return_value=3):
            wire.queue=[runner.IDENTITY]+["SERVO_GUARD_ALIVE UPTIME_MS:1000 MODE:IDLE PWM:OFF"]*3
            with self.assertRaises(ValueError): runner.verify_idle(journal,clock)
        self.assertFalse(journal.verified)


if __name__ == "__main__": unittest.main()
