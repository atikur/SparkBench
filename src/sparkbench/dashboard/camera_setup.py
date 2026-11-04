"""Confirmed camera geometry, isolated from frozen LED thresholds and test evidence.

The execution service supplies a dedicated setup capture and qualifies a candidate
on a subsequent capture. This store never captures, talks to hardware, calls a
model, or derives calibration labels from a behavior test.
"""
import copy
import hashlib
import json
import math
import struct
from datetime import datetime, timezone
from pathlib import Path

from ..intent import save
from ..policy import check_policy
from ..vision import digest
from .planning import IDENTIFIER, SHA256


FILES = {"reference.jpg", "review.json", "geometry.json", "calibration.json", "policy.json"}


def image_dimensions(data):
    """Read bounded native-capture headers; the native reader later decodes pixels."""
    if not 32 <= len(data) <= 6_000_000:
        raise ValueError("Camera reference must be a bounded JPEG or PNG image")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
    elif data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"):
        width = height = 0
        offset = 2
        while offset + 4 <= len(data):
            if data[offset] != 255:
                break
            while offset < len(data) and data[offset] == 255:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            length = int.from_bytes(data[offset:offset + 2], "big")
            if length < 2 or offset + length > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF) and length >= 8:
                height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
                break
            offset += length
    else:
        raise ValueError("Camera reference must be a JPEG or PNG image")
    if not 1 <= width <= 1920 or not 1 <= height <= 1920:
        raise ValueError("Camera reference dimensions are unsupported")
    return width, height


def _point(value, width, height):
    return (isinstance(value, list) and len(value) == 2
            and all(type(v) is int for v in value)
            and 0 <= value[0] < width and 0 <= value[1] < height)


def validate_regions(body, geometry):
    """Keep operator identity confirmation distinct from SAM's region proposals."""
    required = {"image_sha256", "regions", "sources", "points", "oled_corners"}
    if not isinstance(body, dict) or set(body) != required:
        raise ValueError("Confirm the image, component regions, LED lenses and four OLED corners")
    if not isinstance(body["image_sha256"], str) or not SHA256.fullmatch(body["image_sha256"]):
        raise ValueError("Camera reference image hash required")
    width, height = geometry["image_width"], geometry["image_height"]
    regions, sources, points = body["regions"], body["sources"], body["points"]
    names = {"oled", "red", "green"}
    if not isinstance(regions, dict) or set(regions) != names:
        raise ValueError("Confirm all three component regions")
    if (not isinstance(sources, dict) or set(sources) != names
            or any(v not in ("manual", "sam-3.1") for v in sources.values())):
        raise ValueError("Each region needs its proposal source")
    for box in regions.values():
        if (not isinstance(box, list) or len(box) != 4
                or not all(type(v) is int for v in box)
                or not (0 <= box[0] < box[2] < width and 0 <= box[1] < box[3] < height)):
            raise ValueError("Component boxes must fit inside the reference image")
    boxes = list(regions.values())
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                raise ValueError("Component regions must not overlap")
    if not isinstance(points, dict) or set(points) != {"red", "green"}:
        raise ValueError("Confirm both external LED lenses")
    for name in ("red", "green"):
        point = points[name]
        if not _point(point, width, height):
            raise ValueError("LED lens points must be image pixels")
        radius = geometry["leds"][name]["radius"]
        if type(radius) not in (int, float) or not math.isfinite(radius) or radius <= 0:
            raise ValueError("Existing LED measurement radius is invalid")
        x, y = point
        x1, y1, x2, y2 = regions[name]
        if not (x1 <= x - radius and x + radius <= x2 and y1 <= y - radius and y + radius <= y2):
            raise ValueError("The existing LED measurement circle must fit inside its confirmed lens region")
    corners = body["oled_corners"]
    if not isinstance(corners, list) or len(corners) != 4 or not all(_point(p, width, height) for p in corners):
        raise ValueError("Choose OLED corners clockwise: top left, top right, bottom right, bottom left")
    if not all(6 < x < width - 7 and 6 < y < height - 7 for x, y in corners):
        raise ValueError("Leave room around every OLED edge for the fixed border check")
    x1, y1, x2, y2 = regions["oled"]
    if not all(x1 <= x <= x2 and y1 <= y <= y2 for x, y in corners):
        raise ValueError("OLED corners must be inside the confirmed screen region")
    cross = []
    for i in range(4):
        a, b, c = corners[i], corners[(i + 1) % 4], corners[(i + 2) % 4]
        if math.hypot(b[0] - a[0], b[1] - a[1]) <= 20:
            raise ValueError("Each OLED edge must span more than 20 image pixels")
        cross.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    tl, tr, br, bl = corners
    if (not all(v > 0 for v in cross)
            or not tl[0] < tr[0] or not bl[0] < br[0]
            or not tl[1] < bl[1] or not tr[1] < br[1]):
        raise ValueError("OLED corners must form a clockwise screen face in reading order")
    # Tiny or nearly collinear corners cannot produce a useful text crop.
    area2 = abs(sum(corners[i][0] * corners[(i + 1) % 4][1]
                    - corners[(i + 1) % 4][0] * corners[i][1] for i in range(4)))
    if area2 < 128:
        raise ValueError("The OLED screen is too small to establish a reference")


class CameraSetupStore:
    def __init__(self, root, planner):
        self.root = Path(root).resolve()
        self.directory = self.root / "runs/camera-setup"
        self.planner = planner

    def _safe(self, path):
        path = Path(path)
        if not path.is_absolute():
            path = self.root / path
        if not path.is_relative_to(self.root) or ".." in path.parts:
            raise ValueError("Camera reference path must stay inside this project")
        for part in (path, *path.parents):
            if part == self.root:
                break
            if part.is_symlink():
                raise ValueError("Camera reference symlinks are unsupported")
        return path

    def _folder(self, job_id):
        if not isinstance(job_id, str) or not IDENTIFIER.fullmatch(job_id):
            raise ValueError("Valid camera setup ID required")
        return self._safe(self.directory / job_id)

    def _proposal(self, proposal_id):
        if not isinstance(proposal_id, str) or not IDENTIFIER.fullmatch(proposal_id):
            raise ValueError("Valid proposal ID required")
        proposal = self.planner.get(proposal_id)
        if (proposal.get("status") != "ready" or not isinstance(proposal.get("plan_sha256"), str)
                or not SHA256.fullmatch(proposal["plan_sha256"])):
            raise ValueError("A complete unchanged proposal is required for camera setup")
        return proposal

    def _manifest(self, folder, files):
        save(folder / "integrity.json", {"sha256": {name: digest(self._safe(folder / name)) for name in sorted(files)}})

    def _validation(self, record, validation):
        if (not isinstance(validation, dict) or validation.get("status") != "view_ok"
                or validation.get("source") != "fresh_camera_only_validation"
                or validation.get("device_id") != record["device_id"]
                or type(validation.get("frames_checked")) is not int or validation["frames_checked"] != 3):
            raise ValueError("A fresh successful camera-readiness check from the same camera is required")
        location = validation.get("validation_directory")
        if not isinstance(location, str) or not Path(location).is_absolute():
            raise ValueError("Saved camera qualification evidence is required")
        directory = self._safe(location)
        source = self._safe(record["source_path"])
        if directory.is_relative_to(source.parent.parent) or source.is_relative_to(directory):
            raise ValueError("Camera qualification must use a separate fresh capture")
        manifest_path = self._safe(directory / "integrity.json")
        expected = validation.get("validation_integrity_sha256")
        if not isinstance(expected, str) or not SHA256.fullmatch(expected) or digest(manifest_path) != expected:
            raise ValueError("Saved camera qualification manifest changed")
        entries = json.loads(manifest_path.read_text()).get("sha256")
        if not isinstance(entries, dict) or not entries:
            raise ValueError("Camera qualification integrity record is incomplete")
        for name, sha in entries.items():
            if (not isinstance(name, str) or not name or Path(name).is_absolute() or ".." in Path(name).parts
                    or not isinstance(sha, str) or not SHA256.fullmatch(sha)):
                raise ValueError("Camera qualification contains an invalid evidence path")
            file = self._safe(directory / name)
            if not file.is_file() or digest(file) != sha:
                raise ValueError("Saved camera qualification evidence changed")
        frames = validation.get("frames_sha256")
        if not isinstance(frames, dict) or len(frames) != 3:
            raise ValueError("Camera qualification requires three retained frame readings")
        for name, sha in frames.items():
            if (not isinstance(name, str) or Path(name).name != name
                    or not name.startswith("frame-") or not name.endswith(".jpg")
                    or entries.get("camera/" + name) != sha):
                raise ValueError("Camera qualification frame binding differs")
        if not {"camera/capture.json", "camera/frames.jsonl"} <= set(entries):
            raise ValueError("Camera qualification capture provenance is missing")

    def _checked(self, job_id, proposal_id, activated=False):
        folder = self._folder(job_id)
        manifest = json.loads(self._safe(folder / "integrity.json").read_text())
        entries = manifest.get("sha256")
        required = FILES | ({"qualification.json"} if activated else set())
        if not isinstance(entries, dict) or set(entries) not in (required, FILES | {"qualification.json"}):
            raise ValueError("Camera reference integrity record is incomplete")
        for name, expected in entries.items():
            file = self._safe(folder / name)
            if not file.is_file() or digest(file) != expected:
                raise ValueError("Saved camera reference changed: " + name)
        record = json.loads((folder / "review.json").read_text())
        proposal = self._proposal(proposal_id)
        if (record.get("setup_id") != job_id or record.get("proposal_id") != proposal_id
                or record.get("plan_sha256") != proposal["plan_sha256"]):
            raise ValueError("Camera reference belongs to a different proposal")
        policy, calibration = check_policy(folder / "policy.json")
        if Path(calibration).resolve() != (folder / "calibration.json").resolve():
            raise ValueError("Camera policy must bind its saved calibration")
        calibration_data = json.loads(Path(calibration).read_text())
        if (calibration_data.get("geometry") != json.loads((folder / "geometry.json").read_text())
                or calibration_data.get("reference_image_sha256") != entries["reference.jpg"]
                or calibration_data["geometry"].get("reference_frame") != str(folder / "reference.jpg")):
            raise ValueError("Camera calibration does not bind its saved geometry and image")
        if activated:
            qualification = json.loads((folder / "qualification.json").read_text())
            if (qualification.get("setup_id") != job_id or qualification.get("proposal_id") != proposal_id
                    or qualification.get("validation", {}).get("status") != "view_ok"):
                raise ValueError("Camera reference lacks a completed readiness check")
            self._validation(record, qualification["validation"])
        return folder, record

    def policy_path(self, proposal_id, default_path):
        if proposal_id is None:
            return Path(default_path)
        if not isinstance(proposal_id, str) or not IDENTIFIER.fullmatch(proposal_id):
            raise ValueError("Valid proposal ID required")
        pointer = self._safe(self.directory / "proposals" / (proposal_id + ".json"))
        if not pointer.exists():
            return Path(default_path)
        active = json.loads(pointer.read_text())
        if active.get("proposal_id") != proposal_id:
            raise ValueError("Saved camera reference proposal differs")
        folder, record = self._checked(active.get("setup_id"), proposal_id, activated=True)
        if (active.get("manifest_sha256") != digest(folder / "integrity.json")
                or active.get("policy_sha256") != digest(folder / "policy.json")
                or active.get("plan_sha256") != record["plan_sha256"]):
            raise ValueError("Saved camera reference checksum differs")
        return folder / "policy.json"

    def prepare(self, job_id, proposal_id, device_id, source_path, body, base_policy_path, *, registration=None):
        proposal = self._proposal(proposal_id)
        folder = self._folder(job_id)
        source_path = self._safe(source_path)
        source = source_path.read_bytes()
        width, height = image_dimensions(source)
        policy, calibration_path = check_policy(base_policy_path)
        calibration = json.loads(Path(calibration_path).read_text())
        geometry = copy.deepcopy(calibration["geometry"])
        if device_id != calibration.get("camera_id"):
            raise ValueError("This setup requires the camera used for the existing LED calibration")
        if (width, height) != (geometry["image_width"], geometry["image_height"]):
            raise ValueError("Keep the calibrated camera resolution before setting up a new view")
        validate_regions(body, geometry)
        sha = hashlib.sha256(source).hexdigest()
        if body["image_sha256"] != sha:
            raise ValueError("The confirmed image differs from the saved setup capture")
        # A new setup ID is required for every attempt; failed candidates stay intact.
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "reference.jpg").write_bytes(source)
        for channel in ("red", "green"):
            geometry["leds"][channel].update(center_x=body["points"][channel][0], center_y=body["points"][channel][1])
        geometry["oled_corners"] = copy.deepcopy(body["oled_corners"])
        geometry["reference_frame"] = str(folder / "reference.jpg")
        method = "registered_and_sam_checked" if registration is not None else "operator_confirmed"
        if registration is not None and registration.get("method") == "current_frame_color_and_border":
            method = "located_and_sam_checked"
        geometry["note"] = method + " setup geometry; inherited thresholds, crop and rejection limits are unchanged."
        save(folder / "geometry.json", geometry)
        record = {"schema_version": 1, "setup_id": job_id, "proposal_id": proposal_id,
                  "plan_sha256": proposal["plan_sha256"], "device_id": device_id,
                  "confirmed_at_utc": datetime.now(timezone.utc).isoformat(),
                  "source_path": str(source_path), "image_width": width, "image_height": height,
                  **copy.deepcopy(body), "parent_policy_sha256": digest(base_policy_path),
                  "parent_calibration_sha256": digest(calibration_path),
                  "scope": "Confirmed geometry only; inherited LED thresholds; behavior verification not performed"}
        record.update(selection_method=method, registration=registration)
        save(folder / "review.json", record)
        # Preserve measurement definitions, but do not mislabel old frames as this
        # setup's calibration data. Their provenance remains explicitly inherited.
        prior_source = {key: copy.deepcopy(value) for key, value in calibration.items()
                        if key.startswith("source_")}
        calibration = {key: copy.deepcopy(value) for key, value in calibration.items()
                       if not key.startswith("source_")}
        calibration.update(source_kind=method + "_geometry_with_inherited_thresholds",
                           source_run=str(source_path.parent.parent),
                           geometry=geometry, geometry_sha256=digest(folder / "geometry.json"),
                           reference_image_sha256=sha, inherited_thresholds={
                               "calibration_sha256": digest(calibration_path), "source": prior_source},
                           setup_review_sha256=digest(folder / "review.json"))
        save(folder / "calibration.json", calibration)
        policy = copy.deepcopy(policy)
        policy.update(calibration=str(folder / "calibration.json"),
                      calibration_sha256=digest(folder / "calibration.json"),
                      scope="Confirmed setup geometry with inherited frozen reader and LED thresholds; fresh behavior test required")
        save(folder / "policy.json", policy)
        self._manifest(folder, FILES)
        return {"policy_path": folder / "policy.json", "calibration_path": folder / "calibration.json", "record": record}

    def activate(self, job_id, proposal_id, validation):
        if not isinstance(validation, dict) or validation.get("status") != "view_ok":
            raise ValueError("A fresh successful camera-readiness check is required")
        folder, record = self._checked(job_id, proposal_id)
        self._validation(record, validation)
        qualification = {"setup_id": job_id, "proposal_id": proposal_id,
                         "scope": "Camera readiness only; not behavior verification or new LED on/off calibration",
                         "validation": copy.deepcopy(validation)}
        path = self._safe(folder / "qualification.json")
        if path.exists() and json.loads(path.read_text()) != qualification:
            raise ValueError("Camera qualification is already frozen")
        save(path, qualification)
        self._manifest(folder, FILES | {"qualification.json"})
        pointer = self._safe(self.directory / "proposals" / (proposal_id + ".json"))
        pointer.parent.mkdir(parents=True, exist_ok=True)
        active = {"schema_version": 1, "setup_id": job_id, "proposal_id": proposal_id,
                  "plan_sha256": record["plan_sha256"], "manifest_sha256": digest(folder / "integrity.json"),
                  "policy_sha256": digest(folder / "policy.json"),
                  "activated_at_utc": datetime.now(timezone.utc).isoformat()}
        temporary = self._safe(pointer.with_suffix(".tmp"))
        save(temporary, active)
        temporary.replace(pointer)
        return active
