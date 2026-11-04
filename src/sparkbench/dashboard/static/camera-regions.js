'use strict';

{
 const panel = $('regions-panel');
 const canvas = $('regions-photo');
 const context = canvas.getContext('2d');
 const colors = {oled: '#5eead4', red: '#fb7185', green: '#86efac'};
 const labels = {oled: 'OLED', red: 'Red LED', green: 'Green LED'};
 const cornerNames = ['top-left', 'top-right', 'bottom-right', 'bottom-left'];
 const pause = () => new Promise(resolve => setTimeout(resolve, 700));
 let review;

 function publishActivity() {
  window.cameraSetupActivity = review?.guided ? {
   busy: review.busy && !review.terminal,
   note: $('regions-status').textContent,
   owner: review.activityOwner || 'Camera setup'
  } : null;
  window.renderFlow?.();
 }
 function status(message, owner = 'Camera setup') {
  $('regions-status').textContent = message;
  if (review) review.activityOwner = owner;
  publishActivity();
 }
 function validCorners(current) {
  const q = current.corners, box = current.regions.oled;
  if (q.length !== 4 || !box) return false;
  return q.every(([x, y], i) => {
   const b = q[(i + 1) % 4], c = q[(i + 2) % 4];
   return x >= box[0] && y >= box[1] && x <= box[2] && y <= box[3] &&
    (b[0] - x) * (c[1] - b[1]) - (b[1] - y) * (c[0] - b[0]) > 0;
  });
 }
 function validCircles(current) {
  return ['red', 'green'].every(name => {
   const point = current.points[name], box = current.regions[name], radius = current.radii[name];
   return point && box && point[0] - radius >= box[0] && point[0] + radius <= box[2] &&
    point[1] - radius >= box[1] && point[1] + radius <= box[3];
  });
 }
 function redraw() {
  publishActivity();
  if (!review?.bitmap) return;
  context.drawImage(review.bitmap, 0, 0);
  const scale = Math.max(1, canvas.width / 720);
  context.font = (13 * scale) + 'px system-ui';
  context.lineWidth = 2 * scale;
  for (const [name, box] of Object.entries(review.regions)) {
   const [x1, y1, x2, y2] = box;
   context.strokeStyle = colors[name];
   context.strokeRect(x1, y1, x2 - x1 + 1, y2 - y1 + 1);
   const y = Math.max(16 * scale, y1);
   context.fillStyle = '#17201c';
   context.fillRect(x1, y - 16 * scale, context.measureText(labels[name]).width + 8 * scale, 17 * scale);
   context.fillStyle = colors[name];
   context.fillText(labels[name], x1 + 4 * scale, y - 3 * scale);
  }
  for (const [name, [x, y]] of Object.entries(review.points)) {
   context.strokeStyle = colors[name];
   context.beginPath();
   context.arc(x, y, review.guided ? review.radii[name] : 4 * scale, 0, 2 * Math.PI);
   context.stroke();
  }
  if (review.corners.length) {
   context.strokeStyle = colors.oled;
   context.beginPath();
   review.corners.forEach(([x, y], i) => {
    if (i) context.lineTo(x, y); else context.moveTo(x, y);
    context.fillStyle = colors.oled;
    context.fillText(String(i + 1), x + 5 * scale, y - 5 * scale);
   });
   if (review.corners.length === 4) context.closePath();
   context.stroke();
  }
  const busy = review.busy || review.terminal;
  for (const id of ['suggest', 'oled', 'red', 'green', 'corners']) $('regions-' + id).disabled = busy;
  const havePoints = Boolean(review.points.red && review.points.green);
  for (const id of ['outline', 'circles']) $('regions-' + id).disabled = busy || !havePoints;
  const boxes = Object.values(review.regions);
  const overlap = boxes.some((a, i) => boxes.slice(i + 1).some(b =>
   a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3]));
  const valid = boxes.length === 3 && !overlap && (!review.guided || (validCorners(review) && validCircles(review)));
  $('regions-save').disabled = busy || !valid;
  $('regions-review-help').textContent = !review.guided ? '' : overlap ? 'Component regions must not overlap.' :
   havePoints && !validCircles(review) ? 'The sampling circles must fit inside the LED regions. Check the lens centers, or use the selected lens circles as manual regions.' :
   review.corners.length === 4 && !validCorners(review) ? 'The four border corners must form a clockwise rectangle inside the OLED box. Redraw the box or select the corners again.' :
   'Confirm that both sampling circles sit entirely on the LED lenses and the numbered outline follows the lit screen border.';
 }
 function begin(guided = false, proposalId = null) {
  if (review) return null;
  review = {guided, proposalId, regions: {}, points: {}, sources: {}, corners: [], radii: {}, busy: false, cancelled: false};
  window.cameraSetupActive = guided;
  $('regions-editor').hidden = true;
  canvas.hidden = true;
  canvas.style.width = '100%'; $('regions-zoom').value = 'fit'; $('regions-zoom-label').hidden = true;
  $('regions-source').hidden = false;
  $('regions-upload').hidden = guided;
  $('regions-file').value = '';
  $('regions-camera').hidden = true;
  $('regions-camera').replaceChildren();
  $('regions-capture').hidden = true;
  $('regions-capture').disabled = true;
  $('regions-file').disabled = false;
  $('regions-find-camera').disabled = false;
  $('regions-corners').hidden = !guided;
  $('regions-circles').hidden = !guided;
  $('regions-review-help').textContent = '';
  $('regions-title').textContent = guided ? 'Set up the camera for this plan' : 'Review camera regions';
  $('regions-close').textContent = guided ? 'Cancel setup' : 'Close';
  $('regions-help').textContent = guided
   ? 'The agent aligns a fresh iPhone photo with the calibrated bench, checks the regions with SAM, and validates the reference on a separate capture. If it needs help, you can adjust the regions here.'
   : 'Use SAM 3.1 to outline the display and LED lenses in this photo. Each SAM action sends this photo to Meta. Review the boxes before saving them as setup notes.';
  $('regions-save').textContent = guided ? 'Confirm and check camera' : 'Save region notes';
  $('regions-capture').textContent = guided ? 'Capture and suggest regions' : 'Capture review photo';
  for (const id of ['suggest', 'oled', 'red', 'green', 'outline', 'save', 'corners', 'circles']) $('regions-' + id).disabled = true;
  status(guided ? 'Select the iPhone for this plan. Keep the rig idle and the phone fixed.' : 'Choose a bench photo or capture one with the iPhone.');
  panel.hidden = false;
  $('regions-title').focus({preventScroll:true});
  panel.scrollIntoView({block:'nearest'});
  window.updateProjectActions?.();
  return review;
 }
 function openPhoto(url, name, encoded) {
  const current = begin();
  if (!current) return;
  if (url) {
   $('regions-source').hidden = true;
   return loadPhoto(current, url, name, encoded).catch(error => { if (review === current) status(error.message); });
  }
 }
 async function loadPhoto(current, url, name, encoded) {
  status('Loading photo…');
  let blob;
  if (encoded) blob = new Blob([Uint8Array.from(atob(encoded), char => char.charCodeAt(0))], {type: 'image/jpeg'});
  else {
   const response = await fetch(url);
   if (!response.ok) throw new Error('The photo could not be opened.');
   blob = await response.blob();
  }
  const bitmap = await createImageBitmap(blob);
  if (review !== current) { bitmap.close(); return; }
  if (Math.max(bitmap.width, bitmap.height) > 1920) { bitmap.close(); throw new Error('Use a photo up to 1920 pixels wide or tall.'); }
  current.bitmap = bitmap;
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  if (review !== current) return;
  current.sha = Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
  if (!encoded) {
   let binary = '';
   for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
   encoded = btoa(binary);
  }
  current.name = name;
  current.encoded = encoded;
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  canvas.hidden = false;
  $('regions-editor').hidden = false;
  $('regions-zoom-label').hidden = false;
  $('regions-source').hidden = true;
  redraw();
  status('Suggest the OLED region, then select each external LED lens.');
 }
 async function suggest(points) {
  if (!review || review.busy || review.terminal) return;
  const current = review;
  const targets = Object.keys(points).length ? ['red', 'green'] : ['oled'];
  current.busy = true;
  current.tool = null;
  redraw();
  status('SAM is outlining the selected components…', 'SAM 3.1');
  try {
   const result = await planningPost(current.guided ? '/api/camera/setup/' + current.jobId + '/regions' : '/api/camera/regions', current.guided ? {points} : {
    image: {name: current.name, data: current.encoded}, width: canvas.width, height: canvas.height, points
   });
   if (review !== current) return;
   if (result.image_sha256 !== current.sha) throw new Error('The SAM result belongs to a different photo.');
   for (const target of targets) {
    delete current.regions[target];
    delete current.sources[target];
    if (result.regions[target]) { current.regions[target] = result.regions[target]; current.sources[target] = result.model; }
   }
   const missing = targets.filter(target => !result.regions[target]);
   status(missing.length
    ? 'No single usable box for ' + missing.map(target => labels[target]).join(' and ') + '. ' +
      (targets[0] === 'oled' ? 'Draw a box around the full screen.' : 'Check the lens clicks. You can use the selected circles as manual regions.')
    : 'Check that each box covers the intended component.');
  } catch (error) { if (review === current) status(error.message); }
  finally { if (review === current) { current.busy = false; redraw(); } }
 }
 async function chooseSource(operation) {
  if (!review || review.busy) return;
  const current = review;
  current.busy = true;
  $('regions-file').disabled = true;
  $('regions-find-camera').disabled = true;
  $('regions-capture').disabled = true;
  try { await operation(current); }
  catch (error) { if (review === current) status(error.message); }
  finally {
   if (review === current) {
    current.busy = false;
    $('regions-file').disabled = false;
    $('regions-find-camera').disabled = false;
    $('regions-capture').disabled = !$('regions-camera').value;
    redraw();
   }
  }
 }
 async function findCamera(current) {
  status('Looking for the iPhone camera…');
  const devices = await api('/api/devices');
  if (review !== current) return;
  const camera = $('regions-camera'), placeholder = node('option', 'Select the iPhone');
  placeholder.value = '';
  camera.replaceChildren(placeholder);
  for (const device of devices.cameras) { const option = node('option', device.name); option.value = device.id; camera.append(option); }
  camera.hidden = !devices.cameras.length;
  $('regions-capture').hidden = camera.hidden;
  status(devices.cameras.length ? 'Select the iPhone, then capture. Keep the rig idle and the phone fixed.' : devices.camera_error || 'No iPhone camera is available.');
 }
 async function cancelJob(current) {
  if (!current.jobId || current.cancelSent) return;
  current.cancelSent = true;
  try { await planningPost('/api/jobs/' + current.jobId + '/cancel', {}); } catch (error) { /* Job may already be terminal. */ }
 }
 async function pollSetup(current) {
  for (;;) {
   if (current.cancelled) { await cancelJob(current); return null; }
   await pause();
   if (current.cancelled) { await cancelJob(current); return null; }
   const job = await api('/api/jobs/' + current.jobId);
   if (review !== current) return null;
   if (job.status !== 'running') return job;
   status(job.stage === 'capture' ? (job.setup_attempt > 1 ? 'Taking a second capture…' : 'Capturing a fresh iPhone reference…') :
    job.stage === 'validating' || job.stage === 'validation' ? 'Validating on a separate capture…' :
    job.stage === 'aligning' ? 'Matching the calibrated bench landmarks…' :
    job.stage === 'locating' ? 'Finding the LED lenses and lit screen border in this frame…' :
    'Checking component regions with SAM…',
    job.stage === 'capture' ? 'iPhone camera' :
    ['validation', 'validating'].includes(job.stage) ? 'Camera + Muse Spark' :
    ['aligning', 'locating'].includes(job.stage) ? 'Local vision' : 'SAM 3.1');
  }
 }
 function finishSetup(current) {
  current.complete = true;
  (window.cameraSetupSavedPlans ||= new Set()).add(current.proposalId);
  closeReview();
 }
 async function captureSetup(current, deviceId) {
  current.deviceId = deviceId;
  $('regions-source').hidden = true;
  status('Capturing a fresh iPhone reference…', 'iPhone camera');
  const started = await planningPost('/api/camera/setup', {proposal_id: current.proposalId, device_id: deviceId, request_id: crypto.randomUUID().replaceAll('-', '')});
  current.jobId = started.id;
  if (current.cancelled) { await cancelJob(current); return; }
  const job = await pollSetup(current);
  if (!job || review !== current) return;
  if (job.status === 'setup_ready') { finishSetup(current); return; }
  if (job.status !== 'setup_review') throw new Error(job.error || 'Camera setup could not capture a reference. Close this panel to stop.');
  await loadPhoto(current, job.latest_frame.url, 'iPhone-setup.jpg');
  if (review !== current) return;
  if (current.sha !== job.image_sha256 || canvas.width !== job.image_width || canvas.height !== job.image_height) {
   current.terminal = true;
   throw new Error('The setup photo differs from the saved capture. Close this panel and start a new reference.');
  }
  current.regions = {...job.regions}; current.sources = {...job.sources}; current.radii = {...job.led_radii};
  current.points = {...job.points}; current.corners = job.oled_corners || [];
  status((job.setup_note ? job.setup_note + ' ' : '') + (current.corners.length
   ? 'Adjust the regions or the camera view before checking again.'
   : 'Select each LED lens, outline both LEDs, then mark the four corners of the lit screen border.'));
 }
 window.setupCameraForAgent = function(proposalId, deviceId) {
  const current = begin(true, proposalId);
  if (!current) return Promise.resolve(false);
  const outcome = new Promise(resolve => { current.resolve = resolve; });
  chooseSource(async () => deviceId ? captureSetup(current, deviceId) : findCamera(current));
  return outcome;
 };
 window.cancelCameraSetup = function() { if (review?.guided) closeReview(); };
 async function setupFromPlan() {
  if (typeof autopilot !== 'undefined' && autopilot || typeof activeExecution !== 'undefined' && activeExecution) return;
  const plan = typeof proposalResult !== 'undefined' ? proposalResult : null;
  if (!plan || plan.status !== 'ready') return;
  const ok = await window.setupCameraForAgent(plan.id, $('execution-camera').value || null);
  if (ok) { window.syncStages?.(); window.updateProjectActions?.(); }
 }
 $('plan-camera-regions').addEventListener('click', setupFromPlan);
 $('regions-file').addEventListener('change', event => {
  const file = event.target.files[0]; event.target.value = '';
  if (file) chooseSource(async current => { const photo = await prepareProjectPhoto(file); if (review === current) await loadPhoto(current, null, photo.name, photo.data); });
 });
 $('regions-find-camera').addEventListener('click', () => chooseSource(findCamera));
 $('regions-zoom').addEventListener('change', () => {
  if (!review?.bitmap) return;
  canvas.style.width = $('regions-zoom').value === 'fit' ? '100%' : canvas.width * Number($('regions-zoom').value) / 100 + 'px';
 });
 $('regions-camera').addEventListener('change', () => { if (review) $('regions-capture').disabled = review.busy || !$('regions-camera').value; });
 $('regions-capture').addEventListener('click', () => chooseSource(async current => {
  const deviceId = $('regions-camera').value;
  if (!deviceId) return;
  if (current.guided) {
   const selected = $('execution-camera');
   if (![...selected.options].some(option => option.value === deviceId)) { const option = node('option', $('regions-camera').selectedOptions[0].textContent); option.value = deviceId; selected.append(option); }
   selected.value = deviceId;
   await captureSetup(current, deviceId);
  } else { const url = await captureProjectPhoto(deviceId); if (review === current) await loadPhoto(current, url, 'iPhone-setup.jpg'); }
 }));
 window.openCameraRegions = openPhoto;
 $('view-regions').addEventListener('click', () => openPhoto($('view-live').src, 'camera-check.jpg'));
 function closeReview() {
  const current = review; review = null;
  if (!current) return;
  panel.hidden = true;
  current.cancelled = !current.complete;
  if (current.guided && !current.complete) cancelJob(current);
  current.bitmap?.close(); current.resolve?.(Boolean(current.complete));
  window.cameraSetupActive = false;
  window.cameraSetupActivity = null;
  window.updateProjectActions?.();
 }
 $('regions-close').addEventListener('click', closeReview);
 window.closeCameraRegions = closeReview;
 $('regions-suggest').addEventListener('click', () => suggest({}));
 $('regions-outline').addEventListener('click', () => suggest({...review.points}));
 $('regions-circles').addEventListener('click', () => {
  if (!review?.guided || review.busy) return;
  for (const name of ['red', 'green']) {
   const [x, y] = review.points[name], radius = review.radii[name];
   review.regions[name] = [x - radius, y - radius, x + radius, y + radius];
   review.sources[name] = 'manual';
  }
  status('Manual LED regions selected. Check both circles sit entirely on the lenses.'); redraw();
 });
 const selectionButtons = {oled: $('regions-oled'), red: $('regions-red'), green: $('regions-green'), corners: $('regions-corners')};
 for (const [name, button] of Object.entries(selectionButtons)) button.addEventListener('click', () => {
  if (!review || review.busy) return;
  review.tool = name; review.corner = null;
  if (name === 'corners') { review.corners = []; redraw(); }
  status(name === 'corners' ? 'Zoom in if needed. Click the top-left corner of the lit screen border (1 of 4).' : name === 'oled'
   ? 'Click two opposite corners of a box containing the whole lit screen border.' : 'Click the center of the external ' + labels[name].toLowerCase() + ' lens.');
 });
 canvas.addEventListener('click', event => {
  if (!review?.tool || review.busy || review.terminal) return;
  const bounds = canvas.getBoundingClientRect();
  const pixel = (offset, size, length) => Math.min(length - 1, Math.max(0, Math.floor(offset * length / size)));
  const x = pixel(event.clientX - bounds.left, bounds.width, canvas.width), y = pixel(event.clientY - bounds.top, bounds.height, canvas.height), name = review.tool;
  if (name === 'corners') {
   review.corners.push([x, y]);
   if (review.corners.length < 4) { status('Click the ' + cornerNames[review.corners.length] + ' corner of the lit screen border (' + (review.corners.length + 1) + ' of 4).'); redraw(); return; }
   status('Check the four numbered border corners and both LED sampling circles.');
  } else if (name === 'oled') {
   if (!review.corner) { review.corner = [x, y]; status('Click the opposite corner of the OLED box.'); return; }
   const [a, b] = review.corner;
   if (a === x || b === y) { status('Choose a corner that gives the screen box width and height.'); return; }
   review.regions.oled = [Math.min(a, x), Math.min(b, y), Math.max(a, x), Math.max(b, y)]; review.sources.oled = 'manual';
   status('Check the screen box and select both LED lenses.');
  } else {
   review.points[name] = [x, y]; delete review.regions[name]; delete review.sources[name];
   status('Select the other lens, then outline both LEDs with SAM.');
  }
  review.tool = null; redraw();
 });
 $('regions-save').addEventListener('click', async () => {
  if (!review || $('regions-save').disabled) return;
  const current = review;
  if (current.guided) {
   current.busy = true; current.tool = null; redraw(); status('Saving your confirmed regions and checking a separate capture…');
   try {
    await planningPost('/api/camera/setup/' + current.jobId + '/confirm', {
     image_sha256: current.sha, regions: current.regions, sources: current.sources, points: current.points, oled_corners: current.corners
    });
    const job = await pollSetup(current);
    if (!job || review !== current) return;
    if (job.status !== 'setup_ready') { current.terminal = true; throw new Error((job.error || 'The camera reference did not pass its check.') + ' Close this panel, fix the view, then start a new reference.'); }
    finishSetup(current);
   } catch (error) { if (review === current) status(error.message); }
   finally { if (review === current) { current.busy = false; redraw(); } }
   return;
  }
  const record = {schema_version: 1, purpose: 'camera_setup_review', confirmed_at: new Date().toISOString(),
   image: {name: current.name, sha256: current.sha, width: canvas.width, height: canvas.height},
   coordinates: 'inclusive xyxy in source image pixels', regions: current.regions, sources: current.sources};
  const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2) + '\n'], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'sparkbench-camera-regions.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); status('Camera region notes saved.');
 });
}
