"""Serialized, idempotent planning jobs. No serial/camera/build dependencies."""
import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..intent import fingerprint, instruction_text, plan_intent, save, validate_proposal
from ..plans import validate_plan

IDENTIFIER = re.compile(r"[0-9a-f]{32}\Z")


class BusyError(ValueError): pass


class PlanningService:
    def __init__(self, directory, generator=plan_intent):
        self.directory = Path(directory)
        self.generator = generator
        self.lock = threading.Lock()
        self.active = None
        self.jobs = {}
        self.requests = {}

    def start(self, instruction, request_id):
        instruction = instruction_text(instruction)
        if not isinstance(request_id, str) or not IDENTIFIER.fullmatch(request_id):
            raise ValueError("A valid request ID is required")
        with self.lock:
            if request_id in self.requests:
                job_id, prior = self.requests[request_id]
                if prior != instruction:
                    raise ValueError("Request ID already used for another instruction")
                return job_id
            if self.active:
                raise BusyError("A Meta proposal is already running. Wait for its result.")
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {"id": job_id, "status": "queued", "instruction": instruction, "proposal": None,
                                 "physical_verification": "not_performed", "api_requests": 0}
            self.requests[request_id] = (job_id, instruction)
            self.active = job_id
            threading.Thread(target=self._run, args=(job_id,instruction), daemon=True).start()
            return job_id

    def _run(self, job_id, instruction):
        try:
            result = self.generator(instruction, self.directory/job_id)
        except Exception:
            # Never serialize exception strings (network libraries may include secrets).
            result = {"status": "error", "instruction": "Instruction withheld after a local planning error", "proposal": None,
                      "error": "Planning failed. Check local configuration or the saved request; no automatic retry.",
                      "physical_verification": "not_performed"}
            folder = self.directory/job_id
            try:
                folder.mkdir(parents=True, exist_ok=True)
                save(folder/"result.json", result)
                save(folder/"integrity.json", {"sha256": {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file() and p.name!="integrity.json"}})
            except OSError:
                pass  # Retain the safe failure in memory and release the worker.
        with self.lock:
            self.jobs[job_id] = {"id": job_id, **result}
            self.active = None

    def _checked_result(self, job_id):
        if not IDENTIFIER.fullmatch(job_id):
            raise KeyError("Unknown proposal")
        folder = self.directory/job_id
        if folder.is_symlink() or not folder.is_dir():
            raise KeyError("Unknown proposal")
        path = folder/"result.json"; manifest = folder/"integrity.json"
        if path.is_symlink() or manifest.is_symlink():
            raise ValueError("Saved proposal path is invalid")
        try:
            data = path.read_bytes()
            entries = json.loads(manifest.read_text())["sha256"]
            if hashlib.sha256(data).hexdigest() != entries.get("result.json"):
                raise ValueError("Saved proposal checksum mismatch")
            result = json.loads(data)
            if not isinstance(result, dict) or result.get("status") not in ("ready", "clarify", "unsupported", "invalid_response", "error"):
                raise ValueError("Saved proposal state is invalid")
            if result["status"] in ("ready", "clarify", "unsupported"):
                if validate_proposal(result.get("proposal"))["decision"] != result["status"]:
                    raise ValueError("Saved proposal decision differs")
            if result.get("status") == "ready":
                plan_path = folder/"plan.json"
                if plan_path.is_symlink(): raise ValueError("Invalid plan path")
                plan_data = plan_path.read_bytes()
                if hashlib.sha256(plan_data).hexdigest() != entries.get("plan.json") or fingerprint(json.loads(plan_data)) != result.get("plan_sha256"):
                    raise ValueError("Saved plan checksum mismatch")
                plan = validate_plan(json.loads(plan_data))
                if plan["steps"] != result["proposal"]["steps"] or plan["mapping"] != {"red":25,"green":26}:
                    raise ValueError("Saved plan differs from the reviewed proposal data")
            return {"id": job_id, **result}
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Saved proposal is unavailable or incomplete") from exc

    def get(self, job_id):
        with self.lock:
            if job_id in self.jobs:
                job = dict(self.jobs[job_id])
                if job.get("status") in ("queued","generating") or not (self.directory/job_id/"result.json").exists():
                    return job
        result = self._checked_result(job_id)
        review = self.directory/job_id/"review.json"
        if review.is_file() and not review.is_symlink():
            try:
                r = json.loads(review.read_text())
                if r.get("plan_sha256") == result.get("plan_sha256"):
                    result.update(review_status="reviewed", reviewed_at_utc=r.get("reviewed_at_utc"))
            except (OSError, ValueError): pass
        return result

    def list(self):
        if not self.directory.exists(): return []
        items = []
        with self.lock:
            ids = set(self.jobs)
        ids.update(p.name for p in self.directory.iterdir() if p.is_dir() and IDENTIFIER.fullmatch(p.name))
        for job_id in sorted(ids):
            try:
                job = self.get(job_id)
                items.append({k: job.get(k) for k in ("id","status","instruction","started_at_utc","review_status")})
            except (KeyError, ValueError):
                items.append({"id":job_id,"status":"unavailable","instruction":"Saved proposal unavailable"})
        return sorted(items,key=lambda r:r.get("started_at_utc") or "",reverse=True)[:30]

    def review(self, job_id, plan_sha256):
        with self.lock:
            result = self._checked_result(job_id)
            if result.get("status")!="ready" or not isinstance(plan_sha256,str) or result.get("plan_sha256") != plan_sha256:
                raise ValueError("Only the unchanged ready proposal can be marked reviewed")
            review = {"plan_sha256":plan_sha256,"reviewed_at_utc":datetime.now(timezone.utc).isoformat(),
                      "scope":"Operator reviewed the proposed data. No compilation, installation, execution or physical acceptance authorized."}
            save(self.directory/job_id/"review.json",review)
        return self.get(job_id)
