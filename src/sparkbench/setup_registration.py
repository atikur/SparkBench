"""Propose a camera refresh by transferring the commissioned bench landmarks."""
import hashlib
import json
import math
import platform
import shutil
import subprocess
from pathlib import Path

from .camera import ROOT
from .vision import digest

CHANNELS = ("red", "green")


def register_setup(source, calibration, *, screen=None):
    geometry = calibration["geometry"]
    reference = (ROOT / geometry["reference_frame"]).resolve()
    if digest(reference) != calibration["reference_image_sha256"]:
        raise ValueError("The commissioned reference image changed")
    tool = ROOT / "tools/macos_vision/register_setup.swift"
    compiler = shutil.which("xcrun")
    if platform.system() != "Darwin" or not compiler or not tool.is_file():
        raise ValueError("Automatic alignment needs the macOS vision helper")
    fingerprint = hashlib.sha256(tool.read_bytes() + platform.machine().encode()
                                 + platform.mac_ver()[0].encode()).hexdigest()[:20]
    build = ROOT / ".cache/setup-registration"
    build.mkdir(parents=True, exist_ok=True)
    binary = build / ("register-" + fingerprint)
    if not binary.is_file():
        result = subprocess.run([compiler, "swiftc", "-swift-version", "5", "-O",
            "-module-cache-path", str(build / "modules"), str(tool), "-o", str(binary)],
            capture_output=True, timeout=45)
        if result.returncode:
            raise ValueError("The macOS alignment helper could not build")
    leds = [geometry["leds"][name] for name in CHANNELS]
    request = {"reference": str(reference), "current": str(source),
               "landmarks": geometry["oled_corners"] + [[v["center_x"], v["center_y"]] for v in leds],
               "radii": [v["radius"] for v in leds]}
    if screen is not None:
        request["screen"] = screen
    result = subprocess.run([str(binary)], input=json.dumps(request), capture_output=True,
                            text=True, timeout=15)
    if result.returncode:
        if screen is not None:
            raise ValueError("The current frame does not clearly isolate both LED lenses and the lit OLED border")
        raise ValueError("The camera could not align both LED neighborhoods with the saved bench")
    data = json.loads(result.stdout)
    if screen is not None:
        return {**data, "method": "current_frame_color_and_border"}
    if (len(data["landmarks"]) != 6 or len(data["lens_similarity"]) != 2
            or any(not math.isfinite(s) or s < .85 for s in data["lens_similarity"])):
        raise ValueError("The LED neighborhoods do not match the commissioned view closely enough")
    return {**data, "method": "macos_vision_homography", "reference_sha256": digest(reference)}


def check_regions(regions, corners, points, radii):
    """Require SAM to independently bound the registered components."""
    for name, point in points.items():
        box = regions.get(name)
        radius = radii[name]
        if not box:
            raise ValueError("SAM could not isolate both LED lenses")
        x1, y1, x2, y2 = box
        w, h = x2 - x1, y2 - y1
        # SAM may include the LED leads. The registered neighborhood supplies
        # the lens center; the box must support it without covering the bench.
        if (max(w, h) > radius * 8
                or abs(point[0] - (x1 + x2) / 2) > .32 * w
                or abs(point[1] - (y1 + y2) / 2) > .32 * h):
            raise ValueError("SAM and the saved bench disagree on an LED lens")
    if "oled" not in regions:
        raise ValueError("SAM did not isolate the OLED")
    x1, y1, x2, y2 = regions["oled"]
    width = max(p[0] for p in corners) - min(p[0] for p in corners)
    height = max(p[1] for p in corners) - min(p[1] for p in corners)
    if width * height < .55 * (x2 - x1) * (y2 - y1):
        raise ValueError("SAM and the saved bench disagree on the screen extent")
