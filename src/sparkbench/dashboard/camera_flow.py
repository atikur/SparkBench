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

    def _tests_for(self, proposal_id):
        return sorted(j.get('id') or key for key, j in self.jobs.items() if j.get('action') == 'test' and j.get('proposal_id') == proposal_id)

    def _setup_eligible(self, proposal_id, tests_seen=None):
        """A ready plan may get a new camera reference at any time the bench is idle. Every test records
        the reference it used, so earlier results keep their own. A test that ran after a setup capture
        means the capture no longer describes the bench, so that capture cannot be activated."""
        if not isinstance(proposal_id, str) or not IDENTIFIER.fullmatch(proposal_id):
            raise ValueError('Choose a ready project plan before camera setup')
        proposal = self.planner.get(proposal_id)
        if proposal.get('status') != 'ready' or proposal.get('origin') == 'mapping_repair':
            raise ValueError('Camera setup needs an original ready plan, not a repair')
        if tests_seen is not None and set(self._tests_for(proposal_id)) - set(tests_seen):
            raise ValueError('A test ran after this setup capture. Capture a fresh reference.')
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
                   'tests_seen': self._tests_for(body['proposal_id']),
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

    SETUP_CAPTURES = 2
    SETUP_FRAMES = 3

    def _capture_once(self, job_id, camera, attempt, cancel):
        output = self._folder(job_id) / ('workflow/capture' if attempt == 1 else 'workflow/capture-%d' % attempt) / 'camera'
        output.parent.mkdir(parents=True)
        capture_frames(camera, seconds=5, fps=2, output=output)
        if cancel.is_set(): raise ValueError('Setup cancelled after capture')
        return output, self._setup_frames(output, camera)

    def _auto_landmarks(self, job_id, source, screen, calibration, cancel):
        """Landmarks for one frame: the commissioned view aligned onto it, else the lenses and lit
        border found in the frame itself inside SAM's screen box."""
        try:
            self._set(job_id, stage='aligning')
            return register_setup(source, calibration)
        except ValueError as exc:
            if cancel.is_set(): raise ValueError('Setup cancelled before locating components') from exc
            save(self._folder(job_id) / ('alignment-failure-' + source.stem + '.json'), {'reason': str(exc)})
            if screen is None:
                raise ValueError('SAM could not isolate the screen and the saved view does not align') from exc
            self._set(job_id, stage='locating')
            return register_setup(source, calibration, screen=screen)

    def _capture_camera_setup(self, job_id, calibration, cancel):
        job = self.jobs[job_id]
        geometry = calibration['geometry']
        radii = {name: geometry['leds'][name]['radius'] for name in ('red', 'green')}
        reasons = []
        try:
            camera = job['request']['device_id']
            if camera not in [d['id'] for d in self.enumerate_devices()['cameras']]:
                raise ValueError('Selected iPhone absent in this process context; no fallback camera')
            if cancel.is_set(): raise ValueError('Setup cancelled before capture')
            found = None; last = None
            for attempt in range(1, self.SETUP_CAPTURES + 1):
                self._set(job_id, stage='capture', setup_attempt=attempt)
                try:
                    output, rows = self._capture_once(job_id, camera, attempt, cancel)
                except ValueError as exc:
                    # A short camera-only capture costs no model call and moves nothing on the board.
                    if cancel.is_set() or attempt == self.SETUP_CAPTURES: raise
                    reasons.append('capture %d: %s' % (attempt, exc))
                    continue
                for row in reversed(rows[-self.SETUP_FRAMES:]):
                    if cancel.is_set(): raise ValueError('Setup cancelled while choosing a frame')
                    if (row['width'], row['height']) != (geometry['image_width'], geometry['image_height']):
                        raise ValueError('Capture resolution differs from the calibrated bench')
                    source = output / row['file']
                    last = {'source': source, 'row': row, 'regions': {}, 'sources': {}, 'suggestion': None}
                    self._set(job_id, stage='suggesting', image_sha256=digest(source), source_file=source.name, source_path=str(source.relative_to(self._folder(job_id) / 'workflow')),
                              image_width=row['width'], image_height=row['height'], led_radii=radii, proposed_regions=None,
                              meta_requests=job['meta_requests'] + 1)
                    screen = None
                    try:
                        suggestion = self.region_proposer({'image': {'name': source.name,
                            'data': base64.b64encode(source.read_bytes()).decode('ascii')},
                            'width': row['width'], 'height': row['height'], 'points': {}})
                        if suggestion['image_sha256'] != digest(source):
                            raise ValueError('SAM result belongs to another photo')
                        screen = suggestion['regions'].get('oled')
                        # Display only: lets the page draw SAM's output as it arrives. The validation capture decides.
                        self._set(job_id, proposed_regions=dict(suggestion['regions']))
                        last.update(regions=dict(suggestion['regions']), sources={n: suggestion['model'] for n in suggestion['regions']}, suggestion=suggestion)
                        save(self._folder(job_id) / ('screen-suggestion-' + source.stem + '.json'), suggestion)
                    except ValueError as exc:
                        reasons.append(row['file'] + ': ' + str(exc))
                    try:
                        aligned = self._auto_landmarks(job_id, source, screen, calibration, cancel)
                        found = (source, row, screen, aligned); break
                    except ValueError as exc:
                        reasons.append(row['file'] + ': ' + str(exc))
                if found: break
            if not found:
                raise ValueError('No frame from %d captures gave a usable view. ' % self.SETUP_CAPTURES + reasons[-1].split(': ', 1)[-1])
            source, row, screen, aligned = found
            corners = aligned['landmarks'][:4]
            points = dict(zip(('red', 'green'), aligned['landmarks'][4:]))
            # SAM's view of the lenses is corroboration, never a gate: the separate validation capture decides.
            agreement = True; lens_note = None; boxes = {}
            if cancel.is_set(): raise ValueError('Setup cancelled before SAM lens check')
            self._set(job_id, stage='suggesting', meta_requests=job['meta_requests'] + 1)
            try:
                led = self.region_proposer({'image': {'name': source.name,
                    'data': base64.b64encode(source.read_bytes()).decode('ascii')},
                    'width': row['width'], 'height': row['height'], 'points': points})
                if led['image_sha256'] != job['image_sha256']:
                    raise ValueError('SAM lens result belongs to another photo')
                save(self._folder(job_id) / 'sam-auto-lenses.json', led)
                boxes = {'oled': screen, **led['regions']} if screen else dict(led['regions'])
                self._set(job_id, proposed_regions=boxes)
                # Each lens stands on its own, so one poor outline does not discard a good one.
                notes = []
                for name in ('red', 'green'):
                    try:
                        check_regions({**boxes, 'oled': boxes.get('oled') or self._box_around(corners, row)}, corners, {name: points[name]}, radii)
                    except ValueError as exc:
                        boxes.pop(name, None); notes.append('%s: %s' % (name, exc))
                if notes:
                    agreement = False; lens_note = '; '.join(notes)
            except ValueError as exc:
                agreement = False; lens_note = str(exc); boxes = {}
            sources = {}
            regions = {'oled': screen or self._box_around(corners, row)}
            sources['oled'] = 'sam-3.1' if screen else 'local-vision'
            for name in ('red', 'green'):
                box = boxes.get(name)
                regions[name] = box or self._box_around([points[name]], row, pad=radii[name] * 2)
                sources[name] = 'sam-3.1' if box else 'local-vision'
            body = {'image_sha256': job['image_sha256'], 'regions': regions, 'sources': sources,
                    'points': points, 'oled_corners': corners}
            if cancel.is_set(): raise ValueError('Setup cancelled before validation')
            base = self._camera_policy_path(job['proposal_id'])
            if str(base) != job['base_policy_path'] or digest(base) != job['base_policy_sha256']:
                raise ValueError('Camera policy changed during setup')
            candidate_id = uuid.uuid4().hex
            candidate = CameraSetupStore(self.root, self.planner).prepare(
                candidate_id, job['proposal_id'], camera, source, body, base,
                registration={**aligned, 'sam_lens_agreement': agreement, 'sam_lens_note': lens_note})
            self._set(job_id, stage='validating', automatic_candidate_id=candidate_id, regions=regions, sources=sources,
                      points=points, oled_corners=corners, sam_lens_agreement=agreement)
            for validation in range(1, 3):
                try:
                    self._qualify_camera_setup(job_id, candidate_id, candidate, cancel, automatic=True, attempt=validation)
                    return
                except ValueError as exc:
                    if cancel.is_set() or validation == 2 or not ('Reference check blocked' in str(exc) or 'fresh iPhone capture' in str(exc)): raise
                    reasons.append('validation %d: %s' % (validation, exc))
                    self._set(job_id, stage='validating', setup_attempt=validation + 1)
        except Exception as exc:
            if cancel.is_set() or not isinstance(exc, ValueError) or last is None:
                self._set(job_id, status='cancelled' if cancel.is_set() else 'incomplete', stage='finished',
                          error=str(exc)[:400] if isinstance(exc, ValueError) else 'Camera setup capture unavailable',
                          ended_at_utc=now())
            else:
                note = ('Automatic setup could not qualify a reference: ' + str(exc)[:300]
                        + ' Keep the phone still and run again, or adjust the regions by hand.')
                prefill = {}
                if found:
                    prefill = {'points': points, 'oled_corners': corners}
                self._set(job_id, status='setup_review', stage='review', regions=last['regions'] if not found else regions,
                          sources=last['sources'] if not found else sources, setup_note=note,
                          setup_attempts=reasons, ended_at_utc=now(), **prefill)
        finally:
            with self.lock: self.active = None

    @staticmethod
    def _box_around(points, row, pad=12):
        xs = [p[0] for p in points]; ys = [p[1] for p in points]
        return [max(0, min(xs) - pad), max(0, min(ys) - pad),
                min(row['width'] - 1, max(xs) + pad), min(row['height'] - 1, max(ys) + pad)]

    def confirm_camera_setup(self, job_id, body):
        with self.lock:
            job = self.jobs.get(job_id, {})
            if job.get('action') != 'camera_setup': raise ValueError('Unknown camera setup')
            if job.get('confirmation') == body and job.get('status') in ('running', 'setup_ready'):
                return job_id
            if self.active: raise BusyError('Another job owns the bench')
            if job.get('status') != 'setup_review': raise ValueError('Capture a new setup reference before confirming')
            proposal = self._setup_eligible(job['proposal_id'], job.get('tests_seen'))
            if proposal['plan_sha256'] != job['plan_sha256']:
                raise ValueError('The project plan changed during setup')
            base = self._camera_policy_path(job['proposal_id'])
            if str(base) != job['base_policy_path'] or digest(base) != job['base_policy_sha256']:
                raise ValueError('Camera policy changed during setup; capture a fresh reference')
            source = self._folder(job_id) / 'workflow' / job.get('source_path', 'capture/camera/' + job['source_file'])
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
            source = self._folder(job_id) / 'workflow' / job.get('source_path', 'capture/camera/' + job['source_file'])
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

    def _qualify_camera_setup(self, job_id, candidate_id, candidate, cancel, *, automatic=False, attempt=1):
        job = self.jobs[job_id]
        camera = job['request']['device_id']
        if camera not in [d['id'] for d in self.enumerate_devices()['cameras']]:
            raise ValueError('Selected iPhone is absent; no fallback camera')
        if cancel.is_set(): raise ValueError('Setup cancelled before validation')
        _, calibration_path = check_policy(candidate['policy_path'])
        calibration = json.loads(calibration_path.read_text()); geometry = calibration['geometry']
        run = self._folder(job_id) / (('workflow/automatic-validation' if automatic else 'workflow/validation') + ('' if attempt == 1 else '-%d' % attempt)); run.mkdir()
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
            self._setup_eligible(job['proposal_id'], job.get('tests_seen'))
            if cancel.is_set(): raise ValueError('Setup cancelled before reference activation')
            CameraSetupStore(self.root, self.planner).activate(candidate_id, job['proposal_id'], proof)
            self._set(job_id, status='setup_ready', stage='finished', ended_at_utc=now(),
                      setup_mode='automatic' if automatic else 'manual',
                      oled_reading=reading.get('text'), reference_url='/api/camera/reference/' + job['proposal_id'],
                      setup_note='Reference saved. LED thresholds are unchanged; behavior verification still requires a fresh test.')
