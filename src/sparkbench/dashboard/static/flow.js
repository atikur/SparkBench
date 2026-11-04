'use strict';
// The project page shows one state at a time: the plan, the running bench, or the result.
// It only reads the same jobs and records the agent uses. It never starts hardware by itself or changes a verdict.
let flowOverride=null,flowHold=null,flowRun=null,flowRunId=null,flowStep=null,flowLastState=null,flowQueued=false;
const RUN_PHASES=[['ready','Bench ready'],['installed','Firmware installed'],['recorded','Recorded on camera'],['reading','OLED read by Muse Spark'],['verdict','Verdict']];
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
 else if(stageState('connect')==='running'||stageState('view')==='running'){set('ready','running',stageState('view')==='running'?stageNote('view')||'Checking every part is in frame and the OLED is readable':'Looking for the board and the phone');percent=3;}
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
 if(explain==='running'){set('verdict','running',activeExecution?.action==='mapping_repair'?stageNote('explain'):'Muse Spark is explaining the evidence');percent=97;}
 else if(autopilot?.waiting&&testEnded)set('verdict','stopped',test==='bad'?'Mismatch. Waiting for your fix, then testing again':'Not verified. Waiting for you, then testing again');
 else if(stageFinished(decide)||(testEnded&&!autopilot))set('verdict','done');
 else if(testEnded){set('verdict','running','Comparing the readings with the plan');percent=96;}
 else set('verdict','pending');
 return {phases:out,percent:Math.round(percent)};}
function showFlowFrame(img,label,url,text){if(url&&img.dataset.url!==url){img.dataset.url=url;img.src=url;}$(label).textContent=text;}
let flowPeak=0;
// The run stage: real camera frames as soon as there are any. Until then it plays the approved plan at the board's own
// pace, labelled as the plan, so the person sees what the camera is about to check. It is never presented as evidence.
let stageTimer=null,stageTicks=0,stageStep=0,runClock=null;
const stageStill=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
function paintStagePreview(){const steps=planSteps();if(!steps.length)return;const step=steps[stageStep%steps.length],text=$('stage-oled-text');
 if(text.textContent!==step.text){text.textContent=step.text;text.parentNode.dataset.size=step.text.length<=6?'large':step.text.length<=12?'medium':'small';text.classList.remove('stage-swap');void text.offsetWidth;text.classList.add('stage-swap');}
 $('stage-led-red').classList.toggle('on',!!step.red);$('stage-led-green').classList.toggle('on',!!step.green);
 if(!$('stage-preview').hidden){$('stage-count').textContent='Step '+(stageStep%steps.length+1)+' of '+steps.length;for(const [i,chip] of Array.from($('run-strip').children).entries()){if(i===stageStep%steps.length)chip.dataset.preview='';else delete chip.dataset.preview;}}}
// Camera setup on the stage. The boxes are the job's own regions, drawn on the frame they came from.
const STAGE_PART_COLORS={oled:'#5EEAD4',red:'#FB7185',green:'#86EFAC'},STAGE_PART_NAMES={oled:'OLED',red:'Red LED',green:'Green LED'};
function setupStage(){const s=window.samStageJob;if(!s)return null;if(s.until&&Date.now()>s.until){window.samStageJob=null;return null;}return s;}
const setupRegions=job=>job?.regions||job?.proposed_regions||{};
const setupUsedSam=job=>!job?.sources||Object.values(job.sources).includes('sam-3.1');
function paintStageBoxes(job){const wrap=$('stage-boxes'),ns='http://www.w3.org/2000/svg';let svg=wrap.firstElementChild;wrap.hidden=!job;if(!job)return;
 if(!svg){svg=document.createElementNS(ns,'svg');svg.setAttribute('preserveAspectRatio','xMidYMid slice');wrap.append(svg);}
 const width=job.image_width||1920,height=job.image_height||1080,regions=setupRegions(job),scale=width/1920;
 svg.setAttribute('viewBox','0 0 '+width+' '+height);
 for(const old of Array.from(svg.children))if(!regions[old.dataset.part])old.remove();
 for(const [part,box] of Object.entries(regions)){if(!Array.isArray(box)||box.length!==4)continue;
  const key=box.join(','),local=!!job.sources&&job.sources[part]!=='sam-3.1';let g=Array.from(svg.children).find(x=>x.dataset.part===part);
  if(g?.dataset.box!==key){g?.remove();g=document.createElementNS(ns,'g');g.dataset.part=part;g.dataset.box=key;g.style.color=STAGE_PART_COLORS[part]||'#fff';
   const rect=document.createElementNS(ns,'rect'),label=document.createElementNS(ns,'text'),[x0,y0,x1,y1]=box;
   for(const [k,v] of Object.entries({x:x0,y:y0,width:x1-x0,height:y1-y0,pathLength:1,rx:4*scale}))rect.setAttribute(k,v);
   const right=x0>width*.7;label.textContent=STAGE_PART_NAMES[part]||part;label.setAttribute('x',right?x1:x0);label.setAttribute('y',y0>70*scale?y0-14*scale:y1+40*scale);label.setAttribute('text-anchor',right?'end':'start');label.setAttribute('font-size',42*scale);
   g.append(rect,label);svg.append(g);}
  g.classList.toggle('local',local);}}
function paintRunClock(){const s=Math.max(0,Math.floor((Date.now()-runClock)/1000));$('run-elapsed').textContent=Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
function stageTick(){stageTimer=null;if($('run-view').hidden||$('guide-workspace').hidden||flowHold)return;paintRunClock();
 if(window.samStageJob?.until&&Date.now()>window.samStageJob.until)window.renderFlow();
 if(!$('stage-preview').hidden&&!stageStill()&&++stageTicks%3===0){stageStep++;paintStagePreview();}
 stageTimer=setTimeout(stageTick,1000);}
function renderRunView(){const {phases,percent}=runPhases(),blocked=!$('view-check').hidden,repairing=activeExecution?.action==='mapping_repair'||!!(typeof mappingRepair!=='undefined'&&mappingRepair.waiter),fixing=!$('fix-check').hidden;let active=RUN_PHASES.find(([id])=>phases[id].state==='running')||RUN_PHASES.find(([id])=>phases[id].state==='stopped');
 const attempt=autopilot?.attempt>1?' · attempt '+autopilot.attempt:'';
 const setup=activeExecution?.action==='test'?null:setupStage(),setupJob=setup?.job,setupSaved=!!setup?.until,samInUse=!!setup&&setupUsedSam(setupJob);
 if(setup&&!setupSaved&&active&&window.cameraSetupActivity?.note)phases[active[0]].note=window.cameraSetupActivity.note;
 const setupTitle=setup&&(samInUse?(setupSaved?'Camera set up with SAM 3.1':'Setting up the camera with SAM 3.1'):setupSaved?'Camera set up':'Setting up the camera');
 $('flow-title').textContent=flowHold?flowHold:blocked?'Bench run · paused':fixing||repairing?$('autopilot-status').textContent||'Waiting for you':setupTitle||'Bench run'+attempt;
 flowPeak=Math.max(flowPeak,percent);$('run-bar').style.width=Math.max(flowPeak,2)+'%';$('run-view').classList.toggle('blocked',blocked||fixing);$('run-view').classList.toggle('fixing',fixing&&!blocked);$('run-ended').hidden=!flowHold;
 if (!$('run-phases').children.length) $('run-phases').replaceChildren(...RUN_PHASES.map(([id,name])=>{
  const li=node('li');li.dataset.phase=id;li.append(node('span',undefined,'phase-dot'));
  const body=node('div');body.append(node('strong',name),node('span','','help'));li.append(body);return li;
 }));
 for (const li of $('run-phases').children) {
  const p=phases[li.dataset.phase];li.dataset.state=p.state;
  const heading=li.querySelector('strong');if(samInUse&&li.dataset.phase===active?.[0])heading.dataset.model='SAM 3.1';else delete heading.dataset.model;
  const note=li.querySelector('.help');note.textContent=p.note;note.hidden=!p.note;
 }
 const job=activeExecution?.action==='test'?activeExecution:null,progress=job?.stage==='analysis'?job.reading_progress:null,steps=planSteps();
 const checking=!!autopilot&&!flowHold&&stageState('view')==='running';
 const checkFrame=checking&&lastViewCheck?.status==='running'&&lastViewCheck.proposal_id===executionPlan.id?lastViewCheck.latest_frame:null;
 // Between a blocked check and the setup's first frame, the check's own frame shows why the agent is setting up again.
 const movedCheck=!job&&window.cameraSetupActive&&!setupJob?.latest_frame&&lastViewCheck?.status==='view_blocked'&&lastViewCheck.proposal_id===executionPlan?.id?lastViewCheck:null;
 const frame=(setup&&setupJob?.latest_frame)||job?.latest_frame||checkFrame||movedCheck?.latest_frame;
 const preview=$('run-camera-preview'),img=$('run-frame');
 preview.hidden=blocked||fixing||repairing||!!flowHold;
 img.hidden=preview.hidden||!frame;
 const previewing=!preview.hidden&&!frame&&steps.length>0,capturing=!!job&&!progress;
 $('stage-preview').hidden=!previewing;
 const setupOnStage=!!setupJob?.latest_frame,setupStep=setupJob?.stage,samWorking=setupOnStage&&!setupSaved&&setupStep==='suggesting',haveBoxes=setupOnStage&&Object.keys(setupRegions(setupJob)).length>0;
 const savedCheck=!setupOnStage?(checkFrame?lastViewCheck:movedCheck):null,showSaved=!!savedCheck?.saved_regions;
 paintStageBoxes(setupOnStage?setupJob:showSaved?{id:savedCheck.id,image_width:savedCheck.image_width,image_height:savedCheck.image_height,regions:savedCheck.saved_regions,sources:{red:'saved',green:'saved',oled:'saved'}}:null);
 preview.dataset.mode=setupOnStage?(setupStep==='capture'&&!setupSaved?'checking':samWorking?'sam-working':samInUse?'sam':'checking'):frame?(progress?'reading':capturing?'recording':'checking'):'plan';
 $('stage-tag-text').textContent=setupOnStage
  ?(setupSaved?(samInUse?'SAM 3.1 · regions saved':'Regions saved'):setupStep==='capture'?'iPhone · capturing':samWorking?'SAM 3.1 · outlining parts':['aligning','locating'].includes(setupStep)?'Local vision · aligning':samInUse?'SAM 3.1 regions · checking':'Regions · checking')
  :movedCheck&&frame?'Camera view changed':frame?(progress?'Muse Spark reading':capturing?(frame.live?'Live · recording':'Recording'):'Camera check'):'Plan preview';
 const count=$('stage-count'),setupRetry=setupOnStage&&setupJob.setup_attempt>1;count.hidden=!previewing&&!setupRetry&&!(frame&&!setup&&(progress||(capturing&&job.capture_step)));
 if(setupRetry)count.textContent='Attempt '+setupJob.setup_attempt;else if(frame)count.textContent=progress?readingNote(progress):capturing&&job.capture_step?'Step '+job.capture_step+' of '+steps.length:'';
 if(runClock===null){const began=Date.parse(activeExecution?.started_at_utc||'');runClock=Number.isNaN(began)?Date.now():began;}
 $('run-elapsed').hidden=!!flowHold;
 if(!flowHold){paintRunClock();if(stageTimer===null)stageTimer=setTimeout(stageTick,1000);}
 if(img.hidden){img.removeAttribute('src');delete img.dataset.url;}
 const said=progress?.last_text;
 const someLocal=Object.values(setupJob?.sources||{}).includes('local-vision');
 const caption=movedCheck&&frame?'Dashed boxes show the saved positions, which no longer match this frame. The agent is finding the parts again.'
  :showSaved&&checkFrame?(frame.live?'Live camera. ':'')+'Dashed boxes show where the saved view expects each part.'
  :setupOnStage
  ? (setupStep==='capture'&&!setupSaved?'Live camera':!haveBoxes?'SAM 3.1 is outlining the parts in this frame.':(samInUse?'SAM 3.1 proposed these regions from this frame.':'Local vision placed these regions on this frame.')+(someLocal&&samInUse?' Dashed boxes came from local vision.':'')+(setupSaved?' A separate capture confirmed them. SAM takes no part in the verdict.':' A separate capture decides if they are used.'))
  : frame
  ? frame.live?'Live camera':checkFrame?'Frame from this camera check':progress?(said?'Muse Spark read "'+said+'"':'Muse Spark found this frame unreadable'):'Recorded frame'
  : 'Drawn from your plan, not the camera. Real frames replace this as soon as they arrive.';
 showFlowFrame(img,'run-frame-label',img.hidden?null:frame.url,preview.hidden?'':caption);
 const failed=autopilot?.waiting&&window.flowFailedRun?window.flowFailedRun:null;
 const per=Object.fromEntries((progress?.steps||[]).map(s=>[s.step,s]));
 if(!steps.length)return;
 $('run-strip').replaceChildren(...steps.map((s,i)=>{const n=i+1,chip=node('div',undefined,'step-chip');chip.append(node('strong',s.text),ledDots(!!s.red,!!s.green));const info=per[n];let state='';let small='';
   if(failed){const s=failed.steps.find(x=>x.id===n);if(s){state=stepResult(failed,n);small=state==='bad'?'mismatch':state==='unknown'?'unknown':'matched';}}
   else if(progress){if(info){small=info.read+' of '+info.total;state=info.read>=info.total?'read':info.read>0?'now':'';}}
   else if(job?.stage==='capture'&&job.capture_step){state=n===job.capture_step?'now':n<job.capture_step?'read':'';small=n===job.capture_step?'on screen':'';}
   chip.dataset.state=state;if(small)chip.append(node('small',small));return chip;}));
 if(previewing)paintStagePreview();}
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
// Names SAM only when this test really used a reference from a camera setup that SAM took part in.
function renderSamNote(job){const note=$('result-sam'),path=job.camera_policy_path||'',setup=(typeof executionJobs!=='undefined'?executionJobs:[]).find(j=>j.action==='camera_setup'&&j.status==='setup_ready'&&[j.automatic_candidate_id,j.id].some(id=>id&&path.includes('/'+id+'/')));
 const sources=Object.values(setup?.sources||setup?.confirmation?.sources||{}),sam=sources.filter(s=>s==='sam-3.1').length;note.hidden=!sam;if(!sam)return;
 note.replaceChildren(node('strong','SAM 3.1'),node('span',' outlined '+sam+' of '+sources.length+' camera regions for this test, and a separate capture confirmed them. SAM takes no part in the verdict.'));}
async function loadResult(job){if(flowRunId===job.id)return;flowRunId=job.id;flowRun=null;$('result-error').hidden=true;$('result-explain').hidden=true;$('result-explain-run').hidden=true;
 try{const run=await api('/api/runs/test-'+job.id);if(flowRunId!==job.id)return;flowRun=run;showTestResult(job);window.showMappingRepairFor?.(job);$('result-again').textContent=run.behavior_verdict==='fail'?'I fixed it, run again':'Run again';renderHistory(job.id);
  const tests=testHistory(),prior=priorNonPass(tests,tests.findIndex(j=>j.id===job.id));$('result-retest').hidden=!prior;if(prior)$('result-retest').textContent=(prior==='fail'?'The previous test of this firmware found a mismatch.':'The previous test of this firmware was incomplete.')+' This test passed with the same plan.';renderSamNote(job);const problem=run.steps.find(s=>stepResult(run,s.id)!=='ok');flowStep=(problem||run.steps[0])?.id;renderResultStep();loadExplanationFor(run,job.id);}
 catch(e){if(flowRunId===job.id){$('result-error').textContent='This test\'s evidence failed its checks: '+e.message;$('result-error').hidden=false;}}}
function renderStatus(){const running=runIsHere(),[label,state]=running?['Running','busy']:projectStatus(lifecycleSnapshot,project?.draft);$('flow-status').textContent=project?label:'';if(state)$('flow-status').dataset.state=state;else delete $('flow-status').dataset.state;}
// Presentation only. Activity comes from current jobs and requests, never a simulated timer.
function projectActivity(state) {
 const activity = (step, tone, title, note, owner, detail = '') => ({step, tone, title, note, owner, detail});
 if (window.cameraSetupActive) {
  const setup = window.cameraSetupActivity;
  return activity(2, setup?.busy ? 'working' : 'waiting',
   setup?.busy ? (setup.owner === 'SAM 3.1' ? 'SAM 3.1 is outlining your build' : 'Finding a clear view of your build') : 'The camera needs your help',
   setup?.note || 'Choose the iPhone camera to continue.', setup?.owner || 'Camera setup');
 }
 if (state === 'running') {
  const job = activeExecution?.proposal_id === executionPlan?.id ? activeExecution : null;
  const stage = STAGES.find(([id]) => stageState(id) === 'running')?.[0];
  const step = stageFinished(stageState('view')) || ['compile','install','identity','test','mapping_repair'].includes(job?.action) ? 3 : 2;
  if (autopilot?.cancelled || job?.cancel_requested) return activity(step, 'working', 'Stopping the bench run', 'Waiting for the current operation to finish cleanup.', 'Local runtime');
  if (flowHold) return activity(step, 'waiting', 'The run needs attention', flowHold, 'Your turn');
  if (autopilot?.waiting || !$('view-check').hidden || !$('fix-check').hidden) return activity(
   !$('view-check').hidden ? 2 : step, 'waiting', !$('view-check').hidden ? 'The camera view needs a fix' : !$('fix-check').hidden ? 'Fix the bench, then test again' : 'The agent is waiting for you',
   !$('view-check').hidden ? 'The run is paused. Fix what the check found, then continue.' : !$('fix-check').hidden ? 'The run is paused until you have checked the bench.' : $('autopilot-status').textContent || 'Follow the check below to continue this run.', 'Your turn');
  if (job?.action === 'test' && job.stage === 'analysis') {
   const result = activity(3, 'working', 'Muse Spark is reading the OLED',
    'Each camera sample is read without the expected text, then compared with your plan.', 'Muse Spark', readingNote(job.reading_progress));
   result.reading = job.reading_progress;
   return result;
  }
  if (job?.action === 'mapping_repair') {
   const proposing = job.stage === 'proposing';
   return activity(3, 'working', proposing ? 'Muse Spark is proposing a repair' : 'Measuring the LED mapping',
    proposing ? 'Proposing a pin mapping from the camera measurements for local validation.' : 'Checking the fixed GPIO25/26 probe against the recorded LED states.',
    proposing ? 'Muse Spark' : 'Camera + local runtime');
  }
  const task = job?.action || stage;
  const tasks = {
   connect: ['Connecting to your bench', 'Looking for the ESP32 and iPhone camera.', 'Local runtime'],
   view: ['Checking the live camera view', 'Checking that both LEDs and the OLED can be measured.', 'Camera + Muse Spark'],
   compile: ['Building your firmware', 'Turning the approved plan into the trusted LED/OLED runtime.', 'Local compiler'],
   install: ['Installing on the ESP32', 'Writing the application and verifying the installed bytes.', 'Local runtime'],
   identity: ['Checking the board’s identity', 'Confirming that the ESP32 reports the expected firmware.', 'Local runtime'],
   test: ['Watching your build in action', 'Recording the LEDs and OLED while the approved sequence runs.', 'iPhone camera'],
   explain: ['Investigating the evidence', 'Reviewing the recorded findings to work out the next step.', 'Muse Spark'],
   decide: ['Checking the result', 'Comparing the measured behavior with your approved plan.', 'Local verifier']
  };
  const [title, note, owner] = tasks[task] || ['Preparing the next step', 'The bench agent is continuing the approved run.', 'Bench agent'];
  return activity(step, 'working', title, stageNote(stage) || note, owner,
   job?.capture_step ? 'Step '+job.capture_step+' of '+planSteps().length+' on camera' : '');
 }
 if (state === 'result') {
  const job = (flowPick && testHistory().find(j => j.id === flowPick)) || currentTest();
  const messages = {
   pass: ['done', 'Your build matched the plan', 'The sampled LED states and OLED readings passed the camera comparison.'],
   fail: ['bad', 'The camera found a mismatch', 'Review the measured difference and the next check below.'],
   incomplete: ['waiting', 'More evidence is needed', 'Some required readings or checks were missing. Review the details below.'],
   cancelled: ['idle', 'This test was cancelled', 'The retained evidence is available below. No completed verdict was reached.'],
   interrupted: ['waiting', 'This test was interrupted', 'Review the retained evidence before starting another run.']
  };
  const [tone, title] = messages[job?.status] || ['waiting', 'Review the test result', 'Open the evidence for the recorded outcome.'];
  const count = flowRunId === job?.id ? flowRun?.evaluated_sample_count : null;
  return activity(4, tone, title, '', 'Local verifier', Number.isFinite(count) ? count+' samples checked' : 'Saved result');
 }
 if (plannerBusy || planUpdating || project?.busy) return activity(0, 'working',
  plannerBusy ? 'Muse Spark is planning the steps' : 'Muse Spark is working on your idea',
  plannerBusy ? 'Defining the LED states, OLED text and timing for your review.' : 'Working through the behavior, parts and wiring for this build.', 'Muse Spark');
 if (planApproving) return activity(1, 'working', 'Saving your approval', 'Preparing to run the plan you reviewed.', 'Bench agent');
 if (!$('approve-run').hidden) return activity(1, 'waiting',
  proposalResult?.review_status === 'reviewed' ? 'Your plan is ready to run' : 'Your plan is ready for review',
  'Check the steps below, then start the bench run when you’re ready.', 'Your turn');
 if (!$('project-error').hidden || !$('planner-error').hidden) return activity(0, 'waiting', 'Planning needs attention',
  !$('project-error').hidden ? $('project-error').textContent : $('planner-error').textContent, 'Your turn');
 return activity(0, 'waiting', project?.draft?.decision === 'clarify' ? 'Muse Spark has a question' : 'Let’s shape your build',
  $('lifecycle-next').textContent.replace(/^Next:\s*(.)/, (_, c) => c.toUpperCase()) || 'Describe the behavior you want, and Muse Spark will help plan it.', 'Your turn');
}
function renderProjectProgress(state) {
 const panel = $('progress-panel'), progress = $('project-progress');
 panel.hidden = !project && !planUpdating;
 if (panel.hidden) return;
 const a = projectActivity(state), working = a.tone === 'working';
 panel.dataset.state = a.tone;
 $('guide-workspace').dataset.agentState = a.tone;
 $('run-view').dataset.activity = a.tone;
 for (const [index, item] of Array.from(progress.children).entries()) {
  item.dataset.state = index < a.step ? 'done' : index === a.step ? 'current' : 'pending';
  if (index === a.step) item.setAttribute('aria-current', 'step');
  else item.removeAttribute('aria-current');
  item.querySelector('small').textContent = index < a.step ? 'Complete' : index === a.step
   ? (window.cameraSetupActive&&working&&index===2?a.owner:{working:'In progress',waiting:'Your turn',done:'Passed',bad:'Mismatch found',idle:'Stopped'}[a.tone])
   : ['Muse Spark','Your review','SAM + camera','Build + test','Camera evidence'][index];
  if (state === 'result' && index === 3) item.querySelector('small').textContent = a.tone === 'idle' ? 'Stopped' : 'Finished';
 }
 $('agent-activity').dataset.state = a.tone;
 const label = {working:'Agent working',waiting:'Your turn',done:'Run complete',bad:'Review needed',idle:'Run stopped'}[a.tone];
 $('activity-state').textContent = label;
 // Avoid repeatedly announcing the same title on each job poll.
 if ($('activity-title').textContent !== a.title) $('activity-title').textContent = a.title;
 $('activity-note').textContent = a.note;
 $('activity-owner').textContent = a.owner;
 $('activity-owner').hidden = a.owner === label;
 $('activity-detail').textContent = a.detail;
 $('activity-detail').hidden = !a.detail;
 const meter = $('activity-meter');
 meter.hidden = !(working && a.reading?.total > 0);
 if (!meter.hidden) { meter.max = a.reading.total; meter.value = a.reading.done; }
}
function renderFlowNow(){flowQueued=false;if(typeof lifecycleSnapshot==='undefined'||typeof autopilot==='undefined')return;const state=flowState(),page=$('guide-workspace');page.dataset.flow=state;$('run-view').hidden=state!=='running';$('result-view').hidden=state!=='result';$('flow-details').hidden=!project;
 if(state!==flowLastState){flowLastState=state;if(!page.hidden)window.scrollTo({top:0});}
 if(state!=='running')runClock=null;
 if(state==='running')renderRunView();
 if(state==='result'){const job=(flowPick&&testHistory().find(j=>j.id===flowPick))||currentTest();if(job)loadResult(job);}else flowRunId=state==='running'?null:flowRunId;
 $('flow-back').hidden=!(state==='plan'&&flowOverride==='plan'&&currentTest());renderProjectProgress(state);renderStatus();}
// A timer, not requestAnimationFrame: the page must keep up while its tab is in the background.
window.renderFlow=function(){if(flowQueued)return;flowQueued=true;setTimeout(renderFlowNow,0);};
// The progress panel stays in view: the full panel in its place at the top of the page, and once that has nearly scrolled
// out of view, the same panel as one compact row fixed over the top of the window, so the overall picture and the current task
// are visible beside the plan, the run or the result. A spacer holds the panel's place only while the panel is fixed, so
// the page keeps its length and nothing under the pointer jumps or clamps the scroll position.
{const panel=$('progress-panel'),spacer=document.createElement('div');spacer.className='progress-spacer';spacer.hidden=true;panel.parentNode.insertBefore(spacer,panel.nextSibling);
 let compact=false,gap=0;
 const place=()=>{const column=spacer.getBoundingClientRect();panel.style.left=(column.left-8)+'px';panel.style.width=(column.width+16)+'px';};
 const apply=next=>{compact=next;if(compact){gap=parseFloat(getComputedStyle(panel).marginBottom);spacer.style.height=(panel.offsetHeight+gap)+'px';spacer.hidden=false;panel.classList.add('compact');place();}else{panel.classList.remove('compact');spacer.hidden=true;panel.style.left='';panel.style.width='';}};
 const update=()=>{if(panel.hidden){if(compact)apply(false);return;}
  // Dock once less of the panel shows than the bar would: nothing shifts, and the swap never leaves a visible hole.
  const next=(compact?spacer.getBoundingClientRect().bottom-gap:panel.getBoundingClientRect().bottom)<64;
  if(next!==compact)apply(next);else if(compact)place();};
 window.addEventListener('scroll',update,{passive:true});window.addEventListener('resize',update);new MutationObserver(update).observe(panel,{attributes:true,attributeFilter:['hidden']});window.progressPanelUpdate=update;}
window.resetFlow=function(){runClock=null;stageStep=0;flowPick=null;flowOverride=null;flowHold=null;flowRun=null;flowRunId=null;flowStep=null;flowLastState=null;window.closeCameraRegions?.();window.resetMappingRepair?.();window.renderFlow();};
window.flowRunStarted=function(){runClock=Date.now();stageStep=0;window.closeCameraRegions?.();flowPick=null;window.flowFailedRun=null;flowPeak=0;$('autopilot-error').hidden=true;flowOverride=null;flowHold=null;flowRunId=null;window.renderFlow();};
// A run that ends without a test result stays on the running screen, so the reason is not lost.
window.flowRunEnded=function(text,hold){flowHold=hold?text:null;window.renderFlow();};
function startAgain(){flowHold=null;runBench();}
$('result-again').addEventListener('click',startAgain);$('run-again').addEventListener('click',startAgain);
$('run-to-plan').addEventListener('click',()=>{flowHold=null;flowOverride='plan';window.renderFlow();});
$('result-change').addEventListener('click',()=>{flowOverride='plan';renderFlowNow();setTimeout(()=>$('plan-edit').focus(),50);});
$('flow-back').addEventListener('click',()=>{flowOverride=null;$('plan-edit-form').hidden=true;window.renderFlow();window.updateProjectActions?.();});
$('result-evidence').addEventListener('click',async()=>{if(!flowRun)return;await loadRuns();await selectRun(flowRun.id);});
$('result-explain-run').addEventListener('click',async()=>{const run=flowRun;if(!run)return;$('result-explain-run').hidden=true;$('result-explain').hidden=false;renderExplanationBlock(run,null,true);try{const r=await explainRun(run);if(flowRun!==run)return;if(r.status==='explained')renderExplanationBlock(run,r);else{renderExplanationBlock(run);$('result-error').textContent=r.error||'No explanation came back. Nothing was retried.';$('result-error').hidden=false;}}catch(e){renderExplanationBlock(run);$('result-error').textContent=e.message;$('result-error').hidden=false;}});
for(const el of document.querySelectorAll('[data-view="projects"],#tab-projects'))el.addEventListener('click',()=>refreshProjects().catch(()=>{}));
window.renderFlow();
