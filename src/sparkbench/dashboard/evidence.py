"""Read-only adapters for frozen evidence. Never runs a workflow or verifier."""
import hashlib
import json
import math
import re
from pathlib import Path

from .catalog import CATALOG

ROOT = Path(__file__).resolve().parents[3]
FRAME = re.compile(r"frame-([0-9]{6})\.jpg\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceError(ValueError):
    pass


def safe_file(root, relative):
    root = Path(root).resolve()
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise EvidenceError("Evidence path is outside the approved run")
    path = root/part
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in [path, *path.parents] if p != root):
        raise EvidenceError("Symlink or escaped evidence path rejected")
    if not path.is_file():
        raise EvidenceError("Required evidence is missing")
    return path


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError, TypeError) as exc:
        raise EvidenceError("Evidence JSON is unavailable or invalid") from exc


def sha(data):
    return hashlib.sha256(data).hexdigest()


class EvidenceStore:
    def __init__(self, root=ROOT, catalog=CATALOG):
        self.root = Path(root).resolve()
        self.catalog = {item.id: item for item in catalog}

    def entry(self, run_id):
        if run_id not in self.catalog:
            raise KeyError("Unknown run")
        return self.catalog[run_id]

    def checked_bytes(self, relative):
        path = safe_file(self.root, relative)
        # Trust only the predeclared run root's manifest. Never follow source paths
        # supplied by a browser, report or manifest to locate evidence.
        candidates = []
        for entry in list(self.catalog.values()):
            for base in (entry.directory, entry.capture.rsplit("/", 1)[0]):
                if relative.startswith(base+"/"):
                    candidates.append(base)
        if not candidates:
            raise EvidenceError("Evidence is not in an approved run")
        for base in sorted(set(candidates), key=len, reverse=True):
            manifest = read_json(safe_file(self.root, base+"/integrity.json"))
            expected = manifest.get("sha256", {}).get(relative[len(base)+1:])
            if expected is None:
                continue
            data = path.read_bytes()
            if not isinstance(expected, str) or not SHA.fullmatch(expected) or sha(data) != expected:
                raise EvidenceError("Evidence checksum mismatch")
            return data
        raise EvidenceError("Required evidence has no recorded checksum")

    def checked_json(self, relative):
        try:
            return json.loads(self.checked_bytes(relative))
        except (ValueError, TypeError) as exc:
            if isinstance(exc, EvidenceError):
                raise
            raise EvidenceError("Checked evidence has invalid JSON") from exc

    def load(self, run_id):
        e = self.entry(run_id)
        report_path, spec_path = e.directory+"/"+e.report, e.directory+"/"+e.spec
        report, spec = self.checked_json(report_path), self.checked_json(spec_path)
        metadata = self.checked_json(e.capture+"/camera/capture.json")
        raw_index = self.checked_bytes(e.capture+"/camera/frames.jsonl")
        try:
            index = [json.loads(line) for line in raw_index.splitlines()]
            steps = {row["step"]: row for row in spec["steps"]}
            if len(steps) != len(spec["steps"]):
                raise ValueError("Duplicate steps")
            if metadata["frame_count"] != len(index) or not index:
                raise ValueError("Frame count")
            if [r["frame"] for r in index] != list(range(1, len(index)+1)):
                raise ValueError("Frame order")
            if report.get("spec_sha256") and report["spec_sha256"] != sha(self.checked_bytes(spec_path)):
                raise EvidenceError("Report specification binding differs")
            if report.get("source_run") and Path(report["source_run"]).resolve() != (self.root/e.capture).resolve():
                raise EvidenceError("Report capture binding differs")
            measured = {}
            for window in report["windows"]:
                step = window["step"]
                if step not in steps:
                    raise ValueError("Unknown step")
                for observation in window["measurements"]:
                    name = observation["file"]
                    if name in measured or not FRAME.fullmatch(name):
                        raise ValueError("Duplicate or unsafe measured frame")
                    measured[name] = (step, observation)
            names = {row["file"] for row in index}
            if not set(measured) <= names:
                raise ValueError("Measured frame missing from index")
            frames = []
            first_pts = index[0]["sample_pts_seconds"]
            for row in index:
                if row["file"] != "frame-%06d.jpg" % row["frame"]:
                    raise ValueError("Frame name")
                step, observation = measured.get(row["file"], (None, None))
                expected = steps.get(step)
                pts = row.get("sample_pts_seconds")
                if not isinstance(pts, (float, int)) or not math.isfinite(pts):
                    raise ValueError("Frame timestamp")
                if observation and observation.get("sample_pts_seconds") != pts:
                    raise ValueError("Observation timestamp binding")
                frames.append({"id": row["frame"], "file": row["file"], "offset_seconds": round(pts-first_pts, 3),
                    "evaluated": observation is not None, "step": step,
                    "expected": {"red": expected["red"], "green": expected["green"], "oled_text": expected["oled_text"]} if expected else None,
                    "observed": {k: observation.get(k) for k in ("red", "green", "oled_text")} if observation else None,
                    "geometry_supported": observation.get("geometry_supported") if observation else None,
                    "image_sha256": observation.get("sha256") if observation else None,
                    "image_url": f"/api/runs/{run_id}/frames/{row['frame']}/image"})
            behavior = report.get("led_behavior_comparison") if e.kind == "negative" else report.get("status")
            if behavior not in ("pass", "fail", "incomplete"):
                raise ValueError("Unsupported verdict")
            failures, unknowns = report.get("mismatches", report.get("failures", [])), report.get("unknowns", [])
            if not isinstance(failures, list) or not isinstance(unknowns, list):
                raise ValueError("Invalid findings")
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, EvidenceError):
                raise
            raise EvidenceError("Recorded evidence schema or frame binding is invalid") from exc
        has_text = e.kind != "negative"
        model = None
        if has_text:
            policy = self.checked_json(e.directory+"/reader-policy.snapshot.json")
            model = policy.get("model")
        geometry_rejected = bool(measured) and all(o.get("geometry_supported") is False for _,o in measured.values())
        model_role = ("No model requests: camera geometry rejected" if geometry_rejected else
                      "OLED image transcription without expected labels" if has_text else "No model requests in this test")
        if geometry_rejected: model = None
        evaluated = sum(f["evaluated"] for f in frames)
        return {"id": e.id, "title": e.title, "description": e.description, "available": True,
            "mode": "recorded", "source_kind": metadata.get("source"),
            "recorded_at": metadata.get("started_at_utc"), "camera_name": metadata.get("camera", {}).get("name", "Recorded camera"),
            "scope": "LED/OLED · sampled settled windows" if has_text else "LEDs only · sampled settled windows",
            "acquisition_status": metadata.get("status"), "behavior_verdict": behavior,
            "measurement_status": "incomplete" if unknowns else "complete",
            "qualification_outcome": "fault_detected" if e.kind == "negative" and report.get("status") == "pass" and behavior == "fail" else None,
            "frame_count": len(frames), "evaluated_sample_count": evaluated, "mismatch_count": len(failures), "unknown_count": len(unknowns),
            "finding_unit": "channel readings" if e.kind == "negative" else "field readings", "failures": failures, "unknowns": unknowns,
            "servo_angle_deg": None, "full_behavior_verdict": "incomplete", "oled_evaluated": has_text,
            "model_activity": {"model": model, "role": model_role, "new_requests": 0},
            "integrity": {"status": "verified_metadata", "scope": "Report, frozen specification, capture metadata and frame index match local manifests. Images checked when opened. Checksums do not authenticate origin."},
            "provenance": {"report": report_path, "specification": spec_path, "capture": e.capture, "report_sha256": sha(self.checked_bytes(report_path))},
            "frames": frames, "steps": [{"id": k, "label": v["oled_text"], "samples": sum(f["step"] == k for f in frames)} for k,v in steps.items()],
            "capabilities": {"hardware_actions": False, "model_actions": False}}

    def list_runs(self):
        result = []
        for e in list(self.catalog.values()):
            try:
                run = self.load(e.id)
                result.append({k: run[k] for k in ("id", "title", "description", "available", "recorded_at", "behavior_verdict", "qualification_outcome", "evaluated_sample_count", "mismatch_count", "unknown_count", "finding_unit", "oled_evaluated")})
            except (EvidenceError, OSError, ValueError, TypeError) as exc:
                result.append({"id": e.id, "title": e.title, "description": e.description, "available": False,
                               "behavior_verdict": "unavailable", "error": str(exc) if isinstance(exc, EvidenceError) else "Evidence unavailable"})
        return result

    def image(self, run_id, frame_id):
        run = self.load(run_id)  # Recheck report/index before serving the matching frame.
        if not 1 <= frame_id <= len(run["frames"]):
            raise KeyError("Unknown frame")
        frame = run["frames"][frame_id-1]
        data = self.checked_bytes(self.entry(run_id).capture+"/camera/"+frame["file"])
        if frame["image_sha256"] is not None and sha(data) != frame["image_sha256"]:
            raise EvidenceError("Image differs from the measured frame")
        if not data.startswith(b"\xff\xd8\xff"):
            raise EvidenceError("Unsupported image")
        return data
