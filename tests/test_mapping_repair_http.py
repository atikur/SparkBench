"""Local HTTP authorization/routing only; all bench/model operations are mocked."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from sparkbench.dashboard.evidence import EvidenceStore
from sparkbench.dashboard.planning import PlanningService
from sparkbench.dashboard.server import DashboardServer


class MappingRepairHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.execution = Mock()
        self.execution.repair_eligibility.return_value = {"eligible": False, "reason": "Unknown camera readings"}
        self.execution.start_repair.return_value = "b" * 32
        self.execution.approve_repair.return_value = {"id": "c" * 32, "origin": "mapping_repair", "review_status": "reviewed"}
        self.projects = Mock()
        self.server = DashboardServer(0, EvidenceStore(root, ()), PlanningService(root / "plans"),
                                      self.execution, self.projects)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
        self.temp.cleanup()

    def request(self, path, body=None, authorized=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers.update(Origin="http://127.0.0.1:" + str(self.server.server_port))
            headers["X-SparkBench-Session"] = self.server.session_token
        conn.request("POST" if body is not None else "GET", path,
                     json.dumps(body) if body is not None else None, headers)
        reply = conn.getresponse(); data = reply.read(); status = reply.status; conn.close()
        return status, data

    def test_read_only_eligibility_and_static_script_never_probe(self):
        status, data = self.request("/api/repairs/eligibility/" + "a" * 32)
        self.assertEqual(status, 200); self.assertFalse(json.loads(data)["eligible"])
        self.execution.start_repair.assert_not_called()
        status, data = self.request("/mapping-repair.js")
        self.assertEqual(status, 200); self.assertIn(b"Approve", data)

    def test_probe_and_approval_require_local_session(self):
        for route in ("/api/repairs", "/api/repairs/" + "b" * 32 + "/approve"):
            with self.subTest(route=route):
                self.assertEqual(self.request(route, {}, authorized=False)[0], 403)
        self.execution.start_repair.assert_not_called()
        self.execution.approve_repair.assert_not_called()

    def test_probe_routes_to_one_job_and_approval_links_candidate_only(self):
        body = {"source_test_id": "a" * 32, "request_id": "d" * 32, "port": "synthetic", "device_id": "synthetic"}
        status, data = self.request("/api/repairs", body)
        self.assertEqual(status, 202); self.assertEqual(json.loads(data)["id"], "b" * 32)
        self.execution.start_repair.assert_called_once_with(body)
        status, data = self.request("/api/repairs/" + "b" * 32 + "/approve", {"plan_sha256": "e" * 64})
        self.assertEqual(status, 200)
        self.projects.link_repair.assert_called_once_with(json.loads(data))
        self.execution.start.assert_not_called()  # Approval itself never compiles, installs or tests.


if __name__ == "__main__":
    unittest.main()
