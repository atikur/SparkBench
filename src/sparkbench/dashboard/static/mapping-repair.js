'use strict';
// One fixed experiment and one reviewable mapping candidate. Loading saved records never probes,
// calls Meta, approves a candidate or flashes. Only the explicit approval continues to installation.
let mappingRepair={job:null,test:null,busy:false,waiter:null,version:0};
const repairStatusWords={running:'Investigating',repair_ready:'Approval required',no_change:'No mapping change',incomplete:'Cannot determine',invalid_response:'Proposal rejected',error:'Stopped',cancelled:'Cancelled',interrupted:'Interrupted'};
function repairError(message){$('repair-error').textContent=message;$('repair-error').hidden=false;}
function repairBelongs(job){return job&&(job.proposal_id===executionPlan?.id||job.parent_proposal_id===executionPlan?.id||job.candidate_proposal_id===executionPlan?.id);}
function renderMappingRepair(job){
 mappingRepair.job=job;$('mapping-repair').hidden=false;$('repair-error').hidden=true;
 const approved=job.approval_status==='approved'||!!job.approved_at_utc;
 const retest=approved&&executionJobs.find(j=>j.action==='test'&&j.proposal_id===job.candidate_proposal_id&&j.status!=='running');
 $('repair-status').textContent=retest?'Approved · retest '+retest.status:approved?'Approved · not yet verified':repairStatusWords[job.status]||job.status;
 $('repair-status').dataset.state=job.status==='repair_ready'?'warn':job.status==='running'?'busy':'';
 const ready=job.status==='repair_ready'&&!!job.candidate_proposal_id;
 $('repair-message').textContent=job.status==='running'?({preflight:'Checking the original failed test and current bench.',probe:'Running the fixed GPIO25/26 probe. No firmware is being changed.',analysis:'Checking whether the camera supports a complete LED mapping.',proposing:'Muse Spark is proposing a mapping from the measurements.'}[job.stage]||'Preparing the fixed LED mapping probe.'):
 ready?(retest?'The corrected configuration was retested against the same approved behavior. The original failure remains in the evidence.':approved?'The mapping change is approved. A fresh camera test must still pass the original behavior.':'Camera measurements support this proposed mapping. Approval will compile and install the corrected configuration, then run a new camera test against the same approved behavior.'):
 job.status==='no_change'?'The measured mapping already matches the firmware. No correction was created. Inspect the original failure before changing anything.':
 job.status==='cancelled'?'Investigation cancelled. No mapping repair was installed.':
 job.error||'A complete, consistent mapping was not established. No repair is available and nothing was flashed.';
 $('repair-diff').hidden=!ready;$('repair-diff-rows').replaceChildren();
 if(ready)for(const color of ['red','green']){const row=node('tr');row.append(node('th',color==='red'?'Red LED':'Green LED'),node('td','GPIO'+job.old_mapping?.[color]),node('td','GPIO'+job.proposed_mapping?.[color]));$('repair-diff-rows').append(row);}
 $('repair-explanation').textContent=job.explanation?'Muse Spark: '+job.explanation:'';$('repair-explanation').hidden=!job.explanation;
 $('repair-contract').hidden=!job.contract_sha256;$('repair-contract').textContent=job.contract_sha256?'Unchanged behavior · '+job.contract_sha256.slice(0,16)+'…':'';
 $('repair-start').hidden=true;$('repair-approve').hidden=!ready||approved;$('repair-decline').hidden=!ready||approved;
 $('repair-approve').disabled=mappingRepair.busy||!!activeExecution;$('repair-decline').disabled=mappingRepair.busy||!!activeExecution;
 $('repair-source').hidden=!job.source_test_id;$('repair-log').hidden=!job.id;
 window.renderFlow?.();
}
window.resetMappingRepair=function(){if(mappingRepair.busy||mappingRepair.waiter)return;mappingRepair.version++;mappingRepair.job=null;mappingRepair.test=null;$('mapping-repair').hidden=true;};
// Refreshes only saved state. Eligibility does not authorize or perform a probe.
window.showMappingRepairFor=async function(test){
 if(mappingRepair.busy||mappingRepair.waiter)return;
 const version=++mappingRepair.version;mappingRepair.test=test||null;
 const saved=executionJobs.find(j=>j.action==='mapping_repair'&&repairBelongs(j)&&(!test||j.source_test_id===test.id||j.candidate_proposal_id===executionPlan?.id));
 if(saved){renderMappingRepair(saved);return;}
 if(!test||test.status!=='fail'||executionPlan?.origin==='mapping_repair'){$('mapping-repair').hidden=true;return;}
 try{const eligibility=await api('/api/repairs/eligibility/'+test.id);if(version!==mappingRepair.version)return;
  if(eligibility.repair_job_id){const job=await api('/api/jobs/'+eligibility.repair_job_id);if(version===mappingRepair.version)renderMappingRepair(job);return;}
  if(!eligibility.eligible){$('mapping-repair').hidden=true;return;}
  mappingRepair.job=null;$('mapping-repair').hidden=false;$('repair-status').textContent='Available';$('repair-message').textContent='This test contains a confirmed LED mismatch. Run one fixed probe to check whether a firmware mapping correction is supported.';
  for(const id of ['repair-diff','repair-explanation','repair-contract','repair-error','repair-approve','repair-decline','repair-log'])$(id).hidden=true;
  $('repair-start').hidden=false;$('repair-start').disabled=!!activeExecution||!!autopilot;$('repair-source').hidden=false;
 }catch(e){if(version===mappingRepair.version)$('mapping-repair').hidden=true;}
};
async function pollMappingRepair(id){let job;for(;;){job=await api('/api/jobs/'+id);activeExecution=job.status==='running'?job:null;renderMappingRepair(job);updateExecutionButtons();
  if(job.status!=='running')break;
  setAutoState(job.stage==='proposing'?'Muse Spark is proposing a mapping…':'Checking the LED mapping…','busy');
  setStage('explain','running',job.stage==='proposing'?'Muse Spark proposes; local code checks the measured mapping':'Fixed probe: measure GPIO25 and GPIO26 separately');
  if(autopilot?.cancelled&&!job.cancel_requested){try{await planningPost('/api/jobs/'+id+'/cancel',{});}catch(e){}}
  await wait(700);
 }
 await refreshJobs();renderMappingRepair(job);return job;
}
async function activateRepairCandidate(candidate){
 // The server links the approved child to the same accepted project brief. Refresh before the
 // regular lifecycle poll can otherwise reselect the parent while the child is being installed.
 let projectPoll=null;
 if(project?.id){const id=project.id,version=++projectVersion;const fresh=await api('/api/projects/'+id);if(project?.id===fresh.id&&projectVersion===version){project=fresh;projectPoll={id,version};}}
 await renderProposal(candidate);
 if(autopilot)autopilot.plan=candidate.id;
 if(projectPoll)window.pollProjectFirmware?.(projectPoll.id,projectPoll.version);
 window.renderFlow?.();
}
window.cancelMappingRepair=function(){if(mappingRepair.waiter){const resolve=mappingRepair.waiter;mappingRepair.waiter=null;resolve({status:'declined'});}if(!mappingRepair.busy){$('repair-approve').disabled=true;$('repair-decline').disabled=true;}};
window.tryMappingRepair=async function(test){
 if(executionPlan?.origin==='mapping_repair')return null;
 const eligibility=await api('/api/repairs/eligibility/'+test.id);
 if(!eligibility.eligible&&!eligibility.repair_job_id)return null;
 if(autopilot?.cancelled)throw new Error('Stopped');
 mappingRepair.test=test;mappingRepair.busy=true;mappingRepair.version++;
 let job;
 try{
  autoLog('do','Confirmed LED mismatch: run the fixed pin probe, then ask Muse Spark for a measured mapping proposal.');
  setAutoState('Checking the LED mapping…','busy');setStage('explain','running','Fixed GPIO25/26 probe; original behavior remains frozen');
  const started=eligibility.repair_job_id?{id:eligibility.repair_job_id}:await planningPost('/api/repairs',{source_test_id:test.id,request_id:newId(),port:$('execution-port').value,device_id:$('execution-camera').value});
  job=await pollMappingRepair(started.id);
 }finally{mappingRepair.busy=false;}
 renderMappingRepair(job);
 if(autopilot?.cancelled)throw new Error('Stopped');
 if(job.status!=='repair_ready'||job.approval_status==='approved'||job.approved_at_utc){setStage('explain',job.status==='no_change'?'done':'stopped',job.explanation||job.error||job.status);return {status:'stopped',reason:$('repair-message').textContent};}
 setStage('explain','done','Measured mapping checked; proposed correction awaits approval');
 autoLog('meta',job.explanation||'Muse Spark proposed the mapping supported by the camera probe.');
 setStage('decide','stopped','Approval required before the corrected configuration is flashed');
 if(autopilot)autopilot.waiting=true;setAutoState('Review the mapping change before flashing','warn');window.renderFlow?.();
 const outcome=await new Promise(resolve=>{mappingRepair.waiter=resolve;});
 if(autopilot)autopilot.waiting=false;
 return outcome;
};
$('repair-approve').addEventListener('click',async()=>{
 const job=mappingRepair.job;if(!job||job.status!=='repair_ready'||mappingRepair.busy||activeExecution||autopilot?.cancelled)return;
 mappingRepair.busy=true;$('repair-approve').disabled=true;$('repair-decline').disabled=true;$('repair-error').hidden=true;
 try{
  const candidate=await planningPost('/api/repairs/'+job.id+'/approve',{plan_sha256:job.candidate_plan_sha256});
  if(autopilot?.cancelled)throw new Error('Stopped');
  await activateRepairCandidate(candidate);
  mappingRepair.job={...job,approval_status:'approved'};$('repair-status').textContent='Approved · not yet verified';$('repair-approve').hidden=true;$('repair-decline').hidden=true;
  $('repair-message').textContent='Mapping change approved. The next camera test must still pass the original behavior.';
  autoLog('ok','Mapping repair approved; required behavior and measurement policy are unchanged.');
  if(mappingRepair.waiter){const resolve=mappingRepair.waiter;mappingRepair.waiter=null;resolve({status:'approved',candidate});}
  else{mappingRepair.busy=false;await runBench();}
 }catch(e){repairError(e.message);if(e.message==='Stopped')window.cancelMappingRepair();}
 finally{mappingRepair.busy=false;if(mappingRepair.job?.status==='repair_ready'&&!$('repair-approve').hidden){$('repair-approve').disabled=false;$('repair-decline').disabled=false;}}
});
$('repair-decline').addEventListener('click',()=>{
 if(mappingRepair.busy)return;$('repair-message').textContent='Current firmware kept. The recorded failure and proposed correction are saved.';
 window.cancelMappingRepair();
});
$('repair-source').addEventListener('click',async()=>{const id=mappingRepair.job?.source_test_id||mappingRepair.test?.id;if(id){await loadRuns();await selectRun('test-'+id);}});
$('repair-log').addEventListener('click',()=>{if(mappingRepair.job?.id)window.inspectFirmwareJob?.(mappingRepair.job.id);});
$('repair-start').addEventListener('click',async()=>{
 const test=mappingRepair.test;if(!test||autopilot||activeExecution||mappingRepair.busy)return;
 autopilot={cancelled:false,plan:executionPlan.id,testDone:true,attempt:1,waiting:false};window.flowRunStarted?.();$('stop-bench').hidden=false;window.updateProjectActions?.();
 let approved=false;
 try{if(!await ensureDevices())return;if(!await checkView()){repairError('Restore the camera view before probing. Open the camera check in the run log for details.');setAutoState('Restore the camera view before probing','warn');return;}
  const outcome=await window.tryMappingRepair(test);approved=outcome?.status==='approved';if(!approved)setAutoState(outcome?.reason||'Current firmware kept.','warn');
 }catch(e){repairError(e.message);setAutoState('Investigation stopped','warn');}
 finally{autopilot=null;$('stop-bench').hidden=true;window.flowRunEnded?.('',false);updateExecutionButtons();window.updateProjectActions?.();}
 if(approved)await runBench();
});
