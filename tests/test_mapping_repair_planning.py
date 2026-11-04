"""Offline checks for frozen requirements and mapping-only derived proposals."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sparkbench.acceptance import logical_contract
from sparkbench.dashboard.planning import PlanningService
from sparkbench.intent import fingerprint, save


PLAN = {"schema_version": 1, "mapping": {"red": 25, "green": 26}, "steps": [
    {"red": False, "green": True, "text": "READY"},
    {"red": True, "green": False, "text": "BUSY"},
    {"red": False, "green": False, "text": "DONE"},
]}
PARENT = "a" * 32
PROVENANCE = {
    "repair_job_id": "b" * 32, "source_test_id": "c" * 32,
    "source_test_sha256": "d" * 64, "discovery_sha256": "e" * 64,
    "policy_sha256": "f" * 64, "calibration_sha256": "1" * 64,
}


def seal(folder):
    save(folder/"integrity.json", {"sha256": {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.iterdir() if p.is_file() and p.name != "integrity.json"
    }})


class FrozenMappingRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = PlanningService(self.root)
        folder = self.root/PARENT
        folder.mkdir()
        save(folder/"plan.json", PLAN)
        save(folder/"result.json", {
            "status": "ready", "instruction": "READY green, BUSY red, DONE off",
            "proposal": {"decision": "ready", "summary": "Three status steps", "question": None,
                         "steps": copy.deepcopy(PLAN["steps"])},
            "plan_sha256": fingerprint(PLAN), "review_status": "pending",
        })
        seal(folder)

    def tearDown(self):
        self.temp.cleanup()

    def review(self):
        return self.service.review(PARENT, fingerprint(PLAN))

    def repair(self):
        self.review()
        return self.service.create_mapping_repair(
            PARENT, fingerprint(PLAN), {"red": 26, "green": 25}, PROVENANCE)

    def rewrite(self, folder, name, change):
        value = json.loads((folder/name).read_text())
        change(value)
        save(folder/name, value)
        seal(folder)

    def test_review_freezes_exact_logical_requirements_without_pins(self):
        reviewed = self.review()
        data = (self.root/PARENT/"contract.json").read_bytes()
        spec = self.service.contract(PARENT)
        self.assertEqual(spec, logical_contract(PLAN))
        self.assertNotIn("mapping", spec)
        self.assertEqual(reviewed["contract_sha256"], hashlib.sha256(data).hexdigest())
        again = self.service.review(PARENT, fingerprint(PLAN))
        self.assertEqual(again["reviewed_at_utc"], reviewed["reviewed_at_utc"])
        self.assertEqual((self.root/PARENT/"contract.json").read_bytes(), data)

    def test_unreviewed_plan_cannot_freeze_or_prepare_repair(self):
        with self.assertRaises(ValueError):
            self.service.contract(PARENT)
        with self.assertRaises(ValueError):
            self.service.create_mapping_repair(PARENT, fingerprint(PLAN), {"red": 26, "green": 25}, PROVENANCE)
        self.assertFalse((self.root/PARENT/"contract.json").exists())

    def test_legacy_review_freezes_only_on_contract_access(self):
        folder = self.root/PARENT
        save(folder/"review.json", {"plan_sha256": fingerprint(PLAN), "reviewed_at_utc": "historical"})
        self.assertEqual(self.service.get(PARENT)["review_status"], "reviewed")
        self.assertFalse((folder/"contract.json").exists())
        self.assertEqual(self.service.contract(PARENT), logical_contract(PLAN))
        self.assertEqual(self.service.get(PARENT)["reviewed_at_utc"], "historical")
        self.assertTrue(json.loads((folder/"review.json").read_text())["contract_sha256"])

    def test_mapping_candidate_preserves_exact_contract_and_needs_own_review(self):
        candidate = self.repair()
        folder = self.root/candidate["id"]
        self.assertEqual(candidate["origin"], "mapping_repair")
        self.assertEqual(candidate["mapping"], {"red": 26, "green": 25})
        self.assertEqual(candidate["proposal"]["steps"], PLAN["steps"])
        self.assertEqual(candidate["parent_plan_sha256"], fingerprint(PLAN))
        self.assertEqual(candidate["provenance"], PROVENANCE)
        self.assertEqual(candidate["review_status"], "pending")
        self.assertEqual(candidate["hardware_actions"], [])
        self.assertFalse(candidate["firmware_uploaded"])
        self.assertEqual((folder/"contract.json").read_bytes(), (self.root/PARENT/"contract.json").read_bytes())
        with self.assertRaises(ValueError):
            self.service.contract(candidate["id"])
        reviewed = self.service.review(candidate["id"], candidate["plan_sha256"])
        self.assertEqual(reviewed["review_status"], "reviewed")
        self.assertEqual(self.service.contract(candidate["id"]), self.service.contract(PARENT))
        self.assertEqual(PlanningService(self.root).get(candidate["id"])["contract_sha256"], candidate["contract_sha256"])

    def test_repair_cannot_change_servo_pin_or_duplicate_pins(self):
        self.review()
        for mapping in ({"red": 27, "green": 25}, {"red": 25, "green": 25}, {"red": True, "green": 26}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                self.service.create_mapping_repair(PARENT, fingerprint(PLAN), mapping, PROVENANCE)

    def test_unchanged_mapping_or_stale_parent_cannot_create_candidate(self):
        self.review()
        with self.assertRaises(ValueError):
            self.service.create_mapping_repair(PARENT, fingerprint(PLAN), PLAN["mapping"], PROVENANCE)
        with self.assertRaises(ValueError):
            self.service.create_mapping_repair(PARENT, "0"*64, {"red": 26, "green": 25}, PROVENANCE)

    def test_repair_of_repair_is_rejected(self):
        candidate = self.repair()
        self.service.review(candidate["id"], candidate["plan_sha256"])
        with self.assertRaises(ValueError):
            self.service.create_mapping_repair(candidate["id"], candidate["plan_sha256"], PLAN["mapping"], PROVENANCE)

    def test_provenance_requires_exact_typed_evidence_bindings(self):
        self.review()
        for change in (lambda p: p.pop("source_test_sha256"), lambda p: p.update(extra="x"),
                       lambda p: p.update(repair_job_id="../"), lambda p: p.update(policy_sha256=None)):
            provenance = dict(PROVENANCE)
            change(provenance)
            with self.assertRaises(ValueError):
                self.service.create_mapping_repair(PARENT, fingerprint(PLAN), {"red": 26, "green": 25}, provenance)

    def test_altered_frozen_contract_cannot_be_re_reviewed_or_used(self):
        self.review()
        folder = self.root/PARENT
        self.rewrite(folder, "contract.json", lambda p: p["steps"][0].update(oled_text="WRONG"))
        for call in (lambda: self.service.get(PARENT), lambda: self.service.contract(PARENT),
                     lambda: self.service.review(PARENT, fingerprint(PLAN))):
            with self.assertRaises(ValueError):
                call()

    def test_original_intent_cannot_sneak_in_alternative_mapping(self):
        folder = self.root/PARENT
        changed = copy.deepcopy(PLAN)
        changed["mapping"] = {"red": 26, "green": 25}
        save(folder/"plan.json", changed)
        self.rewrite(folder, "result.json", lambda p: p.update(plan_sha256=fingerprint(changed)))
        with self.assertRaises(ValueError):
            self.service.get(PARENT)

    def test_resigned_child_behavior_change_is_rejected_against_parent(self):
        candidate = self.repair()
        folder = self.root/candidate["id"]
        plan = json.loads((folder/"plan.json").read_text())
        plan["steps"][0]["text"] = "WRONG"
        save(folder/"plan.json", plan)
        def mutate(result):
            result["plan_sha256"] = fingerprint(plan)
            result["proposal"]["steps"] = copy.deepcopy(plan["steps"])
        self.rewrite(folder, "result.json", mutate)
        with self.assertRaises(ValueError):
            self.service.get(candidate["id"])

    def test_parent_change_invalidates_derived_candidate(self):
        candidate = self.repair()
        folder = self.root/PARENT
        plan = copy.deepcopy(PLAN)
        plan["steps"][1]["text"] = "OTHER"
        save(folder/"plan.json", plan)
        def mutate(result):
            result["plan_sha256"] = fingerprint(plan)
            result["proposal"]["steps"] = copy.deepcopy(plan["steps"])
        self.rewrite(folder, "result.json", mutate)
        with self.assertRaises(ValueError):
            self.service.get(candidate["id"])

    def test_missing_parent_review_or_contract_invalidates_candidate(self):
        candidate = self.repair()
        (self.root/PARENT/"review.json").unlink()
        with self.assertRaises(ValueError):
            self.service.get(candidate["id"])

    def test_contract_symlink_is_rejected(self):
        self.review()
        path = self.root/PARENT/"contract.json"
        data = path.read_bytes()
        path.unlink()
        target = self.root/"contract-copy.json"
        target.write_bytes(data)
        path.symlink_to(target)
        with self.assertRaises(ValueError):
            self.service.contract(PARENT)

    def test_cyclic_ancestry_is_rejected_without_recursion(self):
        candidate = self.repair()
        folder = self.root/candidate["id"]
        self.rewrite(folder, "result.json", lambda p: p.update(parent_id=candidate["id"]))
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            self.service.get(candidate["id"])


if __name__ == "__main__":
    unittest.main()
