"""Serialized, idempotent planning jobs. No serial/camera/build dependencies."""
import copy
import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..intent import fingerprint, instruction_text, plan_intent, save, validate_proposal
from ..acceptance import logical_contract
from ..plans import validate_mapping, validate_plan

IDENTIFIER = re.compile(r"[0-9a-f]{32}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REPAIR_PROVENANCE = {
    "repair_job_id", "source_test_id", "source_test_sha256", "discovery_sha256",
    "policy_sha256", "calibration_sha256",
}


def checked_provenance(value):
    if not isinstance(value, dict) or set(value) != REPAIR_PROVENANCE:
        raise ValueError("A complete mapping-repair evidence binding is required")
    for name, item in value.items():
        pattern = IDENTIFIER if name in ("repair_job_id", "source_test_id") else SHA256
        if not isinstance(item, str) or not pattern.fullmatch(item):
            raise ValueError("Invalid mapping-repair evidence binding")
    return value


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

    def _checked_result(self, job_id, _seen=None):
        if not isinstance(job_id, str) or not IDENTIFIER.fullmatch(job_id):
            raise KeyError("Unknown proposal")
        seen = set() if _seen is None else set(_seen)
        if job_id in seen:
            raise ValueError("Cyclic proposal ancestry rejected")
        seen.add(job_id)
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
                if plan["steps"] != result["proposal"]["steps"]:
                    raise ValueError("Saved plan differs from the reviewed proposal data")
                if result.get("origin") == "mapping_repair":
                    parent_id = result.get("parent_id")
                    parent = self._checked_result(parent_id, seen)
                    if parent.get("origin") == "mapping_repair" or parent.get("status") != "ready":
                        raise ValueError("Mapping repairs require an original ready proposal")
                    if result.get("parent_plan_sha256") != parent.get("plan_sha256"):
                        raise ValueError("Mapping-repair parent changed")
                    parent_review = self._review_record(parent_id, parent)
                    if parent_review is None or not parent_review.get("contract_sha256"):
                        raise ValueError("Mapping-repair parent requires a frozen reviewed contract")
                    parent_contract = self._checked_contract(parent_id, parent, parent_review["contract_sha256"])
                    parent_plan = json.loads((self.directory/parent_id/"plan.json").read_text())
                    if plan["steps"] != parent_plan["steps"] or result["proposal"] != parent["proposal"]:
                        raise ValueError("Mapping repair changed the original behavior")
                    if plan["mapping"] == parent_plan["mapping"]:
                        raise ValueError("Mapping repair must change the implementation mapping")
                    checked_provenance(result.get("provenance"))
                    if result.get("contract_sha256") != parent_review["contract_sha256"]:
                        raise ValueError("Mapping repair must retain the original contract")
                    contract_path = folder/"contract.json"
                    if entries.get("contract.json") != result["contract_sha256"]:
                        raise ValueError("Mapping-repair contract is not bound to proposal integrity")
                    if self._checked_contract(job_id, result, result["contract_sha256"]) != parent_contract:
                        raise ValueError("Mapping repair changed the original contract")
                    if contract_path.read_bytes() != (self.directory/parent_id/"contract.json").read_bytes():
                        raise ValueError("Mapping repair must retain the exact original contract bytes")
                elif result.get("origin") not in (None, "intent") or plan["mapping"] != {"red":25,"green":26}:
                    raise ValueError("Only a validated mapping-repair proposal may change pins")
                result["mapping"] = dict(plan["mapping"])
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
        r = self._review_record(job_id, result)
        if r is not None:
            if r.get("contract_sha256"):
                self._checked_contract(job_id, result, r["contract_sha256"])
                result["contract_sha256"] = r["contract_sha256"]
            result.update(review_status="reviewed", reviewed_at_utc=r.get("reviewed_at_utc"))
        return result

    def _review_record(self, job_id, result):
        path = self.directory/job_id/"review.json"
        if path.is_symlink():
            raise ValueError("Saved review path is invalid")
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise ValueError("Saved review is unavailable or invalid") from exc
        if not isinstance(record, dict) or record.get("plan_sha256") != result.get("plan_sha256"):
            return None
        return record

    def _checked_contract(self, job_id, result, expected_hash):
        path = self.directory/job_id/"contract.json"
        if not isinstance(expected_hash, str) or not SHA256.fullmatch(expected_hash) or path.is_symlink():
            raise ValueError("Frozen contract binding is invalid")
        try:
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected_hash:
                raise ValueError("Frozen behavior contract changed")
            spec = json.loads(data)
            plan = json.loads((self.directory/job_id/"plan.json").read_text())
            if spec != logical_contract(plan):
                raise ValueError("Frozen contract differs from the original reviewed behavior")
            if result.get("origin") == "mapping_repair" and expected_hash != result.get("contract_sha256"):
                raise ValueError("Review differs from the inherited behavior contract")
            return spec
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Frozen behavior contract is unavailable") from exc

    def _freeze_contract(self, job_id, result, review):
        """Called under the planning lock; never replaces an already bound contract."""
        if review.get("contract_sha256"):
            return self._checked_contract(job_id, result, review["contract_sha256"])
        folder = self.directory/job_id
        path = folder/"contract.json"
        plan = json.loads((folder/"plan.json").read_text())
        spec = logical_contract(plan)
        if path.is_symlink():
            raise ValueError("Frozen contract path is invalid")
        if path.exists():
            # A pending derived proposal already carries its parent's contract. A
            # crash before saving an original review may also leave these bytes.
            if json.loads(path.read_text()) != spec:
                raise ValueError("Existing contract differs from the reviewed behavior")
        else:
            if result.get("origin") == "mapping_repair":
                raise ValueError("Mapping-repair contract is missing")
            save(path, spec)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if result.get("origin") == "mapping_repair" and sha != result.get("contract_sha256"):
            raise ValueError("Mapping-repair contract changed before review")
        review["contract_sha256"] = sha
        review["contract_scope"] = "Original reviewed logical behavior, fixed across mapping-only repair"
        save(folder/"review.json", review)
        return spec

    def contract(self, job_id):
        """Read the frozen spec, or lazily bind an unchanged legacy reviewed plan."""
        with self.lock:
            result = self._checked_result(job_id)
            review = self._review_record(job_id, result)
            if result.get("status") != "ready" or review is None:
                raise ValueError("Review the unchanged proposal before freezing its behavior")
            return copy.deepcopy(self._freeze_contract(job_id, result, review))

    def create_mapping_repair(self, parent_id, expected_parent_hash, mapping, provenance):
        """Create a pending-review candidate; its only executable change is pins.

        The caller verifies fresh probe measurements and the Meta proposal before
        calling this method, then rechecks that evidence before hardware work.
        """
        validate_mapping(mapping)
        checked_provenance(provenance)
        with self.lock:
            parent = self._checked_result(parent_id)
            if parent.get("origin") == "mapping_repair":
                raise ValueError("A mapping repair cannot be repaired again")
            if parent.get("status") != "ready" or parent.get("plan_sha256") != expected_parent_hash:
                raise ValueError("The unchanged original proposal is required")
            review = self._review_record(parent_id, parent)
            if review is None:
                raise ValueError("Review the original proposal before preparing a repair")
            self._freeze_contract(parent_id, parent, review)
            parent_folder = self.directory/parent_id
            plan = json.loads((parent_folder/"plan.json").read_text())
            if plan["mapping"] == mapping:
                raise ValueError("Observed mapping is unchanged; no repair is needed")
            plan["mapping"] = dict(mapping)
            validate_plan(plan)
            job_id = uuid.uuid4().hex
            folder = self.directory/job_id
            folder.mkdir(parents=True, exist_ok=False)
            (folder/"contract.json").write_bytes((parent_folder/"contract.json").read_bytes())
            result = {
                "schema_version": 1, "status": "ready", "origin": "mapping_repair",
                "parent_id": parent_id, "parent_plan_sha256": expected_parent_hash,
                "contract_sha256": review["contract_sha256"], "provenance": copy.deepcopy(provenance),
                "instruction": parent["instruction"], "proposal": copy.deepcopy(parent["proposal"]),
                "plan_sha256": fingerprint(plan), "review_status": "pending",
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "provider": "meta_api", "model": "muse-spark-1.3-contributor",
                "api_requests": 0, "mapping_proposal_request": provenance["repair_job_id"],
                "validation": "mapping_only_candidate_from_checked_probe",
                "semantic_verification": "original_operator_review_retained",
                "physical_verification": "not_performed", "hardware_actions": [],
                "firmware_uploaded": False, "compiled": False,
            }
            save(folder/"plan.json", plan)
            save(folder/"result.json", result)
            save(folder/"integrity.json", {"sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.iterdir() if p.is_file() and p.name != "integrity.json"
            }})
        return self.get(job_id)

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
            review = self._review_record(job_id, result)
            if review is None:
                review = {"plan_sha256":plan_sha256,"reviewed_at_utc":datetime.now(timezone.utc).isoformat(),
                          "scope":"Operator reviewed the mapping-only correction. Installation still requires a separate explicit action; no physical acceptance claimed."
                          if result.get("origin") == "mapping_repair" else
                          "Operator reviewed the proposed data. No compilation, installation, execution or physical acceptance authorized."}
            self._freeze_contract(job_id, result, review)
        return self.get(job_id)
