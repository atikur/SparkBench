"""Prepared servo firmware simulation only; never opens serial or flashes."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from sparkbench.camera import ROOT


class GuardedServoTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"),"Native C++ compiler unavailable")
    def test_actual_adapter_boot_stop_lease_deadline_bounds_faults_and_rollover(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/"servo-guarded-test"
            command=["c++","-std=c++11","-I"+str(ROOT/"tests/native_servo"),
                     "-I"+str(ROOT/"firmware/servo_guarded/src"),
                     str(ROOT/"tests/native_servo/servo_guarded_test.cpp"),"-o",str(binary)]
            build=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)


if __name__=="__main__":unittest.main()
