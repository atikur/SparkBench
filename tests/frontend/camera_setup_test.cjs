// Real browser scripts with an in-memory DOM and fake API. No device or model calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const dir = path.resolve(__dirname, '../../src/sparkbench/dashboard/static');
class Element {
 constructor() { this.hidden = true; this.disabled = false; this.children = []; this.listeners = {}; this.value = ''; this.dataset = {}; this.style = {}; this.textContent = ''; this.open = false; }
 addEventListener(name, fn) { this.listeners[name] = fn; }
 append(...items) { this.children.push(...items); }
 replaceChildren(...items) { this.children = items; }
 querySelector() { return new Element(); }
 removeAttribute(name) { delete this[name]; }
 get options() { return this.children; }
 get selectedOptions() { return this.children.filter(x => x.value === this.value); }
 focus() {}
 scrollIntoView() {}
 getBoundingClientRect() { return {left: 0, top: 0, width: 800, height: 600}; }
 getContext() { return {drawImage(){},strokeRect(){},fillRect(){},fillText(){},beginPath(){},arc(){},stroke(){},moveTo(){},lineTo(){},closePath(){},measureText(){return{width:50};}}; }
 async click(event) { if (!this.disabled) return this.listeners.click?.(event); }
}
async function flush() { for (let i = 0; i < 20; i++) await new Promise(resolve => setTimeout(resolve, 2)); }
function base() {
 const nodes = new Map(); const $ = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
 const ctx = {console, Blob, Uint8Array, URL, crypto: webcrypto, atob, btoa, setTimeout: fn => setTimeout(fn, 0), $,
  document: {querySelector: () => null, createElement: () => new Element()}, node: (_, text) => {const e=new Element();e.textContent=text;return e;},
  updateProjectActions(){},renderFlow(){}};
 ctx.window=ctx; vm.createContext(ctx);return {ctx,$};
}
function panelFixture({badHash=false,startGate,validationGate,confirmError=false,automatic=false}={}) {
 const f=base(), {ctx,$}=f, calls=[];const bytes=Buffer.from('simulated capture bytes'),sha=createHash('sha256').update(bytes).digest('hex');
 const jobId='c'.repeat(32),proposalId='a'.repeat(32);let confirmed=false;
 ctx.fetch=async()=>({ok:true,blob:async()=>new Blob([bytes],{type:'image/jpeg'})});
 ctx.createImageBitmap=async()=>({width:800,height:600,close(){}});
 ctx.api=async url=>{calls.push(['GET',url]);if(url==='/api/devices')return{cameras:[{id:'iphone',name:'iPhone'}]};
  if(url==='/api/jobs/'+jobId){if(automatic||confirmed){if(validationGate)await validationGate;return{id:jobId,status:'setup_ready'};}
   return{id:jobId,status:'setup_review',latest_frame:{url:'/source.jpg'},image_sha256:badHash?'0'.repeat(64):sha,image_width:800,image_height:600,
    regions:{oled:[100,100,300,250]},sources:{oled:'sam-3.1'},led_radii:{red:9,green:9}};}
  throw Error('Unexpected GET '+url);};
 ctx.planningPost=async(url,body)=>{calls.push(['POST',url,body]);if(url==='/api/camera/setup'){if(startGate)await startGate;return{id:jobId};}
  if(url==='/api/camera/setup/'+jobId+'/regions')return{image_sha256:sha,model:'sam-3.1',regions:{red:[388,188,412,212],green:[438,188,462,212]}};
  if(url==='/api/camera/setup/'+jobId+'/confirm'){if(confirmError)throw Error('Corner check failed');confirmed=true;return{id:jobId};}
  if(url.endsWith('/cancel'))return{};throw Error('Unexpected POST '+url);};
 vm.runInContext(fs.readFileSync(path.join(dir,'camera-regions.js'),'utf8'),ctx);
 return{...f,calls,proposalId,jobId,sha};
}
async function clickPoint(f,x,y) { await f.$('regions-photo').click({clientX:x,clientY:y}); }
async function selectRegions(f,{manual=false}={}) {
 await f.$('regions-red').click();await clickPoint(f,400,200);
 await f.$('regions-green').click();await clickPoint(f,450,200);
 await f.$(manual?'regions-circles':'regions-outline').click();
 await f.$('regions-corners').click();
 for(const [x,y]of[[110,110],[290,110],[290,240],[110,240]])await clickPoint(f,x,y);
}
function agentFixture(statuses,{started=false,repair=false}={}) {
 const f=base(),{ctx,$}=f,calls=[];let n=0,setupCalls=0;
 ctx.executionPlan={id:'a'.repeat(32),origin:repair?'mapping_repair':undefined};ctx.activeExecution=null;
 ctx.matchingJobs=()=>[];ctx.buildJob=()=>null;ctx.optionName=()=>'';ctx.updateExecutionButtons=()=>{};
 $('execution-camera').value='iphone';
 ctx.planningPost=async(url,body)=>{calls.push([url,body]);return{id:String(n++)};};
 ctx.api=async()=>statuses.shift();
 vm.runInContext(fs.readFileSync(path.join(dir,'autopilot.js'),'utf8'),ctx);
 vm.runInContext('autopilot={cancelled:false,setupAttempted:false,testStarted:'+started+',waiting:false}',ctx);
 // These scenarios start from a plan with a reference. autopilot_camera_test.cjs covers a new plan.
 ctx.cameraSetupSavedPlans=new Set(['a'.repeat(32)]);
 ctx.setStage=()=>{};ctx.autoLog=()=>{};ctx.setupCameraForAgent=async()=>{setupCalls++;return true;};ctx.waitForPerson=async()=>false;
 return{...f,calls,setupCalls:()=>setupCalls};
}
async function main(){
 // Fresh photo is bound to hash/dimensions; no save until every required selection is valid.
 {
  const f=panelFixture();const outcome=f.ctx.setupCameraForAgent(f.proposalId,'iphone');await flush();
  assert.equal(f.$('regions-save').disabled,true);assert.equal(f.calls.filter(x=>x[1].endsWith('/confirm')).length,0);
  await selectRegions(f);assert.equal(f.$('regions-save').disabled,false);await f.$('regions-save').click();assert.equal(await outcome,true);
  const confirmation=f.calls.find(x=>x[1].endsWith('/confirm'))[2];assert.equal(confirmation.image_sha256,f.sha);
  assert.deepEqual(Object.keys(confirmation).sort(),['image_sha256','oled_corners','points','regions','sources']);
  assert.equal(confirmation.oled_corners.length,4);assert.equal(f.ctx.cameraSetupActive,false);assert.equal(f.$('regions-panel').hidden,true);
 }
 // Automatic readiness resumes the agent without opening the editor or asking for confirmation.
 {
  const f=panelFixture({automatic:true});
  assert.equal(await f.ctx.setupCameraForAgent(f.proposalId,'iphone'),true);
  assert.equal(f.$('regions-panel').hidden,true);
  assert.equal(f.calls.some(x=>x[1].endsWith('/confirm')),false);
  assert.equal(f.ctx.cameraSetupSavedPlans.has(f.proposalId),true);
 }
 // The panel stays hidden while the agent sets up alone, and Stop still cancels it.
 {
  let release;const gate=new Promise(r=>release=r),f=panelFixture({automatic:true,validationGate:gate});const outcome=f.ctx.setupCameraForAgent(f.proposalId,'iphone');await flush();
  assert.equal(f.$('regions-panel').hidden,true);assert.equal(f.ctx.cameraSetupActive,true);assert.equal(f.ctx.cameraSetupActivity.busy,true);
  release();assert.equal(await outcome,true);assert.equal(f.$('regions-panel').hidden,true);
  const g=panelFixture({automatic:true,startGate:new Promise(()=>{})});const stopped=g.ctx.setupCameraForAgent(g.proposalId,'iphone');await flush();
  g.ctx.cancelCameraSetup();assert.equal(await stopped,false);assert.equal(g.$('regions-panel').hidden,true);
 }
 // It opens with a reason when the agent cannot place the parts.
 {
  const f=panelFixture();const outcome=f.ctx.setupCameraForAgent(f.proposalId,'iphone');await flush();
  assert.equal(f.$('regions-panel').hidden,false);assert.match(f.$('regions-title').textContent,/needs your help/);assert.match(f.$('regions-help').textContent,/could not place every part/);
  await f.$('regions-close').click();assert.equal(await outcome,false);
 }
 // It opens with the error when setup stops, so the run cannot look stuck.
 {
  const f=panelFixture();f.ctx.planningPost=async()=>{throw new Error('The camera is busy');};const outcome=f.ctx.setupCameraForAgent(f.proposalId,'iphone');await flush();
  assert.equal(f.$('regions-panel').hidden,false);assert.match(f.$('regions-status').textContent,/camera is busy/);assert.match(f.$('regions-title').textContent,/needs your help/);
  await f.$('regions-close').click();assert.equal(await outcome,false);
 }
 // It opens when no camera is selected, and at once when the person asks for it by hand.
 {
  const f=panelFixture();const outcome=f.ctx.setupCameraForAgent(f.proposalId,null);await flush();
  assert.equal(f.$('regions-panel').hidden,false);assert.match(f.$('regions-help').textContent,/Choose the iPhone/);await f.$('regions-close').click();assert.equal(await outcome,false);
  const g=panelFixture({startGate:new Promise(()=>{})});const manual=g.ctx.setupCameraForAgent(g.proposalId,'iphone',true);
  assert.equal(g.$('regions-panel').hidden,false);assert.match(g.$('regions-title').textContent,/Set up the camera/);await g.$('regions-close').click();assert.equal(await manual,false);
 }
 // Closing during creation cancels the exact new job even if its ID arrives later.
 {
  let release;const gate=new Promise(r=>release=r),f=panelFixture({startGate:gate});const outcome=f.ctx.setupCameraForAgent(f.proposalId,'iphone');
  await f.$('regions-close').click();assert.equal(await outcome,false);release();await flush();
  assert.equal(f.calls.filter(x=>x[1]==='/api/jobs/'+f.jobId+'/cancel').length,1);
  assert.equal(f.calls.filter(x=>x[1].endsWith('/confirm')).length,0);
 }
 // An altered source photo cannot become an approved reference.
 {
  const f=panelFixture({badHash:true});const outcome=f.ctx.setupCameraForAgent(f.proposalId,'iphone');await flush();
  assert.equal(f.$('regions-save').disabled,true);assert.match(f.$('regions-status').textContent,/differs/);await f.$('regions-close').click();assert.equal(await outcome,false);
 }
 // Manual circles carry explicit manual provenance, and failed confirmation does not report success.
 {
  const f=panelFixture({confirmError:true});const outcome=f.ctx.setupCameraForAgent(f.proposalId,'iphone');await flush();await selectRegions(f,{manual:true});
  await f.$('regions-save').click();assert.match(f.$('regions-status').textContent,/Corner check failed/);assert.equal(f.$('regions-panel').hidden,false);
  const body=f.calls.find(x=>x[1].endsWith('/confirm'))[2];assert.equal(body.sources.red,'manual');assert.equal(body.sources.green,'manual');
  await f.$('regions-close').click();assert.equal(await outcome,false);
 }
 // Clockwise OLED corners and sampling circles inside LED boxes are required client-side.
 {
  const f=panelFixture();const outcome=f.ctx.setupCameraForAgent(f.proposalId,'iphone');await flush();await selectRegions(f);
  await f.$('regions-corners').click();for(const [x,y]of[[110,110],[110,240],[290,240],[290,110]])await clickPoint(f,x,y);
  assert.equal(f.$('regions-save').disabled,true);assert.match(f.$('regions-review-help').textContent,/clockwise/);
  await f.$('regions-close').click();assert.equal(await outcome,false);
 }
 // Cancel during validation cannot fall through when a successful response arrives late.
 {
  let release;const gate=new Promise(r=>release=r),f=panelFixture({validationGate:gate});const outcome=f.ctx.setupCameraForAgent(f.proposalId,'iphone');await flush();await selectRegions(f);
  const save=f.$('regions-save').click();await flush();f.ctx.cancelCameraSetup();assert.equal(await outcome,false);release();await save;
  assert.equal(f.ctx.cameraSetupActive,false);assert.equal(f.calls.filter(x=>x[1].endsWith('/cancel')).length,1);
 }
 // No automatic camera choice when setup begins without an explicit selected camera.
 {
  const f=panelFixture();const outcome=f.ctx.setupCameraForAgent(f.proposalId,null);await flush();
  assert.equal(f.calls.some(x=>x[1]==='/api/camera/setup'),false);assert.equal(f.$('regions-camera').value,'');
  await f.$('regions-close').click();assert.equal(await outcome,false);
 }
 // A blocked check leads to one guided setup. Its validation capture already ran the same checks, so no recheck follows.
 {
  const f=agentFixture([{status:'view_blocked',setup_available:true,view_issues:[{problem:'Camera moved'}]}, {status:'view_ok',oled_reading:'READY'}]);
  await f.ctx.checkViewUntilClear();assert.equal(f.setupCalls(),1);assert.equal(f.calls.length,1);
  assert.equal(f.calls[0][1].proposal_id,'a'.repeat(32));
 }
 // A valid reference skips SAM. Missing/ambiguous measurements never become a pass from setup alone.
 {
  const f=agentFixture([{status:'view_ok',oled_reading:'READY'}]);await f.ctx.checkViewUntilClear();assert.equal(f.setupCalls(),0);
 }
 // A repair keeps its parent's reference, so the agent never sets up for one.
 {
  const f=agentFixture([{status:'view_blocked',setup_available:true,view_issues:[{problem:'Camera moved'}]}],{repair:true});
  await assert.rejects(f.ctx.checkViewUntilClear(),/Stopped/);assert.equal(f.setupCalls(),0);
 }
 // After a test has started in this run, a bumped phone still gets an automatic setup before the next test.
 {
  const f=agentFixture([{status:'view_blocked',setup_available:true,view_issues:[{problem:'Camera moved'}]}, {status:'view_ok',oled_reading:'READY'}],{started:true});
  await f.ctx.checkViewUntilClear();assert.equal(f.setupCalls(),1);
 }
 // Each camera check leads to at most one setup, and the check after flashing can lead to its own.
 {
  const f=agentFixture([{status:'view_blocked',setup_available:true,view_issues:[{problem:'Camera moved'}]}, {status:'view_blocked',setup_available:true,view_issues:[{problem:'Camera moved'}]}]);
  await f.ctx.checkViewUntilClear();assert.equal(f.setupCalls(),1);assert.equal(f.calls.length,1);
  await f.ctx.checkViewUntilClear();assert.equal(f.setupCalls(),2);assert.equal(f.calls.length,2);
 }
 console.log('Camera setup UI: 17 simulated scenarios passed; no hardware or model requests.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
