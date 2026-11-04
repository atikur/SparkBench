"""Single-owner compile/install/camera-test jobs for reviewed LED/OLED plans."""
import copy
import io
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..artifacts import build_artifact, load_artifact, runtime_current
from ..camera import capture_frames, list_cameras
from ..installation import install, verify_identity
from ..intent import save
from ..plans import plan_hash
from ..policy import check_policy
from ..framing import inspect_frame
from ..meta import read_label
from ..vision import digest, geometry_valid, led_state, read_images, windows
from ..workflow import execute
from .catalog import Run
from .planning import BusyError, IDENTIFIER
from .repair import MappingRepairMixin
from .camera_flow import CameraSetupMixin
from ..sam_regions import propose_regions


def devices():
    try:
        from serial.tools import list_ports
        result = {"ports":[{"id":p.device,"name":p.description,"serial_number":p.serial_number}
                            for p in list_ports.comports() if (p.vid,p.pid)==(0x10C4,0xEA60)], "cameras":[]}
    except ImportError:
        # The source-only preview runs without the dev requirements; only live bench work needs pyserial.
        result = {"ports":[], "cameras":[],
                  "port_error":"Serial port listing needs the pyserial package from requirements-dev.txt. The preview works without it; live bench work does not."}
    try:
        cameras=list_cameras()
        result["camera_permission"]=cameras.get("camera_permission")
        result["cameras"]=[{"id":d["id"],"name":d["name"]} for d in cameras.get("devices",[])
                           if d.get("connected") and d.get("type")=="AVCaptureDeviceTypeContinuityCamera"]
        if not result["cameras"]:
            result["camera_error"]=("No Continuity Camera returned in this process context (permission: "
                +str(result.get("camera_permission","unknown"))+"). Sandboxed denial/empty discovery does not establish host camera unavailability; check fresh host enumeration.")
    except (OSError,ValueError,subprocess.TimeoutExpired):
        result["camera_error"]="Camera enumeration unavailable in this host context; no built-in-camera fallback."
    return result


class Cancelled(ValueError): pass


def _saved_regions(geometry):
    """Where the saved view expects each part, for drawing on a frame. Display only; never read by a check."""
    regions={name:[led['center_x']-led['radius']*2,led['center_y']-led['radius']*2,led['center_x']+led['radius']*2,led['center_y']+led['radius']*2] for name,led in geometry['leds'].items()}
    xs,ys=zip(*geometry['oled_corners']);regions['oled']=[min(xs),min(ys),max(xs),max(ys)]
    return regions


class ExecutionService(CameraSetupMixin, MappingRepairMixin):
    def __init__(self, root, planner, store, *, builder=build_artifact, installer=install, runner=execute, enumerate_devices=devices, identity_checker=verify_identity, view_reader=read_images, label_reader=read_label, frame_inspector=inspect_frame, probe_runner=None, probe_analyzer=None, mapping_proposer=None, region_proposer=propose_regions):
        self.root=Path(root).resolve();self.directory=self.root/"runs/dashboard-execution"
        self.planner,self.store=planner,store
        self.builder,self.installer,self.runner,self.enumerate_devices=builder,installer,runner,enumerate_devices
        self.identity_checker=identity_checker;self.view_reader=view_reader;self.label_reader=label_reader;self.frame_inspector=frame_inspector
        self.region_proposer=region_proposer
        self._init_repairs(probe_runner, probe_analyzer, mapping_proposer)
        self.lock=threading.RLock();self.active=None;self.cancel_event=None;self.thread=None;self.jobs={}
        if self.directory.is_dir():
            for folder in self.directory.iterdir():
                if IDENTIFIER.fullmatch(folder.name) and folder.is_dir() and not folder.is_symlink():
                    try:
                        job=json.loads((folder/"job.json").read_text())
                        if job.get("id")!=folder.name:continue
                        if job.get("status")=="running":
                            job.update(status="interrupted",error="Previous worker stopped; no automatic resume. Recheck device state.")
                            save(folder/"job.json",job)
                        self.jobs[folder.name]=job
                    except (OSError,ValueError,TypeError):pass

    def _folder(self, job_id):
        if not isinstance(job_id,str) or not IDENTIFIER.fullmatch(job_id):raise KeyError("Unknown job")
        folder=self.directory/job_id
        if folder.is_symlink():raise ValueError("Job symlink rejected")
        return folder

    def _set(self, job_id, **values):
        with self.lock:
            self.jobs[job_id].update(values,updated_at_utc=datetime.now(timezone.utc).isoformat())
            save(self._folder(job_id)/"job.json",self.jobs[job_id])

    def _reviewed(self, proposal_id, expected_hash):
        result=self.planner.get(proposal_id)
        if result.get("status")!="ready" or result.get("review_status")!="reviewed" or result.get("plan_sha256")!=expected_hash:
            raise ValueError("The unchanged proposal must be reviewed before building or testing")
        self._validate_repair_candidate(result)
        plan=json.loads((self.planner.directory/proposal_id/"plan.json").read_text())
        if plan_hash(plan)!=expected_hash:raise ValueError("Reviewed plan hash differs")
        return plan

    def _build(self, build_id, proposal_id, expected_hash):
        build=self.jobs.get(build_id,{})
        if build.get("action")!="compile" or build.get("status")!="compiled" or build.get("proposal_id")!=proposal_id or build.get("plan_sha256")!=expected_hash:
            raise ValueError("Matching compiled proposal required")
        path=self._folder(build_id)/"artifact"
        plan,artifact=load_artifact(path)
        if plan_hash(plan)!=expected_hash:raise ValueError("Compiled artifact differs from review")
        return path,artifact

    def start(self, action, body):
        fields={"proposal_id","plan_sha256","request_id"}
        if action in ("install","test","identity"):fields|={"build_id","port"}
        if action=="test":fields|={"device_id"}
        if action not in ("compile","install","test","identity") or set(body)!=fields:raise ValueError("Invalid execution action or fields")
        if not isinstance(body["request_id"],str) or not IDENTIFIER.fullmatch(body["request_id"]):raise ValueError("Valid request ID required")
        if not isinstance(body["proposal_id"],str) or not IDENTIFIER.fullmatch(body["proposal_id"]):raise ValueError("Valid proposal ID required")
        self._reviewed(body["proposal_id"],body["plan_sha256"])
        if action!="compile":
            self._build(body["build_id"],body["proposal_id"],body["plan_sha256"])
            if not isinstance(body["port"],str) or not body["port"].strip():raise ValueError("Select the freshly enumerated CP2102")
        if action=="test" and (not isinstance(body["device_id"],str) or not body["device_id"].strip()):raise ValueError("Explicit iPhone camera required")
        with self.lock:
            for job in self.jobs.values():
                if job.get("request_id")==body["request_id"]:
                    if job.get("action")!=action or job.get("request")!=body:raise ValueError("Request ID already used")
                    return job["id"]
            if self.active:raise BusyError("Another build or hardware job owns the bench")
            job_id=uuid.uuid4().hex;folder=self._folder(job_id);folder.mkdir(parents=True,exist_ok=False)
            job={"id":job_id,"action":action,"proposal_id":body["proposal_id"],"plan_sha256":body["plan_sha256"],
                 "request_id":body["request_id"],"request":body,"status":"running","stage":"queued",
                 "servo_actuation":False,"physical_verification":"not_performed","started_at_utc":datetime.now(timezone.utc).isoformat()}
            if action=='test':
                policy_path=self._camera_policy_path(body['proposal_id'])
                check_policy(policy_path)
                job.update(camera_policy_path=str(policy_path),camera_policy_sha256=digest(policy_path))
            self.jobs[job_id]=job;save(folder/"job.json",job)
            self.active=job_id;self.cancel_event=threading.Event()
            self.thread=threading.Thread(target=self._work,args=(job_id,action,dict(body),self.cancel_event),daemon=False)
            self.thread.start()
            return job_id

    def _board(self):
        data=json.loads((self.root/"hardware/board.json").read_text())
        active=data["active_firmware"];image=(self.root/active["application_binary"]).resolve()
        if not image.is_relative_to(self.root) or image.is_symlink() or digest(image)!=active["firmware_sha256"]:
            raise ValueError("Recorded current application is unavailable or changed")
        return data,image

    def board_summary(self):
        """Read-only: the recorded active application, for deciding whether an install can be skipped."""
        try:
            board,_=self._board();active=board.get("active_firmware") or {}
        except (OSError,ValueError,KeyError,TypeError):
            return {"active_firmware_sha256":None,"plan_sha256":None,"proposal_id":None,"upload_status":None,"recorded":False,"scope":"No board record on this host"}
        return {"active_firmware_sha256":active.get("firmware_sha256"),"plan_sha256":active.get("plan_sha256"),"proposal_id":active.get("proposal_id"),
                "upload_status":active.get("upload_status"),"recorded":True,"scope":"Saved record of the last verified installation; not a live read of the board"}

    def start_photo(self, body):
        if set(body)!={'request_id','device_id'} or not isinstance(body['request_id'],str) or not IDENTIFIER.fullmatch(body['request_id']):raise ValueError('Explicit camera and request ID required')
        if not isinstance(body['device_id'],str) or not body['device_id']:raise ValueError('Select the iPhone camera')
        with self.lock:
            for job in self.jobs.values():
                if job.get('request_id')==body['request_id']:
                    if job.get('action')!='photo' or job.get('request')!=body:raise ValueError('Request ID already used')
                    return job['id']
            if self.active:raise BusyError('Another job owns the bench; wait before taking a progress photo')
            job_id=uuid.uuid4().hex;folder=self._folder(job_id);folder.mkdir(parents=True)
            self.jobs[job_id]={'id':job_id,'action':'photo','proposal_id':None,'plan_sha256':None,'request_id':body['request_id'],'request':body,'status':'running','stage':'capture','physical_verification':'not_performed','servo_actuation':False,'started_at_utc':datetime.now(timezone.utc).isoformat()}
            save(folder/'job.json',self.jobs[job_id]);self.active=job_id;self.cancel_event=threading.Event()
            self.thread=threading.Thread(target=self._photo,args=(job_id,body['device_id'],self.cancel_event),daemon=False);self.thread.start();return job_id

    def _photo(self, job_id, device_id, cancel):
        try:
            if device_id not in [d['id'] for d in self.enumerate_devices()['cameras']]:raise ValueError('Selected iPhone absent in this process context; no fallback camera')
            if cancel.is_set():raise Cancelled('Cancelled before camera access')
            output=self._folder(job_id)/'workflow/capture/camera';output.parent.mkdir(parents=True)
            capture_frames(device_id,seconds=10,fps=2,output=output)
            self._set(job_id,status='cancelled' if cancel.is_set() else 'captured',stage='finished',ended_at_utc=datetime.now(timezone.utc).isoformat(),serial_commands_sent=[],meta_requests=0)
        except Exception:
            self._set(job_id,status='incomplete',stage='finished',error='Progress photo unavailable in this host context; check camera permission and availability. No serial commands sent.')
        finally:
            with self.lock:self.active=None

    # Camera check: a short capture compared with the frozen view, before the plan runs. It sends no serial commands
    # and only says whether a test could be measured from here. The board is idle, so both LEDs must read off.
    def _frozen_calibration(self, proposal_id=None):
        _,calibration=check_policy(self._camera_policy_path(proposal_id))
        return json.loads(Path(calibration).read_text())

    def reference_image(self, proposal_id=None):
        file=self.root/self._frozen_calibration(proposal_id)["geometry"]["reference_frame"]
        if file.is_symlink() or not file.is_file():raise KeyError("Reference frame unavailable")
        return file.read_bytes()

    def _view_issues(self, rows, matched, measured, calibration):
        if not measured:return [{'part':'camera','problem':'The camera is not in its calibrated position.'}]
        if measured<len(rows):return [{'part':'camera','problem':'The camera moved during the check. Keep the phone still.'}]
        if matched<len(rows):return [{'part':'oled','problem':'The OLED border was not found where it should be. Check that the OLED is on and nothing covers it.'}]
        names={'red':'red LED','green':'green LED'};issues=[]
        for channel,name in names.items():
            states=[led_state(row.get('leds',{}).get(channel,{}).get('mean_luma_srgb'),calibration['thresholds'][channel]) for row in rows]
            if any(state is not False for state in states):issues.append({'part':channel+'_led','problem':'The '+name+' could not be read as off while the board is idle. Check that both LEDs are still where the calibrated view shows them. A moved LED looks like this. Then check for glare or something covering it.'})
        return issues

    def start_view(self, body):
        if set(body) not in ({'request_id','device_id'}, {'request_id','device_id','proposal_id'}, {'request_id','device_id','proposal_id','automatic_setup'}) or body.get('automatic_setup',True) is not True or not isinstance(body['request_id'],str) or not IDENTIFIER.fullmatch(body['request_id']):raise ValueError('Explicit camera and request ID required')
        if not isinstance(body['device_id'],str) or not body['device_id']:raise ValueError('Select the iPhone camera')
        if 'proposal_id' in body:
            if not isinstance(body['proposal_id'],str) or not IDENTIFIER.fullmatch(body['proposal_id']):raise ValueError('Valid proposal ID required')
            self.planner.get(body['proposal_id'])
        with self.lock:
            for job in self.jobs.values():
                if job.get('request_id')==body['request_id']:
                    if job.get('action')!='view' or job.get('request')!=body:raise ValueError('Request ID already used')
                    return job['id']
            if self.active:raise BusyError('Another job owns the bench; wait before checking the camera')
            job_id=uuid.uuid4().hex;folder=self._folder(job_id);folder.mkdir(parents=True)
            self.jobs[job_id]={'id':job_id,'action':'view','proposal_id':body.get('proposal_id'),'plan_sha256':None,'request_id':body['request_id'],'request':body,'status':'running','stage':'capture','physical_verification':'not_performed','servo_actuation':False,'started_at_utc':datetime.now(timezone.utc).isoformat(),'updated_at_utc':datetime.now(timezone.utc).isoformat(),'shutdown':False,'failures':0,'unknowns':0,'error':None}
            self.jobs[job_id].update(setup_available=False,
                reference_url='/api/camera/reference'+('/'+body['proposal_id'] if body.get('proposal_id') else ''))
            save(folder/'job.json',self.jobs[job_id]);self.active=job_id;self.cancel_event=threading.Event()
            self.thread=threading.Thread(target=self._view,args=(job_id,body['device_id'],self.cancel_event),daemon=False);self.thread.start();return job_id

    def _view(self, job_id, device_id, cancel):
        try:
            proposal_id=self.jobs[job_id].get('proposal_id')
            calibration=self._frozen_calibration(proposal_id);geometry=calibration["geometry"]
            try:self._set(job_id,saved_regions=_saved_regions(geometry),image_width=geometry['image_width'],image_height=geometry['image_height'])
            except (KeyError,TypeError,ValueError):pass  # Display only: it can never fail a check.
            if calibration["camera_id"]!=device_id:raise ValueError("Selected camera differs from the frozen measurement policy")
            if device_id not in [d['id'] for d in self.enumerate_devices()['cameras']]:raise ValueError('Selected iPhone absent in this process context; no fallback camera')
            if cancel.is_set():raise Cancelled('Cancelled before camera access')
            run=self._folder(job_id)/'workflow/capture';output=run/'camera';run.mkdir(parents=True)
            capture_frames(device_id,seconds=5,fps=2,output=output)
            from ..led_oled import frame_rows
            chosen=frame_rows(output/'frames.jsonl')[-3:]
            if len(chosen)!=3:raise ValueError('Three fresh camera frames required')
            analysis=run.parent/'view';analysis.mkdir();self._set(job_id,stage='analysis')
            native=self.view_reader(run,geometry,chosen,analysis,read_labels=False)
            rows=[native[row['file']] for row in chosen]
            matched=sum(geometry_valid(row,geometry) for row in rows);measured=sum(row.get('status')=='measured' for row in rows)
            issues=self._view_issues(rows,matched,measured,calibration);requests=0;reading=None;inspection=None
            # The frozen reader, without any expected text, confirms the OLED can be read from here.
            if not issues:
                if cancel.is_set():raise Cancelled('Cancelled before the OLED reading')
                last=rows[-1];result=self.label_reader(analysis/'crops'/last['label_crop'],analysis/'meta'/last['id']);requests+=1
                if result.get('status')=='read':reading=result.get('text')
                else:issues.append({'part':'oled','problem':'The OLED is in view, but its text could not be read from here. Check for glare or a blurry image.'})
            # Only to tell the person what to fix. It can never clear an issue. When the agent is about to
            # set the camera up itself there is nobody to tell, so it spends no model request on this.
            automatic=self.jobs[job_id].get('request',{}).get('automatic_setup') is True and all(i['part']=='camera' for i in issues) and self.camera_setup_available(proposal_id)
            if issues and not automatic and not cancel.is_set():
                try:
                    requests+=1;looked=self.frame_inspector((output/chosen[-1]['file']).read_bytes(),self.reference_image(proposal_id),analysis/'inspection')
                    inspection=looked.get('inspection')
                except Exception:inspection=None
            if cancel.is_set():raise Cancelled('Cancelled before publishing camera readiness')
            setup_available=any(i['part']=='camera' for i in issues) and self.camera_setup_available(proposal_id)
            self._set(job_id,status='view_blocked' if issues else 'view_ok',stage='finished',frames_checked=len(chosen),frames_matched=matched,view_issues=issues,view_inspection=inspection,oled_reading=reading,ended_at_utc=datetime.now(timezone.utc).isoformat(),serial_commands_sent=[],meta_requests=requests,setup_available=setup_available)
        except Cancelled:
            self._set(job_id,status='cancelled',stage='finished',error='Cancelled before camera access. No serial commands sent.')
        except Exception as exc:
            detail=str(exc) if isinstance(exc,ValueError) else 'check camera permission and availability'
            self._set(job_id,status='incomplete',stage='finished',error='Camera check unavailable: '+detail+'. No serial commands sent.')
        finally:
            with self.lock:self.active=None

    def download(self, job_id, name):
        job=self.get(job_id)
        if job.get('action')!='compile' or job.get('status')!='compiled':raise ValueError('A completed compiled artifact is required')
        folder=self._folder(job_id)/'artifact';_,artifact=load_artifact(folder)
        if name=='firmware.bin':return (folder/artifact['firmware']).read_bytes(),'application/octet-stream'
        if name=='compile.log':return (folder/'compile.log').read_bytes(),'text/plain; charset=utf-8'
        files={n:(folder/'project'/n).read_text() for n in ['platformio.ini','include/engine.h','include/plan_data.h','src/main.cpp']}
        if name=='source':return json.dumps({'files':files,'firmware_sha256':artifact['firmware_sha256'],'plan_sha256':artifact['plan_sha256'],'authorship':'Meta proposes behavior data. Trusted local code renders plan_data.h and supplies the runtime.'}).encode(),'application/json; charset=utf-8'
        if name=='source.zip':
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as archive:
                for n,content in files.items():archive.writestr(n,content)
            return data.getvalue(),'application/zip'
        raise KeyError('Unknown artifact download')

    def _record_install(self, body, artifact_path, artifact, folder):
        board,_=self._board();prior=copy.deepcopy(board["active_firmware"])
        board.setdefault("firmware_history",[]).append(prior)
        board["active_firmware"]={"date":datetime.now(timezone.utc).date().isoformat(),"firmware":"firmware/runtime",
            "environment":"classic-led-oled-runtime","firmware_sha256":artifact["firmware_sha256"],"plan_sha256":artifact["plan_sha256"],
            "application_binary":str((folder/"application.bin").relative_to(self.root)),"artifact":str(artifact_path.relative_to(self.root)),
            "installation_record":str((folder/"installation.json").relative_to(self.root)),"upload_status":"installed_hash_verified",
            "proposal_id":body["proposal_id"],"servo_actuation":False,"servo_gpio27_used":False,
            "servo_policy":"LED/OLED-only runtime; GPIO27 never driven; no servo movement authorized.",
            "full_behavior_verification":"incomplete_required_servo_measurements_missing","last_seen_port":body["port"]}
        save(self.root/"hardware/board.json",board)

    def _identity(self, job_id, body, artifact, folder):
        self._set(job_id,stage='identity')
        result=self.identity_checker(body['port'],artifact['plan_sha256'],folder/'identity')
        self._set(job_id,runtime_identity=result)
        board,_=self._board()
        if board['active_firmware']['firmware_sha256']==artifact['firmware_sha256']:
            board['active_firmware']['runtime_identity']=result
            board['active_firmware']['runtime_identity_record']=str((folder/'identity/identity.json').relative_to(self.root))
            save(self.root/'hardware/board.json',board)
        return result

    def _analyze(self, job_id, cancel, run, calibration, spec, output):
        parent=output.parent
        with (parent/"analysis.stdout.log").open('x') as stdout,(parent/"analysis.stderr.log").open('x') as stderr:
            proc=subprocess.Popen([sys.executable,"-m","sparkbench.vision","analyze","--run",str(run),"--calibration",str(calibration),"--spec",str(spec),"--output",str(output)],
                                  stdout=stdout,stderr=stderr,start_new_session=True)
            deadline=time.monotonic()+600
            try:
                while proc.poll() is None:
                    if cancel.is_set():raise Cancelled("Analysis cancelled; an in-flight Meta request may still be charged")
                    if time.monotonic()>deadline:raise ValueError("Analysis exceeded its bounded deadline")
                    time.sleep(.2)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
        path=output/"verification.json"
        if not path.is_file():raise ValueError("Analysis incomplete; retained logs contain details")
        return json.loads(path.read_text())

    def _work(self, job_id, action, body, cancel):
        folder=self._folder(job_id)
        try:
            if cancel.is_set():raise Cancelled("Cancelled before work started")
            plan=self._reviewed(body["proposal_id"],body["plan_sha256"])
            proposal=self.planner.get(body["proposal_id"])
            if proposal.get("origin")=="mapping_repair" and action!="compile":
                repair=self.jobs[proposal['provenance']['repair_job_id']]
                if body['port']!=repair['request']['port'] or (action=='test' and body['device_id']!=repair['request']['device_id']):
                    raise ValueError('Use the board port and frozen camera from the mapping probe')
                if action=='install':
                    board,_=self._board()
                    source=self._repair_source(repair['source_test_id'],current=False)
                    _,candidate=self._build(body['build_id'],body['proposal_id'],body['plan_sha256'])
                    if board['active_firmware']['firmware_sha256'] not in (source['artifact']['firmware_sha256'],candidate['firmware_sha256']):
                        raise ValueError('The board firmware changed after the mapping probe')
            if action=="compile":
                self._set(job_id,stage="compiling")
                result=self.builder(plan,folder/"artifact")
                if cancel.is_set():raise Cancelled("Cancelled after bounded compile step")
                if result["status"]!="compiled":raise ValueError("Compilation failed; retained compile log available")
                self._set(job_id,status="compiled",stage="compiled",firmware_sha256=result["firmware_sha256"],firmware_bytes=result.get("firmware_bytes"))
            else:
                artifact_path,artifact=self._build(body["build_id"],body["proposal_id"],body["plan_sha256"])
                current=self.enumerate_devices()
                if body["port"] not in [p["id"] for p in current["ports"]]:raise ValueError("Selected CP2102 is absent from fresh host enumeration")
                if cancel.is_set():raise Cancelled("Cancelled before hardware access")
                if action=="install":
                    self._set(job_id,stage="installing")
                    _,previous=self._board();old_hash=digest(previous)
                    result=self.installer(artifact_path,body["port"],previous,old_hash,folder/"installation")
                    if result.get("status")!="installed_hash_verified":raise ValueError("Installation incomplete; inspect retained installation and recovery record")
                    self._record_install(body,artifact_path,artifact,folder/"installation")
                    self._identity(job_id,body,artifact,folder)
                    self._set(job_id,status="installed",stage="installed",firmware_sha256=artifact["firmware_sha256"],cancel_requested=cancel.is_set())
                elif action=='identity':
                    board,_=self._board()
                    if board['active_firmware']['firmware_sha256']!=artifact['firmware_sha256']:raise ValueError('Install this compiled application before checking its identity')
                    result=self._identity(job_id,body,artifact,folder)
                    self._set(job_id,status='identity_confirmed' if result['status']=='pass' else 'incomplete',stage='finished',firmware_sha256=artifact['firmware_sha256'])
                else:
                    if body["device_id"] not in [d["id"] for d in current["cameras"]]:raise ValueError("Selected iPhone absent in this host context; no fallback camera")
                    policy_path=self._camera_policy_path(body['proposal_id'])
                    if (str(policy_path)!=self.jobs[job_id]['camera_policy_path']
                            or digest(policy_path)!=self.jobs[job_id]['camera_policy_sha256']):
                        raise ValueError('Camera reference changed after the test was queued')
                    policy,calibration_path=check_policy(policy_path)
                    calibration=json.loads(calibration_path.read_text())
                    if calibration["camera_id"]!=body["device_id"]:raise ValueError("Selected camera differs from frozen measurement policy")
                    board,_=self._board()
                    if board["active_firmware"]["firmware_sha256"]!=artifact["firmware_sha256"]:raise ValueError("Install this compiled application before its camera test")
                    spec=self.planner.contract(body['proposal_id'])
                    contract_hash=self.planner.get(body['proposal_id']).get('contract_sha256')
                    save(folder/"spec.json",spec)
                    self._set(job_id,stage="preflight",contract_sha256=contract_hash)
                    result=self.runner(body["port"],body["device_id"],folder/"workflow",policy_path,folder/"spec.json",artifact_path=artifact_path,
                        cancel=cancel,on_stage=lambda stage:self._set(job_id,stage=stage),analyzer=lambda *args:self._analyze(job_id,cancel,*args))
                    capture_path=folder/"workflow/capture/run.json"
                    capture=json.loads(capture_path.read_text()) if capture_path.is_file() else {}
                    shutdown="acknowledged_uart_only" if capture.get("stop_acknowledged_uart_only") else "unconfirmed" if capture.get("sequence_started") else "not_started"
                    if cancel.is_set():
                        self._set(job_id,status="cancelled",stage="cancelled",shutdown=shutdown,error="Test cancelled; no behavior pass claimed")
                    else:
                        self._validate_repair_candidate(self.planner.get(body['proposal_id']))
                        if self.planner.contract(body['proposal_id'])!=spec:
                            raise ValueError('Behavior contract changed during the camera test')
                        self._set(job_id,status=result["status"],stage="finished",shutdown=shutdown,physical_verification=result["status"],
                                  failures=result.get("failures"),unknowns=result.get("unknowns"),error=result.get("error"),
                                  expectation_scope="Matches reviewed plan; natural-language intent is not independently certified")
                        if proposal.get('origin')=='mapping_repair':
                            self._set(job_id,repair_job_id=proposal['provenance']['repair_job_id'],
                                      source_test_id=proposal['provenance']['source_test_id'],
                                      repair_verified=result['status']=='pass')
            self._set(job_id,ended_at_utc=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            shutdown={}
            if action=="test":
                capture_path=folder/"workflow/capture/run.json"
                try: capture=json.loads(capture_path.read_text())
                except (OSError,ValueError): capture={}
                shutdown["shutdown"]="acknowledged_uart_only" if capture.get("stop_acknowledged_uart_only") else "unconfirmed" if capture.get("sequence_started") else "not_started"
            self._set(job_id,status="cancelled" if isinstance(exc,Cancelled) else "incomplete",stage="finished",
                      error=str(exc)[:400] if isinstance(exc,ValueError) else "Job failed; inspect retained local evidence",
                      ended_at_utc=datetime.now(timezone.utc).isoformat(),**shutdown)
        finally:
            with self.lock:self.active=None

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs:raise KeyError("Unknown job")
            result=copy.deepcopy(self.jobs[job_id])
            if result.get('action') in ('mapping_repair','camera_setup') and self.active==job_id:
                result['status']='running'  # Publish the terminal result only after its evidence is sealed.
        if result.get("action")=="compile" and result.get("status")=="compiled":result["runtime_current"]=runtime_current(self._folder(job_id)/"artifact")
        result["evidence_available"] = (result.get("status") in ("pass","fail","incomplete")
            and (self._folder(job_id)/"workflow/analysis/verification.json").is_file())
        capture=self._folder(job_id)/('repair' if result.get('action')=='mapping_repair' else 'workflow')/"capture/camera/frames.jsonl"
        if capture.is_file():
            from ..led_oled import frame_rows
            rows=frame_rows(capture)
            if rows and re.fullmatch(r"frame-\d{6}\.jpg",rows[-1].get("file","")):
                row=rows[-1];result["latest_frame"]={"file":row["file"],"url":f"/api/jobs/{job_id}/frames/{row['file']}","live":result.get("stage") in ('capture','probe') and result.get("status")=="running"}
        # Camera setup draws its regions on the frame they came from, which a second capture may have replaced.
        if result.get("action")=="camera_setup" and result.get("source_file") and result.get("stage")!="capture":
            result["latest_frame"]={"file":result["source_file"],"url":f"/api/jobs/{job_id}/frames/{result['source_file']}","live":False}
        if result.get("action")=="test" and result.get("status")=="running" and result.get("stage")=="capture":
            step=self._capture_step(job_id)
            if step:result["capture_step"]=step
        if result.get("action")=="test" and result.get("status")=="running" and result.get("stage")=="analysis":
            progress=self._reading_progress(job_id)
            if progress:
                last=progress.pop("last_frame")
                result["reading_progress"]=progress
                if last:result["latest_frame"]={"file":last,"url":f"/api/jobs/{job_id}/frames/{last}","live":False}
        return result

    def _reading_progress(self, job_id):
        """How far the OLED reading has got, from the files it saves. Display only; never read by the verifier."""
        analysis=self._folder(job_id)/"workflow/analysis"
        try:
            geometry=json.loads((analysis/"calibration.snapshot.json").read_text())["geometry"]
            rows=[json.loads(line) for line in (analysis/"pixels.jsonl").read_text().splitlines() if line.strip()]
            ready=[row["id"] for row in rows if geometry_valid(row,geometry)]
            finished=sorted((path.stat().st_mtime,name) for name in ready if (path:=analysis/"meta"/name/"reading.json").is_file())
        except (OSError,ValueError,KeyError,TypeError):
            return None
        if not ready:return None
        done=len(finished);seconds_left=None
        if done>=2:seconds_left=round((finished[-1][0]-finished[0][0])/(done-1)*(len(ready)-done))
        last_text=None
        if finished:
            try:last_text=json.loads((analysis/"meta"/finished[-1][1]/"reading.json").read_text()).get("text")
            except (OSError,ValueError,AttributeError):pass
        return {"done":done,"total":len(ready),"seconds_left":seconds_left,"last_frame":finished[-1][1]+".jpg" if finished else None,"last_text":last_text,"steps":self._reading_steps(job_id,set(ready),{name for _,name in finished})}

    def _reading_steps(self, job_id, ready, finished):
        workflow=self._folder(job_id)/"workflow"
        try:
            spec=json.loads((workflow/"analysis/spec.snapshot.json").read_text())["steps"]
            frames=[json.loads(line) for line in (workflow/"capture/camera/frames.jsonl").read_text().splitlines() if line.strip()]
            spans=windows(workflow/"capture",frames,[s["step"] for s in spec])
        except (OSError,ValueError,KeyError,TypeError):
            return []
        steps=[]
        for item,span in zip(spec,spans):
            names=[Path(f["file"]).stem for f in span["frames"]]
            steps.append({"step":item["step"],"total":sum(n in ready for n in names),"read":sum(n in finished for n in names)})
        return steps

    def _capture_step(self, job_id):
        """The plan step the board last reported. Display only: UART never supplies a reading."""
        try:lines=(self._folder(job_id)/"workflow/capture/uart.jsonl").read_text().splitlines()
        except OSError:return None
        step=None;started=False
        for line in lines:
            try:event=json.loads(line)
            except ValueError:continue
            if event.get("kind")=="tx" and event.get("command")=="VISUAL":started=True
            elif started and event.get("kind")=="rx_line":
                found=re.match(r"VISUAL_STEP:(\d+) ",event.get("line",""))
                if found:step=int(found[1])
        return step

    def image(self, job_id, name):
        job=self.get(job_id)
        if not re.fullmatch(r"frame-\d{6}\.jpg",name):raise KeyError("Unknown frame")
        file=self._folder(job_id)/('repair' if job.get('action')=='mapping_repair' else 'workflow')/"capture/camera"/name
        if job.get('action')=='camera_setup' and job.get('source_file')==name and job.get('source_path'):
            file=self._folder(job_id)/'workflow'/job['source_path']
        if file.is_symlink() or not file.is_file():raise KeyError("Frame unavailable")
        data=file.read_bytes()
        if not data.startswith(b'\xff\xd8\xff'):raise ValueError("Unsupported image")
        return data

    def _diagnostic_files(self, job_id):
        folder=self._folder(job_id)
        names=['artifact/compile.log','installation/installation.json','identity/identity.json','identity/uart.jsonl',
               'workflow/analysis.stdout.log','workflow/analysis.stderr.log','workflow/capture/uart.jsonl',
               'repair/capture/uart.jsonl','repair/discovery/discovery.json','repair/proposal/request.json',
               'repair/proposal/result.json','repair/binding.json','approval.json']
        names += ['installation/'+p.name for p in sorted((folder/'installation').glob('*.log')) if re.fullmatch(r'\d{2}-[a-z-]+\.log',p.name)]
        return [name for name in names if (folder/name).is_file() and not (folder/name).is_symlink() and (folder/name).resolve().is_relative_to(folder.resolve())]

    def diagnostics(self, job_id):
        job=self.get(job_id);folder=self._folder(job_id);installation=None
        if 'installation/installation.json' in self._diagnostic_files(job_id):
            report=json.loads((folder/'installation/installation.json').read_text())
            installation={k:report.get(k) for k in ['status','uploaded','reused_verified_application','previous_installed_bytes_verified','firmware_sha256','previous_firmware_sha256','recovery','error','ended_at_utc']}
            installation['write_attempted']=any('write-flash' in cmd for cmd in report.get('commands',[]))
        identity=job.get('runtime_identity')
        recovery=installation.get('recovery') if installation else None
        if job['action']=='compile':
            next_step='Review the compiler log. Resolve the reported toolchain/dependency error, then explicitly compile again.' if job['status'] in ('incomplete','interrupted','cancelled') else 'Compilation does not install firmware. Continue with explicit device selection and installation.'
        elif recovery=='previous_application_restored_hash_verified':
            next_step='The previous application was restored and flash-verified. Inspect the failed installation step before explicitly retrying.'
        elif recovery:
            next_step='Recovery is unconfirmed. Keep the servo supply off. Inspect the recovery logs and establish the board firmware state before running a test.'
        elif installation and installation['status']=='installed_hash_verified':
            next_step='Flash bytes are verified. '+('The idle runtime identity and OLED ACK are confirmed over UART; visible behavior still needs a camera test.' if identity and identity.get('status')=='pass' else 'Recheck the runtime identity using the selected USB device. This does not execute the LED sequence.')
        elif job['action']=='install':
            next_step='No successful installation is recorded. Refresh connected devices, select the CP2102 and inspect the retained preflight/write logs before retrying.'
        elif job['action']=='identity':
            next_step='Identity checking sends only ID. Check the USB connection and expected plan identity; no physical output pass is implied.'
        else:next_step='Inspect the retained test evidence and unknown readings. Refresh camera geometry if the saved reference no longer matches; a missing reading remains incomplete.'
        return {'job_id':job_id,'action':job['action'],'status':job['status'],'stage':job['stage'],'error':job.get('error'),
                'installation':installation,'runtime_identity':identity,'next_step':next_step,
                'logs':[{'name':name,'url':f'/api/jobs/{job_id}/logs/{i}'} for i,name in enumerate(self._diagnostic_files(job_id))],
                'scope':'Local build/installation/UART records; no automatic physical output assertion'}

    def log(self, job_id, index):
        self.get(job_id);names=self._diagnostic_files(job_id)
        if not 0<=index<len(names):raise KeyError('Unknown job log')
        path=self._folder(job_id)/names[index]
        with path.open('rb') as stream:
            size=path.stat().st_size
            if size>262144:stream.seek(-262144,2)
            text=stream.read().decode('utf-8',errors='replace')
        return {'name':names[index],'text':text,'truncated':size>262144}

    def list(self, proposal_id=None):
        with self.lock:
            ids=[j["id"] for j in sorted(self.jobs.values(),key=lambda j:j["started_at_utc"],reverse=True)
                 if proposal_id is None or j["proposal_id"]==proposal_id][:40]
        return [self.get(job_id) for job_id in ids]

    def cancel(self, job_id):
        with self.lock:
            if job_id not in self.jobs:raise KeyError("Unknown job")
            if self.active==job_id:
                self.cancel_event.set();self._set(job_id,cancel_requested=True)
            elif self.jobs[job_id].get('action')=='camera_setup' and self.jobs[job_id].get('status')=='setup_review':
                self._set(job_id,status='cancelled',stage='finished',cancel_requested=True)
        return self.get(job_id)

    def shutdown(self):
        with self.lock:
            if self.active:self.cancel_event.set()

    def _test_title(self, job_id):
        """Names a recorded test after what the plan showed, so the runs can be told apart."""
        try:
            labels=[step["oled_text"] for step in json.loads((self._folder(job_id)/"spec.json").read_text())["steps"]]
            return ", ".join(labels) or "Camera test"
        except (OSError,ValueError,KeyError,TypeError):
            return "Camera test"

    def register_evidence(self):
        for job in self.list():
            folder=self._folder(job["id"])/"workflow"
            if job["action"]=="test" and job["status"] in ("pass","fail","incomplete") and (folder/"analysis/verification.json").is_file():
                relative=str(folder.relative_to(self.root))
                self.store.catalog["test-"+job["id"]]=Run("test-"+job["id"],self._test_title(job["id"]),"Camera test of an approved plan",relative,relative+"/capture")
