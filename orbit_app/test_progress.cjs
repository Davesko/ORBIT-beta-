const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');const ctx=vm.createContext({statusLabel:s=>s});vm.runInContext(fs.readFileSync(__dirname+'/web/progress_ui.js','utf8'),ctx);
let r=vm.runInContext("workflowSummary([{status:'done'},{status:'running'},{status:'queued'},{status:'blocked'}])",ctx);assert.equal(r.done,1);assert.equal(r.errors,1);assert.equal(r.total,4);assert.equal(r.label,'Folyamatban');
r=vm.runInContext("workflowSummary([{status:'done'},{status:'failed'},{status:'blocked'}])",ctx);assert.equal(r.done,1);assert.equal(r.label,'Hibával megállt');assert.equal(vm.runInContext("jobLabel({status:'cancelled',runtime:{label:'Model still replying'}})",ctx),'cancelled');
r=vm.runInContext("workflowSummary([{status:'done'},{status:'done'}])",ctx);assert.equal(r.done,2);assert.equal(r.label,'Elkészült');console.log('Progress: completed steps, blocked branches, successful runs and terminal states verified.');

const picked=vm.runInContext("activeAgentJob([{id:'queued-new',agent:'a',kind:'chat',status:'queued'},{id:'running-old',agent:'a',kind:'graph',status:'running'}],'a')",ctx);assert.equal(picked.id,'running-old');console.log('Active agent state prefers actual running work over a newer queued chat.');
for(const [seconds,label] of [[59.9,'59 mp'],[60,'1 perc 00 mp'],[125,'2 perc 05 mp'],[3946,'1 óra 05 perc 46 mp']]){
 assert.equal(vm.runInContext('formatAgentDuration('+seconds+')',ctx),label);
}
