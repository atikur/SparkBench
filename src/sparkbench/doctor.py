"""Read-only readiness checks. Never opens a serial port or camera."""

import glob
import importlib.util
import json
import os
import platform
import shutil
import sys
from pathlib import Path


def readiness():
    from .meta import configuration
    try:
        meta_configured = bool(configuration().api_key)
    except (OSError, ValueError):
        meta_configured = False
    ports = sorted(set(glob.glob("/dev/cu.*") + glob.glob("/dev/ttyUSB*")
                       + glob.glob("/dev/ttyACM*")))
    candidates = [port for port in ports
                  if "Bluetooth" not in port and "debug-console" not in port]
    project_root = Path(__file__).resolve().parents[2]
    local_candidates = [Path(sys.executable).parent / "pio",
                        project_root / ".venv" / "bin" / "pio"]
    pio = next((str(path) for path in local_candidates if path.is_file()),
               shutil.which("pio"))
    board_path = project_root / "hardware" / "board.json"
    board = json.loads(board_path.read_text()) if board_path.is_file() else None
    return {
        "python": platform.python_version(),
        "platformio": pio,
        "serial_port_candidates": candidates,
        "board": board,
        "pyserial_installed": importlib.util.find_spec("serial") is not None,
        "opencv_installed": importlib.util.find_spec("cv2") is not None,
        "native_camera_backend": {
            "platform_supported": platform.system() == "Darwin",
            "compiler_available": shutil.which("xcrun") is not None,
            "camera_access": "not queried; run camera list",
            "opencv_required": False,
        },
        "meta_api_key_configured": meta_configured,
        "meta_api_access": "not queried by doctor; see runs/meta for recorded API checks",
        "physical_rig_verification": "not checked by doctor; see hardware records",
    }
