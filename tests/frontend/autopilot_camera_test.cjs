// Real autopilot.js with an in-memory DOM and fake jobs: which camera step a run takes. No device or model calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const dir = path.resolve(__dirname, '../../src/sparkbench/dashboard/static');
class Element {
 constructor() { this.hidden = true; this.children = []; this.dataset = {}; this.value = 'iphone'; this.textContent = ''; }
 addEventListener() {}
 append(...items) { this.children.push(...items); }
 replaceChildren(...items) { this.children = items; }
 querySelector() { return new Element(); }
 setAttribute() {}
}
function fixture({jobs = [], saved = false, origin = 'proposal', blocked = false, ready = true, clear = true}) {
 const nodes = new Map(), $ = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
 const calls = {checks: 0, setups: 0, waits: 0, stages: [], logs: []};
 const ctx = {console, $, setTimeout, clearTimeout, document: {querySelector: () => null, querySelectorAll: () => [], createElement: () => new Element()},
  node: (_, text) => { const e = new Element(); e.textContent = text; return e; }, renderFlow() {}, api: async () => ({}), planningPost: async () => ({}), calls};
 ctx.window = ctx;
 vm.createContext(ctx);
 vm.runInContext('let executionPlan=null,executionJobs=[],activeExecution=null;let testResultVersion=0;', ctx);
 vm.runInContext(fs.readFileSync(path.join(dir, 'autopilot.js'), 'utf8'), ctx);
 vm.runInContext(`autopilot={cancelled:false,plan:'p',setupAttempted:false,attempt:0,waiting:false};`, ctx);
 ctx.__plan = {id: 'p', origin}; ctx.__jobs = jobs;
 vm.runInContext('executionPlan=__plan;executionJobs=__jobs;', ctx);
 if (saved) ctx.cameraSetupSavedPlans = new Set(['p']);
 ctx.setStage = (id, state, note) => calls.stages.push([id, state, note]);
 ctx.autoLog = (kind, text) => calls.logs.push([kind, text]);
 ctx.setAutoState = () => {};
 ctx.waitForPerson = async () => { calls.waits++; return false; };
 ctx.setupCameraForAgent = async () => {
  calls.setups++;
  ctx.samStageJob = {job: {sources: {oled: 'sam-3.1', red: 'local-vision', green: 'sam-3.1'}, oled_reading: 'READY'}};
  return ready;
 };
 ctx.checkView = async () => {
  calls.checks++;
  vm.runInContext(`lastViewCheck=${JSON.stringify({setup_available: blocked})};`, ctx);
  return clear && !blocked;
 };
 return {ctx, calls, run: () => vm.runInContext('checkViewUntilClear()', ctx), get: code => vm.runInContext(code, ctx)};
}
(async () => {
 // A new plan goes straight to setup, with no check before or after it.
 let f = fixture({});
 await f.run();
 assert.deepEqual([f.calls.setups, f.calls.checks, f.calls.waits], [1, 0, 0]);
 assert.deepEqual(f.calls.stages.at(-1), ['view', 'done', 'Camera set up · OLED reads "READY"']);
 assert.match(f.calls.logs.at(-1)[1], /SAM 3\.1 outlined 2 of 3 parts/);
 assert.equal(f.get('autopilot.setupAttempted'), false);
 // The look after flashing is the quick check, since the plan now has its reference.
 f.ctx.cameraSetupSavedPlans = new Set(['p']);
 await f.run();
 assert.deepEqual([f.calls.setups, f.calls.checks], [1, 1]);
 // A plan with a reference, or a test on record, keeps the quick check.
 for (const options of [{saved: true}, {jobs: [{proposal_id: 'p', action: 'camera_setup', status: 'setup_ready'}]}, {jobs: [{proposal_id: 'p', action: 'test', status: 'pass'}]}]) {
  f = fixture(options);
  await f.run();
  assert.deepEqual([f.calls.setups, f.calls.checks], [0, 1]);
 }
 // Another plan's records do not count, and an unfinished setup is not a reference.
 for (const jobs of [[{proposal_id: 'q', action: 'test', status: 'pass'}], [{proposal_id: 'p', action: 'camera_setup', status: 'setup_review'}]]) {
  f = fixture({jobs});
  await f.run();
  assert.deepEqual([f.calls.setups, f.calls.checks], [1, 0]);
 }
 // A moved phone on a plan with a reference falls back to setup, with no recheck.
 f = fixture({saved: true, blocked: true});
 await f.run();
 assert.deepEqual([f.calls.checks, f.calls.setups, f.calls.waits], [1, 1, 0]);
 // A repair keeps its parent's reference: it never sets up, and a blocked view waits for the person.
 f = fixture({origin: 'mapping_repair', blocked: true});
 await assert.rejects(f.run(), /Stopped/);
 assert.deepEqual([f.calls.setups, f.calls.checks, f.calls.waits], [0, 1, 1]);
 // A setup that does not finish stops the run instead of continuing.
 f = fixture({ready: false});
 await assert.rejects(f.run(), /Stopped/);
 assert.deepEqual([f.calls.setups, f.calls.checks], [1, 0]);
 assert.notDeepEqual(f.calls.stages.at(-1)[1], 'done');
 console.log('Autopilot camera steps: 10 simulated scenarios passed; no hardware or model requests.');
})().catch(error => { console.error(error); process.exit(1); });
