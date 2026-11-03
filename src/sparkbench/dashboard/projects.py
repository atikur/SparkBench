"""Persistent beginner projects and explicit, serialized Meta guidance turns."""
import copy
import hashlib
import json
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ..guide import ASSEMBLY, CATALOG_IDS, ask_guide, bounded_text, image_bytes
from ..intent import fingerprint, save
from .planning import BusyError, IDENTIFIER

def now():return datetime.now(timezone.utc).isoformat()

class ProjectService:
    def __init__(self, root, planner, store, generator=ask_guide, execution=None):
        self.root=Path(root);self.directory=self.root/'runs/projects';self.planner=planner;self.store=store;self.generator=generator
        self.lock=threading.RLock();self.active=None
        self.execution=execution

    def folder(self, project_id):
        if not isinstance(project_id,str) or not IDENTIFIER.fullmatch(project_id):raise KeyError('Unknown project')
        folder=self.directory/project_id
        if folder.is_symlink():raise ValueError('Project path rejected')
        return folder

    def _write(self, project):
        folder=self.folder(project['id']);folder.mkdir(parents=True,exist_ok=True)
        save(folder/'project.json',project);save(folder/'integrity.json',{'sha256':{'project.json':hashlib.sha256((folder/'project.json').read_bytes()).hexdigest()}})

    def _read(self, project_id):
        folder=self.folder(project_id);path=folder/'project.json'
        if path.is_symlink() or (folder/'integrity.json').is_symlink():raise ValueError('Project path rejected')
        try:
            data=path.read_bytes();manifest=json.loads((folder/'integrity.json').read_text())
            if hashlib.sha256(data).hexdigest()!=manifest['sha256']['project.json']:raise ValueError('Project checksum mismatch')
            return json.loads(data)
        except FileNotFoundError:raise KeyError('Unknown project')

    def _turn(self, project_id, turn_id):
        if not isinstance(turn_id,str) or not IDENTIFIER.fullmatch(turn_id):raise KeyError('Unknown guide turn')
        folder=self.folder(project_id)/'turns'/turn_id
        if folder.is_symlink():raise ValueError('Turn path rejected')
        return folder

    def _checked_turn(self, project_id, turn_id):
        folder=self._turn(project_id,turn_id)
        try:
            data=(folder/'result.json').read_bytes();manifest=json.loads((folder/'integrity.json').read_text())
            if (folder/'result.json').is_symlink() or (folder/'integrity.json').is_symlink() or hashlib.sha256(data).hexdigest()!=manifest['sha256']['result.json']:raise ValueError('Guide response checksum mismatch')
            return json.loads(data)
        except FileNotFoundError:return None

    def get(self, project_id):
        with self.lock:
            project=copy.deepcopy(self._read(project_id));turns=[]
            for turn in project['turns']:
                result=self._checked_turn(project_id,turn['id'])
                if result is None:result={'status':'generating' if self.active==(project_id,turn['id']) else 'interrupted','reply':None,'api_requests':None,'error':None if self.active==(project_id,turn['id']) else 'Previous request interrupted; no automatic resume.'}
                turns.append({**turn,**result})
            project['turns']=turns
            project['draft']=next((t['reply'] for t in reversed(turns) if t['status']=='complete'),None)
            project['busy']=any(t['status']=='generating' for t in turns)
            project['physical_verification']='not_performed_by_guide'
            if self.execution:project['firmware_status']=self.status(project_id)
            return project

    def status(self, project_id):
        from .lifecycle import firmware_status
        with self.lock:project=copy.deepcopy(self._read(project_id))
        if not self.execution:return None
        return firmware_status(project,self.planner,self.execution)

    def list(self):
        if not self.directory.exists():return []
        rows=[]
        for folder in self.directory.iterdir():
            if IDENTIFIER.fullmatch(folder.name) and folder.is_dir():
                try:
                    p=self.get(folder.name);rows.append({'id':p['id'],'title':p['draft']['title'] if p['draft'] else p['idea'][:70],'updated_at_utc':p['updated_at_utc'],'busy':p['busy']})
                except (KeyError,ValueError,OSError):rows.append({'id':folder.name,'title':'Project unavailable','updated_at_utc':'','busy':False})
        return sorted(rows,key=lambda r:r['updated_at_utc'],reverse=True)[:40]

    def create(self, body):
        if set(body)!={'idea','experience','budget','parts_notes','request_id'}:raise ValueError('Invalid new-project fields')
        if not isinstance(body['request_id'],str) or not IDENTIFIER.fullmatch(body['request_id']):raise ValueError('Valid request ID required')
        idea=bounded_text(body['idea'],2000,'Project idea');profile=self._profile(body)
        with self.lock:
            for row in self.list():
                prior=self._read(row['id'])
                if prior.get('request_id')==body['request_id']:
                    if prior['idea']!=idea or prior['profile']!=profile:raise ValueError('Request ID already used')
                    return prior['id']
            project={'id':uuid.uuid4().hex,'idea':idea,'profile':profile,'request_id':body['request_id'],'owned':{},'completed_steps':[],
                     'turns':[],'accepted':None,'acceptance_history':[],'firmware_links':[],'revision':1,'created_at_utc':now(),'updated_at_utc':now()}
            self._write(project);return project['id']

    def _profile(self, body):
        if not isinstance(body,dict):raise ValueError('Project profile object required')
        if body.get('experience') not in ('beginner','some_experience'):raise ValueError('Choose an experience level')
        return {'experience':body['experience'],'budget':bounded_text(body['budget'],120,'Budget',True),'parts_notes':bounded_text(body['parts_notes'],1500,'Parts notes',True)}

    def update(self, project_id, body):
        if set(body)!={'revision','profile','owned','completed_steps'}:raise ValueError('Invalid project update fields')
        profile=self._profile(body['profile']);owned=body['owned'];steps=body['completed_steps']
        if not isinstance(owned,dict) or not set(owned)<=CATALOG_IDS or any(type(q) is not int or not 0<=q<=100 for q in owned.values()):raise ValueError('Invalid owned-part quantities')
        if not isinstance(steps,list) or len(set(steps))!=len(steps) or not set(steps)<={s['id'] for s in ASSEMBLY}:raise ValueError('Invalid assembly checklist')
        with self.lock:
            p=self._read(project_id)
            if body['revision']!=p['revision']:raise ValueError('Project changed. Reload before saving.')
            p.update(profile=profile,owned=owned,completed_steps=steps,revision=p['revision']+1,updated_at_utc=now());self._write(p)
        return self.get(project_id)

    def ask(self, project_id, body):
        if set(body)!={'message','images','request_id','run_id'}:raise ValueError('Invalid guide request fields')
        message=bounded_text(body['message'],3000,'Question');images=body['images'];request_id=body['request_id']
        if not isinstance(request_id,str) or not IDENTIFIER.fullmatch(request_id):raise ValueError('Valid request ID required')
        if not isinstance(images,list) or len(images)>3:raise ValueError('Attach up to three photos')
        for image in images:image_bytes(image)
        request_hash=fingerprint(body)
        with self.lock:
            p=self._read(project_id)
            for turn in p['turns']:
                if turn['request_id']==request_id:
                    if turn['request_hash']!=request_hash:raise ValueError('Request ID already used')
                    return turn['id']
            if self.active:raise BusyError('A build-guide request is already running. Wait for its result.')
            if len(p['turns'])>=60:raise ValueError('This project reached 60 saved turns; start a new project')
            context={k:p[k] for k in ['idea','profile','owned','completed_steps','accepted']}
            recent=self.get(project_id)['turns'][-6:]
            context['history']=[{'question':t['message'],'reply':t['reply']} for t in recent if t.get('reply')]
            context['photo_scope']='Only photos attached to this question are supplied as image bytes; prior photo descriptions are historical.'
            if body['run_id'] is not None:
                if not isinstance(body['run_id'],str):raise ValueError('Invalid recorded run')
                run=self.store.load(body['run_id']);context['recorded_test']={k:run[k] for k in ['title','recorded_at','behavior_verdict','evaluated_sample_count','mismatch_count','unknown_count','failures','unknowns','provenance']}
                context['recorded_test']['unknowns']=context['recorded_test']['unknowns'][:12]
                context['recorded_test']['failures']=context['recorded_test']['failures'][:12]
                samples=[f for f in run['frames'] if f['evaluated']]
                context['recorded_test']['geometry_supported_samples']=sum(f['geometry_supported'] is True for f in samples)
                context['recorded_test']['geometry_rejected_samples']=sum(f['geometry_supported'] is False for f in samples)
                context['recorded_test']['expected_steps']=[{'step':s['id'],**next((f['expected'] for f in samples if f['step']==s['id']),{})} for s in run['steps']]
                context['recorded_test']['project_binding']='Unlinked historical run selected by the user. It is not evidence that this project was executed. State its own frozen step labels and do not substitute the current project goals.'
                try:
                    entry=self.store.entry(body['run_id']);pixels=self.store.checked_bytes(entry.directory+'/analysis/pixels.jsonl')
                    context['recorded_test']['pixel_rejection_reasons']=dict(Counter(json.loads(line).get('error') for line in pixels.splitlines() if json.loads(line).get('error')))
                except (OSError,ValueError,KeyError):pass
            turn_id=uuid.uuid4().hex
            turn={'id':turn_id,'message':message,'request_id':request_id,'request_hash':request_hash,'run_id':body['run_id'],'created_at_utc':now()}
            p['turns'].append(turn);p.update(revision=p['revision']+1,updated_at_utc=now());self._write(p);self.active=(project_id,turn_id)
            threading.Thread(target=self._work,args=(project_id,turn_id,context,message,images),daemon=True).start();return turn_id

    def _work(self, project_id, turn_id, context, message, images):
        folder=self._turn(project_id,turn_id)
        try:self.generator(context,message,images,folder)
        except Exception:
            folder.mkdir(parents=True,exist_ok=True)
            save(folder/'result.json',{'status':'error','reply':None,'error':'Guide request failed. Check local Meta configuration; no automatic retry.','api_requests':None,'physical_verification':'not_performed'})
            save(folder/'integrity.json',{'sha256':{'result.json':hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()}})
        finally:
            with self.lock:self.active=None

    def accept(self, project_id, turn_id):
        with self.lock:
            p=self._read(project_id)
            if self.active and self.active[0]==project_id:raise BusyError('Wait for the guide response before accepting the brief')
            if not any(t['id']==turn_id for t in p['turns']):raise KeyError('Unknown project turn')
            turn=self._checked_turn(project_id,turn_id)
            if not turn or turn['status']!='complete' or turn['reply']['decision']!='planned':raise ValueError('Accept a complete supported project brief')
            if p['accepted'] and p['accepted']['turn_id']==turn_id:return self.get(project_id)
            brief={k:turn['reply'][k] for k in ['title','summary','goals','components','firmware_instruction']}
            accepted={'turn_id':turn_id,'brief':brief,'sha256':fingerprint(brief),'accepted_at_utc':now(),'scope':'User-accepted intended behavior; no physical pass asserted'}
            if p['accepted']:p['acceptance_history'].append(p['accepted'])
            p.update(accepted=accepted,revision=p['revision']+1,updated_at_utc=now());self._write(p)
        return self.get(project_id)

    def firmware(self, project_id, body):
        if set(body)!={'accepted_sha256','request_id'}:raise ValueError('Accepted brief hash and request ID required')
        with self.lock:
            p=self._read(project_id);accepted=p['accepted']
            if not accepted or accepted['sha256']!=body['accepted_sha256'] or fingerprint(accepted['brief'])!=accepted['sha256']:raise ValueError('Accept the unchanged project brief first')
            proposal=self.planner.start(accepted['brief']['firmware_instruction'],body['request_id'])
            if not any(l['proposal_id']==proposal for l in p['firmware_links']):
                p['firmware_links'].append({'proposal_id':proposal,'accepted_sha256':accepted['sha256'],'created_at_utc':now()});p.update(revision=p['revision']+1,updated_at_utc=now());self._write(p)
            return proposal

    def image(self, project_id, turn_id, name):
        turn=self._checked_turn(project_id,turn_id)
        if not turn:raise KeyError('Image unavailable')
        attachment=next((a for a in turn.get('attachments',[]) if a['file']==name),None)
        if not attachment or '/' in name or '\\' in name:raise KeyError('Unknown image')
        path=self._turn(project_id,turn_id)/name
        if path.is_symlink():raise ValueError('Image path rejected')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=attachment['sha256']:raise ValueError('Image checksum mismatch')
        return data,attachment['mime']
