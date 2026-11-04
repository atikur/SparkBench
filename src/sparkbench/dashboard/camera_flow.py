"""Camera-only reference setup for the existing calibrated LED/OLED bench.

Setup never derives measurements from a behavior test, changes LED thresholds,
or sends serial commands. A reference is activated only after a new idle capture.
"""
import base64
import copy
import json
import re
import subprocess
import threading
import uuid
from datetime import datetime, timezone

from ..camera import capture_frames
from ..intent import save
from ..policy import check_policy
from ..setup_registration import check_regions, register_setup
from ..vision import digest, finite, geometry_valid
from .camera_setup import CameraSetupStore
from .planning import BusyError, IDENTIFIER


def now():
    return datetime.now(timezone.utc).isoformat()


class CameraSetupMixin:
    def _camera_policy_path(self, proposal_id=None):
        default = self.root / 'hardware/oled-reader.policy.json'
        if proposal_id is None:
            return default
        if not isinstance(proposal_id, str) or not IDENTIFIER.fullmatch(proposal_id):
            raise ValueError('Valid proposal ID required')
        proposal = self.planner.get(proposal_id)
        if proposal.get('origin') == 'mapping_repair':
            # A repair is measured with exactly its parent's reference.
            proposal_id = proposal['parent_id']
        return CameraSetupStore(self.root, self.planner).policy_path(proposal_id, default)

    def _setup_eligible(self, proposal_id):
        if not isinstance(proposal_id, str) or not IDENTIFIER.fullmatch(proposal_id):
            raise ValueError('Choose a ready project plan before camera setup')
        proposal = self.planner.get(proposal_id)
        if proposal.get('status') != 'ready' or proposal.get('origin') == 'mapping_repair':
            raise ValueError('Camera setup needs an original ready plan, not a repair')
        if any(j.get('action') == 'test' and j.get('proposal_id') == proposal_id
               for j in self.jobs.values()):
            raise ValueError('This plan has already been tested. Restore its saved camera view, '
                             'or create a new plan to establish a new reference. Earlier results stay unchanged.')
        return proposal

    def camera_setup_available(self, proposal_id):
        try:
            self._setup_eligible(proposal_id)
            return True
        except (ValueError, KeyError):
            return False

    def start_camera_setup(self, body):
        if (set(body) != {'request_id', 'proposal_id', 'device_id'}
                or not isinstance(body['request_id'], str) or not IDENTIFIER.fullmatch(body['request_id'])
                or not isinstance(body['device_id'], str) or not body['device_id']):
            raise ValueError('Select a plan, an iPhone and a fresh request ID')
        with self.lock:
            for job in self.jobs.values():
                if job.get('request_id') == body['request_id']:
                    if job.get('action') != 'camera_setup' or job.get('request') != body:
                        raise ValueError('Request ID already used')
                    return job['id']
            if self.active:
                raise BusyError('Another job owns the bench')
            proposal = self._setup_eligible(body['proposal_id'])
            policy_path = self._camera_policy_path(body['proposal_id'])
            _, calibration_path = check_policy(policy_path)
            calibration = json.loads(calibration_path.read_text())
            if calibration['camera_id'] != body['device_id']:
                raise ValueError('This setup refreshes the calibrated iPhone view. A different camera '
                                 'needs separate LED on/off calibration first.')
            job_id = uuid.uuid4().hex
            folder = self._folder(job_id); folder.mkdir(parents=True)
            job = {'id': job_id, 'action': 'camera_setup', 'status': 'running', 'stage': 'capture',
                   'proposal_id': body['proposal_id'], 'plan_sha256': proposal['plan_sha256'],
                   'request_id': body['request_id'], 'request': dict(body), 'started_at_utc': now(),
                   'base_policy_path': str(policy_path), 'base_policy_sha256': digest(policy_path),
                   'serial_commands_sent': [], 'servo_actuation': False,
                   'physical_verification': 'not_performed', 'meta_requests': 0}
            self.jobs[job_id] = job; save(folder / 'job.json', job)
            self.active = job_id; self.cancel_event = threading.Event()
            self.thread = threading.Thread(target=self._capture_camera_setup,
                args=(job_id, calibration, self.cancel_event), daemon=False)
            self.thread.start()
            return job_id

    @staticmethod
    def _setup_frames(output, device_id):
        from ..led_oled import frame_rows
        metadata = json.loads((output / 'capture.json').read_text())
        rows = frame_rows(output / 'frames.jsonl')
        if (metadata.get('status') != 'captured' or metadata.get('source') != 'live_camera'
                or metadata.get('camera', {}).get('id') != device_id
                or metadata.get('frame_count') != len(rows) or len(rows) < 3):
            raise ValueError('A complete fresh iPhone capture is required')
        last = None
        for row in rows:
            if not re.fullmatch(r'frame-\d{6}\.jpg', row.get('file', '')):
                raise ValueError('Unsupported camera frame name')
            path = output / row['file']
            pts, uptime = row.get('sample_pts_seconds'), row.get('host_uptime_seconds')
            if (path.is_symlink() or not path.is_file() or not finite(pts) or not finite(uptime)
                    or not 0 <= uptime - pts <= 1 or (last is not None and pts <= last)):
                raise ValueError('Fresh camera frames have invalid timing or missing images')
            last = pts
        return rows

    def _capture_camera_setup(self, job_id, calibration, cancel):
        job = self.jobs[job_id]
        try:
            camera = job['request']['device_id']
            if camera not in [d['id'] for d in self.enumerate_devices()['cameras']]:
                raise ValueError('Selected iPhone absent in this process context; no fallback camera')
            if cancel.is_set(): raise ValueError('Setup cancelled before capture')
            output = self._folder(job_id) / 'workflow/capture/camera'
            output.parent.mkdir(parents=True)
            capture_frames(camera, seconds=5, fps=2, output=output)
            if cancel.is_set(): raise ValueError('Setup cancelled after capture')
            row = self._setup_frames(output, camera)[-1]
            geometry = calibration['geometry']
            if (row['width'], row['height']) != (geometry['image_width'], geometry['image_height']):
                raise ValueError('Capture resolution differs from the calibrated bench')
            source = output / row['file']
            self._set(job_id, stage='suggesting', image_sha256=digest(source),
                      source_file=row['file'], image_width=row['width'], image_height=row['height'],
                      led_radii={name: geometry['leds'][name]['radius'] for name in ('red', 'green')},
                      meta_requests=1)
            regions, sources, note = {}, {}, None
            try:
                suggestion = self.region_proposer({'image': {'name': source.name,
                    'data': base64.b64encode(source.read_bytes()).decode('ascii')},
                    'width': row['width'], 'height': row['height'], 'points': {}})
                if suggestion['image_sha256'] != digest(source):
                    raise ValueError('SAM result belongs to another photo')
                regions = suggestion['regions']
                sources = {name: suggestion['model'] for name in regions}
                save(self._folder(job_id) / 'sam-suggestion.json', suggestion)
            except ValueError as exc:
                note = str(exc) + ' Draw the screen box manually.'
            if cancel.is_set(): raise ValueError('Setup cancelled before alignment')
            prefill = {}
            if 'oled' in regions:
                try:
                    self._set(job_id, stage='aligning')
                    try:
                        aligned = register_setup(source, calibration)
                    except ValueError as exc:
                        if cancel.is_set():
                            raise ValueError('Setup cancelled before locating components') from exc
                        save(self._folder(job_id) / 'alignment-failure.json', {'reason': str(exc)})
                        self._set(job_id, stage='locating')
                        aligned = register_setup(source, calibration, screen=regions['oled'])
                    corners = aligned['landmarks'][:4]
                    points = dict(zip(('red', 'green'), aligned['landmarks'][4:]))
                    if cancel.is_set(): raise ValueError('Setup cancelled before SAM lens check')
                    self._set(job_id, stage='suggesting', meta_requests=job['meta_requests'] + 1)
                    led = self.region_proposer({'image': {'name': source.name,
                        'data': base64.b64encode(source.read_bytes()).decode('ascii')},
                        'width': row['width'], 'height': row['height'], 'points': points})
                    if led['image_sha256'] != job['image_sha256']:
                        raise ValueError('SAM lens result belongs to another photo')
                    save(self._folder(job_id) / 'sam-auto-lenses.json', led)
                    boxes = {'oled': regions['oled'], **led['regions']}
                    check_regions(boxes, corners, points, job['led_radii'])
                    body = {'image_sha256': job['image_sha256'], 'regions': boxes,
                            'sources': {name: 'sam-3.1' for name in boxes},
                            'points': points, 'oled_corners': corners}
                    if cancel.is_set(): raise ValueError('Setup cancelled before validation')
                    base = self._camera_policy_path(job['proposal_id'])
                    if str(base) != job['base_policy_path'] or digest(base) != job['base_policy_sha256']:
                        raise ValueError('Camera policy changed during setup')
                    # Keep an unsuccessful automatic candidate separate from the
                    # manual fallback, so neither overwrites the other's evidence.
                    candidate_id = uuid.uuid4().hex
                    candidate = CameraSetupStore(self.root, self.planner).prepare(
                        candidate_id, job['proposal_id'], camera, source, body, base,
                        registration=aligned)
                    prefill = {'points': points, 'oled_corners': corners}
                    regions, sources = boxes, body['sources']
                    self._set(job_id, stage='validating', automatic_candidate_id=candidate_id)
                    self._qualify_camera_setup(job_id, candidate_id, candidate, cancel, automatic=True)
                    return
                except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
                    note = 'Automatic setup needs help: ' + str(exc)[:300]
            else:
                note = note or 'SAM could not isolate the screen. Mark it to continue.'
            if cancel.is_set(): raise ValueError('Setup cancelled before review')
            self._set(job_id, status='setup_review', stage='review', regions=regions,
                      sources=sources, setup_note=note, ended_at_utc=now(), **prefill)
        except Exception as exc:
            self._set(job_id, status='cancelled' if cancel.is_set() else 'incomplete', stage='finished',
                      error=str(exc)[:400] if isinstance(exc, ValueError) else 'Camera setup capture unavailable',
                      ended_at_utc=now())
        finally:
            with self.lock: self.active = None

    def confirm_camera_setup(self, job_id, body):
        with self.lock:
            job = self.jobs.get(job_id, {})
            if job.get('action') != 'camera_setup': raise ValueError('Unknown camera setup')
            if job.get('confirmation') == body and job.get('status') in ('running', 'setup_ready'):
                return job_id
            if self.active: raise BusyError('Another job owns the bench')
            if job.get('status') != 'setup_review': raise ValueError('Capture a new setup reference before confirming')
            proposal = self._setup_eligible(job['proposal_id'])
            if proposal['plan_sha256'] != job['plan_sha256']:
                raise ValueError('The project plan changed during setup')
            base = self._camera_policy_path(job['proposal_id'])
            if str(base) != job['base_policy_path'] or digest(base) != job['base_policy_sha256']:
                raise ValueError('Camera policy changed during setup; capture a fresh reference')
            source = self._folder(job_id) / 'workflow/capture/camera' / job['source_file']
            if digest(source) != job['image_sha256']:
                raise ValueError('The setup source image changed')
            candidate = CameraSetupStore(self.root, self.planner).prepare(job_id, job['proposal_id'],
                job['request']['device_id'], source, body, base)
            self._set(job_id, status='running', stage='validating', confirmation=copy.deepcopy(body), error=None)
            self.active = job_id; self.cancel_event = threading.Event()
            self.thread = threading.Thread(target=self._validate_camera_setup,
                args=(job_id, candidate, self.cancel_event), daemon=False)
            self.thread.start()
            return job_id

    def suggest_camera_setup(self, job_id, body):
        """Bound each guided SAM request to the saved source and bench owner."""
        if set(body) != {'points'} or not isinstance(body['points'], dict):
            raise ValueError('LED lens points required')
        points = body['points']
        if points and set(points) != {'red', 'green'}:
            raise ValueError('Select both LED lenses')
        with self.lock:
            job = self.jobs.get(job_id, {})
            if job.get('action') != 'camera_setup' or job.get('status') != 'setup_review':
                raise ValueError('A pending camera setup review is required')
            if self.active: raise BusyError('Another job owns the bench')
            self._setup_eligible(job['proposal_id'])
            width, height = job['image_width'], job['image_height']
            for point in points.values():
                if (not isinstance(point, list) or len(point) != 2
                        or any(type(v) is not int for v in point)
                        or not 0 <= point[0] < width or not 0 <= point[1] < height):
                    raise ValueError('Lens points must be inside the setup image')
            if points and points['red'] == points['green']:
                raise ValueError('Select separate LED lenses')
            source = self._folder(job_id) / 'workflow/capture/camera' / job['source_file']
            if digest(source) != job['image_sha256']:
                raise ValueError('The setup source image changed')
            call_id = uuid.uuid4().hex
            record_path = self._folder(job_id) / ('sam-' + call_id + '.json')
            record = {'image_sha256': job['image_sha256'], 'points': copy.deepcopy(points),
                      'model': 'sam-3.1', 'requested_at_utc': now()}
            save(record_path, record)
            self._set(job_id, status='running', stage='suggesting', meta_requests=job['meta_requests'] + 1)
            self.active = job_id; self.cancel_event = threading.Event()
            cancel = self.cancel_event
        try:
            result = self.region_proposer({'image': {'name': source.name,
                'data': base64.b64encode(source.read_bytes()).decode('ascii')},
                'width': width, 'height': height, 'points': points})
            if result['image_sha256'] != job['image_sha256']:
                raise ValueError('SAM returned regions for a different source image')
            save(record_path, {**record, 'result': result, 'finished_at_utc': now()})
            if cancel.is_set(): raise ValueError('Camera setup suggestion cancelled')
            return result
        except Exception as exc:
            save(record_path, {**record, 'error': str(exc)[:400] if isinstance(exc, ValueError)
                              else 'SAM suggestion incomplete', 'finished_at_utc': now()})
            raise
        finally:
            with self.lock:
                self._set(job_id, status='cancelled' if cancel.is_set() else 'setup_review',
                          stage='finished' if cancel.is_set() else 'review')
                self.active = None

    def _validate_camera_setup(self, job_id, candidate, cancel):
        try:
            self._qualify_camera_setup(job_id, job_id, candidate, cancel)
        except Exception as exc:
            self._set(job_id, status='cancelled' if cancel.is_set() else 'setup_blocked', stage='finished',
                      error=str(exc)[:400] if isinstance(exc, ValueError) else 'Reference validation incomplete',
                      ended_at_utc=now())
        finally:
            with self.lock: self.active = None

    def _qualify_camera_setup(self, job_id, candidate_id, candidate, cancel, *, automatic=False):
        job = self.jobs[job_id]
        camera = job['request']['device_id']
        if camera not in [d['id'] for d in self.enumerate_devices()['cameras']]:
            raise ValueError('Selected iPhone is absent; no fallback camera')
        if cancel.is_set(): raise ValueError('Setup cancelled before validation')
        _, calibration_path = check_policy(candidate['policy_path'])
        calibration = json.loads(calibration_path.read_text()); geometry = calibration['geometry']
        run = self._folder(job_id) / ('workflow/automatic-validation' if automatic else 'workflow/validation'); run.mkdir()
        output = run / 'camera'
        capture_frames(camera, seconds=5, fps=2, output=output)
        if cancel.is_set(): raise ValueError('Setup cancelled after validation capture')
        chosen = self._setup_frames(output, camera)[-3:]
        analysis = run / 'analysis'; analysis.mkdir()
        native = self.view_reader(run, geometry, chosen, analysis, read_labels=False)
        rows = [native[r['file']] for r in chosen]
        issues = self._view_issues(rows, sum(geometry_valid(r, geometry) for r in rows),
                                   sum(r.get('status') == 'measured' for r in rows), calibration)
        if issues: raise ValueError('Reference check blocked. ' + ' '.join(i['problem'] for i in issues))
        if cancel.is_set(): raise ValueError('Setup cancelled before OLED check')
        self._set(job_id, meta_requests=job.get('meta_requests', 0) + 1)
        reading = self.label_reader(analysis / 'crops' / rows[-1]['label_crop'], analysis / 'meta')
        if reading.get('status') != 'read':
            raise ValueError('OLED text is not readable from the confirmed corners. Check the view and try a new setup.')
        if cancel.is_set(): raise ValueError('Setup cancelled before reference activation')
        save(run / 'integrity.json', {'sha256': {str(p.relative_to(run)): digest(p)
             for p in sorted(run.rglob('*')) if p.is_file() and p != run / 'integrity.json'}})
        proof = {'status': 'view_ok', 'source': 'fresh_camera_only_validation',
                 'device_id': camera, 'frames_checked': len(chosen), 'oled_reading': reading.get('text'),
                 'serial_commands_sent': [], 'physical_verification': 'not_performed',
                 'validated_at_utc': now(), 'frames_sha256': {r['file']: digest(output / r['file']) for r in chosen},
                 'validation_directory': str(run), 'validation_integrity_sha256': digest(run / 'integrity.json'),
                 'thresholds': 'inherited_unchanged'}
        with self.lock:
            self._setup_eligible(job['proposal_id'])
            if cancel.is_set(): raise ValueError('Setup cancelled before reference activation')
            CameraSetupStore(self.root, self.planner).activate(candidate_id, job['proposal_id'], proof)
            self._set(job_id, status='setup_ready', stage='finished', ended_at_utc=now(),
                      setup_mode='automatic' if automatic else 'manual',
                      oled_reading=reading.get('text'), reference_url='/api/camera/reference/' + job['proposal_id'],
                      setup_note='Reference saved. LED thresholds are unchanged; behavior verification still requires a fresh test.')
