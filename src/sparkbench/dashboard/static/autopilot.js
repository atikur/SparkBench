'use strict';
// Bench agent. After the plan is approved it runs the same explicit jobs a person would click, in
// order: compile, install, identity, camera test. If the test does not pass it asks Muse Spark to
// explain the evidence and decides what to do next. It never changes wiring or limits and stops
// wherever a person is needed. Every step is an ordinary saved job; the timeline shows progress.
let autopilot=null;
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const newId=()=>crypto.randomUUID().replaceAll('-','');
const STAGES=[['connect','Connect'],['view','Camera view'],['compile','Compile'],['install','Install'],['identity','Identity'],['test','Camera test'],['explain','Explain'],['decide','Decision']];
function autoLog(kind,text){const li=node('li',undefined,'auto-'+kind);li.append(node('time',new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'})),node('span',text));$('autopilot-log').append(li);$('autopilot-log').scrollTop=$('autopilot-log').scrollHeight;}
function setAutoState(text,state){$('autopilot-status').textContent=text;$('autopilot-status').dataset.state=state||'';}
// Timeline: one row per stage with a state (pending, running, done, skipped, warn, bad, stopped) and a note.
function setStage(id,state,note){let li=document.querySelector('#timeline li[data-stage="'+id+'"]');if(!li){li=node('li');li.dataset.stage=id;const body=node('div',undefined,'tl-body');body.append(node('strong',STAGES.find(s=>s[0]===id)[1]),node('span',undefined,'help tl-note'));li.append(node('span',undefined,'tl-dot'),body);$('timeline').append(li);}li.dataset.state=state;li.querySelector('.tl-note').textContent=note||'';}
function resetTimeline(){$('timeline').replaceChildren();for(const [id] of STAGES)setStage(id,'pending','');}
// What the records already prove, shown while no run is in progress.
window.syncStages=function(){if(autopilot)return;if(!executionPlan||executionPlan.status!=='ready'){resetTimeline();return;}
 if(!$('timeline').children.length)resetTimeline();
 const build=buildJob(),jobs=matchingJobs(),port=$('execution-port').value,camera=$('execution-camera').value;
 setStage('compile',build?'done':'pending',build?'firmware '+build.firmware_sha256.slice(0,12)+'…':'');
 setStage('connect',port&&camera?'done':'pending',port&&camera?optionName('execution-port')+' + '+optionName('execution-camera'):'chosen when the run starts');
 setStage('view','pending','checked when the run starts');
 const inst=build&&jobs.find(j=>j.action==='install'&&j.status==='installed'&&j.firmware_sha256===build.firmware_sha256);
 setStage('install',inst?'done':'pending',inst?'flash verified':'');
 const identity=inst&&(inst.runtime_identity?.status==='pass'||jobs.some(j=>j.action==='identity'&&j.status==='identity_confirmed'));
 setStage('identity',identity?'done':'pending',identity?'confirmed over USB':'');
 const last=jobs.find(j=>j.action==='test'&&j.status!=='running');
 setStage('test',last?(last.status==='pass'?'done':last.status==='fail'?'bad':last.status==='cancelled'?'stopped':'warn'):'pending',last?(last.status==='pass'?'verified on camera':last.status==='fail'?'behavior mismatch':last.status):'');
 setStage('explain',!last?'pending':last.status==='pass'?'skipped':'pending',last&&last.status==='pass'?'not needed':'');setStage('decide','pending','');
 $('run-bench').textContent=last?'Run again':'Run on the bench';};
window.updateAutopilot=function(){$('run-bench').disabled=!!autopilot||!!activeExecution||!executionPlan||executionPlan.review_status!=='reviewed'||!plannerSession?.planning_available;};
async function refreshJobs(){const data=await api('/api/jobs');executionJobs=data.jobs;updateExecutionButtons();}
// One explicit bench job, polled to completion; the timeline and manual controls stay in sync while it runs.
async function runJob(action,stage){const body={proposal_id:executionPlan.id,plan_sha256:executionPlan.plan_sha256,request_id:newId()};
 if(action!=='compile'){const b=buildJob();if(!b)throw new Error('No compiled build to use');body.build_id=b.id;body.port=$('execution-port').value;}
 if(action==='test')body.device_id=$('execution-camera').value;
 const started=await planningPost('/api/execute/'+action,body);activeExecution={id:started.id,action,stage:'queued'};updateExecutionButtons();
 let job;for(;;){await wait(700);job=await api('/api/jobs/'+started.id);activeExecution=job.status==='running'?job:null;renderExecution(job);updateExecutionButtons();if(stage&&job.status==='running')setStage(stage,'running',executionLabels[job.stage]||job.stage);if(job.status!=='running')break;if(autopilot?.cancelled&&!job.cancel_requested){try{await planningPost('/api/jobs/'+job.id+'/cancel',{});}catch(e){}}}
 await refreshJobs();return job;}
// Devices: use what is selected; otherwise enumerate and pick only when the choice is unambiguous.
async function ensureDevices(){if(!($('execution-port').value&&$('execution-camera').value)){setStage('connect','running','looking for the ESP32 port and the iPhone camera');const data=await api('/api/devices');$('device-controls').hidden=false;
  for(const [id,items] of [['execution-port',data.ports],['execution-camera',data.cameras]]){const select=$(id);if(select.value)continue;select.replaceChildren();const ph=node('option',items.length?'Select device':'No device available');ph.value='';select.append(ph);items.forEach(item=>{const o=node('option',item.name+' · '+item.id);o.value=item.id;select.append(o);});if(items.length===1)select.value=items[0].id;}
  updateExecutionButtons();}
 const ok=!!($('execution-port').value&&$('execution-camera').value);
 setStage('connect',ok?'done':'stopped',ok?optionName('execution-port')+' + '+optionName('execution-camera'):'choose the ESP32 port and the iPhone camera under Manual controls, then run again');
 autoLog(ok?'ok':'stop',ok?'Devices: '+optionName('execution-port')+' + '+optionName('execution-camera'):'I will not guess a device. Choose the ESP32 port and the iPhone camera, then run again.');if(!ok)$('manual-controls').open=true;return ok;}
// Camera check: every part in frame and the OLED readable before the plan runs. When something is wrong the
// agent says what, waits for the person to fix it, checks again and carries on with the same run.
let viewWait=null;
const VIEW_WORDS={fully_visible:'in frame',partly_visible:'cut off',not_visible:'not in frame'};
function showViewCheck(text,liveUrl,job){$('view-check-text').textContent=text;$('view-reference').src='/api/camera/reference';if(liveUrl)$('view-live').src=liveUrl;
 const seen=job?.view_inspection;$('view-parts').replaceChildren(...(seen?[['OLED',seen.oled],['Red LED',seen.red_led],['Green LED',seen.green_led]].map(([name,state])=>{const li=node('li',name+': '+VIEW_WORDS[state]);li.dataset.ok=String(state==='fully_visible');return li;}):[]));
 if(seen&&seen.oled==='fully_visible'&&!seen.oled_legible){const li=node('li','OLED text: not legible');li.dataset.ok='false';$('view-parts').append(li);}
 $('view-fix').hidden=!seen;$('view-fix').textContent=seen?'Muse Spark suggests: '+seen.fix:'';$('view-check').hidden=false;}
async function checkView(){$('view-check').hidden=true;setStage('view','running','checking that every part is in frame and the OLED is readable');
 const started=await planningPost('/api/camera/check',{device_id:$('execution-camera').value,request_id:newId()});let job;
 for(;;){await wait(700);job=await api('/api/jobs/'+started.id);if(job.status!=='running')break;if(autopilot?.cancelled&&!job.cancel_requested){try{await planningPost('/api/jobs/'+job.id+'/cancel',{});}catch(e){}}}
 if(job.status==='view_ok'){const note='OLED and both LEDs where they should be · OLED reads "'+job.oled_reading+'"';setStage('view','done',note);autoLog('ok','Camera check: '+note);return true;}
 if(job.status==='view_blocked'){const text=job.view_issues.map(i=>i.problem).join(' ');setStage('view','stopped',text);autoLog('stop','Camera check: '+text);showViewCheck(text+' Fix it to match the left picture, keep the phone still, then check again.',job.latest_frame?.url,job);return false;}
 const text=job.error||'The camera check did not finish.';setStage('view','stopped',text);autoLog('stop',text);showViewCheck(text+' Fix it, then check again.',null,null);return false;}
// Waits here for as long as it takes. Stop ends the run.
async function checkViewUntilClear(){for(;;){if(await checkView())return;if(autopilot?.cancelled)throw new Error('Stopped');setAutoState('Waiting for you: fix the camera view','warn');const again=await new Promise(resolve=>{viewWait=resolve;});if(!again)throw new Error('Stopped');setAutoState('Checking the camera…','busy');}}
$('view-again').addEventListener('click',async()=>{if(viewWait){const resolve=viewWait;viewWait=null;resolve(true);return;}if(autopilot||activeExecution)return;$('view-again').disabled=true;try{if(await checkView())setAutoState('Camera clear. Run on the bench when ready.','done');}catch(e){$('autopilot-error').textContent=e.message;$('autopilot-error').hidden=false;}finally{$('view-again').disabled=false;}});
async function explainRun(run){const started=await planningPost('/api/runs/'+encodeURIComponent(run.id)+'/explain',{request_id:newId()});let r;for(;;){await wait(800);r=await api('/api/explanations/'+started.id);if(r.status!=='generating')return r;}}
async function runBench(){if(autopilot||!executionPlan||executionPlan.review_status!=='reviewed'||activeExecution)return;
 autopilot={cancelled:false};$('autopilot-log').replaceChildren();$('autopilot-error').hidden=true;$('agent-decision').hidden=true;$('view-check').hidden=true;testResultVersion++;$('test-result').hidden=true;$('execution-image').hidden=true;$('execution-image-label').textContent='';$('stop-bench').hidden=false;resetTimeline();window.updateAutopilot();window.updateProjectActions?.();
 const finish=(state,text)=>{setAutoState(text,state);autopilot=null;$('stop-bench').hidden=true;window.updateAutopilot();window.updateProjectActions?.();};
 const decide=(state,text)=>{setStage('decide',state,text);autoLog('decide',text);};
 const stopped=()=>{if(autopilot?.cancelled)throw new Error('Stopped');};
 try{
  autoLog('plan','Goal: verify the approved plan on camera. I only run the same jobs you could click; nothing physical changes without you.');
  setAutoState('Checking devices…','busy');if(!await ensureDevices())return finish('stopped','Waiting for a device choice.');
  stopped();setAutoState('Checking the camera…','busy');await checkViewUntilClear();
  stopped();let build=buildJob();
  if(build){setStage('compile','skipped','already compiled · firmware '+build.firmware_sha256.slice(0,12)+'…');autoLog('skip','Compile: already compiled');}
  else{setAutoState('Compiling…','busy');setStage('compile','running','rendering the plan into the trusted runtime');const job=await runJob('compile','compile');if(job.status!=='compiled'){setStage('compile','bad',job.error||job.status);throw new Error('Compile did not finish: '+(job.error||job.status));}build=buildJob();setStage('compile','done','firmware '+build.firmware_sha256.slice(0,12)+'…');autoLog('ok','Compiled');}
  const board=await api('/api/board');let inst=matchingJobs().find(j=>j.action==='install'&&j.status==='installed'&&j.firmware_sha256===build.firmware_sha256);
  let flashed=false;if(inst&&board.active_firmware_sha256!==build.firmware_sha256){autoLog('do','Install: the board record shows a different application, so I will reinstall this one');inst=null;}
  if(inst){setStage('install','skipped','the board record already shows this firmware');autoLog('skip','Install: already on the board');}
  else{stopped();setAutoState('Installing…','busy');setStage('install','running','writing the application only and keeping the previous image');const job=await runJob('install','install');if(job.status!=='installed'){setStage('install','bad',job.error||job.status);throw new Error('Install did not finish: '+(job.error||job.status));}inst=job;flashed=true;setStage('install','done','flash bytes verified');autoLog('ok','Installed');}
  if(inst.runtime_identity?.status==='pass'){setStage('identity','skipped','confirmed over USB during install');autoLog('skip','Identity: confirmed');}
  else{stopped();setAutoState('Checking identity…','busy');setStage('identity','running','asking the board once with ID');const job=await runJob('identity','identity');if(job.status!=='identity_confirmed'){setStage('identity','stopped','the board does not report this plan');return finish('stopped','The board does not report the installed plan. Check the USB connection, then run again.');}setStage('identity','done','confirmed over USB');autoLog('ok','Identity confirmed');}
  // Flashing takes a while and restarts the board, so look again right before the plan runs.
  if(flashed){stopped();setAutoState('Checking the camera…','busy');await checkViewUntilClear();}
  stopped();setAutoState('Running the camera test…','busy');setStage('test','running','recording the board while the plan runs');autoLog('do','Camera test: recording the board while the plan runs');
  const test=await runJob('test','test');
  if(test.status==='cancelled'){setStage('test','stopped','cancelled');return finish('stopped','Test cancelled; no pass claimed.');}
  if(test.status==='pass'){setStage('test','done','verified on camera');setStage('explain','skipped','not needed');showTestResult(test);autoLog('ok','Verified on camera');decide('done','Verified on camera: the board did what the plan said.');return finish('done','Verified on camera');}
  setStage('test',test.status==='fail'?'bad':'warn',(test.status==='fail'?'behavior mismatch':'incomplete')+(test.error?' · '+test.error:''));autoLog(test.status==='fail'?'bad':'warn','Camera test: '+test.status);
  if(!test.evidence_available){setStage('explain','stopped','no evidence saved');return finish('stopped','No evidence was saved. Open the job logs.');}
  const run=await api('/api/runs/test-'+test.id);showTestResult(test);
  // Nothing was measured, and the records already say why, so there is no evidence to spend a Meta request on.
  if(run.evaluated_sample_count&&run.geometry_rejected_sample_count===run.evaluated_sample_count){setStage('explain','skipped','nothing was measured');decide('warn','The camera left its calibrated position, so nothing was measured and the board is not blamed. Put the phone back to match the left picture, keep it still for the whole run, then run again.');showViewCheck('The camera moved during the test. No frame matched the calibrated view.',test.latest_frame?.url);return finish('warn','Needs you: put the phone back');}
  stopped();setAutoState('Reading the evidence…','busy');setStage('explain','running','Muse Spark is reading the expected steps, the findings and the key frames');
  const r=await explainRun(run);showTestResult(test);
  if(r.status!=='explained'){setStage('explain','stopped',r.error||r.status);return finish('stopped','No explanation came back. Open the evidence and look yourself.');}
  setStage('explain','done',r.explanation.diagnosis);autoLog('meta','Muse Spark ('+r.explanation.confidence+'): '+r.explanation.diagnosis);
  if(run.behavior_verdict==='fail'){decide('bad','The board did something other than the plan. I will not change the plan to match a fault. Next check: '+r.explanation.next_check+' Then run again.');return finish('bad','Needs you: check the wiring');}
  decide('warn','The readings are unknown, not wrong, so no pass and no fail. Next check: '+r.explanation.next_check);return finish('warn','Needs you: see the next check');
 }catch(e){if(e.message==='Stopped'||autopilot?.cancelled){autoLog('stop','Stopped by you.');return finish('stopped','Stopped.');}$('autopilot-error').textContent=e.message;$('autopilot-error').hidden=false;autoLog('bad',e.message);finish('bad','Stopped on an error.');}}
$('run-bench').addEventListener('click',runBench);
$('stop-bench').addEventListener('click',async()=>{if(!autopilot)return;autopilot.cancelled=true;if(viewWait){const resolve=viewWait;viewWait=null;resolve(false);}setAutoState('Stopping after the current step…','busy');if(activeExecution?.id){try{await planningPost('/api/jobs/'+activeExecution.id+'/cancel',{});}catch(e){}}});
