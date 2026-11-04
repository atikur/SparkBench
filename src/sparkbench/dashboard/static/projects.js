'use strict';
let lastGuideRender='',project=null,projectCatalog=[],assemblySteps=[],projectVersion=0,projectPhotos=[],guideCapture=false,sourceFiles={};
const uid=()=>crypto.randomUUID().replaceAll('-','');
function projectError(message){$('project-error').textContent=message;$('project-error').hidden=false;}
function showGuide(){selectionVersion++;clearImage();current=null;showView('project');}
// Each card shows where the project stands, from the same records the project page uses.
// The one status a project has, everywhere it appears. It comes from the latest test of its current firmware.
function projectStatus(s,draft){const cam=s?.camera_result?.status;if(s?.active_job||cam==='running')return ['Running','busy'];if(cam==='pass')return ['Verified on camera','done'];if(cam==='fail')return ['Mismatch on camera','bad'];if(cam==='incomplete')return ['Not verified','warn'];if(s?.state==='firmware_unconfirmed')return ['Check the board','warn'];if(draft?.decision==='clarify')return ['Needs an answer','warn'];if(draft?.decision==='unsupported')return ['Outside the kit','warn'];
 if(!s||s.state==='accept_brief'||s.state==='prepare_proposal')return draft?['Brief ready','']:['Planning',''];if(s.state==='planning')return ['Planning',''];if(s.state==='review')return ['Plan ready',''];if(['compile','install','check_identity','installed'].includes(s.state))return ['Approved, not tested',''];return ['Plan needs work','warn'];}
async function projectOutcome(p){try{const s=await api('/api/projects/'+p.id+'/firmware-status');const draft=s.state==='accept_brief'||!s.camera_result?(await api('/api/projects/'+p.id)).draft:null;return projectStatus(s,draft);}catch(e){return ['',''];}}
let showAllProjects=false;
async function refreshProjects(){const data=await api('/api/projects');projectCatalog=data.catalog;assemblySteps=data.assembly;const shown=showAllProjects?data.projects:data.projects.slice(0,6),outcomes=await Promise.all(shown.map(projectOutcome));$('project-more').hidden=data.projects.length<=6;$('project-more').textContent=showAllProjects?'Show fewer':'Show all '+data.projects.length+' projects';$('project-list').replaceChildren(...(shown.length?shown.map((p,i)=>{const b=node('button',undefined,'saved-plan-button');b.type='button';const text=node('span');text.append(node('strong',p.title),node('small',p.busy?'Muse Spark is working…':date(p.updated_at_utc)));b.append(text);const [label,state]=outcomes[i];if(label){const pill=node('span',label,'pill');if(state)pill.dataset.state=state;b.append(pill);}b.addEventListener('click',()=>openProject(p.id));return b;}):[node('p','Your saved builds appear here.','small muted')]));}
function fillProfile(){const profile=project?.profile;$('project-idea').value=project?.idea||'';$('project-idea').disabled=!!project;$('project-experience').value=profile?.experience||'beginner';$('project-budget').value=profile?.budget||'';$('project-parts-notes').value=profile?.parts_notes||'';const has=!!project;$('project-idea').hidden=has;$('project-idea-view').hidden=!has;$('project-idea-view').textContent=project?.idea||'';$('project-form-title').textContent=has?'The idea':'What should it do?';}
async function openProject(id){if(autopilot||window.cameraSetupActive||planApproving||planUpdating||plannerBusy){showGuide();return;}window.resetFlow?.();autoPlanNext=false;planUpdating=false;showGuide();window.resetPlanStage?.();const version=++projectVersion;try{const p=await api('/api/projects/'+id);if(version!==projectVersion)return;project=p;fillProfile();clearProjectPhotos();renderProject();if(window.pollProjectFirmware)window.pollProjectFirmware(id,version);if(p.busy)pollProject(id,version);}catch(e){projectError(e.message);}}
function listText(title,values,parent){if(!values?.length)return;const block=node('div',undefined,'guide-response-list');block.append(node('strong',title));const ul=node('ul');values.forEach(t=>ul.append(node('li',t)));block.append(ul);parent.append(block);}
function renderProject(){
 if(window.renderProjectFirmware)window.renderProjectFirmware(project?.firmware_status);
 const renderKey=JSON.stringify({project,capture:guideCapture,configured:plannerSession?.planning_available});if(renderKey===lastGuideRender)return;lastGuideRender=renderKey;
 const draft=project?.draft,accepted=project?.accepted,busy=project?.busy,brief=accepted?.brief||draft;
 $('project-title').textContent=brief?.title||'What would you like to build?';$('create-project').hidden=!!project;$('guide-conversation-card').hidden=!project;
 $('guide-summary').textContent=brief?.summary||'Muse Spark will clarify the idea and propose a supported build.';
 $('guide-goals').replaceChildren(...(brief?.goals||[]).map(t=>node('li',t)));
 $('guide-questions').hidden=!draft?.questions?.length;$('guide-questions').replaceChildren(...(draft?.questions||[]).map(t=>node('p',t)));
 const latest=project?.turns.findLast(t=>t.status==='complete'),changed=accepted&&draft&&['title','summary','goals','components','firmware_instruction'].some(k=>JSON.stringify(draft[k])!==JSON.stringify(accepted.brief[k]));
 $('ask-guide').disabled=!!busy||guideCapture||!plannerSession?.planning_available;
 $('guide-request-status').textContent=busy?'Waiting for Muse Spark…':'Saved locally';
 $('guide-conversation').replaceChildren();
 for(const turn of project?.turns||[]){
  const entry=node('article',undefined,'guide-turn');entry.append(node('p','YOU','turn-author'),node('p',turn.message,'guide-copy'));
  const images=node('div',undefined,'turn-images');for(const a of turn.attachments||[]){const img=node('img');img.src='/api/projects/'+project.id+'/turns/'+turn.id+'/'+a.file;img.alt=a.name;images.append(img);}entry.append(images);if(turn.run_id){const evidence=node('button','Open the attached test','button');evidence.type='button';evidence.addEventListener('click',()=>selectRun(turn.run_id));entry.append(evidence,node('p','A recorded test, not a run of this project.','small muted'));}
  entry.append(node('p','MUSE SPARK','turn-author meta-author'));
  if(turn.reply){entry.append(node('p',turn.reply.answer,'guide-copy'));listText('Visible in your attached photos',turn.reply.visible,entry);listText('Uncertain or needs a check',turn.reply.uncertain,entry);entry.append(node('div','Next: '+turn.reply.next_step,'next-step'));}
  else entry.append(node('p',turn.status==='generating'?'Reviewing your project…':turn.error||'Request interrupted; no automatic retry.','small muted'));
  const usage=turn.usage,meta=[typeof turn.latency_seconds==='number'?turn.latency_seconds.toFixed(1)+' s':null,typeof usage?.total_tokens==='number'?usage.total_tokens.toLocaleString()+' tokens':null].filter(Boolean).join(' · ');if(meta)entry.append(node('p',meta,'small muted'));
  $('guide-conversation').append(entry);
 }
 // Parts: one tick per part. A tick records the required quantity as owned and saves at once.
 const parts=(brief?.components||[]).map(item=>({item,part:projectCatalog.find(c=>c.id===item.id)})).filter(x=>x.part),have=parts.filter(({item})=>(project.owned[item.id]||0)>=item.quantity).length;
 $('guide-parts').replaceChildren(...(parts.length?parts.map(({item,part})=>{const li=node('li',undefined,'kit-row');const label=node('label');label.title=part.spec;const input=node('input');input.type='checkbox';input.checked=(project.owned[item.id]||0)>=item.quantity;input.disabled=!!busy;input.addEventListener('change',()=>queueSave(()=>({owned:{...project.owned,[item.id]:input.checked?item.quantity:0}})));const text=node('span');text.append(node('strong',part.name+(item.quantity>1?' × '+item.quantity:'')),node('small',item.purpose));if(item.optional)text.append(node('em','optional','tag'));label.append(input,text);li.append(label);return li;}):[node('li','Parts appear after Muse Spark plans the idea.','help')]));
 // Steps: finished steps fold away and only the next step shows its instructions.
 const done=new Set(project?.completed_steps||[]),next=assemblySteps.find(s=>!done.has(s.id));
 $('guide-assembly').replaceChildren(...assemblySteps.map(step=>{const li=node('li',undefined,'kit-step'+(done.has(step.id)?' done':step===next?' current':''));const label=node('label');const input=node('input');input.type='checkbox';input.checked=done.has(step.id);input.disabled=!project||!!busy;input.addEventListener('change',()=>queueSave(()=>({completed_steps:input.checked?[...new Set([...project.completed_steps,step.id])]:project.completed_steps.filter(id=>id!==step.id)})));label.append(input,node('span',step.title));li.append(label);if(step===next)li.append(node('p',step.detail,'help'));return li;}));
 $('kit-progress').textContent=(parts.length?have+' of '+parts.length+' parts · ':'')+done.size+' of '+assemblySteps.length+' steps done';$('build-kit-card').hidden=!project;
 updateProjectActions();
 requestAnimationFrame(()=>{const c=$('guide-conversation'),last=c.lastElementChild;c.scrollTop=last?last.offsetTop:c.scrollHeight;});
}
function profileValues(){return {experience:$('project-experience').value,budget:$('project-budget').value,parts_notes:$('project-parts-notes').value};}
async function saveProject(changes={}){if(!project)return;try{project=await planningPost('/api/projects/'+project.id+'/update',{revision:project.revision,profile:profileValues(),owned:project.owned,completed_steps:project.completed_steps,...changes});renderProject();return true;}catch(e){projectError(e.message);return false;}}
let saveChain=Promise.resolve();
// Ticks can arrive faster than saves; run every save in order against the latest revision.
function queueSave(changes){saveChain=saveChain.then(()=>project?saveProject(changes()):undefined);return saveChain;}
const briefChanged=p=>!!(p?.accepted&&p.draft&&['title','summary','goals','components','firmware_instruction'].some(k=>JSON.stringify(p.draft[k])!==JSON.stringify(p.accepted.brief[k])));
let autoPlanNext=false,planUpdating=false,planApproving=false;
function planRequestEnded(){autoPlanNext=false;planUpdating=false;updateProjectActions();}
async function pollProject(id,version){try{const p=await api('/api/projects/'+id);if(version!==projectVersion)return;project=p;renderProject();if(p.busy){setTimeout(()=>pollProject(id,version),900);return;}await refreshProjects();if(autoPlanNext){autoPlanNext=false;const turn=p.turns.at(-1),changed=briefChanged(p);if(turn?.status!=='complete')projectError(turn?.error||'Muse Spark did not finish, so the plan is unchanged. Nothing was retried.');else if(p.draft?.decision==='planned'&&(!p.accepted||changed))await acceptAndPlan();else if(p.draft?.decision==='planned')projectError('Muse Spark kept the plan as it was. Try describing the change differently.');}planRequestEnded();}catch(e){if(version===projectVersion){planRequestEnded();projectError(e.message);}}}
async function sendGuide(message){if(!project||project.busy||guideCapture){autoPlanNext=false;return false;}$('project-error').hidden=true;planUpdating=autoPlanNext;updateProjectActions();const id=project.id;try{if(!await queueSave(()=>({}))){planRequestEnded();return false;}await planningPost('/api/projects/'+id+'/ask',{message,images:projectPhotos.map(p=>({name:p.name,data:p.data})),request_id:uid(),run_id:$('guide-run').value||null});$('guide-question').value='';clearProjectPhotos();project.busy=true;renderProject();await pollProject(id,++projectVersion);return true;}catch(e){planRequestEnded();projectError(e.message);return false;}}
$('project-form').addEventListener('submit',async e=>{e.preventDefault();$('create-project').disabled=true;$('project-error').hidden=true;autoPlanNext=true;planUpdating=true;updateProjectActions();try{if(!plannerSession?.planning_available)throw new Error('Configure the existing Meta Contributor API locally before asking for a project.');project=await planningPost('/api/projects',{idea:$('project-idea').value,...profileValues(),request_id:uid()});fillProfile();renderProject();await refreshProjects();await sendGuide('Help me plan this idea. Clarify material missing details, suggest the required parts from the supported catalog, and give me one next step.');}catch(e){planRequestEnded();projectError(e.message);}finally{$('create-project').disabled=false;}});
$('guide-question-form').addEventListener('submit',e=>{e.preventDefault();sendGuide($('guide-question').value.trim());});
// One next action at a time: accept-and-plan, open the existing plan, or reply to Muse Spark.
function updateProjectActionsCore(){const draft=project?.draft,accepted=project?.accepted,busy=!!project?.busy||planUpdating||plannerBusy||!!window.cameraSetupActive,snap=typeof lifecycleSnapshot!=='undefined'?lifecycleSnapshot:null;
 const changed=briefChanged(project);
 const canAccept=draft?.decision==='planned'&&(!accepted||changed),hasPlan=!!snap?.proposal,unresolved=!!draft&&draft.decision!=='planned';
 $('accept-brief').hidden=!canAccept;$('accept-brief').disabled=busy;$('accept-brief').textContent=accepted?'Accept the revised brief and plan →':'Accept and plan firmware →';
 $('plan-stage').hidden=!project&&!planUpdating;
 const planReady=proposalResult?.status==='ready'&&proposalResult.id===snap?.proposal?.id&&!changed&&(!draft||draft.decision==='planned');
 const cameraSaved=planReady&&(window.cameraSetupSavedPlans?.has(proposalResult.id)||(typeof executionJobs!=='undefined'&&executionJobs.some(j=>j.proposal_id===proposalResult.id&&j.action==='camera_setup'&&j.status==='setup_ready')));
 $('plan-camera-status').hidden=!cameraSaved;
 const setupLocked=planReady&&(proposalResult.origin==='mapping_repair'||(typeof executionJobs!=='undefined'&&executionJobs.some(j=>j.proposal_id===proposalResult.id&&j.action==='test')));
 $('plan-edit-open').hidden=!planReady||busy||!$('plan-edit-form').hidden||!!(typeof autopilot!=='undefined'&&autopilot);if(busy)$('plan-edit-form').hidden=true;
 $('plan-camera-regions').hidden=!planReady||busy||setupLocked||!!(typeof autopilot!=='undefined'&&autopilot)||!!(typeof activeExecution!=='undefined'&&activeExecution);
 $('approve-run').hidden=!planReady||busy||!!(typeof activeExecution!=='undefined'&&activeExecution)||!!(typeof autopilot!=='undefined'&&autopilot);$('approve-run').textContent=planReady&&proposalResult.review_status==='reviewed'?'Run on the bench →':'Approve plan and run on the bench →';
 $('project-firmware').hidden=canAccept||!accepted||planReady;$('project-firmware').disabled=busy;$('project-firmware').textContent=hasPlan?'Replan the steps':'Plan the steps →';$('project-firmware').className=hasPlan?'link-button':'primary-button';
 $('brief-reply-form').hidden=!unresolved||busy;$('brief-defaults').hidden=draft?.decision!=='clarify';$('brief-reply-label').textContent=draft?.decision==='clarify'?'Your answer':'What should change?';
 if(plannerBusy)$('lifecycle-next').textContent='Muse Spark is writing the plan…';
 else if(project?.busy||planUpdating)$('lifecycle-next').textContent='Muse Spark is working on the brief…';
 else if(planReady)$('lifecycle-next').textContent='';
 else if(!draft)$('lifecycle-next').textContent='';
 else if(unresolved)$('lifecycle-next').textContent=draft.decision==='clarify'?'Next: answer the question so Muse Spark can finish the brief.':'Next: change the idea so it fits the bench, then ask again below.';
 else if(canAccept)$('lifecycle-next').textContent='Next: accept the '+(changed?'revised ':'')+'brief and plan the firmware.';
 else if(!snap)$('lifecycle-next').textContent='';}
function updateProjectActions(){updateProjectActionsCore();window.renderFlow?.();}
window.updateProjectActions=updateProjectActions;
async function prepareFirmware(){if(!project?.accepted||project.busy)return;try{if(!await queueSave(()=>({})))return;const job=await planningPost('/api/projects/'+project.id+'/firmware',{accepted_sha256:project.accepted.sha256,request_id:uid()});plannerBusy=true;showPlanner();pollProposal(job.id,++pollVersion);const id=project.id,fresh=await api('/api/projects/'+id);if(project?.id===id){project=fresh;renderProject();}}catch(e){projectError(e.message);}}
async function acceptAndPlan(){if(!project||project.busy)return;const latest=project.turns.findLast(t=>t.status==='complete');if(!latest)return;$('accept-brief').disabled=true;try{project=await planningPost('/api/projects/'+project.id+'/accept',{turn_id:latest.id});renderProject();await prepareFirmware();}catch(e){projectError(e.message);updateProjectActions();}}
$('accept-brief').addEventListener('click',acceptAndPlan);$('project-firmware').addEventListener('click',prepareFirmware);
$('brief-reply-form').addEventListener('submit',e=>{e.preventDefault();const text=$('brief-reply').value.trim();if(!text)return;$('brief-reply').value='';autoPlanNext=true;sendGuide(text);});
async function approveAndRun() {
 const button = $('approve-run');
 if (button.hidden || proposalResult?.status !== 'ready' || planApproving || window.cameraSetupActive) return;
 planApproving = true;
 button.disabled = true;
 window.renderFlow?.();
 try {
  if (proposalResult.review_status !== 'reviewed') {
   const reviewed = await planningPost('/api/plans/'+proposalId+'/review',{plan_sha256:proposalResult.plan_sha256});
   renderProposal(reviewed);
  }
  $('bench-stage').hidden = false;
  await runBench();
 } catch (error) {
  projectError(error.message);
 } finally {
  planApproving = false;
  button.disabled = false;
  updateProjectActions();
 }
}
$('approve-run').addEventListener('click',approveAndRun);
document.querySelectorAll('.idea-chip').forEach(b=>b.addEventListener('click',()=>{$('home-idea').value=b.dataset.idea;$('home-idea').focus();}));
$('project-more').addEventListener('click',()=>{showAllProjects=!showAllProjects;refreshProjects().catch(()=>{});});
$('home-plan-form').addEventListener('submit',e=>{e.preventDefault();const idea=$('home-idea').value.trim();if(!idea)return;if(autopilot||window.cameraSetupActive||planApproving||planUpdating||plannerBusy){showGuide();return;}window.resetFlow?.();projectVersion++;project=null;window.resetPlanStage?.();fillProfile();clearProjectPhotos();planUpdating=true;$('project-idea').value=idea;$('project-experience').value='beginner';$('project-budget').value='';$('project-parts-notes').value='';$('project-error').hidden=true;showGuide();renderProject();$('home-idea').value='';$('project-form').requestSubmit();});
// One click answers a question with the bench's standing facts and lets Muse Spark pick the defaults.
const DEFAULT_REPLY='Yes, I have every listed part, assembled and wired as the known kit reference. For anything I did not specify, use the simplest reasonable default you suggested, state it in the goals, and go ahead with the plan.';
$('brief-defaults').addEventListener('click',()=>{if(!project||project.busy)return;autoPlanNext=true;sendGuide(DEFAULT_REPLY);});
// "Change something": the change goes to Muse Spark as a brief revision, which is accepted and re-planned automatically.
function requestPlanChange(text){if(!project||project.busy||!text)return Promise.resolve(false);autoPlanNext=true;return sendGuide('Please change the plan: '+text+' Keep everything else as it is, update the brief and the firmware intent, and return planned.');}
$('plan-edit-open').addEventListener('click',()=>{
 $('plan-edit-form').hidden=false;
 $('plan-edit-open').hidden=true;
 $('plan-edit').focus();
});
$('plan-edit-cancel').addEventListener('click',()=>{
 $('plan-edit-form').hidden=true;
 updateProjectActions();
});
$('plan-edit-form').addEventListener('submit',async event=>{
 event.preventDefault();
 const field=$('plan-edit'), text=field.value.trim();
 if(!text)return;
 field.value='';
 $('plan-edit-form').hidden=true;
 if(!await requestPlanChange(text)){
  field.value=text;
  $('plan-edit-form').hidden=false;
  updateProjectActions();
 }
});
function clearProjectPhotos(){for(const p of projectPhotos)URL.revokeObjectURL(p.url);projectPhotos=[];$('guide-photos').value='';renderAttachments();}
function renderAttachments() {
 const figures = projectPhotos.map((photo, index) => {
  const figure = node('figure');
  const img = node('img');
  img.src = photo.url;
  img.alt = photo.name;
  const regions = node('button', 'Review camera regions', 'button');
  regions.type = 'button';
  regions.addEventListener('click', () => window.openCameraRegions(photo.url, photo.name, photo.data));
  const remove = node('button', 'Remove', 'button');
  remove.type = 'button';
  remove.addEventListener('click', () => {
   URL.revokeObjectURL(photo.url);
   projectPhotos.splice(index, 1);
   renderAttachments();
  });
  figure.append(img, node('figcaption', photo.name, 'small muted'), regions, remove);
  return figure;
 });
 $('guide-attachments').replaceChildren(...figures);
}
async function prepareProjectPhoto(file) {
 if (!['image/jpeg', 'image/png'].includes(file.type)) throw new Error('Use JPEG or PNG photos; export HEIC as JPEG first.');
 if (file.size > 20_000_000) throw new Error('Choose a photo smaller than 20 MB.');
 const bitmap = await createImageBitmap(file);
 try {
  if (bitmap.width * bitmap.height > 50_000_000) throw new Error('Please resize this very large image.');
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return {
   name: (file.name.replace(/\.[^.]+$/, '') + '.jpg').slice(0, 120),
   data: canvas.toDataURL('image/jpeg', .88).split(',')[1]
  };
 } finally {
  bitmap.close();
 }
}

async function attachFile(file) {
 if (projectPhotos.length >= 3) throw new Error('Attach up to three photos per question.');
 const photo = await prepareProjectPhoto(file);
 const blob = new Blob([Uint8Array.from(atob(photo.data), char => char.charCodeAt(0))], {type: 'image/jpeg'});
 projectPhotos.push({...photo, url: URL.createObjectURL(blob)});
 renderAttachments();
}

async function captureProjectPhoto(deviceId) {
 const job = await planningPost('/api/guide/photo', {device_id: deviceId, request_id: uid()});
 for (;;) {
  await new Promise(resolve => setTimeout(resolve, 900));
  const result = await api('/api/jobs/' + job.id);
  if (result.status === 'running') continue;
  if (result.status !== 'captured' || !result.latest_frame) {
   throw new Error(result.error || 'No camera frame was captured.');
  }
  return result.latest_frame.url;
 }
}
$('guide-photos').addEventListener('change',async()=>{try{for(const file of $('guide-photos').files)await attachFile(file);}catch(e){projectError(e.message);}});
$('guide-show-camera').addEventListener('click',async()=>{try{$('guide-camera-controls').hidden=false;const devices=await api('/api/devices');$('guide-camera').replaceChildren(node('option','Select the iPhone'));$('guide-camera').firstChild.value='';for(const d of devices.cameras){const option=node('option',d.name+' · '+d.id);option.value=d.id;$('guide-camera').append(option);}if(devices.camera_error)projectError(devices.camera_error);}catch(e){projectError(e.message);}});
$('guide-camera').addEventListener('change',()=>{$('guide-take-photo').disabled=!$('guide-camera').value||guideCapture;});
$('guide-take-photo').addEventListener('click', async () => {
 if (guideCapture || !$('guide-camera').value) return;
 if (projectPhotos.length >= 3) { projectError('Remove a photo before capturing another.'); return; }
 const captureProject = project?.id;
 guideCapture = true;
 $('guide-take-photo').disabled = true;
 renderProject();
 $('guide-request-status').textContent = 'Taking local iPhone photo…';
 try {
  const url = await captureProjectPhoto($('guide-camera').value);
  if (project?.id !== captureProject) throw new Error('Photo saved locally; return to the original project to attach a new photo.');
  const response = await fetch(url);
  if (!response.ok) throw new Error('Captured photo unavailable');
  await attachFile(new File([await response.blob()], 'iPhone-progress.jpg', {type: 'image/jpeg'}));
 } catch (error) {
  projectError(error.message);
 } finally {
  guideCapture = false;
  $('guide-take-photo').disabled = !$('guide-camera').value;
  renderProject();
 }
});
window.loadFirmwareSource=async result=>{$('firmware-source-panel').hidden=true;if(result?.review_status!=='reviewed')return;try{const data=await api('/api/jobs');const build=data.jobs.find(j=>j.action==='compile'&&j.status==='compiled'&&j.runtime_current!==false&&j.proposal_id===result.id&&j.plan_sha256===result.plan_sha256);if(!build)return;const source=await api('/api/jobs/'+build.id+'/source');if(proposalId!==result.id)return;sourceFiles=source.files;$('firmware-source-panel').hidden=false;$('firmware-authorship').textContent=source.authorship;$('firmware-build-hash').textContent='Firmware SHA-256: '+source.firmware_sha256;$('firmware-source-file').replaceChildren(...Object.keys(sourceFiles).map(name=>{const o=node('option',name);o.value=name;return o;}));$('firmware-source-file').value='include/plan_data.h';$('firmware-source-code').textContent=sourceFiles['include/plan_data.h'];for(const [id,name] of [['firmware-source-download','source.zip'],['firmware-binary-download','firmware.bin'],['firmware-log-download','compile.log']])$(id).href='/api/jobs/'+build.id+'/'+name;}catch(e){$('firmware-source-panel').hidden=true;}};
$('firmware-source-file').addEventListener('change',()=>{$('firmware-source-code').textContent=sourceFiles[$('firmware-source-file').value]||'';});
(async()=>{try{await refreshProjects();const runs=await api('/api/runs');for(const r of runs.runs.filter(r=>r.available)){const o=node('option',r.title+' · '+r.evaluated_sample_count+' samples · '+r.behavior_verdict);o.value=r.id;$('guide-run').append(o);}}catch(e){$('project-list').replaceChildren(node('p','Projects unavailable','small muted'));}})();
