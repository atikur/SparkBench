"""Simulated browser checks; no real camera, model, firmware or HTTP operations."""
import shutil
import subprocess
import unittest
from pathlib import Path


class CameraSetupBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for browser-script checks')
    def test_guided_confirmation_and_agent_flow(self):
        script = Path(__file__).parent / 'frontend/camera_setup_test.cjs'
        result = subprocess.run([shutil.which('node'), str(script)], capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('simulated', result.stdout)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for browser-script checks')
    def test_agent_chooses_setup_or_quick_check(self):
        script = Path(__file__).parent / 'frontend/autopilot_camera_test.cjs'
        result = subprocess.run([shutil.which('node'), str(script)], capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('simulated', result.stdout)


if __name__ == '__main__':
    unittest.main()
