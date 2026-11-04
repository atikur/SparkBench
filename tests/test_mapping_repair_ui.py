"""Browser orchestration contract checks, with no real HTTP or hardware."""
import shutil
import subprocess
import unittest
from pathlib import Path


class MappingRepairBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required for browser-script checks")
    def test_approval_gate_and_single_attempt(self):
        script = Path(__file__).parent / "frontend/mapping_repair_test.cjs"
        result = subprocess.run([shutil.which("node"), str(script)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("10 simulated scenarios passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
