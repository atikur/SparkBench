"""Serialized, idempotent explanation jobs for recorded runs. Reads evidence; never touches hardware."""
import hashlib
import json
import re
import threading
import uuid
from pathlib import Path

from ..diagnosis import explain_run, select_frames, validate_reply
from ..intent import save
from .planning import BusyError, IDENTIFIER

RUN_ID = re.compile(r"[a-z0-9-]{1,80}\Z")
STATES = ("explained", "invalid_response", "error")


class ExplanationService:
    def __init__(self, directory, store, generator=explain_run):
        self.directory = Path(directory)
        self.store = store
        self.generator = generator
        self.lock = threading.Lock()
        self.active = None
        self.jobs = {}
        self.requests = {}

    def start(self, run_id, request_id):
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise KeyError("Unknown run")
        if not isinstance(request_id, str) or not IDENTIFIER.fullmatch(request_id):
            raise ValueError("A valid request ID is required")
        with self.lock:
            if request_id in self.requests:
                job_id, prior = self.requests[request_id]
                if prior != run_id:
                    raise ValueError("Request ID already used for another run")
                return job_id
            if self.active:
                raise BusyError("An explanation is already being written. Wait for its result.")
            run = self.store.load(run_id)  # Integrity-checked; raises for unknown or altered evidence.
            if run.get("behavior_verdict") not in ("fail", "incomplete"):
                raise ValueError("Only a failed or incomplete run can be explained")
            frame_ids = select_frames(run)
            if not frame_ids:
                raise ValueError("This run has no evaluated frame to explain")
            images = [(run["frames"][i - 1]["file"], self.store.image(run_id, i)) for i in frame_ids]
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {"id": job_id, "status": "generating", "run_id": run_id, "explanation": None, "api_requests": 0}
            self.requests[request_id] = (job_id, run_id)
            self.active = job_id
            threading.Thread(target=self._run, args=(job_id, run, images), daemon=True).start()
            return job_id

    def _folder(self, run_id, job_id):
        return self.directory / run_id / job_id

    def _run(self, job_id, run, images):
        folder = self._folder(run["id"], job_id)
        try:
            result = self.generator(run, images, folder)
        except Exception:
            # Never serialize exception strings; network libraries may include secrets.
            result = {"status": "error", "run_id": run["id"], "explanation": None, "advisory": True, "verdict_changed": False,
                      "error": "Explanation failed. Check local configuration or the saved request; no automatic retry."}
            try:
                folder.mkdir(parents=True, exist_ok=True)
                save(folder / "result.json", result)
                save(folder / "integrity.json", {"sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file() and p.name != "integrity.json"}})
            except OSError:
                pass
        with self.lock:
            self.jobs[job_id] = {"id": job_id, **result}
            self.active = None

    def _checked_result(self, run_id, job_id):
        folder = self._folder(run_id, job_id)
        if folder.is_symlink() or not folder.is_dir():
            raise KeyError("Unknown explanation")
        path, manifest = folder / "result.json", folder / "integrity.json"
        if path.is_symlink() or manifest.is_symlink():
            raise ValueError("Saved explanation path is invalid")
        try:
            data = path.read_bytes()
            entries = json.loads(manifest.read_text())["sha256"]
            if hashlib.sha256(data).hexdigest() != entries.get("result.json"):
                raise ValueError("Saved explanation checksum mismatch")
            result = json.loads(data)
            if not isinstance(result, dict) or result.get("status") not in STATES or result.get("run_id") != run_id:
                raise ValueError("Saved explanation state is invalid")
            if result["status"] == "explained":
                validate_reply(result.get("explanation"), [f["name"] for f in result.get("frames", [])])
            return {"id": job_id, **result}
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Saved explanation is unavailable or incomplete") from exc

    def get(self, job_id):
        if not IDENTIFIER.fullmatch(job_id or ""):
            raise KeyError("Unknown explanation")
        with self.lock:
            job = self.jobs.get(job_id)
            if job is not None:
                job = dict(job)
                if job.get("status") == "generating" or not self._folder(job["run_id"], job_id).joinpath("result.json").exists():
                    return job
                run_id = job["run_id"]
            else:
                run_id = None
        if run_id is None:
            matches = [p for p in self.directory.glob("*/" + job_id) if p.is_dir()] if self.directory.exists() else []
            if len(matches) != 1 or not RUN_ID.fullmatch(matches[0].parent.name):
                raise KeyError("Unknown explanation")
            run_id = matches[0].parent.name
        return self._checked_result(run_id, job_id)

    def list_for_run(self, run_id):
        """Saved explanations for one run, newest first. Reading makes no model call."""
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise KeyError("Unknown run")
        folder = self.directory / run_id
        items = []
        with self.lock:
            for job in self.jobs.values():
                if job.get("run_id") == run_id and job.get("status") == "generating":
                    items.append(dict(job))
        if folder.is_dir() and not folder.is_symlink():
            for p in folder.iterdir():
                if p.is_dir() and IDENTIFIER.fullmatch(p.name):
                    try:
                        items.append(self._checked_result(run_id, p.name))
                    except (KeyError, ValueError):
                        items.append({"id": p.name, "run_id": run_id, "status": "unavailable", "explanation": None})
        return sorted(items, key=lambda r: r.get("started_at_utc") or "", reverse=True)[:10]
