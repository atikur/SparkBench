'use strict';
// The project page shows one state at a time: the plan, the running bench, or the result.
// It only reads the same jobs and records the agent uses. It never starts hardware by itself or changes a verdict.
let flowOverride=null,flowHold=null,flowRun=null,flowRunId=null,flowStep=null,flowLastState=null,flowQueued=false;
const RUN_PHASES=[['ready','Ready'],['installed','Installed'],['recorded','Recorded'],['reading','Read by Muse Spark'],['verdict','Verdict']];
const RUN_TITLES={ready:'Checking the bench',installed:'Putting the firmware on the board',recorded:'Recording the board on camera',reading:'Muse Spark is reading the OLED',verdict:'Working out the verdict'};
// Every finished test of the current firmware, newest first. The result screen shows the latest unless the person picks another.
function testHistory(){const build=buildJob();return build?matchingJobs().filter(j=>j.action==='test'&&j.status!=='running'&&j.evidence_available&&j.request?.build_id===build.id):[];}
function currentTest(){return testHistory()[0];}
let flowPick=null;
function runIsHere(){return !!(autopilot&&autopilot.plan===executionPlan?.id)||!!(activeExecution&&activeExecution.proposal_id&&activeExecution.proposal_id===executionPlan?.id);}
function flowState(){if(!project)return 'plan';if(runIsHere()||flowHold)return 'running';if(flowOverride==='plan')return 'plan';return currentTest()?'result':'plan';}
function stageState(id){return document.querySelector('#timeline li[data-stage="'+id+'"]')?.dataset.state||'pending';}
function stageNote(id){return document.querySelector('#timeline li[data-stage="'+id+'"] .tl-note')?.textContent||'';}
const stageFinished=state=>['done','skipped'].includes(state);
const stageFailed=state=>['stopped','bad'].includes(state);
function planSteps(){return executionPlan?.proposal?.steps||[];}
function readingNote(progress){if(!progress)return 'Starting';const s=progress.seconds_left;return progress.done+' of '+progress.total+' frames'+(typeof s==='number'&&progress.done<progress.total?', about '+(s<60?Math.max(s,1)+' s':Math.round(s/60)+' min')+' left':'');}
// Maps the agent's detailed stages onto five plain phases, plus how far along the whole run is.
function runPhases(){const job=activeExecution?.action==='test'?activeExecution:null,test=stageState('test'),testActive=!!job||test==='running',testEnded=stageFinished(test)||['warn','bad'].includes(test);
 const steps=planSteps().length||1,flashed=stageState('install')==='done',secondCheck=flashed&&!testActive&&!testEnded&&['running','stopped'].includes(stageState('view'));
 const out={},set=(id,state,note)=>{out[id]={state,note:note||''};};let percent=0;
 const rows=['compile','install','identity'].map(stageState),past=testActive||testEnded;
 if(stageFailed(stageState('connect')))set('ready','stopped',stageNote('connect'));
 else if(past||secondCheck||(stageState('connect')==='done'&&stageFinished(stageState('view'))))set('ready','done',stageNote('view')||'Board, phone, and camera view checked');
 else if(stageFailed(stageState('view')))set('ready','stopped','The camera view needs a fix');
 else if(stageState('connect')==='running'||stageState('view')==='running'){set('ready','running',stageState('view')==='running'?'Checking every part is in frame and the OLED is readable':'Looking for the board and the phone');percent=3;}
 else set('ready','pending');
 if(secondCheck&&stageState('view')==='stopped')set('installed','stopped','The camera view needs a fix');
 else if(secondCheck){set('installed','running','Checking the camera again');percent=18;}
 else if(rows.some(stageFailed))set('installed','stopped','Stopped here');
 else if(rows[0]==='running'){set('installed','running','Building the firmware');percent=7;}
 else if(rows[1]==='running'){set('installed','running','Flashing the board');percent=12;}
 else if(rows[2]==='running'){set('installed','running','Confirming the board runs this plan');percent=16;}
 else if(past||rows.every(stageFinished))set('installed','done',rows.every(s=>s==='skipped')?'Already on the board':'Firmware flashed and confirmed');
 else set('installed','pending');
 const stage=job?.stage,reading=stage==='analysis';
 if(testActive&&!reading){const n=job?.capture_step;set('recorded','running',n?'Step '+n+' of '+steps:'Starting the plan');percent=20+15*((n||0)/steps);}
 else if(reading||testEnded)set('recorded','done',steps+' step'+(steps===1?'':'s')+' on camera');
 else if(test==='stopped')set('recorded','stopped','This recording could not be used');
 else set('recorded','pending');
 if(reading){const p=job.reading_progress;set('reading','running',readingNote(p));percent=35+60*(p&&p.total?p.done/p.total:0);}
 else if(testEnded)set('reading','done','Read without being told what to expect');
 else set('reading','pending');
 const explain=stageState('explain'),decide=stageState('decide');
 if(explain==='running'){set('verdict','running','Muse Spark is explaining the evidence');percent=97;}
 else if(autopilot?.waiting&&testEnded)set('verdict','stopped',test==='bad'?'Mismatch. Waiting for your fix, then testing again':'Not verified. Waiting for you, then testing again');
 else if(stageFinished(decide)||(testEnded&&!autopilot))set('verdict','done');
 else if(testEnded){set('verdict','running','Comparing the readings with the plan');percent=96;}
 else set('verdict','pending');
 return {phases:out,percent:Math.round(percent)};}
function showFlowFrame(img,label,url,text){if(url&&img.dataset.url!==url){img.dataset.url=url;img.src=url;}$(label).textContent=text;}
let flowPeak=0;
function renderRunView(){const {phases,percent}=runPhases(),blocked=!$('view-check').hidden,fixing=!$('fix-check').hidden;let active=RUN_PHASES.find(([id])=>phases[id].state==='running')||RUN_PHASES.find(([id])=>phases[id].state==='stopped');
 const attempt=autopilot?.attempt>1?' · attempt '+autopilot.attempt:'';
 $('flow-title').textContent=flowHold?flowHold:blocked?'Waiting for you: fix the camera view':fixing?$('autopilot-status').textContent||'Waiting for you':(active?RUN_TITLES[active[0]]:'Starting')+attempt;
 flowPeak=Math.max(flowPeak,percent);$('run-bar').style.width=Math.max(flowPeak,2)+'%';$('run-view').classList.toggle('blocked',blocked||fixing);$('run-view').classList.toggle('fixing',fixing&&!blocked);$('run-ended').hidden=!flowHold;
 $('run-phases').replaceChildren(...RUN_PHASES.map(([id,name])=>{const p=phases[id],li=node('li');li.dataset.state=p.state;li.append(node('span',undefined,'phase-dot'));const body=node('div');body.append(node('strong',name));if(p.note)body.append(node('span',p.note,'help'));li.append(body);return li;}));
 const job=activeExecution?.action==='test'?activeExecution:null,progress=job?.stage==='analysis'?job.reading_progress:null,steps=planSteps();
 if(job?.latest_frame){const said=progress?.last_text;showFlowFrame($('run-frame'),'run-frame-label',job.latest_frame.url,job.latest_frame.live?'Live camera':progress?(said?'Muse Spark read "'+said+'"':'Muse Spark found this frame unreadable'):'Recorded frame');}
 else showFlowFrame($('run-frame'),'run-frame-label','/api/camera/reference','Calibrated camera view');
 const failed=autopilot?.waiting&&window.flowFailedRun?window.flowFailedRun:null;
 const per=Object.fromEntries((progress?.steps||[]).map(s=>[s.step,s]));
 if(!steps.length)return;
 $('run-strip').replaceChildren(...steps.map((s,i)=>{const n=i+1,chip=node('div',undefined,'step-chip');chip.append(node('strong',s.text));const info=per[n];let state='';let small='';
   if(failed){const s=failed.steps.find(x=>x.id===n);if(s){state=stepResult(failed,n);small=state==='bad'?'mismatch':state==='unknown'?'unknown':'matched';}}
   else if(progress){if(info){small=info.read+' of '+info.total;state=info.read>=info.total?'read':info.read>0?'now':'';}}
   else if(job?.stage==='capture'&&job.capture_step){state=n===job.capture_step?'now':n<job.capture_step?'read':'';small=n===job.capture_step?'on screen':'';}
   chip.dataset.state=state;if(small)chip.append(node('small',small));return chip;}));}
// Result: the verdict first, then one chip per plan step. A chip opens that step's frame and readings.
function stepFrames(run,id){return run.frames.filter(f=>f.evaluated&&f.step===id);}
function stepResult(run,id){const frames=stepFrames(run,id);return frames.some(f=>frameMismatch(f,run))?'bad':frames.some(f=>frameUnknown(f,run))?'unknown':'ok';}
const ledWords=(r,g)=>[r,g].map((v,i)=>(i?'green ':'red ')+(v===null||v===undefined?'unknown':v?'on':'off')).join(', ');
// LED states drawn as dots, so a mismatch is visible at a glance: filled is on, hollow is off, dashed is unknown.
function ledDots(r,g,text){const wrap=node('span',undefined,'leds');for(const [v,c] of [[r,'red'],[g,'green']]){const dot=node('i',undefined,'led '+c+(v===true?' on':v===false?'':' unknown'));dot.title=c+' LED '+(v===true?'on':v===false?'off':'unknown');wrap.append(dot);}if(text!==undefined)wrap.append(node('span',text,'led-text'));return wrap;}
const verdictWord={pass:'Verified',fail:'Mismatch',incomplete:'Not verified'};
function priorNonPass(tests,index){const prior=tests[index+1]?.status;return tests[index]?.status==='pass'&&['fail','incomplete'].includes(prior)?prior:null;}
function renderHistory(shown){const tests=testHistory(),box=$('result-history');box.replaceChildren();if(tests.length<2)return;
 box.append(node('span','Tests of this firmware','help'));
 tests.slice(0,6).forEach((j,i)=>{const b=node('button',undefined,'history-row');b.type='button';b.dataset.state=j.status;b.setAttribute('aria-pressed',String(j.id===shown));
  const retest=priorNonPass(tests,i);
  b.append(node('span',verdictWord[j.status]||j.status,'history-verdict'),node('span',(retest?'passed on retest · ':'')+(j.failures?j.failures+' mismatches · ':'')+(j.unknowns?j.unknowns+' unknown · ':'')+new Date(j.started_at_utc).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}),'help'));
  b.addEventListener('click',()=>{flowPick=j.id;window.renderFlow();});box.append(b);});}
function renderResultStep(){const run=flowRun;if(!run)return;const frames=stepFrames(run,flowStep),f=frames.find(x=>frameMismatch(x,run))||frames.find(x=>frameUnknown(x,run))||frames[Math.floor(frames.length/2)];
 $('result-strip').replaceChildren(...run.steps.map(s=>{const b=node('button',undefined,'step-chip');b.type='button';b.dataset.state=stepResult(run,s.id);b.setAttribute('aria-pressed',String(s.id===flowStep));b.append(node('strong',s.label));b.addEventListener('click',()=>{flowStep=s.id;renderResultStep();});return b;}));
 if(!f){$('result-step').replaceChildren(node('p','No samples for this step.','help'));return;}
 showFlowFrame($('result-frame'),'result-frame-label',f.image_url,'Step '+flowStep+' · '+f.file);
 const clean=frames.filter(x=>!frameMismatch(x,run)&&!frameUnknown(x,run)).length,row=(name,text,cls)=>{const p=node('p');p.append(node('span',name,'help'),node('span',text,cls));return p;};
 const expected=f.expected||{},seen=f.observed||{},rejected=f.geometry_supported===false;
 const dots=(name,r,g,text,cls)=>{const p=node('p');p.append(node('span',name,'help'),ledDots(r,g,text));if(cls)p.className=cls;return p;};
 $('result-step').replaceChildren(node('h3','Step '+flowStep),
  dots('Plan',expected.red,expected.green,'"'+expected.oled_text+'"'),
  rejected?row('Camera measured','not measured: camera out of position','result-off'):dots('Camera measured',seen.red,seen.green,undefined,seen.red!==expected.red||seen.green!==expected.green?'result-off':''),
  row('Muse Spark read',!run.oled_evaluated?'not part of this test':rejected?'not read':seen.oled_text?'"'+seen.oled_text+'"':'unreadable',run.oled_evaluated&&seen.oled_text!==expected.oled_text?'result-off':''),
  row('Samples',clean+' of '+frames.length+' matched the plan'));}
function renderExplanationBlock(run,saved,busy){const box=$('result-explain'),rejected=run.evaluated_sample_count&&run.geometry_rejected_sample_count===run.evaluated_sample_count,show=run.behavior_verdict!=='pass';box.hidden=!show;$('result-explain-run').hidden=true;if(!show)return;box.replaceChildren();
 if(rejected){box.append(node('strong','What to do next'),node('p','Put the phone back to match its calibrated position and keep it still for the whole run, then run again. Nothing here counts against the board.'));return;}
 if(saved?.explanation){const x=saved.explanation;box.append(node('strong','Muse Spark on this result'),node('p',x.diagnosis),node('p','Next check: '+x.next_check,'result-next'),node('p','Fix the bench, then run again: the agent checks the camera and tests the same plan. The explanation is advisory and cannot change the verdict.','help'));return;}
 if(busy){box.append(node('p','Muse Spark is reading the evidence…','help'));return;}
 box.hidden=true;$('result-explain-run').hidden=!plannerSession?.planning_available;}
async function loadExplanationFor(run,version){try{const data=await api('/api/runs/'+encodeURIComponent(run.id)+'/explanations');if(version!==flowRunId)return;renderExplanationBlock(run,data.explanations.find(e=>e.status==='explained'));}catch(e){renderExplanationBlock(run);}}
async function loadResult(job){if(flowRunId===job.id)return;flowRunId=job.id;flowRun=null;$('result-error').hidden=true;$('result-explain').hidden=true;$('result-explain-run').hidden=true;
 try{const run=await api('/api/runs/test-'+job.id);if(flowRunId!==job.id)return;flowRun=run;showTestResult(job);$('result-again').textContent=run.behavior_verdict==='fail'?'I fixed it, run again':'Run again';renderHistory(job.id);
  const tests=testHistory(),prior=priorNonPass(tests,tests.findIndex(j=>j.id===job.id));$('result-retest').hidden=!prior;if(prior)$('result-retest').textContent=(prior==='fail'?'The previous test of this firmware found a mismatch.':'The previous test of this firmware was incomplete.')+' This test passed with the same plan.';const problem=run.steps.find(s=>stepResult(run,s.id)!=='ok');flowStep=(problem||run.steps[0])?.id;renderResultStep();loadExplanationFor(run,job.id);}
 catch(e){if(flowRunId===job.id){$('result-error').textContent='This test\'s evidence failed its checks: '+e.message;$('result-error').hidden=false;}}}
function renderStatus(){const running=runIsHere(),[label,state]=running?['Running','busy']:projectStatus(lifecycleSnapshot,project?.draft);$('flow-status').textContent=project?label:'';if(state)$('flow-status').dataset.state=state;else delete $('flow-status').dataset.state;}
function renderFlowNow(){flowQueued=false;if(typeof lifecycleSnapshot==='undefined'||typeof autopilot==='undefined')return;const state=flowState(),page=$('guide-workspace');page.dataset.flow=state;$('run-view').hidden=state!=='running';$('result-view').hidden=state!=='result';$('flow-details').hidden=!project;
 if(state!==flowLastState){flowLastState=state;if(!page.hidden)window.scrollTo({top:0});}
 if(state==='running')renderRunView();
 if(state==='result'){const job=(flowPick&&testHistory().find(j=>j.id===flowPick))||currentTest();if(job)loadResult(job);}else flowRunId=state==='running'?null:flowRunId;
 $('flow-back').hidden=!(state==='plan'&&flowOverride==='plan'&&currentTest());renderStatus();}
// A timer, not requestAnimationFrame: the page must keep up while its tab is in the background.
window.renderFlow=function(){if(flowQueued)return;flowQueued=true;setTimeout(renderFlowNow,0);};
window.resetFlow=function(){flowPick=null;flowOverride=null;flowHold=null;flowRun=null;flowRunId=null;flowStep=null;flowLastState=null;window.renderFlow();};
window.flowRunStarted=function(){flowPick=null;window.flowFailedRun=null;flowPeak=0;$('autopilot-error').hidden=true;flowOverride=null;flowHold=null;flowRunId=null;window.renderFlow();};
// A run that ends without a test result stays on the running screen, so the reason is not lost.
window.flowRunEnded=function(text,hold){flowHold=hold?text:null;window.renderFlow();};
function startAgain(){flowHold=null;runBench();}
$('result-again').addEventListener('click',startAgain);$('run-again').addEventListener('click',startAgain);
$('run-to-plan').addEventListener('click',()=>{flowHold=null;flowOverride='plan';window.renderFlow();});
$('result-change').addEventListener('click',()=>{flowOverride='plan';renderFlowNow();$('plan-edit-open').click();});
$('flow-back').addEventListener('click',()=>{flowOverride=null;$('plan-edit-form').hidden=true;window.renderFlow();window.updateProjectActions?.();});
$('result-evidence').addEventListener('click',async()=>{if(!flowRun)return;await loadRuns();await selectRun(flowRun.id);});
$('result-explain-run').addEventListener('click',async()=>{const run=flowRun;if(!run)return;$('result-explain-run').hidden=true;$('result-explain').hidden=false;renderExplanationBlock(run,null,true);try{const r=await explainRun(run);if(flowRun!==run)return;if(r.status==='explained')renderExplanationBlock(run,r);else{renderExplanationBlock(run);$('result-error').textContent=r.error||'No explanation came back. Nothing was retried.';$('result-error').hidden=false;}}catch(e){renderExplanationBlock(run);$('result-error').textContent=e.message;$('result-error').hidden=false;}});
for(const el of document.querySelectorAll('[data-view="projects"],#tab-projects'))el.addEventListener('click',()=>refreshProjects().catch(()=>{}));
window.renderFlow();
