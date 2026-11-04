"""Synthetic saved-file fixtures; no camera, serial, model or physical evidence."""
import copy
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from sparkbench.dashboard.catalog import Run
from sparkbench.dashboard.evidence import EvidenceError, EvidenceStore
from sparkbench.dashboard.server import DashboardServer


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())


def fixture(root, kind="led_oled", verdict="pass", unknown=False):
    folder=root/"runs/test"; capture=folder/"capture"
    spec={"steps":[{"step":1,"red":False,"green":True,"oled_text":"GREEN"}]}
    index=[]; observations=[]
    for i in range(1,4):
        name=f"frame-{i:06d}.jpg";image=b'\xff\xd8\xffsynthetic fixture '+str(i).encode()
        write(capture/"camera"/name,image)
        index.append({"frame":i,"file":name,"sample_pts_seconds":10+i*.2})
        if i<3:
            observations.append({"file":name,"sample_pts_seconds":10+i*.2,"sha256":hashlib.sha256(image).hexdigest(),
                                 "red":kind=="negative","green":kind!="negative","oled_text":None if unknown or kind=="negative" else "GREEN"})
    write(folder/"spec.json",spec)
    write(capture/"camera/capture.json",{"source":"live_camera","status":"captured","frame_count":3,"started_at_utc":"2026-11-03T10:00:00Z","camera":{"name":"Synthetic fixture"}})
    write(capture/"camera/frames.jsonl",b"\n".join(json.dumps(r).encode() for r in index)+b"\n")
    report={"status":"pass" if kind=="negative" else verdict,"source_run":str(capture),
            "spec_sha256":hashlib.sha256((folder/"spec.json").read_bytes()).hexdigest(),"windows":[{"step":1,"measurements":observations}],"failures":[],"unknowns":["unreadable"] if unknown else []}
    if kind=="negative": report.update(led_behavior_comparison="fail",mismatches=["red","green"])
    write(folder/"report.json",report);write(folder/"reader-policy.snapshot.json",{"model":"synthetic-mocked"})
    seal(folder)
    return EvidenceStore(root,(Run("fixture","Fixture","Synthetic fixture","runs/test","runs/test/capture","report.json","spec.json",kind),))


def seal(folder):
    write(folder/"integrity.json",{"sha256":{str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file() and p.name!='integrity.json'}})


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_frame_values_and_expectations_bind_to_saved_spec(self):
        store=fixture(self.root);run=store.load("fixture")
        self.assertEqual(run["evaluated_sample_count"],2)
        self.assertEqual(run["frames"][0]["expected"]["oled_text"],"GREEN")
        self.assertFalse(run["frames"][0]["observed"]["red"])
        self.assertFalse(run["frames"][2]["evaluated"])
        self.assertIsNone(run["frames"][2]["observed"])
        self.assertIsNone(run["servo_angle_deg"])
        self.assertFalse(run["capabilities"]["hardware_actions"])
        self.assertEqual(run["model_activity"]["new_requests"],0)
        self.assertTrue(store.image("fixture",1).startswith(b'\xff\xd8\xff'))

    def test_negative_success_is_behavior_failure_not_hardware_pass(self):
        run=fixture(self.root,"negative").load("fixture")
        self.assertEqual(run["behavior_verdict"],"fail")
        self.assertEqual(run["qualification_outcome"],"fault_detected")
        self.assertEqual(run["mismatch_count"],2)
        self.assertFalse(run["oled_evaluated"])
        self.assertIsNone(run["frames"][0]["observed"]["oled_text"])

    def test_unknown_is_not_off_zero_or_pass(self):
        run=fixture(self.root,verdict="incomplete",unknown=True).load("fixture")
        self.assertEqual(run["behavior_verdict"],"incomplete")
        self.assertEqual(run["unknown_count"],1)
        self.assertIsNone(run["frames"][0]["observed"]["oled_text"])

    def test_geometry_rejection_does_not_claim_model_transcription(self):
        store=fixture(self.root,verdict="incomplete",unknown=True);folder=self.root/'runs/test'
        report=json.loads((folder/'report.json').read_text())
        for w in report['windows']:
            for observation in w['measurements']:observation['geometry_supported']=False
        write(folder/'report.json',report);seal(folder);run=store.load('fixture')
        self.assertIsNone(run['model_activity']['model'])
        self.assertEqual(run['model_activity']['role'],'No model requests: camera geometry rejected')

    def test_corrupt_report_or_missing_evidence_is_unavailable(self):
        store=fixture(self.root);(self.root/'runs/test/report.json').write_text('{}')
        self.assertFalse(store.list_runs()[0]["available"])
        with self.assertRaises(EvidenceError):store.load("fixture")
        (self.root/'runs/test/report.json').unlink()
        self.assertFalse(store.list_runs()[0]["available"])

    def test_changed_image_is_refused_even_after_other_metadata_loads(self):
        store=fixture(self.root);store.load("fixture")
        image=self.root/'runs/test/capture/camera/frame-000001.jpg';image.write_bytes(b'changed')
        with self.assertRaisesRegex(EvidenceError,"checksum"):store.image("fixture",1)

    def test_resealed_image_still_must_match_observation_hash(self):
        store=fixture(self.root)
        (self.root/'runs/test/capture/camera/frame-000001.jpg').write_bytes(b'\xff\xd8\xffchanged')
        seal(self.root/'runs/test')
        with self.assertRaisesRegex(EvidenceError,"measured frame"):store.image("fixture",1)

    def test_duplicate_observations_and_wrong_capture_binding_rejected(self):
        store=fixture(self.root);folder=self.root/'runs/test';report=json.loads((folder/'report.json').read_text())
        modified=copy.deepcopy(report);modified['windows'][0]['measurements'].append(modified['windows'][0]['measurements'][0])
        write(folder/'report.json',modified);seal(folder)
        with self.assertRaises(EvidenceError):store.load("fixture")
        report['source_run']=str(self.root/'other-capture');write(folder/'report.json',report);seal(folder)
        with self.assertRaisesRegex(EvidenceError,"capture binding"):store.load("fixture")

    def test_symlink_and_unknown_run_never_expose_other_files(self):
        store=fixture(self.root);image=self.root/'runs/test/capture/camera/frame-000001.jpg'
        write(self.root/'private.txt',b'private fixture');image.unlink();image.symlink_to(self.root/'private.txt')
        with self.assertRaises(EvidenceError):store.image("fixture",1)
        with self.assertRaises(KeyError):store.load('../private.txt')


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=fixture(Path(self.temp.name))
        self.server=DashboardServer(0,self.store);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path,method="GET",headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        connection.request(method,path,headers=headers or {});response=connection.getresponse();status=response.status;body=response.read();headers=dict(response.getheaders());connection.close();return status,body,headers
    def test_read_only_api_and_static_page(self):
        self.assertEqual(self.request('/')[0],200)
        status,body,headers=self.request('/api/runs');self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['runs'][0]['id'],'fixture')
        self.assertEqual(self.request('/api/runs/fixture/frames/1/image')[2]['X-SparkBench-Image-Integrity'],'verified')
        for method in ['POST','PUT','DELETE','PATCH','OPTIONS']:
            self.assertEqual(self.request('/api/run',method)[0],405)
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
    def test_csp_allows_the_stylesheet_hosts_the_page_uses(self):
        import re
        html=self.request('/')[1].decode()
        csp=self.request('/')[2]['Content-Security-Policy']
        style_src=next(part for part in csp.split(';') if part.strip().startswith('style-src'))
        for host in set(re.findall(r'<link rel="stylesheet" href="(https://[^/"]+)',html)):
            self.assertIn(host,style_src,'the page links a stylesheet the CSP blocks: '+host)
        if 'fonts.googleapis.com' in style_src:
            self.assertIn('https://fonts.gstatic.com',csp,'Google Fonts stylesheets load fonts from fonts.gstatic.com')
    def test_origin_host_and_path_restrictions(self):
        self.assertEqual(self.request('/api/runs',headers={'Origin':'https://outside.invalid'})[0],403)
        self.assertEqual(self.request('/api/runs',headers={'Host':'outside.invalid'})[0],403)
        self.assertEqual(self.request('/api/runs',headers={'Sec-Fetch-Site':'cross-site'})[0],403)
        for path in ['/.env','/../../.env','/%2e%2e/.env','/api/runs/fixture?path=.env','/api/runs/fixture/frames/0/image']:
            self.assertIn(self.request(path)[0],(400,404))


class StaticPageTests(unittest.TestCase):
    def test_suggest_ideas_is_on_the_home_page_and_only_fills_the_box(self):
        static=Path(__file__).parent.parent/'src/sparkbench/dashboard/static'
        html=(static/'index.html').read_text();script=(static/'projects.js').read_text()
        self.assertIn('id="idea-suggest"',html)
        self.assertIn("planningPost('/api/idea/suggest'",script)
        self.assertIn("$('home-idea').value=chip.dataset.idea",script)
    def test_the_project_page_keeps_wiring_and_drops_the_chat(self):
        static=Path(__file__).parent.parent/'src/sparkbench/dashboard/static'
        html=(static/'index.html').read_text();script=(static/'projects.js').read_text()
        for gone in ('guide-question-form','guide-conversation','guide-photos','build-kit-card','guide-assembly'):
            self.assertNotIn(gone,html+script)
        for kept in ('open-bench','bench-dialog','fix-wiring','result-wiring'):
            self.assertIn('id="%s"'%kept,html)
        self.assertEqual(html.count('src="/wiring.svg"'),3)
        self.assertIn('images:[]',script)
        scripts=''.join(path.read_text() for path in static.glob('*.js'))
        for name in ('clearProjectPhotos','renderAttachments','attachFile','listText','projectPhotos','guideCapture'):
            self.assertNotIn(name,scripts)
    def test_every_function_the_page_scripts_call_exists(self):
        # A removed helper fails only when its button is pressed, so catch it here.
        import re
        static=Path(__file__).parent.parent/'src/sparkbench/dashboard/static'
        code='\n'.join(path.read_text() for path in static.glob('*.js'))
        defined=set(re.findall(r'(?:function\s+|(?:const|let|var)\s+|,\s*)([A-Za-z_$][\w$]*)\s*(?==|\()',code))
        for params in re.findall(r'function\s*\w*\(([^)]*)\)',code):
            defined.update(p.split('=')[0].strip() for p in params.split(','))
        builtin=set('if for while switch catch return function typeof await async new parseFloat parseInt setTimeout clearTimeout setInterval clearInterval fetch String Number Boolean Array Object JSON Math Date Promise Set Map URL File Blob Error matchMedia atob btoa encodeURIComponent decodeURIComponent isNaN createImageBitmap requestAnimationFrame super constructor AudioContext AudioWorkletNode AudioWorkletProcessor registerProcessor Float32Array Uint8Array ArrayBuffer DataView AbortController Response MutationObserver process sampleRate getComputedStyle of Spark border'.split())
        called=set(re.findall(r"(?<![.\w$'\"])([A-Za-z_$][\w$]*)\s*\(",code))
        self.assertEqual(called-defined-builtin,set())
    """The page is plain scripts sharing one scope, so a clash fails silently in the browser."""
    STATIC=Path(__file__).resolve().parents[1]/"src/sparkbench/dashboard/static"
    def scripts(self):
        return {p.name:p.read_text() for p in self.STATIC.glob("*.js")}
    def ids(self):
        import re
        return re.findall(r'\bid="([^"]+)"',(self.STATIC/"index.html").read_text())
    def test_page_ids_are_unique(self):
        ids=self.ids();self.assertEqual(sorted(i for i in set(ids) if ids.count(i)>1),[])
    def test_every_element_a_script_asks_for_exists(self):
        import re
        ids=set(self.ids())
        missing={m for s in self.scripts().values() for m in re.findall(r"\$\('([\w-]+)'\)",s)}-ids
        self.assertEqual(sorted(missing),[])
    def test_every_button_on_the_page_has_a_handler(self):
        import re
        html=(self.STATIC/"index.html").read_text();scripts="".join(self.scripts().values())
        buttons=re.findall(r'<button[^>]*\bid="([^"]+)"[^>]*type="button"',html)
        unhandled=[b for b in buttons if "'"+b+"'" not in scripts]
        self.assertEqual(unhandled,[])
    def test_page_loads_runs_on_startup(self):
        self.assertIn("loadRuns();",self.scripts()["app.js"].splitlines()[-1])
    def test_every_script_parses(self):
        import shutil,subprocess
        node=shutil.which("node")
        if not node:self.skipTest("node is not installed")
        for path in self.STATIC.glob("*.js"):
            result=subprocess.run([node,"--check",str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,path.name+": "+result.stderr[-300:])
    def test_no_two_scripts_define_the_same_top_level_function(self):
        import re
        seen={}
        for name,source in self.scripts().items():
            for fn in re.findall(r"^(?:async )?function (\w+)\(",source,re.M):
                self.assertNotIn(fn,seen,fn+" is defined in "+name+" and "+seen.get(fn,""));seen[fn]=name


if __name__=='__main__':unittest.main()
