'use strict';
// Bench autopilot. One click runs the reviewed plan through the same explicit jobs a person would
// click, in order: compile, install, identity, camera test. If the test does not pass it asks Muse
// Spark to explain the evidence and decides what to do next. It never changes wiring or limits and
// stops wherever a person is needed. Every step it takes is an ordinary saved job.
let autopilot=null;
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const newId=()=>crypto.randomUUID().replaceAll('-','');
function autoLog(kind,text){const li=node('li',undefined,'auto-'+kind);li.append(node('time',new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'})),node('span',text));$('autopilot-log').append(li);$('autopilot-log').scrollTop=$('autopilot-log').scrollHeight;}
function setAutoState(text,state){$('autopilot-status').textContent=text;$('autopilot-status').dataset.state=state||'';}
window.updateAutopilot=function(){$('run-bench').disabled=!!autopilot||!!activeExecution||!executionPlan||executionPlan.review_status!=='reviewed'||!plannerSession?.planning_available;};
async function refreshJobs(){const data=await api('/api/jobs');executionJobs=data.jobs;updateExecutionButtons();}
// One explicit bench job, polled to completion; the manual controls stay in sync while it runs.
async function runJob(action){const body={proposal_id:executionPlan.id,plan_sha256:executionPlan.plan_sha256,request_id:newId()};
 if(action!=='compile'){const b=buildJob();if(!b)throw new Error('No compiled build to use');body.build_id=b.id;body.port=$('execution-port').value;}
 if(action==='test')body.device_id=$('execution-camera').value;
 const started=await planningPost('/api/execute/'+action,body);activeExecution={id:started.id,action,stage:'queued'};updateExecutionButtons();
 let job;for(;;){await wait(700);job=await api('/api/jobs/'+started.id);activeExecution=job.status==='running'?job:null;renderExecution(job);updateExecutionButtons();if(job.status!=='running')break;if(autopilot?.cancelled&&!job.cancel_requested){try{await planningPost('/api/jobs/'+job.id+'/cancel',{});}catch(e){}}}
 await refreshJobs();return job;}
// Devices: use what is selected; otherwise enumerate and pick only when the choice is unambiguous.
async function ensureDevices(){if(!($('execution-port').value&&$('execution-camera').value)){const data=await api('/api/devices');$('device-controls').hidden=false;
  for(const [id,items] of [['execution-port',data.ports],['execution-camera',data.cameras]]){const select=$(id);if(select.value)continue;select.replaceChildren();const ph=node('option',items.length?'Select device':'No device available');ph.value='';select.append(ph);items.forEach(item=>{const o=node('option',item.name+' · '+item.id);o.value=item.id;select.append(o);});if(items.length===1)select.value=items[0].id;}
  updateExecutionButtons();}
 const ok=!!($('execution-port').value&&$('execution-camera').value);
 autoLog(ok?'ok':'stop',ok?'Devices: '+optionName('execution-port')+' + '+optionName('execution-camera'):'I will not guess a device. Choose the ESP32 port and the iPhone camera, then run again.');return ok;}
async function explainRun(run){const started=await planningPost('/api/runs/'+encodeURIComponent(run.id)+'/explain',{request_id:newId()});let r;for(;;){await wait(800);r=await api('/api/explanations/'+started.id);if(r.status!=='generating')return r;}}
async function runBench(){if(autopilot||!executionPlan||executionPlan.review_status!=='reviewed'||activeExecution)return;
 autopilot={cancelled:false};$('autopilot-log').replaceChildren();$('autopilot-error').hidden=true;$('stop-bench').hidden=false;window.updateAutopilot();
 const finish=(state,text)=>{setAutoState(text,state);autopilot=null;$('stop-bench').hidden=true;window.updateAutopilot();};
 const stopped=()=>{if(autopilot?.cancelled)throw new Error('Stopped');};
 try{
  autoLog('plan','Goal: verify the reviewed plan on camera. I only run the same jobs you could click; nothing physical changes without you.');
  let build=buildJob();
  if(build)autoLog('skip','Compile: already compiled · firmware '+build.firmware_sha256.slice(0,12)+'…');
  else{setAutoState('Compiling…','busy');autoLog('do','Compile: rendering the plan into the trusted runtime');const job=await runJob('compile');if(job.status!=='compiled')throw new Error('Compile did not finish: '+(job.error||job.status));build=buildJob();autoLog('ok','Compiled · firmware '+build.firmware_sha256.slice(0,12)+'…');}
  stopped();setAutoState('Checking devices…','busy');if(!await ensureDevices())return finish('stopped','Waiting for a device choice.');
  const board=await api('/api/board');let inst=matchingJobs().find(j=>j.action==='install'&&j.status==='installed'&&j.firmware_sha256===build.firmware_sha256);
  if(inst&&board.active_firmware_sha256!==build.firmware_sha256){autoLog('do','Install: the board record shows a different application, so I will reinstall this one');inst=null;}
  if(inst)autoLog('skip','Install: the board record already shows this firmware');
  else{stopped();setAutoState('Installing…','busy');autoLog('do','Install: writing the application only and keeping the previous image');const job=await runJob('install');if(job.status!=='installed')throw new Error('Install did not finish: '+(job.error||job.status));inst=job;autoLog('ok','Installed · flash bytes verified');}
  if(inst.runtime_identity?.status==='pass')autoLog('skip','Identity: confirmed over USB');
  else{stopped();setAutoState('Checking identity…','busy');autoLog('do','Identity: the board has not reported this plan yet, asking once with ID');const job=await runJob('identity');if(job.status!=='identity_confirmed')return finish('stopped','The board does not report the installed plan. Check the USB connection, then run again.');autoLog('ok','Identity confirmed over USB');}
  stopped();setAutoState('Running the camera test…','busy');autoLog('do','Camera test: recording the board while the plan runs');
  const test=await runJob('test');
  if(test.status==='cancelled')return finish('stopped','Test cancelled; no pass claimed.');
  if(test.status==='pass'){autoLog('ok','Verified on camera: the board did what the plan said.');showTestResult(test);return finish('done','Verified on camera.');}
  autoLog(test.status==='fail'?'bad':'warn','Camera test: '+(test.status==='fail'?'behavior mismatch':'incomplete')+(test.error?' · '+test.error:''));
  if(!test.evidence_available)return finish('stopped','No evidence was saved. Open the job logs.');
  stopped();setAutoState('Reading the evidence…','busy');autoLog('do','Asking Muse Spark to explain the result from the expected steps, the findings and the key frames');
  const run=await api('/api/runs/test-'+test.id);const r=await explainRun(run);showTestResult(test);
  if(r.status!=='explained')return finish('stopped','No explanation came back ('+(r.error||r.status)+'). Open the evidence and look yourself.');
  autoLog('meta','Muse Spark ('+r.explanation.confidence+' confidence): '+r.explanation.diagnosis);
  const rejected=run.frames.filter(f=>f.evaluated).every(f=>f.geometry_supported===false);
  const decision=rejected?'Decision: the camera view no longer matches the frozen reference, so nothing was measured and the board is not blamed. Refresh the camera reference, then run again. I did not touch wiring.':
   run.behavior_verdict==='fail'?'Decision: the board did something other than the plan. I will not change the plan to match a fault. Next check: '+r.explanation.next_check+' Then run again.':
   'Decision: the readings are unknown, not wrong, so no pass and no fail. Next check: '+r.explanation.next_check;
  autoLog('decide',decision);return finish(run.behavior_verdict==='fail'?'bad':'warn',rejected?'Needs you: refresh the camera reference':run.behavior_verdict==='fail'?'Needs you: check the wiring':'Needs you: see the next check');
 }catch(e){if(e.message==='Stopped'||autopilot?.cancelled){autoLog('stop','Stopped by you.');return finish('stopped','Stopped.');}$('autopilot-error').textContent=e.message;$('autopilot-error').hidden=false;autoLog('bad',e.message);finish('bad','Stopped on an error.');}}
$('run-bench').addEventListener('click',runBench);
$('stop-bench').addEventListener('click',async()=>{if(!autopilot)return;autopilot.cancelled=true;setAutoState('Stopping after the current step…','busy');if(activeExecution?.id){try{await planningPost('/api/jobs/'+activeExecution.id+'/cancel',{});}catch(e){}}});
