"""Mocked guide/image/HTTP tests. These do not establish physical correctness."""
import base64
import copy
import http.client
import json
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from sparkbench.guide import ask_guide,image_bytes,validate_reply
from sparkbench.meta import Config
from sparkbench.dashboard.projects import ProjectService
from sparkbench.dashboard.server import DashboardServer
from sparkbench.dashboard.planning import BusyError
from test_dashboard import fixture

REPLY={'decision':'planned','title':'Desk status','summary':'Three visible status stages.','answer':'We can build this with the supported kit.','questions':[],
       'components':[{'id':'esp32','quantity':1,'purpose':'Runs the firmware','optional':False},{'id':'oled','quantity':1,'purpose':'Shows status','optional':False}],
       'visible':[],'uncertain':['Exact module identity needs labels.'],'next_step':'Read the board labels with power disconnected.',
       'goals':['Green READY, red BUSY, then both off DONE; three seconds per stage.'],'firmware_instruction':'Show READY with green only, BUSY with red only, then DONE with both off. Each stage lasts three seconds.'}
CONFIG=Config('private-guide-token','muse-spark-1.3-contributor')

def image_item():
    # Header fixture is only for parser tests; never presented as a real photo.
    data=b'\x89PNG\r\n\x1a\n'+(13).to_bytes(4,'big')+b'IHDR'+struct.pack('>II',2,2)+bytes(20)
    return {'name':'synthetic.png','data':base64.b64encode(data).decode()}

def response(value=REPLY,code=200,finish='stop'):
    return Mock(status_code=code,json=Mock(return_value={'choices':[{'finish_reason':finish,'message':{'content':json.dumps(value)}}],'usage':{'total_tokens':222}}))

class GuideTests(unittest.TestCase):
    def test_image_type_size_and_dimensions_are_bounded(self):
        meta,data=image_bytes(image_item());self.assertEqual(meta['mime'],'image/png')
        for item in [{'name':'x.svg','data':base64.b64encode(b'<svg>'+bytes(40)).decode()},{'name':'x','data':'not base64!'}, {'name':'x','data':base64.b64encode(data[:16]+struct.pack('>II',50000,50000)+bytes(20)).decode()}]:
            with self.assertRaises(ValueError):image_bytes(item)
    def test_model_cannot_add_parts_or_invent_visible_details_without_photo(self):
        for defect in ['parts','visible','instruction','fields','quantity']:
            value=copy.deepcopy(REPLY)
            if defect=='parts':value['components'][0]['id']='arbitrary-motor'
            elif defect=='visible':value['visible']=['I can see your wiring']
            elif defect=='instruction':value['decision']='unsupported'
            elif defect=='fields':value['verdict']='pass'
            else:value['components'][0]['quantity']=True
            with self.assertRaises(ValueError):validate_reply(value)
    def test_text_request_is_single_meta_call_and_has_no_hardware_actions(self):
        with tempfile.TemporaryDirectory() as d:
            post=Mock(return_value=response());out=Path(d)/'turn';r=ask_guide({'idea':'desk status'},'Help me plan',[],out,config=CONFIG,post=post)
            self.assertEqual(r['status'],'complete');self.assertEqual(post.call_count,1);self.assertEqual(r['usage']['total_tokens'],222)
            self.assertEqual(r['hardware_actions'],[]);self.assertEqual(r['physical_verification'],'not_performed')
            self.assertFalse(post.call_args.kwargs['allow_redirects']);self.assertNotIn('tools',post.call_args.kwargs['json'])
            for p in out.glob('*.json'):self.assertNotIn(CONFIG.api_key,p.read_text())
    def test_photo_bytes_are_sent_only_for_explicit_turn_and_audit_is_redacted(self):
        with tempfile.TemporaryDirectory() as d:
            value=copy.deepcopy(REPLY);value['visible']=['A synthetic test fixture'];post=Mock(return_value=response(value));out=Path(d)/'turn'
            r=ask_guide({},'Inspect this',[image_item()],out,config=CONFIG,post=post)
            self.assertEqual(r['status'],'complete');content=post.call_args.kwargs['json']['messages'][1]['content']
            self.assertTrue(content[1]['image_url']['url'].startswith('data:image/png;base64,'))
            self.assertNotIn(image_item()['data'],(out/'request.json').read_text());self.assertTrue((out/'image-1.png').exists())
    def test_http_failure_invalid_response_and_truncation_do_not_retry(self):
        for code,finish in [(429,'stop'),(503,'stop'),(200,'length')]:
            with tempfile.TemporaryDirectory() as d:
                post=Mock(return_value=response(code=code,finish=finish));r=ask_guide({},'Help',[],Path(d)/'out',config=CONFIG,post=post)
                self.assertIn(r['status'],('error','invalid_response'));self.assertEqual(post.call_count,1)
    def test_credential_in_text_is_rejected_before_network_or_storage(self):
        with tempfile.TemporaryDirectory() as d:
            post=Mock();out=Path(d)/'out'
            with self.assertRaises(ValueError):ask_guide({},CONFIG.api_key,[],out,config=CONFIG,post=post)
            self.assertFalse(out.exists());post.assert_not_called()

class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.planner=Mock();self.planner.start.return_value='b'*32;self.calls=[]
        self.generator=lambda c,m,i,o:ask_guide(c,m,i,o,config=CONFIG,post=Mock(return_value=response()))
        self.service=ProjectService(self.root,self.planner,fixture(self.root),self.generator)
        self.body={'idea':'Desk status indicator','experience':'beginner','budget':'Use my parts','parts_notes':'ESP32','request_id':'a'*32}
        self.id=self.service.create(self.body)
    def tearDown(self):
        for _ in range(300):
            if not self.service.active:break
            time.sleep(.01)
        self.temp.cleanup()
    def ask(self,request_id='c'*32):
        return self.service.ask(self.id,{'message':'Plan this','images':[],'request_id':request_id,'run_id':None})
    def wait(self):
        for _ in range(300):
            p=self.service.get(self.id)
            if not p['busy']:return p
            time.sleep(.01)
        self.fail('Synthetic guide timeout')
    def test_create_and_browse_are_offline_and_ownership_persists(self):
        self.assertEqual(self.service.create(self.body),self.id);self.planner.start.assert_not_called();p=self.service.get(self.id)
        self.service.update(self.id,{'revision':p['revision'],'profile':p['profile'],'owned':{'esp32':1},'completed_steps':['identify']})
        restart=ProjectService(self.root,self.planner,fixture(self.root),Mock());p=restart.get(self.id)
        self.assertEqual(p['owned'],{'esp32':1});self.assertEqual(p['completed_steps'],['identify']);restart.generator.assert_not_called()
    def test_duplicate_turn_is_not_sent_twice_and_changed_duplicate_is_rejected(self):
        gate=threading.Event();original=self.generator
        self.service.generator=lambda *args:(gate.wait(2),original(*args))[1]
        turn=self.ask();self.assertEqual(self.ask(),turn)
        with self.assertRaises(BusyError):self.ask('d'*32)
        with self.assertRaises(ValueError):self.service.ask(self.id,{'message':'Changed','images':[],'request_id':'c'*32,'run_id':None})
        gate.set();self.assertEqual(self.wait()['turns'][0]['status'],'complete')
    def test_accepted_brief_stays_fixed_across_later_advice(self):
        first=self.ask();self.wait();accepted=self.service.accept(self.id,first)['accepted'];self.ask('d'*32);self.wait()
        self.assertEqual(self.service.get(self.id)['accepted'],accepted)
        with self.assertRaises(ValueError):self.service.firmware(self.id,{'accepted_sha256':'changed','request_id':'e'*32})
        proposal=self.service.firmware(self.id,{'accepted_sha256':accepted['sha256'],'request_id':'e'*32})
        self.assertEqual(proposal,'b'*32);self.planner.start.assert_called_once_with(REPLY['firmware_instruction'],'e'*32)
    def test_stale_edits_and_unsupported_inventory_are_rejected(self):
        p=self.service.get(self.id);body={'revision':p['revision'],'profile':p['profile'],'owned':{},'completed_steps':[]};self.service.update(self.id,body)
        with self.assertRaises(ValueError):self.service.update(self.id,body)
        body.update(revision=p['revision']+1,owned={'motor':1})
        with self.assertRaises(ValueError):self.service.update(self.id,body)
    def test_historical_test_context_preserves_its_own_frozen_expectations(self):
        generator=Mock(wraps=self.generator);self.service.generator=generator
        self.service.ask(self.id,{'message':'Explain this older test','images':[],'request_id':'f'*32,'run_id':'fixture'});self.wait()
        evidence=generator.call_args.args[0]['recorded_test']
        self.assertEqual(evidence['expected_steps'][0]['oled_text'],'GREEN')
        self.assertTrue(evidence['project_binding'].startswith('Unlinked historical run'))
        self.assertEqual(evidence['evaluated_sample_count'],2)
    def test_uploaded_image_bytes_and_checksum_bind_to_saved_turn(self):
        turn=self.service.ask(self.id,{'message':'Check this synthetic photo','images':[image_item()],'request_id':'f'*32,'run_id':None});self.wait()
        data,mime=self.service.image(self.id,turn,'image-1.png');self.assertEqual(mime,'image/png')
        self.assertEqual(data,base64.b64decode(image_item()['data']))
        (self.service._turn(self.id,turn)/'image-1.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.service.image(self.id,turn,'image-1.png')
    def test_project_and_turn_tampering_is_visible_and_paths_are_bounded(self):
        self.ask();self.wait();folder=self.service.folder(self.id);(folder/'project.json').write_text('{}')
        with self.assertRaises(ValueError):self.service.get(self.id)
        with self.assertRaises(KeyError):self.service.get('../private')
    def test_failure_has_no_raw_exception_or_automatic_retry(self):
        self.service.generator=Mock(side_effect=RuntimeError('private-guide-token'))
        self.ask();p=self.wait();self.assertEqual(p['turns'][0]['status'],'error');self.assertNotIn('private-guide-token',json.dumps(p));self.assertEqual(self.service.generator.call_count,1)

class ProjectHTTPTests(unittest.TestCase):
    def test_projects_require_session_for_mutations_and_never_execute_on_browse(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);store=fixture(root);planner=Mock();projects=ProjectService(root,planner,store,Mock());server=DashboardServer(0,store,projects=projects)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin=f'http://127.0.0.1:{server.server_port}'
            def req(path,method='GET',body=None,headers=None):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);c.request(method,path,json.dumps(body) if body is not None else None,headers or {});r=c.getresponse();data=json.loads(r.read());c.close();return r.status,data
            body={'idea':'Desk indicator','experience':'beginner','budget':'','parts_notes':'','request_id':'a'*32}
            try:
                self.assertEqual(req('/api/projects')[1]['projects'],[]);token=req('/api/session')[1]['session_token']
                self.assertEqual(req('/api/projects','POST',body)[0],403)
                headers={'Origin':origin,'X-SparkBench-Session':token,'Content-Type':'application/json'}
                self.assertEqual(req('/api/projects','POST',body,{**headers,'Origin':'https://external.invalid'})[0],403)
                code,p=req('/api/projects','POST',body,headers);self.assertEqual(code,201)
                self.assertEqual(req('/api/projects/'+p['id'])[1]['idea'],body['idea']);projects.generator.assert_not_called();planner.start.assert_not_called()
                self.assertEqual(req('/api/projects/'+p['id']+'/accept','POST',{'turn_id':'b'*32},headers)[0],404)
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
