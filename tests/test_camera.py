"""Host-side acquisition safeguards. No test opens a physical camera."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sparkbench.camera import capture_frames, list_cameras, run_helper


class CameraAcquisitionTests(unittest.TestCase):
    def test_capture_requires_explicit_selection_before_invoking_backend(self):
        with patch("sparkbench.camera.run_helper") as backend:
            for identifier in (None, "", " "):
                with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                    capture_frames(identifier)
            backend.assert_not_called()

    def test_capture_rejects_unbounded_or_nonfinite_settings(self):
        with patch("sparkbench.camera.run_helper") as backend:
            for seconds in (0, 61, float("nan"), float("inf"), True):
                with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                    capture_frames("selected-iphone", seconds=seconds)
            for fps in (0, 11, float("nan"), True):
                with self.subTest(fps=fps), self.assertRaises(ValueError):
                    capture_frames("selected-iphone", fps=fps)
            backend.assert_not_called()

    def test_existing_evidence_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "capture"
            evidence.mkdir()
            frame = evidence / "frame-000001.jpg"
            frame.write_bytes(b"existing evidence")
            with patch("sparkbench.camera.run_helper") as backend:
                with self.assertRaises(ValueError):
                    capture_frames("selected-iphone", output=evidence)
                backend.assert_not_called()
            self.assertEqual(frame.read_bytes(), b"existing evidence")

    def test_list_is_not_a_capture_or_permission_request(self):
        with patch("sparkbench.camera.run_helper", return_value={"devices": []}) as backend:
            self.assertEqual(list_cameras(), {"devices": []})
            backend.assert_called_once_with(["list"])

    def test_selected_device_id_is_forwarded_without_shell_interpolation(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "new-capture"
            report = {"status": "captured", "frame_count": 10}
            with patch("sparkbench.camera.run_helper", return_value=report) as backend:
                self.assertEqual(capture_frames("iphone with spaces", 2, 5, output), report)
                backend.assert_called_once_with(
                    ["capture", "iphone with spaces", str(output.resolve()), "2", "5"],
                    timeout=102)
            self.assertFalse(output.exists())  # The backend, not the wrapper, creates evidence.

    def test_native_failure_cannot_be_reported_as_success(self):
        result = subprocess.CompletedProcess([], 2,
            json.dumps({"status": "error", "error": "Selected camera is not available"}), "")
        with patch("sparkbench.camera.build_helper", return_value=Path("/fake/helper")), \
                patch("sparkbench.camera.subprocess.run", return_value=result) as backend:
            with self.assertRaisesRegex(ValueError, "Selected camera is not available"):
                run_helper(["capture", "missing-camera"])
            self.assertEqual(backend.call_count, 1)  # No fallback to another camera.

    def test_malformed_native_output_is_an_error(self):
        result = subprocess.CompletedProcess([], 0, "not-json", "diagnostic")
        with patch("sparkbench.camera.build_helper", return_value=Path("/fake/helper")), \
                patch("sparkbench.camera.subprocess.run", return_value=result):
            with self.assertRaisesRegex(ValueError, "did not return JSON"):
                run_helper(["list"])


if __name__ == "__main__":
    unittest.main()
