'use strict';
// Bench agent. After the plan is approved it runs the same explicit jobs a person would click, in
// order: compile, install, identity, camera test. If the test does not pass it asks Muse Spark to
// explain the evidence and decides what to do next. It never changes wiring or limits and stops
// wherever a person is needed. Every step is an ordinary saved job; the timeline shows progress.
let autopilot=null;
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const newId=()=>crypto.randomUUID().replaceAll('-','');
const STAGES=[['connect','Connect'],['view','Camera setup'],['compile','Compile'],['install','Install'],['identity','Identity'],['test','Camera test'],['explain','Explain'],['decide','Decision']];
function autoLog(kind,text){const li=node('li',undefined,'auto-'+kind);li.append(node('time',new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'})),node('span',text));$('autopilot-log').append(li);$('autopilot-log').scrollTop=$('autopilot-log').scrollHeight;window.renderFlow?.();}
function setAutoState(text,state){$('autopilot-status').textContent=text;$('autopilot-status').dataset.state=state||'';}
// Timeline: one row per stage with a state (pending, running, done, skipped, warn, bad, stopped) and a note.
function setStage(id,state,note){let li=document.querySelector('#timeline li[data-stage="'+id+'"]');if(!li){li=node('li');li.dataset.stage=id;const body=node('div',undefined,'tl-body');body.append(node('strong',STAGES.find(s=>s[0]===id)[1]),node('span',undefined,'help tl-note'));li.append(node('span',undefined,'tl-dot'),body);$('timeline').append(li);}li.dataset.state=state;li.querySelector('.tl-note').textContent=note||'';window.renderFlow?.();}
function resetTimeline(){$('timeline').replaceChildren();for(const [id] of STAGES)setStage(id,'pending','');}
// What the records already prove, shown while no run is in progress.
window.syncStages=function(){if(autopilot)return;if(!executionPlan||executionPlan.status!=='ready'){resetTimeline();return;}
 if(!$('timeline').children.length)resetTimeline();
 const build=buildJob(),jobs=matchingJobs(),port=$('execution-port').value,camera=$('execution-camera').value;
 setStage('compile',build?'done':'pending',build?'firmware '+build.firmware_sha256.slice(0,12)+'…':'');
 setStage('connect',port&&camera?'done':'pending',port&&camera?optionName('execution-port')+' + '+optionName('execution-camera'):'');
 const inst=build&&jobs.find(j=>j.action==='install'&&j.status==='installed'&&j.firmware_sha256===build.firmware_sha256);
 setStage('install',inst?'done':'pending',inst?'flash verified':'');
 const identity=inst&&(inst.runtime_identity?.status==='pass'||jobs.some(j=>j.action==='identity'&&j.status==='identity_confirmed'));
 setStage('identity',identity?'done':'pending',identity?'confirmed over USB':'');
 const last=build&&jobs.find(j=>j.action==='test'&&j.status!=='running'&&j.request?.build_id===build.id);
 const view=executionJobs.find(job=>job.proposal_id===executionPlan.id&&job.status!=='running'&&
  (job.action==='view'||job.action==='camera_setup')&&
  (!job.plan_sha256||job.plan_sha256===executionPlan.plan_sha256)&&
  (!last||(job.request?.device_id===last.request.device_id&&job.ended_at_utc<=last.started_at_utc)));
 if(view?.status==='view_ok')setStage('view','done','camera view checked');
 else if(view?.status==='setup_ready')setStage('view','done','camera reference validated');
 else if(view)setStage('view','warn','camera setup did not finish successfully');
 else setStage('view','pending','');
 const outcome={
  pass:['done','verified on camera','Verified on camera. The sampled readings matched the plan.'],
  fail:['bad','behavior mismatch','Mismatch. The camera readings differed from the plan.'],
  incomplete:['warn','incomplete','Not verified. The test ended without a conclusive result.'],
  cancelled:['stopped','cancelled','Test cancelled. No verdict was reached.'],
  interrupted:['stopped','interrupted','Test interrupted. No verdict was reached.']
 }[last?.status];
 setStage('test',outcome?.[0]||'pending',outcome?.[1]||'');
 setStage('explain',last?.status==='pass'?'skipped':'pending',last?.status==='pass'?'not needed':'');
 setStage('decide',outcome?.[0]||'pending',outcome?.[2]||'');};
async function refreshJobs(){const data=await api('/api/jobs');executionJobs=data.jobs;updateExecutionButtons();}
// One explicit bench job, polled to completion; the timeline and manual controls stay in sync while it runs.
async function runJob(action,stage){const body={proposal_id:executionPlan.id,plan_sha256:executionPlan.plan_sha256,request_id:newId()};
 if(action!=='compile'){const b=buildJob();if(!b)throw new Error('No compiled build to use');body.build_id=b.id;body.port=$('execution-port').value;}
 if(action==='test')body.device_id=$('execution-camera').value;
 const started=await planningPost('/api/execute/'+action,body);activeExecution={id:started.id,action,stage:'queued'};updateExecutionButtons();
 let job;for(;;){await wait(700);job=await api('/api/jobs/'+started.id);activeExecution=job.status==='running'?job:null;renderExecution(job);updateExecutionButtons();if(stage&&job.status==='running')setStage(stage,'running',jobStageText(job));if(job.status!=='running')break;if(autopilot?.cancelled&&!job.cancel_requested){try{await planningPost('/api/jobs/'+job.id+'/cancel',{});}catch(e){}}}
 await refreshJobs();return job;}
// Devices: use what is selected; otherwise enumerate and pick only when the choice is unambiguous.
async function ensureDevices(){if(!($('execution-port').value&&$('execution-camera').value)){setStage('connect','running','looking for the ESP32 port and the iPhone camera');const data=await api('/api/devices');$('device-controls').hidden=false;
  for(const [id,items] of [['execution-port',data.ports],['execution-camera',data.cameras]]){const select=$(id);if(select.value)continue;select.replaceChildren();const ph=node('option',items.length?'Select device':'No device available');ph.value='';select.append(ph);items.forEach(item=>{const o=node('option',item.name+' · '+item.id);o.value=item.id;select.append(o);});if(items.length===1)select.value=items[0].id;}
  updateExecutionButtons();}
 const ok=!!($('execution-port').value&&$('execution-camera').value);
 setStage('connect',ok?'done':'stopped',ok?optionName('execution-port')+' + '+optionName('execution-camera'):'choose the ESP32 port and the iPhone camera under Manual controls, then run again');
 autoLog(ok?'ok':'stop',ok?'Devices: '+optionName('execution-port')+' + '+optionName('execution-camera'):'I will not guess a device. Choose the ESP32 port and the iPhone camera, then run again.');if(!ok){$('flow-details').open=true;$('manual-controls').open=true;}return ok;}
// Camera check: every part in frame and the OLED readable before the plan runs. When something is wrong the
// agent says what, waits for the person to fix it, checks again and carries on with the same run.
let humanWait=null,lastViewCheck=null;
const VIEW_WORDS={fully_visible:'in frame',partly_visible:'cut off',not_visible:'not in frame'};
function showViewCheck(text,liveUrl,job){$('view-check-text').textContent=text;$('view-compare').hidden=!liveUrl;
 if(liveUrl){$('view-reference').src=job?.reference_url||'/api/camera/reference/'+executionPlan.id;$('view-live').src=liveUrl;}
 else{$('view-reference').removeAttribute('src');$('view-live').removeAttribute('src');}
 $('view-regions').hidden=!liveUrl;
 const seen=job?.view_inspection;$('view-parts').replaceChildren(...(seen?[['OLED',seen.oled],['Red LED',seen.red_led],['Green LED',seen.green_led]].map(([name,state])=>{const li=node('li',name+': '+VIEW_WORDS[state]);li.dataset.ok=String(state==='fully_visible');return li;}):[]));
 if(seen&&seen.oled==='fully_visible'&&!seen.oled_legible){const li=node('li','OLED text: not legible');li.dataset.ok='false';$('view-parts').append(li);}
 $('view-fix').hidden=!seen;$('view-fix').textContent=seen?'Muse Spark suggests: '+seen.fix:'';$('view-check').hidden=false;}
// The agent sets the camera up itself once per check, so a moved phone needs nothing from the person.
function agentCanSetUpCamera(){return !!autopilot&&!autopilot.setupAttempted&&executionPlan.origin!=='mapping_repair'&&!!window.setupCameraForAgent;}
async function checkView(){$('view-check').hidden=true;lastViewCheck=null;setStage('view','running','Checking live camera view…');
 const started=await planningPost('/api/camera/check',{proposal_id:executionPlan.id,device_id:$('execution-camera').value,request_id:newId(),...(agentCanSetUpCamera()?{automatic_setup:true}:{})});let job;
 for(;;){
  await wait(700);job=await api('/api/jobs/'+started.id);lastViewCheck=job;
  if(job.status!=='running')break;
  if(job.latest_frame)window.renderFlow?.();
  if(autopilot?.cancelled&&!job.cancel_requested){try{await planningPost('/api/jobs/'+job.id+'/cancel',{});}catch(e){}}
 }
 if(job.status==='view_ok'){const note='OLED and both LEDs where they should be · OLED reads "'+job.oled_reading+'"';setStage('view','done',note);autoLog('ok','Camera check: '+note);return true;}
 if(job.status==='view_blocked'&&job.setup_available===true&&agentCanSetUpCamera()){autoLog('do','Camera check: the view no longer matches its saved position, so the agent is setting it up again.');return false;}
 if(job.status==='view_blocked'){const text=job.view_issues.map(i=>i.problem).join(' '),frame=job.latest_frame?.url;setStage('view','stopped',text);autoLog('stop','Camera check: '+text);showViewCheck(text+(frame?' Match the calibrated view, keep the phone still, then check again.':' Adjust the camera, then check again.'),frame,job);return false;}
 const text=job.error||'The camera check did not finish.';
 // A short capture costs no model call and moves nothing on the board, so the agent tries it once more by itself.
 if(job.status==='incomplete'&&/fresh camera frames/.test(text)&&autopilot&&!autopilot.captureRetried){autopilot.captureRetried=true;autoLog('do','The camera capture came up short, so the agent is trying it once more.');return checkView();}
 setStage('view','stopped',text);autoLog('stop',text);showViewCheck(text+' Fix it, then check again.',null,job);return false;}
// Waits here for as long as it takes. Stop ends the run.
async function waitForPerson(text){if(autopilot?.cancelled)return false;autopilot.waiting=true;window.renderFlow?.();setAutoState(text,'warn');window.renderFlow?.();const again=await new Promise(resolve=>{humanWait=resolve;});if(autopilot)autopilot.waiting=false;window.flowFailedRun=null;$('fix-check').hidden=true;window.renderFlow?.();return again;}
// A plan that has neither its own camera reference nor a test yet starts with camera setup.
function planNeedsCameraSetup(){const id=executionPlan.id;return !window.cameraSetupSavedPlans?.has(id)&&!executionJobs.some(j=>j.proposal_id===id&&(j.action==='test'||(j.action==='camera_setup'&&j.status==='setup_ready')));}
// SAM 3.1 labels the parts, and a separate capture must then pass the same checks as a camera check. That capture
// decides whether the run continues, not how many outlines SAM produced, so no second check is needed afterwards.
async function setUpCameraByAgent(note,log){
 autopilot.setupAttempted=true;autopilot.waiting=true;$('view-check').hidden=true;
 setStage('view','running',note);setAutoState('Setting up the camera…','busy');autoLog('do',log);window.renderFlow?.();
 let ready;try{ready=await window.setupCameraForAgent(executionPlan.id,$('execution-camera').value);}finally{if(autopilot)autopilot.waiting=false;window.renderFlow?.();}
 if(!ready||autopilot?.cancelled)throw new Error('Stopped');
 const job=window.samStageJob?.job,samParts=Object.values(job?.sources||{}).filter(s=>s==='sam-3.1').length,reading=job?.oled_reading;
 autoLog('ok',(samParts?'SAM 3.1 outlined '+samParts+' of 3 parts. ':'')+'A separate capture confirmed the view, and the reference is saved for this plan.');
 setStage('view','done','Camera set up'+(reading?' · OLED reads "'+reading+'"':''));autopilot.setupAttempted=false;autopilot.captureRetried=false;}
async function checkViewUntilClear(){
 if(agentCanSetUpCamera()&&planNeedsCameraSetup())return setUpCameraByAgent('Finding the OLED and LEDs with SAM 3.1','Camera setup: this plan has no camera reference yet, so SAM 3.1 labels the OLED and LEDs, then a separate capture checks them.');
 for(;;){if(await checkView()){if(autopilot){autopilot.setupAttempted=false;autopilot.captureRetried=false;}return;}
  if(lastViewCheck?.setup_available===true&&agentCanSetUpCamera())return setUpCameraByAgent('The view has changed. Finding the OLED and LEDs again','Camera setup: SAM 3.1 labels the OLED and LEDs again, then a separate capture checks them.');
  if(!await waitForPerson('Waiting for you: fix the camera view'))throw new Error('Stopped');setAutoState('Checking the camera…','busy');}}
// The fix panel: what Muse Spark saw, the frame that shows it, and one button to carry on.
function showFixPanel(run,x,mismatch){window.flowFailedRun=run;$('fix-text').textContent=x.diagnosis;$('fix-next').textContent='Next check: '+x.next_check;
 const f=run.frames.find(o=>o.id===keyFrame(run))||run.frames.find(o=>o.evaluated);
 if(f){$('fix-frame').src=f.image_url;const e=f.expected||{},o=f.observed||{};const label=$('fix-frame-label');label.replaceChildren(node('span','Step '+f.step+' · plan '),ledDots(e.red,e.green,'"'+e.oled_text+'"'),node('span',' · camera '));if(f.geometry_supported===false)label.append(node('span','not measured'));else label.append(ledDots(o.red,o.green,run.oled_evaluated?(o.oled_text?'"'+o.oled_text+'"':'unreadable'):undefined));}
 $('fix-wiring').hidden=!mismatch;$('fix-again').textContent=mismatch?'I fixed it, test again':'I checked it, test again';$('fix-check').hidden=false;window.renderFlow?.();}
$('fix-again').addEventListener('click',()=>{if(humanWait){const resolve=humanWait;humanWait=null;resolve(true);}});
$('view-again').addEventListener('click',async()=>{if(humanWait){const resolve=humanWait;humanWait=null;resolve(true);return;}if(autopilot||activeExecution)return;$('view-again').disabled=true;try{if(await checkView())setAutoState('Camera clear. Run on the bench when ready.','done');}catch(e){$('autopilot-error').textContent=e.message;$('autopilot-error').hidden=false;}finally{$('view-again').disabled=false;}});
async function explainRun(run){const started=await planningPost('/api/runs/'+encodeURIComponent(run.id)+'/explain',{request_id:newId()});let r;for(;;){await wait(800);r=await api('/api/explanations/'+started.id);if(r.status!=='generating')return r;}}
async function prepareBenchApplication(){
 const stopped=()=>{if(autopilot?.cancelled)throw new Error('Stopped');};
  stopped();let build=buildJob();
  if(build){setStage('compile','skipped','already compiled · firmware '+build.firmware_sha256.slice(0,12)+'…');autoLog('skip','Compile: already compiled');}
  else{setAutoState('Compiling…','busy');setStage('compile','running','rendering the plan into the trusted runtime');const job=await runJob('compile','compile');if(job.status!=='compiled'){setStage('compile','bad',job.error||job.status);throw new Error('Compile did not finish: '+(job.error||job.status));}build=buildJob();setStage('compile','done','firmware '+build.firmware_sha256.slice(0,12)+'…');autoLog('ok','Compiled');}
  const board=await api('/api/board');let inst=matchingJobs().find(j=>j.action==='install'&&j.status==='installed'&&j.firmware_sha256===build.firmware_sha256);
  let flashed=false;if(inst&&board.active_firmware_sha256!==build.firmware_sha256){autoLog('do','Install: the board record shows a different application, so I will reinstall this one');inst=null;}
  if(inst){setStage('install','skipped','the board record already shows this firmware');autoLog('skip','Install: already on the board');}
  else{stopped();setAutoState('Installing…','busy');setStage('install','running','writing the application only and keeping the previous image');const job=await runJob('install','install');if(job.status!=='installed'){setStage('install','bad',job.error||job.status);throw new Error('Install did not finish: '+(job.error||job.status));}inst=job;flashed=true;setStage('install','done','flash bytes verified');autoLog('ok','Installed');}
  if(inst.runtime_identity?.status==='pass'){setStage('identity','skipped','confirmed over USB during install');autoLog('skip','Identity: confirmed');}
  else{stopped();setAutoState('Checking identity…','busy');setStage('identity','running','asking the board once with ID');const job=await runJob('identity','identity');if(job.status!=='identity_confirmed'){setStage('identity','stopped','the board does not report this plan');throw new Error('The board does not report the installed plan. Check the USB connection, then run again.');}setStage('identity','done','confirmed over USB');autoLog('ok','Identity confirmed');}
  // Flashing takes a while and restarts the board, so look again right before the plan runs.
  if(flashed){stopped();setAutoState('Checking the camera…','busy');await checkViewUntilClear();}
}
async function runBench(){if(autopilot||!executionPlan||executionPlan.review_status!=='reviewed'||activeExecution)return;
 autopilot={cancelled:false,plan:executionPlan.id,testDone:false,testStarted:false,setupAttempted:false,attempt:0,waiting:false,repairAttempted:false};$('fix-check').hidden=true;window.flowRunStarted?.();$('autopilot-log').replaceChildren();$('autopilot-error').hidden=true;$('view-check').hidden=true;testResultVersion++;$('test-result').hidden=true;$('stop-bench').hidden=false;resetTimeline();window.updateProjectActions?.();
 const finish=(state,text)=>{setAutoState(text,state);const hold=!autopilot?.testDone&&!autopilot?.cancelled&&state!=='done';autopilot=null;window.flowRunEnded?.(text,hold);$('stop-bench').hidden=true;updateExecutionButtons();window.updateProjectActions?.();};
 const decide=(state,text)=>{setStage('decide',state,text);autoLog('decide',text);};
 const stopped=()=>{if(autopilot?.cancelled)throw new Error('Stopped');};
 try{
  autoLog('plan','Goal: verify the approved behavior on camera. A confirmed LED mismatch triggers one fixed probe; a mapping correction requires your approval before flashing.');
  setAutoState('Checking devices…','busy');if(!await ensureDevices())return finish('stopped','Waiting for a device choice.');
  stopped();setAutoState('Checking the camera…','busy');await checkViewUntilClear();
  await prepareBenchApplication();
  // Compare against the frozen behavior. A measured LED mismatch gets one fixed mapping probe;
  // a candidate is compiled/installed only after explicit approval. Other failures retain the advice flow.
  for(;;){
   autopilot.attempt++;
   if(autopilot.attempt>1){stopped();for(const id of ['test','explain','decide'])setStage(id,'pending','');autoLog('do','Attempt '+autopilot.attempt+': checking the camera, then testing again');setAutoState('Checking the camera…','busy');await checkViewUntilClear();}
   stopped();setAutoState('Running the camera test…','busy');setStage('test','running','recording the board while the plan runs');autoLog('do','Camera test: recording the board while the plan runs');
   autopilot.testStarted=true;const test=await runJob('test','test');autopilot.testDone=!!test.evidence_available&&test.status!=='cancelled';
   if(test.status==='cancelled'){setStage('test','stopped','cancelled');return finish('stopped','Test cancelled; no pass claimed.');}
   if(test.status==='pass'){setStage('test','done','verified on camera');setStage('explain','skipped','not needed');showTestResult(test);const verdict=autopilot.attempt>1?'Passed on retest':'Verified on camera';autoLog('ok',verdict);decide('done',verdict+': the sampled readings matched the plan.');return finish('done',verdict);}
   setStage('test',test.status==='fail'?'bad':'warn',(test.status==='fail'?'behavior mismatch':'incomplete')+(test.error?' · '+test.error:''));autoLog(test.status==='fail'?'bad':'warn','Camera test: '+test.status);
   if(!test.evidence_available){const link=/PTS|timestamp|frame gap/i.test(test.error||'');setStage('test','stopped',test.error||'no evidence saved');setStage('explain','pending','');$('autopilot-error').textContent=link?'The phone\'s video arrived late or out of order, so this recording cannot be trusted and nothing was measured. This says nothing against the board. Connect the phone to the Mac by USB or move it closer to the Wi-Fi router, keep it still, then try again.':'No evidence was saved'+(test.error?': '+test.error:'')+'. Open the run log under Details.';$('autopilot-error').hidden=false;return finish('stopped','The recording could not be used');}
   const run=await api('/api/runs/test-'+test.id);showTestResult(test);
   // Nothing was measured, and the records already say why, so there is no evidence to spend a Meta request on.
   if(run.evaluated_sample_count&&run.geometry_rejected_sample_count===run.evaluated_sample_count){setStage('explain','skipped','nothing was measured');decide('warn','The camera left its calibrated position, so nothing was measured and the board is not blamed. Put the phone back to match the left picture and keep it still; I will check the camera and test again.');showViewCheck('The camera moved during the test. No frame matched the calibrated view. Put the phone back to match the left picture, keep it still, then check again.',test.latest_frame?.url,null);
    if(!await waitForPerson('Waiting for you: put the phone back'))throw new Error('Stopped');continue;}
   if(test.status==='fail'&&!autopilot.repairAttempted&&executionPlan.origin!=='mapping_repair'&&window.tryMappingRepair){
    stopped();const repair=await window.tryMappingRepair(test);
    if(repair){autopilot.repairAttempted=true;
     if(repair.status==='approved'){stopped();autopilot.testDone=false;for(const id of ['compile','install','identity'])setStage(id,'pending','');await prepareBenchApplication();continue;}
     decide('warn',repair.reason||'Current firmware kept. No repair was installed.');return finish('stopped',repair.reason||'Mapping repair was not approved.');
    }
   }
   stopped();setAutoState('Reading the evidence…','busy');setStage('explain','running','Muse Spark is reading the expected steps, the findings and the key frames');
   const r=await explainRun(run);showTestResult(test);
   if(r.status!=='explained'){setStage('explain','stopped',r.error||r.status);return finish('stopped','No explanation came back. Open the evidence and look yourself.');}
   setStage('explain','done',r.explanation.diagnosis);autoLog('meta','Muse Spark ('+r.explanation.confidence+'): '+r.explanation.diagnosis);
   const mismatch=run.behavior_verdict==='fail';
   decide(mismatch?'bad':'warn',(mismatch?'The board did something other than the plan. I will not change the plan to match a fault.':'The readings are unknown, not wrong, so no pass and no fail.')+' Next check: '+r.explanation.next_check+' When it is fixed, I will check the camera and test again.');
   showFixPanel(run,r.explanation,mismatch);
   if(!await waitForPerson(mismatch?'Waiting for you: fix the board':'Waiting for you: see the next check'))throw new Error('Stopped');
  }
 }catch(e){if(e.message==='Stopped'||autopilot?.cancelled){autoLog('stop','Stopped by you.');return finish('stopped','Stopped.');}$('autopilot-error').textContent=e.message;$('autopilot-error').hidden=false;autoLog('bad',e.message);finish('bad','Stopped on an error.');}}
$('stop-bench').addEventListener('click',async()=>{if(!autopilot)return;autopilot.cancelled=true;window.cancelMappingRepair?.();window.cancelCameraSetup?.();if(humanWait){const resolve=humanWait;humanWait=null;resolve(false);}setAutoState('Stopping after the current step…','busy');if(activeExecution?.id){try{await planningPost('/api/jobs/'+activeExecution.id+'/cancel',{});}catch(e){}}});
