"""One bounded mapping repair per reviewed plan, sharing the bench's job lock.

The host always chooses DISCOVER. Meta proposes only a mapping; camera evidence
and local validation decide whether it is eligible for operator approval.
"""
import copy
import json
import threading
import uuid
from datetime import datetime, timezone

from ..camera import capture_frames
from ..discovery import analyze_probes
from ..intent import save
from ..mapping_repair import propose_mapping, verified_mapping
from ..plans import validate_against_spec
from ..policy import check_integrity, check_policy
from ..runtime_io import acquire, identity
from ..vision import digest, geometry_valid, read_images
from .planning import BusyError, IDENTIFIER


def now():
    return datetime.now(timezone.utc).isoformat()


class MappingRepairMixin:
    @staticmethod
    def _bound_capture(capture, action, artifact, request):
        if (not isinstance(capture,dict) or capture.get('status')!='completed' or capture.get('source')!='live_hardware'
                or capture.get('action')!=action or capture.get('servo_actuation') is not False
                or capture.get('plan_sha256')!=artifact['plan_sha256']
                or capture.get('firmware_sha256')!=artifact['firmware_sha256']
                or capture.get('identity')!=identity(artifact['plan_sha256'])
                or capture.get('device_id')!=request['device_id'] or capture.get('port')!=request['port']):
            raise ValueError('Capture is not bound to the completed, servo-free runtime action and selected devices')

    def _init_repairs(self, probe_runner=None, probe_analyzer=None, mapping_proposer=None):
        self.probe_runner = probe_runner or acquire
        self.probe_analyzer = probe_analyzer or analyze_probes
        self.mapping_proposer = mapping_proposer or propose_mapping

    def _repair_policy(self, proposal_id=None):
        path = self._camera_policy_path(proposal_id)
        policy, calibration = check_policy(path)
        return {"policy_sha256": digest(path), "calibration_sha256": digest(calibration)}, policy, calibration

    def _repair_source(self, test_id, *, current=True):
        job = self.jobs.get(test_id, {})
        if job.get("action") != "test" or job.get("status") != "fail":
            raise ValueError("A completed camera test with a confirmed LED mismatch is required")
        proposal = self.planner.get(job["proposal_id"])
        if proposal.get("origin") == "mapping_repair":
            raise ValueError("One mapping repair only; a repaired candidate cannot start another repair")
        if proposal.get("review_status") != "reviewed" or proposal.get("plan_sha256") != job.get("plan_sha256"):
            raise ValueError("The original reviewed plan changed")
        if not job.get("contract_sha256"):
            raise ValueError("Run a fresh camera test to freeze the approved behavior before repairing")
        contract = self.planner.contract(job["proposal_id"])
        if self.planner.get(job["proposal_id"]).get("contract_sha256") != job["contract_sha256"]:
            raise ValueError("The original behavior contract changed")
        with self.lock: jobs = list(self.jobs.values())
        later = [j for j in jobs if j.get("action") == "test"
                 and j.get("proposal_id") == job["proposal_id"]
                 and j.get("started_at_utc", "") > job.get("started_at_utc", "")]
        if later:
            raise ValueError("A newer test supersedes this failure; inspect its evidence")
        folder = self._folder(test_id) / "workflow"
        entries = check_integrity(folder)
        required = {"spec.snapshot.json", "reader-policy.snapshot.json", "analysis/verification.json",
                    "analysis/calibration.snapshot.json", "capture/run.json"}
        if not required <= set(entries):
            raise ValueError("The failed test lacks complete integrity-bound measurements")
        if json.loads((folder / "spec.snapshot.json").read_text()) != contract:
            raise ValueError("The failed test used a different behavior contract")
        policy_state, policy, calibration = self._repair_policy(job['proposal_id'])
        if (json.loads((folder / "reader-policy.snapshot.json").read_text()) != policy
                or json.loads((folder / "analysis/calibration.snapshot.json").read_text()) != json.loads(calibration.read_text())):
            raise ValueError("Camera policy or calibration changed since the failed test")
        self.register_evidence()
        run = self.store.load("test-" + test_id)
        rows = [r for r in run["frames"] if r.get("evaluated")]
        if not rows or run.get("behavior_verdict") != "fail":
            raise ValueError("No confirmed camera failure is available")
        if any(r.get("geometry_supported") is not True
               or any(type((r.get("observed") or {}).get(c)) is not bool for c in ("red", "green")) for r in rows):
            raise ValueError("LED evidence is incomplete; restore a readable camera view first")
        if not any(any(r["observed"][c] != (r.get("expected") or {}).get(c) for c in ("red", "green")) for r in rows):
            raise ValueError("This is not an LED mismatch; a mapping probe cannot repair an OLED-only problem")
        request = job["request"]
        artifact_path, artifact = self._build(request["build_id"], job["proposal_id"], job["plan_sha256"])
        capture = json.loads((folder / "capture/run.json").read_text())
        self._bound_capture(capture,'VISUAL',artifact,request)
        if current:
            board, _ = self._board()
            if board["active_firmware"]["firmware_sha256"] != artifact["firmware_sha256"]:
                raise ValueError("The installed firmware changed since this failure")
        plan = json.loads((self.planner.directory / job["proposal_id"] / "plan.json").read_text())
        validate_against_spec(plan, contract, plan["mapping"])
        return {"job": job, "plan": plan, "contract": contract, "artifact_path": artifact_path,
                "artifact": artifact, "source_test_sha256": digest(folder / "integrity.json"), **policy_state}

    def repair_eligibility(self, test_id):
        try:
            self._folder(test_id)
            job = self.jobs.get(test_id, {})
            with self.lock: jobs = list(self.jobs.values())
            prior = next((j for j in jobs if j.get("action") == "mapping_repair"
                          and j.get("proposal_id") == job.get("proposal_id")), None)
            if prior:
                return {"eligible": False, "reason": "The single mapping repair attempt for this plan is already recorded",
                        "repair_job_id": prior["id"]}
            self._repair_source(test_id)
            return {"eligible": True, "reason": "Confirmed LED mismatch; the fixed pin probe can investigate the mapping"}
        except (ValueError, KeyError, OSError, TypeError) as exc:
            return {"eligible": False, "reason": str(exc) if isinstance(exc, ValueError) else "Complete failed-test evidence is unavailable"}

    def start_repair(self, body):
        if (set(body) != {"source_test_id", "request_id", "port", "device_id"}
                or any(not isinstance(body[k], str) or not IDENTIFIER.fullmatch(body[k]) for k in ("source_test_id", "request_id"))
                or any(not isinstance(body[k], str) or not body[k].strip() for k in ("port", "device_id"))):
            raise ValueError("Select the failed test, CP2102, iPhone and a request ID")
        with self.lock:
            for job in self.jobs.values():
                if job.get("request_id") == body["request_id"]:
                    if job.get("action") != "mapping_repair" or job.get("request") != body:
                        raise ValueError("Request ID already used")
                    return job["id"]
            if self.active:
                raise BusyError("Another job owns the bench")
            eligible = self.repair_eligibility(body["source_test_id"])
            if not eligible["eligible"]:
                raise ValueError(eligible["reason"])
            context = self._repair_source(body["source_test_id"])
            source = context["job"]
            if body["port"] != source["request"]["port"] or body["device_id"] != source["request"]["device_id"]:
                raise ValueError("Use the same board port and frozen camera as the failed test")
            job_id = uuid.uuid4().hex
            folder = self._folder(job_id); folder.mkdir(parents=True, exist_ok=False)
            self.jobs[job_id] = {"id": job_id, "action": "mapping_repair", "status": "running", "stage": "preflight",
                "proposal_id": source["proposal_id"], "parent_proposal_id": source["proposal_id"],
                "plan_sha256": source["plan_sha256"], "source_test_id": source["id"],
                "contract_sha256": source["contract_sha256"], "old_mapping": context["plan"]["mapping"],
                "request_id": body["request_id"], "request": dict(body), "started_at_utc": now(),
                "servo_actuation": False, "physical_verification": "not_performed", "firmware_uploaded": False,
                "probe_selection": "fixed_local_rule_after_confirmed_LED_mismatch", "api_requests": 0}
            save(folder / "job.json", self.jobs[job_id])
            self.active = job_id; self.cancel_event = threading.Event()
            self.thread = threading.Thread(target=self._run_repair, args=(job_id, self.cancel_event), daemon=False)
            self.thread.start()
            return job_id

    def _repair_preflight(self, job, cancel):
        """Fresh idle geometry/off-state check, without an OLED/Meta request."""
        camera = job["request"]["device_id"]
        calibration = self._frozen_calibration(job['proposal_id'])
        if calibration["camera_id"] != camera:
            raise ValueError("The camera differs from the frozen measurement policy")
        run = self._folder(job["id"]) / "repair/preflight"
        run.mkdir(parents=True)
        capture_frames(camera, seconds=5, fps=2, output=run / "camera")
        if cancel.is_set(): raise ValueError("Repair cancelled before probing")
        from ..led_oled import frame_rows
        chosen = frame_rows(run / "camera/frames.jsonl")[-3:]
        if len(chosen) != 3: raise ValueError("Fresh camera frames unavailable; no probe sent")
        geometry = calibration["geometry"]
        analysis = run / "analysis"; analysis.mkdir()
        raw = self.view_reader(run, geometry, chosen, analysis, read_labels=False)
        rows = [raw[f["file"]] for f in chosen]
        issues = self._view_issues(rows, sum(geometry_valid(r, geometry) for r in rows),
                                   sum(r.get("status") == "measured" for r in rows), calibration)
        if issues: raise ValueError("Camera preflight blocked; no probe sent: " + issues[0]["problem"])

    def _run_repair(self, job_id, cancel):
        folder = self._folder(job_id) / "repair"
        folder.mkdir()
        job = self.jobs[job_id]
        try:
            context = self._repair_source(job["source_test_id"])
            current = self.enumerate_devices()
            if job["request"]["port"] not in [p["id"] for p in current["ports"]]:
                raise ValueError("Selected CP2102 is absent from fresh enumeration")
            if job["request"]["device_id"] not in [d["id"] for d in current["cameras"]]:
                raise ValueError("Selected iPhone is absent in this host context; no fallback camera")
            if cancel.is_set(): raise ValueError("Repair cancelled before camera access")
            self._repair_preflight(job, cancel)
            self._set(job_id, stage="probe")
            capture = self.probe_runner(job["request"]["port"], job["request"]["device_id"], context["artifact_path"],
                                        folder / "capture", action="DISCOVER", cancel=cancel)
            if cancel.is_set(): raise ValueError("Repair cancelled after bounded probe")
            self._bound_capture(capture,'DISCOVER',context['artifact'],job['request'])
            self._set(job_id, stage="analysis")
            discovery = self.probe_analyzer(folder / "capture", self._camera_policy_path(job['proposal_id']), folder / "discovery")
            mapping = verified_mapping(discovery)
            if discovery.get('source_run')!=str((folder/'capture').resolve()) or discovery.get('calibration_sha256')!=context['calibration_sha256']:
                raise ValueError('Probe analysis does not match this capture and frozen calibration')
            fresh = self._repair_source(job["source_test_id"])
            for key in ("source_test_sha256", "policy_sha256", "calibration_sha256"):
                if fresh[key] != context[key]: raise ValueError("Failed-test evidence or measurement policy changed during probing")
            if cancel.is_set(): raise ValueError("Repair cancelled before Meta request")
            self._set(job_id, stage="proposing", observed_mapping=mapping, api_requests=1)
            result = self.mapping_proposer(context["plan"]["mapping"], discovery, folder / "proposal")
            self._set(job_id, api_requests=result.get("api_requests", 1), explanation=result.get("explanation"),
                      proposed_mapping=result.get("mapping"), usage=result.get("usage"), model_latency_seconds=result.get("latency_seconds"))
            if cancel.is_set(): raise ValueError("Repair cancelled; proposal not approved")
            if result.get("status") not in ("proposed", "no_change"):
                self._set(job_id, status=result.get("status", "invalid_response"), error=result.get("error", "Meta did not return a valid mapping"))
                return
            if result.get("mapping") != mapping: raise ValueError("Proposed mapping disagrees with measured probe evidence")
            if mapping == context["plan"]["mapping"]:
                self._set(job_id, status="no_change", error="The observed mapping already matches; no firmware change is warranted")
                return
            provenance = {k: context[k] for k in ("source_test_sha256", "policy_sha256", "calibration_sha256")}
            provenance.update(repair_job_id=job_id, source_test_id=job["source_test_id"],
                              discovery_sha256=digest(folder / "discovery/discovery.json"))
            candidate = self.planner.create_mapping_repair(job["proposal_id"], job["plan_sha256"], mapping, provenance)
            binding = {"provenance": provenance, "parent_proposal_id": job["proposal_id"], "parent_plan_sha256": job["plan_sha256"],
                       "candidate_proposal_id": candidate["id"], "candidate_plan_sha256": candidate["plan_sha256"],
                       "contract_sha256": job["contract_sha256"], "old_mapping": context["plan"]["mapping"], "mapping": mapping}
            save(folder / "binding.json", binding)
            self._set(job_id, status="repair_ready", candidate_proposal_id=candidate["id"], candidate_plan_sha256=candidate["plan_sha256"])
        except Exception as exc:
            self._set(job_id, status="cancelled" if cancel.is_set() else "incomplete",
                      error=str(exc)[:400] if isinstance(exc, ValueError) else "Repair stopped; inspect retained local evidence")
        finally:
            try:
                capture_path = folder / "capture/run.json"
                try: capture = json.loads(capture_path.read_text())
                except (OSError, ValueError): capture = {}
                if not isinstance(capture,dict):capture={}
                save(folder / "integrity.json", {"sha256": {str(p.relative_to(folder)): digest(p)
                     for p in sorted(folder.rglob("*")) if p.is_file() and p != folder / "integrity.json"}})
                self._set(job_id, stage="finished", ended_at_utc=now(),
                          shutdown="acknowledged_uart_only" if capture.get("stop_acknowledged_uart_only") else "unconfirmed" if capture.get("sequence_started") else "not_started")
            except (OSError, ValueError):
                with self.lock:
                    self.jobs[job_id].update(status='incomplete',stage='finished',error='Repair evidence could not be sealed; no approval or installation allowed')
            finally:
                with self.lock: self.active = None

    def _validate_repair_candidate(self, proposal, *, approved=True):
        if proposal.get("origin") != "mapping_repair": return
        provenance = proposal["provenance"]
        job = self.jobs.get(provenance["repair_job_id"], {})
        if job.get("status") != "repair_ready" or job.get("candidate_proposal_id") != proposal["id"]:
            raise ValueError("The mapping repair is unavailable or did not complete")
        folder = self._folder(job["id"]) / "repair"
        entries = check_integrity(folder)
        if not {"binding.json", "discovery/discovery.json", "proposal/result.json", "capture/run.json"} <= set(entries):
            raise ValueError("Complete mapping repair evidence is required")
        binding = json.loads((folder / "binding.json").read_text())
        if (binding["provenance"] != provenance or binding["candidate_plan_sha256"] != proposal["plan_sha256"]
                or binding["contract_sha256"] != proposal["contract_sha256"]):
            raise ValueError("The repair candidate binding changed")
        discovery = json.loads((folder / "discovery/discovery.json").read_text())
        if digest(folder / "discovery/discovery.json") != provenance["discovery_sha256"] or verified_mapping(discovery) != binding["mapping"]:
            raise ValueError("Measured mapping evidence changed")
        source = self._repair_source(job["source_test_id"], current=False)
        self._bound_capture(json.loads((folder/'capture/run.json').read_text()),'DISCOVER',source['artifact'],job['request'])
        if discovery.get('source_run')!=str((folder/'capture').resolve()) or discovery.get('calibration_sha256')!=source['calibration_sha256']:
            raise ValueError('Probe analysis capture/calibration binding changed')
        for key in ("source_test_sha256", "policy_sha256", "calibration_sha256"):
            if source[key] != provenance[key]: raise ValueError("Original evidence or frozen camera policy changed")
        if approved:
            approval_path = self._folder(job["id"]) / "approval.json"
            if approval_path.is_symlink() or not approval_path.is_file(): raise ValueError("Approve the mapping repair before building or flashing")
            approval = json.loads(approval_path.read_text())
            if approval.get("candidate_plan_sha256") != proposal["plan_sha256"] or approval.get("contract_sha256") != proposal["contract_sha256"]:
                raise ValueError("Mapping repair approval differs from this candidate")
        return binding

    def approve_repair(self, job_id, body):
        if set(body) != {"plan_sha256"}: raise ValueError("Approve the exact candidate plan hash")
        with self.lock:
            if self.active: raise BusyError("Wait for the bench job to finish before approving a repair")
            job = self.jobs.get(job_id, {})
            if job.get("action") != "mapping_repair" or job.get("status") != "repair_ready" or body["plan_sha256"] != job.get("candidate_plan_sha256"):
                raise ValueError("Only the unchanged completed mapping proposal can be approved")
            proposal = self.planner.get(job["candidate_proposal_id"])
            self._validate_repair_candidate(proposal, approved=False)
            if job.get('approval_status')=='approved':
                self._validate_repair_candidate(proposal)
                return proposal
            self._repair_source(job["source_test_id"], current=True)
            save(self._folder(job_id) / "approval.json", {"candidate_plan_sha256": proposal["plan_sha256"],
                 "contract_sha256": proposal["contract_sha256"], "approved_at_utc": now(),
                 "scope": "Operator approved the mapping diff and subsequent bounded build/install/retest; no hardware action performed by approval"})
            result = self.planner.review(proposal["id"], proposal["plan_sha256"])
            self._set(job_id, approval_status="approved", approved_at_utc=now())
            return result
