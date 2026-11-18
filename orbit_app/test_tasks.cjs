const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const nodes=new Map(),requests=[];let ready;
const ctx=vm.createContext({window:{addEventListener:(name,fn)=>{ready=fn;}},project:'open-project',currentApp:'automations',setInterval:()=>{},$:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},call:async(op,data)=>{requests.push({op,data});return {projects:[],automations:[]};}});
vm.runInContext(fs.readFileSync(__dirname+'/web/automations_ui.js','utf8'),ctx);
vm.runInContext("renderAutomations=function legacy(){};loadAutomations=function legacyLoad(){};",ctx);ready();assert.equal(vm.runInContext('renderAutomations===renderGlobalTasks && loadAutomations===loadGlobalTasks',ctx),true);
(async()=>{
 await vm.runInContext("taskCall('automation_toggle',{id:'task-b',enabled:true},'project-b')",ctx);
 assert.equal(requests[0].data.requestProject,'project-b');assert.equal(ctx.project,'open-project');assert.equal(requests[0].data.id,'task-b');
 assert.equal(vm.runInContext("taskActive({runs:[{status:'running'}]})",ctx),true);
 assert.equal(vm.runInContext("taskActive({runs:[{status:'done'}]})",ctx),false);
 console.log('Task manager: global view mutations target the task owner without changing the open project.');
})().catch(e=>{console.error(e);process.exitCode=1;});
