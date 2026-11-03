"""Mocked Meta responses; these tests are not model or physical benchmark results."""
import copy
import hashlib
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from sparkbench.intent import make_request, plan_intent, validate_proposal
from sparkbench.meta import Config
from sparkbench.dashboard.planning import BusyError, PlanningService
from sparkbench.dashboard.server import DashboardServer
from test_dashboard import fixture

READY={"decision":"ready","summary":"Count with parity LEDs, then finish off.","question":None,"steps":[
    {"red":False,"green":True,"text":"0"},{"red":True,"green":False,"text":"1"},
    {"red":False,"green":False,"text":"DONE"}]}


def response(value=READY,status=200,finish="stop"):
    return Mock(status_code=status,json=Mock(return_value={"choices":[{"finish_reason":finish,"message":{"content":json.dumps(value)}}],"usage":{"prompt_tokens":100,"completion_tokens":50,"total_tokens":150}}))


class IntentTests(unittest.TestCase):
    def test_request_has_intent_and_capabilities_without_oracle_or_measurements(self):
        body=make_request("Count zero through one with parity LEDs", "muse-spark-1.3-contributor")
        user=json.loads(body["messages"][1]["content"])
        self.assertEqual(set(user),{"instruction","capability_contract"})
        self.assertNotIn("expected",json.dumps(user));self.assertNotIn("mapping",json.dumps(user))
        self.assertFalse(body.get("tools"))

    def test_ready_is_saved_as_proposal_not_compiled_or_verified(self):
        with tempfile.TemporaryDirectory() as d:
            post=Mock(return_value=response());p=Path(d)/"proposal"
            result=plan_intent("Count zero through one",p,config=Config("private-key","muse-spark-1.3-contributor"),post=post)
            self.assertEqual(result["status"],"ready");self.assertEqual(post.call_count,1)
            self.assertEqual(result["usage"]["total_tokens"],150)
            self.assertEqual(result["physical_verification"],"not_performed")
            self.assertEqual(result["semantic_verification"],"not_performed")
            self.assertFalse(result["compiled"]);self.assertFalse(result["hardware_actions"])
            self.assertFalse(post.call_args.kwargs["allow_redirects"])
            self.assertEqual(json.loads((p/'plan.json').read_text())['mapping'],{'red':25,'green':26})
            for f in p.glob('*.json'):self.assertNotIn('private-key',f.read_text())

    def test_clarification_and_unsupported_have_no_plan(self):
        for decision,question in [('clarify','Which LED should blink?'),('unsupported',None)]:
            with tempfile.TemporaryDirectory() as d:
                value={'decision':decision,'summary':'More information or different hardware needed','question':question,'steps':[]}
                p=Path(d)/'out';r=plan_intent('Blink a light',p,config=Config('key','muse-spark-1.3-contributor'),post=Mock(return_value=response(value)))
                self.assertEqual(r['status'],decision);self.assertFalse((p/'plan.json').exists())

    def test_invalid_limits_and_executable_fields_rejected(self):
        for defect in ['pin','servo','label','bool','count','question','nonready']:
            value=copy.deepcopy(READY)
            if defect=='pin':value['mapping']={'red':27,'green':26}
            elif defect=='servo':value['steps'][0]['pulse_us']=1500
            elif defect=='label':value['steps'][0]['text']='x'*17
            elif defect=='bool':value['steps'][0]['red']=1
            elif defect=='count':value['steps']*=3
            elif defect=='question':value['question']='Should I move?'
            elif defect=='nonready':value['decision']='unsupported'
            with self.assertRaises(ValueError):validate_proposal(value)

    def test_http_errors_and_truncation_never_retry(self):
        for code,finish in [(429,'stop'),(503,'stop'),(200,'length')]:
            with tempfile.TemporaryDirectory() as d:
                post=Mock(return_value=response(status=code,finish=finish));p=Path(d)/'out'
                r=plan_intent('Show DONE with both LEDs off',p,config=Config('key','muse-spark-1.3-contributor'),post=post)
                self.assertIn(r['status'],('error','invalid_response'));self.assertEqual(post.call_count,1);self.assertFalse((p/'plan.json').exists())

    def test_invalid_instruction_and_model_block_before_network(self):
        with tempfile.TemporaryDirectory() as d:
            post=Mock()
            for text in ['',None,'x'*2001,'bad\0text']:
                with self.assertRaises(ValueError):plan_intent(text,Path(d)/'out',config=Config('key','muse-spark-1.3-contributor'),post=post)
            with self.assertRaises(ValueError):plan_intent('Show DONE',Path(d)/'out',config=Config('key','other-model'),post=post)
            post.assert_not_called()


class JobTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def generator(self,instruction,out):
        return plan_intent(instruction,out,config=Config('key','muse-spark-1.3-contributor'),post=Mock(return_value=response()))
    def wait(self,service,job):
        for _ in range(100):
            r=service.get(job)
            if r['status'] not in ('queued','generating'):return r
            time.sleep(.01)
        self.fail('Mock job did not finish')
    def test_busy_and_duplicate_submission_generate_once(self):
        gate=threading.Event();calls=[]
        def generate(instruction,out):
            calls.append(instruction);gate.wait(3);return self.generator(instruction,out)
        service=PlanningService(self.root,generate)
        job=service.start('Count zero through one','a'*32)
        self.assertEqual(service.start('Count zero through one','a'*32),job)
        with self.assertRaises(BusyError):service.start('Another request','b'*32)
        with self.assertRaises(ValueError):service.start('Changed request','a'*32)
        gate.set();self.assertEqual(self.wait(service,job)['status'],'ready');self.assertEqual(len(calls),1)
    def test_saved_plan_and_review_survive_restart_and_detect_tampering(self):
        service=PlanningService(self.root,self.generator);job=service.start('Count zero through one','a'*32);r=self.wait(service,job)
        service=PlanningService(self.root,self.generator)
        with self.assertRaises(ValueError):service.review(job,'bad-hash')
        self.assertEqual(service.review(job,r['plan_sha256'])['review_status'],'reviewed')
        (self.root/job/'plan.json').write_text('{}')
        with self.assertRaises(ValueError):service.get(job)
    def test_configuration_failure_is_safe_saved_and_releases_worker(self):
        def bad(*args):raise RuntimeError('private-token-must-not-be-serialized')
        service=PlanningService(self.root,bad);job=service.start('Show DONE','c'*32);r=self.wait(service,job)
        self.assertEqual(r['status'],'error');self.assertIsNone(service.active)
        self.assertNotIn('private-token',json.dumps(r));self.assertNotIn('private-token',(self.root/job/'result.json').read_text())


class PlanningHTTPTests(unittest.TestCase):
    def test_only_explicit_session_authorized_post_can_start_model_job(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);post=Mock(return_value=response())
            planner=PlanningService(root/'plans',lambda text,out:plan_intent(text,out,config=Config('key','muse-spark-1.3-contributor'),post=post))
            server=DashboardServer(0,fixture(root),planner);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            origin=f'http://127.0.0.1:{server.server_port}'
            def request(path,method='GET',body=None,headers=None):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);c.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers or {});r=c.getresponse();value=json.loads(r.read());c.close();return r.status,value
            try:
                self.assertEqual(request('/api/plans')[1]['plans'],[]);post.assert_not_called()
                token=request('/api/session')[1]['session_token'];post.assert_not_called()
                payload={'instruction':'Count zero through one','request_id':'d'*32}
                self.assertEqual(request('/api/plans','POST',payload)[0],403);post.assert_not_called()
                headers={'Origin':origin,'X-SparkBench-Session':token,'Content-Type':'application/json'}
                self.assertEqual(request('/api/plans','POST',payload,{**headers,'Origin':'https://outside.invalid'})[0],403);post.assert_not_called()
                status,job=request('/api/plans','POST',payload,headers);self.assertEqual(status,202)
                self.assertEqual(request('/api/plans','POST',payload,headers)[1]['id'],job['id'])
                for _ in range(100):
                    _,result=request('/api/plans/'+job['id'])
                    if result['status']=='ready':break
                    time.sleep(.01)
                self.assertEqual(result['status'],'ready');self.assertEqual(post.call_count,1)
                self.assertNotIn('private-key',json.dumps(result));self.assertEqual(result['physical_verification'],'not_performed')
                self.assertEqual(request('/api/plans/'+job['id']+'/review','POST',{'plan_sha256':result['plan_sha256']},headers)[0],200)
                self.assertEqual(post.call_count,1)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
