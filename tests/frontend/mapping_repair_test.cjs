// Exercises the real browser orchestration against an in-memory DOM and explicit fake APIs.
// No camera, serial port, compiler, model request or live dashboard is used.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const staticDir=path.resolve(__dirname,'../../src/sparkbench/dashboard/static');
class Element{
 constructor(){this.hidden=true;this.disabled=false;this.dataset={};this.children=[];this.listeners={};this.value='';this.style={};this.classList={toggle(){}};this.textContent='';}
 addEventListener(name,fn){this.listeners[name]=fn;}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 querySelector(){return new Element();}
 async click(){if(!this.disabled)return this.listeners.click?.();}
}
function fixture({status='repair_ready',eligibility=true,approvalError=false}={}){
 const nodes=new Map(),el=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
 el('execution-port').value='FAKE-PORT';el('execution-camera').value='FAKE-CAMERA';
 const parent={id:'a'.repeat(32),plan_sha256:'1'.repeat(64),status:'ready',review_status:'reviewed',proposal:{steps:[{red:true,green:false,text:'READY'}]}};
 const candidate={...parent,id:'b'.repeat(32),plan_sha256:'2'.repeat(64),origin:'mapping_repair',parent_id:parent.id};
 const failure={id:'c'.repeat(32),action:'test',proposal_id:parent.id,status:'fail',evidence_available:true};
 const repair={id:'d'.repeat(32),action:'mapping_repair',status,stage:'finished',proposal_id:parent.id,parent_proposal_id:parent.id,source_test_id:failure.id,old_mapping:{red:25,green:26},observed_mapping:{red:26,green:25},proposed_mapping:{red:26,green:25},explanation:'The measured responses support the reversed mapping.',contract_sha256:'3'.repeat(64),candidate_proposal_id:status==='repair_ready'?candidate.id:null,candidate_plan_sha256:candidate.plan_sha256};
 const calls=[],actions=[];
 const jobs=[{id:'original-build',action:'compile',status:'compiled',proposal_id:parent.id,firmware_sha256:'old-firmware'}, {id:'original-install',action:'install',status:'installed',proposal_id:parent.id,firmware_sha256:'old-firmware',runtime_identity:{status:'pass'}}];
 const ctx={console,setTimeout:(fn)=>setTimeout(fn,0),crypto:{randomUUID:()=> '9'.repeat(32)},document:{querySelector:()=>null},project:null,projectVersion:0,
  executionPlan:parent,executionJobs:jobs,activeExecution:null,testResultVersion:0,plannerSession:{planning_available:true},
  $:el,node:()=>new Element(),optionName:id=>el(id).value,
  updateExecutionButtons(){},renderExecution(){},showTestResult(){},loadRuns:async()=>{},selectRun:async()=>{},renderFlow(){},updateProjectActions(){},
  flowRunStarted(){},flowRunEnded(){},renderProposal(value){ctx.executionPlan=value;},executionProposal:async value=>{ctx.executionPlan=value;},
  matchingJobs:()=>jobs.filter(j=>j.proposal_id===ctx.executionPlan.id),buildJob:()=>jobs.find(j=>j.action==='compile'&&j.proposal_id===ctx.executionPlan.id),
  api:async url=>{calls.push(['GET',url]);if(url==='/api/board')return{active_firmware_sha256:'old-firmware'};
   if(url.startsWith('/api/runs/'))return{behavior_verdict:'fail',evaluated_sample_count:10,geometry_rejected_sample_count:0,frames:[]};
   if(url.startsWith('/api/repairs/eligibility/'))return{eligible:eligibility,reason:eligibility?'LED mismatch':'Not eligible'};
   if(url==='/api/jobs/'+repair.id)return repair;if(url==='/api/jobs')return{jobs};throw new Error('Unexpected read '+url);},
  planningPost:async (url,body)=>{calls.push(['POST',url,body]);if(url==='/api/repairs'){jobs.push(repair);return{id:repair.id};}
   if(url==='/api/repairs/'+repair.id+'/approve'){if(approvalError)throw new Error('Evidence changed');repair.approval_status='approved';return candidate;}
   if(url.endsWith('/cancel'))return{};throw new Error('Unexpected mutation '+url);},
 };
 ctx.window=ctx;vm.createContext(ctx);
 vm.runInContext(fs.readFileSync(path.join(staticDir,'autopilot.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(staticDir,'mapping-repair.js'),'utf8'),ctx);
 ctx.setStage=()=>{};ctx.resetTimeline=()=>{};ctx.autoLog=()=>{};ctx.ensureDevices=async()=>true;ctx.checkViewUntilClear=async()=>{};
 ctx.refreshJobs=async()=>{};
 ctx.runJob=async action=>{const id=ctx.executionPlan.id;actions.push(action+':'+(id===parent.id?'parent':'candidate'));
  if(action==='test')return id===parent.id?failure:{id:'success',action:'test',status:'pass',evidence_available:true,proposal_id:id};
  const job={id:action+'-candidate',action,status:action==='compile'?'compiled':'installed',proposal_id:id,firmware_sha256:'new-firmware',runtime_identity:{status:'pass'}};jobs.push(job);return job;};
 ctx.explainRun=async()=>{throw new Error('Unexpected advisory request');};
 return{ctx,calls,actions,el,parent,candidate,repair,failure,jobs};
}
async function settled(){for(let i=0;i<12;i++)await new Promise(resolve=>setImmediate(resolve));}
async function main(){
 // Full orchestration: confirmed failure -> fixed probe -> stop at review -> compile/install/retest.
 {
  const f=fixture();const running=f.ctx.runBench();await settled();
  assert.deepEqual(f.actions,['test:parent']);
  assert.equal(f.calls.filter(c=>c[0]==='POST'&&c[1]==='/api/repairs').length,1);
  assert.equal(f.calls.some(c=>c[1].endsWith('/approve')),false);
  assert.equal(f.el('repair-approve').hidden,false);assert.equal(f.el('repair-diff-rows').children.length,2);
  await f.el('repair-approve').click();await running;
  assert.deepEqual(f.actions,['test:parent','compile:candidate','install:candidate','test:candidate']);
  assert.equal(f.calls.filter(c=>c[1].endsWith('/approve')).length,1);
  assert.equal(f.calls.find(c=>c[1].endsWith('/approve'))[2].plan_sha256,f.candidate.plan_sha256);
  assert.deepEqual(f.candidate.proposal.steps,f.parent.proposal.steps);
 }
 // An unapproved proposal can be inspected or declined without a firmware operation.
 {
  const f=fixture();const running=f.ctx.runBench();await settled();await f.el('repair-decline').click();await running;
  assert.deepEqual(f.actions,['test:parent']);assert.equal(f.calls.some(c=>c[1].endsWith('/approve')),false);
 }
 // Failed evidence checks at approval never fall through to compilation/installation.
 {
  const f=fixture({approvalError:true});const running=f.ctx.runBench();await settled();await f.el('repair-approve').click();
  assert.deepEqual(f.actions,['test:parent']);assert.equal(f.el('repair-error').textContent,'Evidence changed');
  await f.el('repair-decline').click();await running;
 }
 // Missing/contradictory/no-change results terminate the single attempt; no automatic retry or flash.
 for(const status of ['incomplete','invalid_response','no_change','cancelled']){
  const f=fixture({status});await f.ctx.runBench();assert.deepEqual(f.actions,['test:parent']);
  assert.equal(f.calls.filter(c=>c[0]==='POST'&&c[1]==='/api/repairs').length,1);
  assert.equal(f.el('repair-approve').hidden,true);
 }
 // Opening a saved repair record is read-only, including a completed candidate after approval.
 {
  const f=fixture();f.jobs.push(f.repair);await f.ctx.showMappingRepairFor(f.failure);
  assert.equal(f.calls.some(c=>c[0]==='POST'),false);assert.deepEqual(f.actions,[]);
  f.repair.approval_status='approved';await f.ctx.showMappingRepairFor(f.failure);assert.equal(f.el('repair-approve').hidden,true);
 }
 // Ineligible outcomes and child candidates never trigger another probe.
 {
  const f=fixture({eligibility:false});assert.equal(await f.ctx.tryMappingRepair(f.failure),null);
  f.ctx.executionPlan=f.candidate;assert.equal(await f.ctx.tryMappingRepair(f.failure),null);
  assert.equal(f.calls.some(c=>c[0]==='POST'),false);
 }
 // Stop releases a pending approval and cannot race into installation.
 {
  const f=fixture();const running=f.ctx.runBench();await settled();await f.el('stop-bench').click();await running;
  assert.deepEqual(f.actions,['test:parent']);assert.equal(f.calls.some(c=>c[1].endsWith('/approve')),false);
 }
 console.log('Mapping repair UI: 10 simulated scenarios passed; no hardware or model requests.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
