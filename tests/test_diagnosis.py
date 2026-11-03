"""Mocked Meta responses for run explanations; these are not model or physical results."""
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from sparkbench.diagnosis import evidence_packet, explain_run, select_frames, validate_reply
from sparkbench.meta import Config
from sparkbench.dashboard.diagnosis import ExplanationService
from sparkbench.dashboard.planning import BusyError
from sparkbench.dashboard.server import DashboardServer
from test_dashboard import fixture

REPLY = {"diagnosis": "In the mismatch frame the red LED is lit where green was expected and green is dark where it should be lit, which is what swapped LED wires look like.",
         "confidence": "high", "evidence": ["frame-000001.jpg"],
         "hypotheses": ["The GPIO25 and GPIO26 signal wires are plugged into each other's LED."],
         "next_check": "With USB unplugged, follow the wire from GPIO25 and confirm it reaches the red LED's resistor.",
         "cannot_determine": ["Whether the resistors are the right value."]}


def response(value=REPLY, status=200, finish="stop"):
    return Mock(status_code=status, json=Mock(return_value={"choices": [{"finish_reason": finish, "message": {"content": json.dumps(value)}}],
                                                            "usage": {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}}))


def config():
    return Config("private-key", "muse-spark-1.3-contributor")


class PacketTests(unittest.TestCase):
    def setUp(self): self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_story_frames_are_mismatches_first_then_contrast_and_packet_has_no_verdict_logic(self):
        run = fixture(self.root, kind="negative").load("fixture")
        self.assertEqual(run["behavior_verdict"], "fail")
        ids = select_frames(run)
        self.assertTrue(ids and len(ids) <= 3)
        packet = evidence_packet(run, ids)
        self.assertEqual(set(packet), {"run", "bench", "expected_steps", "counts", "findings", "unknowns", "frames"})
        text = json.dumps(packet).lower()
        for word in ("threshold", "policy", "calibration", "verdict_logic", "api_key"):
            self.assertNotIn(word, text)
        self.assertEqual(packet["expected_steps"][0]["expected"]["oled_text"], "GREEN")
        self.assertEqual(packet["frames"][0]["name"], run["frames"][ids[0] - 1]["file"])

    def test_incomplete_run_selects_unknown_frames(self):
        run = fixture(self.root, verdict="incomplete", unknown=True).load("fixture")
        ids = select_frames(run)
        self.assertTrue(ids)
        self.assertIsNone(run["frames"][ids[0] - 1]["observed"]["oled_text"])


class ExplainTests(unittest.TestCase):
    def setUp(self): self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def run_and_images(self, **kw):
        store = fixture(self.root, **kw); run = store.load("fixture")
        ids = select_frames(run)
        return run, [(run["frames"][i - 1]["file"], store.image("fixture", i)) for i in ids]

    def test_explained_result_is_advisory_saved_with_hashes_and_redacted(self):
        run, images = self.run_and_images(kind="negative")
        post = Mock(return_value=response()); out = self.root / "explain"
        result = explain_run(run, images, out, config=config(), post=post)
        self.assertEqual(result["status"], "explained"); self.assertEqual(post.call_count, 1)
        self.assertTrue(result["advisory"]); self.assertFalse(result["verdict_changed"])
        self.assertEqual(result["physical_verification"], "not_performed")
        self.assertEqual(result["explanation"]["evidence"], ["frame-000001.jpg"])
        self.assertEqual(result["usage"]["total_tokens"], 1020)
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["response_format"]["json_schema"]["strict"], True)
        self.assertEqual(len([c for c in sent["messages"][1]["content"] if c["type"] == "image_url"]), len(images))
        for f in out.glob("*.json"):
            self.assertNotIn("private-key", f.read_text())
        self.assertNotIn("base64", (out / "request.json").read_text())
        manifest = json.loads((out / "integrity.json").read_text())["sha256"]
        self.assertIn("result.json", manifest); self.assertIn("response.json", manifest)

    def test_citing_an_unsupplied_frame_or_no_frame_is_invalid(self):
        run, images = self.run_and_images(kind="negative")
        for bad in ({**REPLY, "evidence": ["frame-000099.jpg"]}, {**REPLY, "evidence": []}, {**REPLY, "confidence": "certain"}, {**REPLY, "extra": 1}):
            with self.assertRaises(ValueError):
                validate_reply(bad, [n for n, _ in images])
        post = Mock(return_value=response({**REPLY, "evidence": ["frame-000099.jpg"]}))
        result = explain_run(run, images, self.root / "bad", config=config(), post=post)
        self.assertEqual(result["status"], "invalid_response"); self.assertIsNone(result["explanation"])

    def test_http_errors_and_truncation_never_retry(self):
        for code, finish in [(429, "stop"), (503, "stop"), (200, "length")]:
            run, images = self.run_and_images(kind="negative")
            post = Mock(return_value=response(status=code, finish=finish))
            result = explain_run(run, images, self.root / f"out-{code}-{finish}", config=config(), post=post)
            self.assertIn(result["status"], ("error", "invalid_response")); self.assertEqual(post.call_count, 1)
            self.assertIsNone(result["explanation"])

    def test_passing_run_other_model_and_bad_frames_block_before_network(self):
        post = Mock()
        run, images = self.run_and_images(kind="led_oled", verdict="pass")
        with self.assertRaises(ValueError): explain_run(run, images, self.root / "a", config=config(), post=post)
        run, images = self.run_and_images(kind="negative")
        with self.assertRaises(ValueError): explain_run(run, images, self.root / "b", config=Config("key", "other-model"), post=post)
        with self.assertRaises(ValueError): explain_run(run, [(images[0][0], b"not a jpeg")], self.root / "c", config=config(), post=post)
        post.assert_not_called()


class ServiceTests(unittest.TestCase):
    def setUp(self): self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def generator(self, run, images, out):
        return explain_run(run, images, out, config=config(), post=Mock(return_value=response()))

    def wait(self, service, job):
        for _ in range(200):
            r = service.get(job)
            if r["status"] != "generating": return r
            time.sleep(.01)
        self.fail("Mock job did not finish")

    def test_jobs_are_serialized_deduplicated_saved_and_listed_per_run(self):
        store = fixture(self.root, kind="negative"); gate = threading.Event(); calls = []
        def generate(run, images, out):
            calls.append(run["id"]); gate.wait(3); return self.generator(run, images, out)
        service = ExplanationService(self.root / "diagnosis", store, generate)
        job = service.start("fixture", "a" * 32)
        self.assertEqual(service.start("fixture", "a" * 32), job)
        with self.assertRaises(BusyError): service.start("fixture", "b" * 32)
        gate.set(); self.assertEqual(self.wait(service, job)["status"], "explained"); self.assertEqual(len(calls), 1)
        fresh = ExplanationService(self.root / "diagnosis", store, generate)
        listed = fresh.list_for_run("fixture")
        self.assertEqual([x["id"] for x in listed], [job]); self.assertEqual(listed[0]["explanation"]["confidence"], "high")
        self.assertEqual(fresh.get(job)["status"], "explained")
        (self.root / "diagnosis/fixture" / job / "result.json").write_text("{}")
        with self.assertRaises(ValueError): fresh.get(job)

    def test_passing_run_and_unknown_run_are_refused_without_a_job(self):
        service = ExplanationService(self.root / "diagnosis", fixture(self.root, verdict="pass"), self.generator)
        with self.assertRaises(ValueError): service.start("fixture", "c" * 32)
        with self.assertRaises(KeyError): service.start("missing", "d" * 32)
        self.assertIsNone(service.active)

    def test_generator_failure_is_safe_and_releases_the_worker(self):
        def bad(*args): raise RuntimeError("private-token-must-not-be-serialized")
        service = ExplanationService(self.root / "diagnosis", fixture(self.root, kind="negative"), bad)
        job = service.start("fixture", "e" * 32); r = self.wait(service, job)
        self.assertEqual(r["status"], "error"); self.assertIsNone(service.active)
        self.assertNotIn("private-token", json.dumps(r))
        self.assertNotIn("private-token", (self.root / "diagnosis/fixture" / job / "result.json").read_text())


class HTTPTests(unittest.TestCase):
    def test_only_session_authorized_post_can_request_an_explanation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); store = fixture(root, kind="negative"); post = Mock(return_value=response())
            explanations = ExplanationService(root / "diagnosis", store, lambda run, images, out: explain_run(run, images, out, config=config(), post=post))
            server = DashboardServer(0, store, explanations=explanations)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            origin = f"http://127.0.0.1:{server.server_port}"
            def request(path, method="GET", body=None, headers=None):
                c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers or {})
                r = c.getresponse(); value = json.loads(r.read()); c.close(); return r.status, value
            try:
                self.assertEqual(request("/api/runs/fixture/explanations")[1]["explanations"], []); post.assert_not_called()
                token = request("/api/session")[1]["session_token"]
                payload = {"request_id": "f" * 32}
                self.assertEqual(request("/api/runs/fixture/explain", "POST", payload)[0], 403); post.assert_not_called()
                headers = {"Origin": origin, "X-SparkBench-Session": token, "Content-Type": "application/json"}
                self.assertEqual(request("/api/runs/missing/explain", "POST", payload, headers)[0], 404)
                status, job = request("/api/runs/fixture/explain", "POST", payload, headers); self.assertEqual(status, 202)
                self.assertEqual(request("/api/runs/fixture/explain", "POST", payload, headers)[1]["id"], job["id"])
                for _ in range(200):
                    _, result = request("/api/explanations/" + job["id"])
                    if result["status"] != "generating": break
                    time.sleep(.01)
                self.assertEqual(result["status"], "explained"); self.assertEqual(post.call_count, 1)
                self.assertEqual(request("/api/runs/fixture/explanations")[1]["explanations"][0]["id"], job["id"])
                self.assertEqual(request("/api/runs/fixture")[1]["behavior_verdict"], "fail")
            finally:
                server.shutdown(); server.server_close(); server.execution.shutdown()
