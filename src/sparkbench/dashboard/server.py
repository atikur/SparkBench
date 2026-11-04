"""Local project guide, Meta planning, firmware and physical evidence workspace."""
import argparse
import json
import mimetypes
import re
import secrets
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .evidence import EvidenceError, EvidenceStore
from .planning import BusyError, PlanningService
from .diagnosis import ExplanationService
from .execution import ExecutionService
from .projects import ProjectService
from ..guide import CATALOG, ASSEMBLY
from ..ideas import IdeaError, suggest_ideas
from ..meta import configuration
from ..sam_regions import propose_regions
from ..voice import MAX_VOICE_BYTES, VoiceServiceError, transcribe_idea

STATIC = Path(__file__).with_name("static")
ASSETS = {"/": "index.html", "/app.js": "app.js", "/planning.js": "planning.js", "/execution.js":"execution.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg"}
ASSETS['/projects.js']='projects.js'
ASSETS['/wiring.svg']='wiring.svg'
ASSETS['/lifecycle.js']='lifecycle.js'
ASSETS['/explain.js']='explain.js'
ASSETS['/flow.js']='flow.js'
ASSETS['/autopilot.js']='autopilot.js'
ASSETS['/mapping-repair.js']='mapping-repair.js'
ASSETS['/camera-regions.js']='camera-regions.js'
ASSETS['/idea-voice.js']='idea-voice.js'
ASSETS['/idea-recorder.js']='idea-recorder.js'


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=8765, store=None, planner=None, execution=None, projects=None, explanations=None):
        self.store = store or EvidenceStore()
        self.explanations = explanations or ExplanationService(self.store.root/"runs/diagnosis", self.store)
        self.planner = planner or PlanningService(self.store.root/"runs/planning/intent-v1")
        self.execution = execution or ExecutionService(self.store.root,self.planner,self.store)
        self.projects = projects or ProjectService(self.store.root,self.planner,self.store,execution=self.execution)
        self.session_token = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "SparkBench"

    def log_message(self, *args):
        pass

    def send_data(self, status, data, content_type="application/json; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' blob:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        for k,v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, status, value):
        self.send_data(status, json.dumps(value, allow_nan=False).encode())

    def local_request(self, mutation=False):
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "").lower() not in allowed:
            self.json(403, {"error": "Local Host header required"});return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://"+host for host in allowed}:
            self.json(403, {"error": "Local origin required"});return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.json(403, {"error": "Cross-site access rejected"});return False
        if mutation and (not origin or not secrets.compare_digest(self.headers.get("X-SparkBench-Session", ""), self.server.session_token)):
            self.json(403, {"error": "Local session and origin required"});return False
        return True

    def do_GET(self):
        if not self.local_request(): return
        url = urlsplit(self.path)
        path = unquote(url.path)
        if url.query:
            self.json(400, {"error": "Query parameters are unsupported"});return
        try:
            if path in ASSETS:
                asset = STATIC/ASSETS[path]
                self.send_data(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
            elif path == "/api/runs":
                self.server.execution.register_evidence()
                self.json(200, {"mode": "recorded", "runs": self.server.store.list_runs()})
            elif path == "/api/devices":
                self.json(200, self.server.execution.enumerate_devices())
            elif path == "/api/camera/reference":
                self.send_data(200, self.server.execution.reference_image(), "image/jpeg")
            elif match := re.fullmatch(r'/api/camera/reference/([0-9a-f]{32})',path):
                self.send_data(200,self.server.execution.reference_image(match[1]),'image/jpeg')
            elif path == "/api/board":
                self.json(200, self.server.execution.board_summary())
            elif path == '/api/projects':
                self.json(200,{'projects':self.server.projects.list(),'catalog':CATALOG,'assembly':ASSEMBLY})
            elif match := re.fullmatch(r'/api/projects/([0-9a-f]{32})',path):
                self.json(200,self.server.projects.get(match[1]))
            elif match := re.fullmatch(r'/api/projects/([0-9a-f]{32})/firmware-status',path):
                self.json(200,self.server.projects.status(match[1]))
            elif match := re.fullmatch(r'/api/projects/([0-9a-f]{32})/turns/([0-9a-f]{32})/(image-[1-3]\.(?:png|jpg))',path):
                data,mime=self.server.projects.image(*match.groups());self.send_data(200,data,mime)
            elif path == "/api/jobs":
                self.json(200, {"jobs":self.server.execution.list()})
            elif match := re.fullmatch(r'/api/repairs/eligibility/([0-9a-f]{32})',path):
                self.json(200,self.server.execution.repair_eligibility(match[1]))
            elif match := re.fullmatch(r"/api/jobs/([0-9a-f]{32})", path):
                self.json(200, self.server.execution.get(match[1]))
            elif match := re.fullmatch(r'/api/jobs/([0-9a-f]{32})/diagnostics',path):
                self.json(200,self.server.execution.diagnostics(match[1]))
            elif match := re.fullmatch(r'/api/jobs/([0-9a-f]{32})/logs/(\d{1,3})',path):
                self.json(200,self.server.execution.log(match[1],int(match[2])))
            elif match := re.fullmatch(r"/api/jobs/([0-9a-f]{32})/frames/(frame-\d{6}\.jpg)", path):
                self.send_data(200,self.server.execution.image(match[1],match[2]),"image/jpeg")
            elif match := re.fullmatch(r'/api/jobs/([0-9a-f]{32})/(source|source.zip|firmware.bin|compile.log)',path):
                data,mime=self.server.execution.download(*match.groups());self.send_data(200,data,mime)
            elif path == "/api/session":
                try:
                    config = configuration()
                    available = config.model == "muse-spark-1.3-contributor"
                except ValueError:
                    available = False
                self.json(200, {"session_token": self.server.session_token, "planning_available": available,
                                "model": "muse-spark-1.3-contributor", "hardware_actions": True, "servo_actions":False})
            elif path == "/api/plans":
                self.json(200, {"plans": self.server.planner.list()})
            elif match := re.fullmatch(r"/api/plans/([0-9a-f]{32})", path):
                self.json(200, self.server.planner.get(match[1]))
            elif match := re.fullmatch(r"/api/runs/([a-z0-9-]+)", path):
                self.server.execution.register_evidence()
                self.json(200, self.server.store.load(match[1]))
            elif match := re.fullmatch(r"/api/runs/([a-z0-9-]+)/explanations", path):
                self.json(200, {"explanations": self.server.explanations.list_for_run(match[1])})
            elif match := re.fullmatch(r"/api/explanations/([0-9a-f]{32})", path):
                self.json(200, self.server.explanations.get(match[1]))
            elif match := re.fullmatch(r"/api/runs/([a-z0-9-]+)/frames/([1-9][0-9]{0,5})/image", path):
                self.send_data(200, self.server.store.image(match[1], int(match[2])), "image/jpeg", {"X-SparkBench-Image-Integrity": "verified"})
            else:
                self.json(404, {"error": "Unknown route"})
        except KeyError:
            self.json(404, {"error": "Unknown run or frame"})
        except (EvidenceError, OSError, ValueError, TypeError) as exc:
            self.json(409, {"error": str(exc) if isinstance(exc, EvidenceError) else "Evidence unavailable", "behavior_verdict": "unavailable"})

    def do_POST(self):
        path = self.path
        review = re.fullmatch(r"/api/plans/([0-9a-f]{32})/review", path)
        operation = re.fullmatch(r"/api/execute/(compile|install|test|identity)",path)
        cancellation = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/cancel",path)
        project_action=re.fullmatch(r'/api/projects/([0-9a-f]{32})/(update|ask|accept|firmware)',path)
        explain=re.fullmatch(r"/api/runs/([a-z0-9-]+)/explain",path)
        repair_approval=re.fullmatch(r'/api/repairs/([0-9a-f]{32})/approve',path)
        camera_confirmation=re.fullmatch(r'/api/camera/setup/([0-9a-f]{32})/confirm',path)
        camera_suggestion=re.fullmatch(r'/api/camera/setup/([0-9a-f]{32})/regions',path)
        if path not in ("/api/plans",'/api/projects','/api/guide/photo','/api/camera/check','/api/camera/regions','/api/camera/setup','/api/repairs','/api/idea/transcribe','/api/idea/suggest') and not review and not operation and not cancellation and not project_action and not explain and not repair_approval and not camera_confirmation and not camera_suggestion:
            self.method_rejected();return
        if not self.local_request(mutation=True): return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if path == '/api/idea/transcribe':
                if not 1 <= length <= MAX_VOICE_BYTES:
                    self.json(413, {"error": "Record an idea of up to 30 seconds."});return
                if self.headers.get("Content-Type", "").split(";")[0] != "audio/wav":
                    self.json(415, {"error": "WAV audio required"});return
                self.connection.settimeout(10)
                audio = self.rfile.read(length)
                if len(audio) != length:
                    raise ValueError("The audio upload was incomplete.")
                self.json(200, transcribe_idea(audio, output=self.server.store.root/'runs/voice'/uuid.uuid4().hex));return
            maximum = 16384
            if project_action and project_action[2] == 'ask':
                maximum = 25_000_000
            elif path == '/api/camera/regions':
                maximum = 8_500_000
            if not 1 <= length <= maximum:
                self.json(413, {"error": "Request body exceeds the supported size"});return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.json(415, {"error": "JSON body required"});return
            self.connection.settimeout(30)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError("JSON object required")
            if path=='/api/idea/suggest':
                self.json(200,suggest_ideas(body,self.server.store.root/'runs/ideas'/uuid.uuid4().hex))
            elif path=='/api/projects':
                self.json(201,self.server.projects.get(self.server.projects.create(body)))
            elif path=='/api/repairs':
                self.json(202,{'id':self.server.execution.start_repair(body)})
            elif repair_approval:
                proposal=self.server.execution.approve_repair(repair_approval[1],body)
                self.server.projects.link_repair(proposal)
                self.json(200,proposal)
            elif path=='/api/guide/photo':
                self.json(202,{'id':self.server.execution.start_photo(body)})
            elif path == '/api/camera/regions':
                self.json(200, propose_regions(body))
            elif path=='/api/camera/check':
                self.json(202,{'id':self.server.execution.start_view(body)})
            elif path=='/api/camera/setup':
                self.json(202,{'id':self.server.execution.start_camera_setup(body)})
            elif camera_confirmation:
                self.json(202,{'id':self.server.execution.confirm_camera_setup(camera_confirmation[1],body)})
            elif camera_suggestion:
                self.json(200,self.server.execution.suggest_camera_setup(camera_suggestion[1],body))
            elif project_action:
                project_id,action=project_action.groups()
                if action=='update':self.json(200,self.server.projects.update(project_id,body))
                elif action=='ask':self.json(202,{'id':self.server.projects.ask(project_id,body)})
                elif action=='accept':
                    if set(body)!={'turn_id'}:raise ValueError('Guide turn ID required')
                    self.json(200,self.server.projects.accept(project_id,body['turn_id']))
                else:self.json(202,{'id':self.server.projects.firmware(project_id,body)})
            elif explain:
                if set(body)!={"request_id"}:raise ValueError("Request ID required")
                self.server.execution.register_evidence()
                self.json(202,{"id":self.server.explanations.start(explain[1],body["request_id"])})
            elif cancellation:
                if body!={}:raise ValueError("Empty cancellation object required")
                self.json(200,self.server.execution.cancel(cancellation[1]))
            elif operation:
                self.json(202,{"id":self.server.execution.start(operation[1],body)})
            elif review:
                if set(body) != {"plan_sha256"}: raise ValueError("Plan hash required")
                self.json(200, self.server.planner.review(review[1], body["plan_sha256"]))
            else:
                if set(body) != {"instruction", "request_id"}: raise ValueError("Instruction and request ID required")
                job_id = self.server.planner.start(body["instruction"], body["request_id"])
                self.json(202, {"id": job_id})
        except BusyError as exc:
            self.json(409, {"error": str(exc)})
        except KeyError:
            self.json(404, {"error": "Unknown proposal or run"})
        except EvidenceError as exc:
            self.json(409, {"error": str(exc)})
        except IdeaError as exc:
            self.json(502,{"error":str(exc)})
        except VoiceServiceError as exc:
            self.json(502, {"error": str(exc)})
        except (ValueError, TypeError) as exc:
            self.json(400, {"error": str(exc)[:300]})
        except OSError:
            self.json(503, {"error": "Local proposal storage unavailable"})

    def method_rejected(self):
        self.send_data(405, b'{"error":"Read-only dashboard"}', extra={"Allow": "GET"})

    do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = method_rejected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="Local port; binds only to 127.0.0.1")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535")
    try:
        server = DashboardServer(args.port)
    except OSError as exc:
        parser.exit(2, "Cannot start dashboard: "+str(exc)+"\n")
    print(f"SparkBench dashboard: http://127.0.0.1:{server.server_port}", flush=True)
    print("Meta project/photo guidance and explicit LED/OLED build/install/test jobs. Servo unused. Ctrl-C requests cleanup.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.execution.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
