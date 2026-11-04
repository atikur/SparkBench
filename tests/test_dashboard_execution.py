"""Synthetic execution adapters only: no board, camera, compiler or Meta API."""
import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from sparkbench.artifacts import build_artifact
from sparkbench.dashboard.evidence import EvidenceStore
from sparkbench.dashboard.execution import Cancelled,ExecutionService
from sparkbench.dashboard.planning import BusyError
from sparkbench.intent import fingerprint
from sparkbench.plans import plan_hash
from sparkbench.runtime_io import acquire
from sparkbench.vision import digest

PLAN={'schema_version':1,'mapping':{'red':25,'green':26},'steps':[{'red':True,'green':False,'text':'ONE'},{'red':False,'green':False,'text':'DONE'}]}
PROPOSAL='a'*32


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);folder=self.root/'plans'/PROPOSAL;folder.mkdir(parents=True);(folder/'plan.json').write_text(json.dumps(PLAN))
        self.planner=Mock(directory=self.root/'plans');self.planner.get.return_value={'status':'ready','review_status':'reviewed','plan_sha256':plan_hash(PLAN)}
        (self.root/'hardware').mkdir();(self.root/'old.bin').write_bytes(b'synthetic old app')
        (self.root/'hardware/board.json').write_text(json.dumps({'active_firmware':{'application_binary':'old.bin','firmware_sha256':digest(self.root/'old.bin')},'firmware_history':[]}))
        self.builder=Mock(side_effect=self.build);self.installer=Mock(side_effect=self.install);self.runner=Mock()
        self.identity_checker=Mock(return_value={'status':'pass','scope':'Synthetic UART identity only'})
        self.service=ExecutionService(self.root,self.planner,EvidenceStore(self.root,()),builder=self.builder,installer=self.installer,runner=self.runner,
             enumerate_devices=lambda:{'ports':[{'id':'/dev/synthetic'}],'cameras':[{'id':'iphone'}]},identity_checker=self.identity_checker)
    def tearDown(self):
        self.service.shutdown()
        if self.service.thread:self.service.thread.join(5)
        self.temp.cleanup()
    def build(self,plan,path):
        r=build_artifact(plan,path,False);build=path/'project/.pio/build/classic-led-oled-runtime';build.mkdir(parents=True);binary=build/'firmware.bin';binary.write_bytes(b'synthetic new app');r.update(status='compiled',firmware='project/.pio/build/classic-led-oled-runtime/firmware.bin',firmware_sha256=digest(binary),firmware_bytes=binary.stat().st_size);(path/'artifact.json').write_text(json.dumps(r));return r
    def install(self,artifact,port,previous,previous_hash,out):
        self.assertEqual(digest(previous),previous_hash);out.mkdir();(out/'application.bin').write_bytes((artifact/'project/.pio/build/classic-led-oled-runtime/firmware.bin').read_bytes());return {'status':'installed_hash_verified'}
    def body(self,**extra):return {'proposal_id':PROPOSAL,'plan_sha256':plan_hash(PLAN),'request_id':__import__('uuid').uuid4().hex,**extra}
    def wait(self,job):
        for _ in range(300):
            result=self.service.get(job)
            if result['status']!='running':return result
            time.sleep(.01)
        self.fail('Synthetic worker timeout')
    def compile(self):return self.wait(self.service.start('compile',self.body()))
    def test_review_and_exact_plan_required_before_any_build(self):
        self.planner.get.return_value['review_status']='pending'
        with self.assertRaises(ValueError):self.service.start('compile',self.body())
        self.builder.assert_not_called()
    def test_compile_only_never_installs_or_runs(self):
        result=self.compile();self.assertEqual(result['status'],'compiled');self.installer.assert_not_called();self.runner.assert_not_called()
    def test_source_and_binary_downloads_bind_to_compiled_artifact(self):
        import io,zipfile
        result=self.compile();data,mime=self.service.download(result['id'],'source');source=json.loads(data)
        self.assertEqual(source['firmware_sha256'],result['firmware_sha256']);self.assertIn('include/plan_data.h',source['files'])
        data,mime=self.service.download(result['id'],'source.zip')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:self.assertEqual(set(archive.namelist()),set(source['files']))
        data,mime=self.service.download(result['id'],'firmware.bin');self.assertEqual(data,b'synthetic new app')
        self.installer.assert_not_called();self.runner.assert_not_called()
    def test_progress_photo_has_one_owner_and_no_serial_or_meta_actions(self):
        def capture(device_id,**kwargs):
            self.assertEqual(device_id,'iphone');out=kwargs['output'];out.mkdir()
            (out/'frames.jsonl').write_text(json.dumps({'file':'frame-000001.jpg'})+'\n');(out/'frame-000001.jpg').write_bytes(b'\xff\xd8\xffsynthetic photo')
        with patch('sparkbench.dashboard.execution.capture_frames',side_effect=capture) as camera:
            job=self.service.start_photo({'request_id':'d'*32,'device_id':'iphone'});r=self.wait(job)
        self.assertEqual(r['status'],'captured');self.assertEqual(r['serial_commands_sent'],[]);self.assertEqual(r['meta_requests'],0);self.assertIn('latest_frame',r)
        camera.assert_called_once();self.installer.assert_not_called();self.runner.assert_not_called();self.builder.assert_not_called()
    def test_photo_never_substitutes_an_absent_camera(self):
        with patch('sparkbench.dashboard.execution.capture_frames') as camera:
            job=self.service.start_photo({'request_id':'e'*32,'device_id':'absent'});self.assertEqual(self.wait(job)['status'],'incomplete')
        camera.assert_not_called()
    def test_single_owner_deduplicates_and_serializes(self):
        gate=threading.Event();original=self.builder.side_effect
        self.builder.side_effect=lambda *args:(gate.wait(2),original(*args))[1]
        body=self.body();job=self.service.start('compile',body)
        self.assertEqual(self.service.start('compile',body),job)
        with self.assertRaises(BusyError):self.service.start('compile',self.body())
        self.service.cancel(job);gate.set();self.assertEqual(self.wait(job)['status'],'cancelled');self.assertEqual(self.builder.call_count,1)
    def test_install_updates_verified_app_record_and_keeps_prior(self):
        build=self.compile();job=self.service.start('install',self.body(build_id=build['id'],port='/dev/synthetic'))
        self.assertEqual(self.wait(job)['status'],'installed')
        board=json.loads((self.root/'hardware/board.json').read_text());self.assertEqual(board['active_firmware']['firmware_sha256'],build['firmware_sha256']);self.assertEqual(len(board['firmware_history']),1);self.runner.assert_not_called()
        self.assertEqual(board['active_firmware']['runtime_identity']['status'],'pass');self.identity_checker.assert_called_once()
    def test_missing_identity_does_not_erase_verified_installation_or_claim_physical_pass(self):
        self.identity_checker.return_value={'status':'incomplete','scope':'Synthetic missing UART reply'}
        build=self.compile();job=self.service.start('install',self.body(build_id=build['id'],port='/dev/synthetic'));result=self.wait(job)
        self.assertEqual(result['status'],'installed');self.assertEqual(result['runtime_identity']['status'],'incomplete');self.assertEqual(result['physical_verification'],'not_performed')
    def test_identity_recheck_requires_matching_installation_and_never_reflashes(self):
        build=self.compile();body=lambda:self.body(build_id=build['id'],port='/dev/synthetic')
        self.assertEqual(self.wait(self.service.start('identity',body()))['status'],'incomplete');self.identity_checker.assert_not_called()
        self.wait(self.service.start('install',body()));result=self.wait(self.service.start('identity',body()))
        self.assertEqual(result['status'],'identity_confirmed');self.assertEqual(self.identity_checker.call_count,2);self.assertEqual(self.installer.call_count,1);self.runner.assert_not_called()
    def test_failed_compilation_log_is_available_without_a_compiled_artifact(self):
        def fail(plan,path):path.mkdir();(path/'compile.log').write_text('synthetic compiler error');return {'status':'compile_failed'}
        self.builder.side_effect=fail;result=self.compile();self.assertEqual(result['status'],'incomplete');info=self.service.diagnostics(result['id'])
        self.assertEqual(info['logs'][0]['name'],'artifact/compile.log');self.assertEqual(self.service.log(result['id'],0)['text'],'synthetic compiler error')
        with self.assertRaises(KeyError):self.service.log(result['id'],99)
    def test_restored_previous_image_is_reported_as_recovery_not_new_installation(self):
        def failure(artifact,port,previous,previous_hash,out):
            out.mkdir();result={'status':'incomplete','recovery':'previous_application_restored_hash_verified','commands':[['write-flash']]};(out/'installation.json').write_text(json.dumps(result));return result
        self.installer.side_effect=failure;build=self.compile();job=self.service.start('install',self.body(build_id=build['id'],port='/dev/synthetic'));self.assertEqual(self.wait(job)['status'],'incomplete')
        info=self.service.diagnostics(job);self.assertIn('restored and flash-verified',info['next_step']);self.assertNotEqual(json.loads((self.root/'hardware/board.json').read_text())['active_firmware']['firmware_sha256'],build['firmware_sha256']);self.identity_checker.assert_not_called()
    def test_absent_device_never_calls_installer(self):
        build=self.compile();job=self.service.start('install',self.body(build_id=build['id'],port='/dev/absent'))
        self.assertEqual(self.wait(job)['status'],'incomplete');self.installer.assert_not_called()
    def test_test_requires_installed_matching_image(self):
        build=self.compile()
        with patch('sparkbench.dashboard.execution.check_policy',return_value=({'calibration':'cal.json'},Path('cal.json'))):
            (self.root/'cal.json').write_text(json.dumps({'camera_id':'iphone'}))
            job=self.service.start('test',self.body(build_id=build['id'],port='/dev/synthetic',device_id='iphone'))
            self.assertEqual(self.wait(job)['status'],'incomplete')
        self.runner.assert_not_called()
    def test_cancellation_reaches_the_worker_and_never_claims_pass(self):
        build=self.compile();self.wait(self.service.start('install',self.body(build_id=build['id'],port='/dev/synthetic')))
        entered=threading.Event()
        def runner(port,camera,out,policy,spec,**kwargs):
            self.assertEqual(json.loads(spec.read_text())['expectation_provenance'],'Reviewed proposal data; measurements and OLED reader remain independent of expected values')
            kwargs['on_stage']('capture');entered.set();self.assertTrue(kwargs['cancel'].wait(3))
            (out/'capture').mkdir(parents=True);(out/'capture/run.json').write_text(json.dumps({'sequence_started':True,'stop_acknowledged_uart_only':True}))
            return {'status':'incomplete'}
        self.runner.side_effect=runner;(self.root/'cal.json').write_text(json.dumps({'camera_id':'iphone'}))
        with patch('sparkbench.dashboard.execution.check_policy',return_value=({'calibration':'cal.json'},self.root/'cal.json')):
            job=self.service.start('test',self.body(build_id=build['id'],port='/dev/synthetic',device_id='iphone'));self.assertTrue(entered.wait(2));self.service.cancel(job);r=self.wait(job)
        self.assertEqual(r['status'],'cancelled');self.assertEqual(r['shutdown'],'acknowledged_uart_only');self.assertNotEqual(r['physical_verification'],'pass')
    def test_persisted_job_does_not_restart_on_service_load(self):
        result=self.compile();builder=Mock();new=ExecutionService(self.root,self.planner,EvidenceStore(self.root,()),builder=builder)
        self.assertEqual(new.get(result['id'])['status'],'compiled');builder.assert_not_called();self.assertIsNone(new.active)
    def test_analysis_cancellation_keeps_captured_shutdown_evidence(self):
        build=self.compile();self.wait(self.service.start('install',self.body(build_id=build['id'],port='/dev/synthetic')))
        def runner(port,camera,out,*args,**kwargs):
            (out/'capture').mkdir(parents=True)
            (out/'capture/run.json').write_text(json.dumps({'sequence_started':True,'stop_acknowledged_uart_only':True}))
            raise Cancelled('Analysis cancelled')
        self.runner.side_effect=runner;(self.root/'cal.json').write_text(json.dumps({'camera_id':'iphone'}))
        with patch('sparkbench.dashboard.execution.check_policy',return_value=({'calibration':'cal.json'},self.root/'cal.json')):
            job=self.service.start('test',self.body(build_id=build['id'],port='/dev/synthetic',device_id='iphone'));result=self.wait(job)
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['shutdown'],'acknowledged_uart_only')
    def test_job_history_restores_camera_and_evidence_metadata(self):
        result=self.compile();folder=self.service._folder(result['id'])/'workflow'
        (folder/'analysis').mkdir(parents=True);(folder/'analysis/verification.json').write_text('{}')
        camera=folder/'capture/camera';camera.mkdir(parents=True)
        (camera/'frames.jsonl').write_text(json.dumps({'file':'frame-000009.jpg'})+'\n')
        self.service._set(result['id'],action='test',status='incomplete',stage='finished')
        saved=self.service.list(PROPOSAL)[0]
        self.assertTrue(saved['evidence_available']);self.assertFalse(saved['latest_frame']['live'])
        self.assertEqual(saved['latest_frame']['file'],'frame-000009.jpg')
    def test_precancelled_capture_never_accesses_hardware(self):
        cancel=threading.Event();cancel.set()
        with patch('sparkbench.runtime_io.load_artifact') as artifact,patch('serial.Serial') as serial:
            with self.assertRaisesRegex(ValueError,'Cancelled'):acquire('port','camera','artifact','output',cancel=cancel)
            artifact.assert_not_called();serial.assert_not_called()


    def view_setup(self,matches):
        calibration=self.root/'cal.json';geometry={'minimum_border_support':.85,'reference_frame':'ref.jpg'}
        calibration.write_text(json.dumps({'camera_id':'iphone','geometry':geometry}));(self.root/'ref.jpg').write_bytes(b'\xff\xd8\xffref')
        def capture(device,seconds,fps,output):
            output.mkdir(parents=True);rows=[{'frame':i,'file':'frame-%06d.jpg'%i,'sample_pts_seconds':i,'host_uptime_seconds':i} for i in range(1,6)]
            (output/'frames.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            for r in rows:(output/r['file']).write_bytes(b'\xff\xd8\xffframe')
        self.service.view_reader=Mock(side_effect=lambda run,g,frames,out,read_labels:{r['file']:({'status':'measured','oled_border_support':[1,1,1,1]} if matches else {'status':'unknown','error':'Static border pixels do not match reference'}) for r in frames})
        return patch('sparkbench.dashboard.execution.capture_frames',side_effect=capture),patch('sparkbench.dashboard.execution.check_policy',return_value=({},calibration))
    def test_view_check_reports_match_and_moved_without_serial_or_meta(self):
        for matches,status,count in [(True,'view_ok',3),(False,'view_moved',0)]:
            a,b=self.view_setup(matches)
            with a,b:
                job=self.wait(self.service.start_view({'request_id':__import__('uuid').uuid4().hex,'device_id':'iphone'}))
            self.assertEqual(job['status'],status);self.assertEqual((job['frames_checked'],job['frames_matched']),(3,count))
            self.assertEqual((job['serial_commands_sent'],job['meta_requests']),([],0))
            self.assertFalse(self.service.view_reader.call_args.kwargs['read_labels'])
            self.runner.assert_not_called();self.installer.assert_not_called()
    def test_view_check_refuses_another_camera_and_serves_reference(self):
        a,b=self.view_setup(True)
        with a as capture,b:
            job=self.wait(self.service.start_view({'request_id':__import__('uuid').uuid4().hex,'device_id':'other-camera'}))
            self.assertEqual(job['status'],'incomplete');self.assertIn('differs',job['error']);capture.assert_not_called()
            self.assertEqual(self.service.reference_image(),b'\xff\xd8\xffref')


class RuntimeCancellationTests(unittest.TestCase):
    def scenario(self,ack=True,cancel_on_start=True):
        from sparkbench.runtime_io import identity
        from unittest.mock import patch
        import types
        cancel=threading.Event()
        class Clock:
            t=0
            def now(self):self.t+=.025;return self.t
        clock=Clock()
        class Serial:
            is_open=False;buffer=b''
            @property
            def in_waiting(self):return len(self.buffer)
            def open(self):self.is_open=True
            def close(self):self.is_open=False
            def read(self,n):data=self.buffer[:n];self.buffer=self.buffer[n:];return data
            def flush(self):pass
            def write(self,data):
                if data==b'ID\n':self.buffer=(identity('a'*64)+'\nVISUAL_ALIVE UPTIME_MS:1000 MODE:IDLE\nVISUAL_ALIVE UPTIME_MS:2000 MODE:IDLE\n').encode()
                if data==b'VISUAL\n' and cancel_on_start:cancel.set()
                if data==b'STOP\n' and ack:self.buffer=b'VISUAL_STOPPED STATUS:STOPPED RED:0 GREEN:0 UPTIME_MS:3000\n'
                return len(data)
        connection=Serial();port=types.SimpleNamespace(device='/dev/synthetic',vid=0x10C4,pid=0xEA60,hwid='synthetic')
        camera=Mock(returncode=None);camera.poll.side_effect=lambda:camera.returncode;camera.terminate.side_effect=lambda:setattr(camera,'returncode',0)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'run'
            def popen(command,**kwargs):
                folder=Path(command[3]);folder.mkdir()
                for i in range(1,4):(folder/f'frame-{i:06d}.jpg').write_bytes(b'fake')
                return camera
            calls=[0]
            def frames(path):
                calls[0]+=1
                if calls[0]>1 and not cancel_on_start:return []
                return [{'file':f'frame-{i:06d}.jpg','host_uptime_seconds':clock.t} for i in range(1,4)]
            with patch('serial.tools.list_ports.comports',return_value=[port]),patch('serial.Serial',return_value=connection),\
                 patch('sparkbench.runtime_io.load_artifact',return_value=(PLAN,{'plan_sha256':'a'*64,'firmware_sha256':'b'*64})),\
                 patch('sparkbench.runtime_io.build_helper',return_value=Path('fake-helper')),\
                 patch('sparkbench.runtime_io.time.monotonic',side_effect=clock.now),\
                 patch('sparkbench.runtime_io.subprocess.Popen',side_effect=popen),patch('sparkbench.runtime_io.frame_rows',side_effect=frames):
                result=acquire(port.device,'iphone','artifact',out,cancel=cancel)
            return result
    def test_midrun_cancellation_uses_existing_owner_and_confirms_fresh_stop(self):
        r=self.scenario();self.assertTrue(r['cancelled']);self.assertTrue(r['sequence_started']);self.assertTrue(r['stop_acknowledged_uart_only']);self.assertEqual(r['serial_commands_sent'],['ID','VISUAL','STOP']);self.assertEqual(r['status'],'incomplete')
    def test_missing_stop_acknowledgement_is_never_reported_stopped(self):
        r=self.scenario(ack=False);self.assertFalse(r['stop_acknowledged_uart_only']);self.assertEqual(r['status'],'incomplete');self.assertIn('stop_error',r)
    def test_stale_camera_aborts_sequence_and_attempts_stop(self):
        r=self.scenario(cancel_on_start=False);self.assertTrue(r['stop_acknowledged_uart_only']);self.assertIn('stale',r['error']);self.assertIn('STOP',r['serial_commands_sent']);self.assertEqual(r['status'],'incomplete')


if __name__=='__main__':unittest.main()
