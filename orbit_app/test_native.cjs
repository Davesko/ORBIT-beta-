const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');
const outbound=[];const context=vm.createContext({project:'universe',window:{webkit:{messageHandlers:{orbit:{postMessage:m=>outbound.push(m)}}}},Map,Promise,Error,setTimeout,clearTimeout});vm.runInContext(fs.readFileSync(__dirname+'/web/native.js','utf8'),context);
(async()=>{
 const first=vm.runInContext("call('artifact_preview',{id:'artifact-123'})",context);assert.equal(outbound[0].id,'artifact-123');assert.equal(outbound[0].requestId,'1');context.window.resolveNative({requestId:'1',ok:true,image:'image-data'});assert.equal((await first).image,'image-data');
 const second=vm.runInContext("call('recipe_run',{id:'recipe-123'})",context);assert.equal(outbound[1].id,'recipe-123');assert.equal(outbound[1].requestId,'2');context.window.resolveNative({requestId:'2',ok:true,job:'job-123'});assert.equal((await second).job,'job-123');
 const third=vm.runInContext("call('job_cancel',{id:'job-123'})",context);context.window.resolveNative({requestId:'3',ok:false,message:'Denied'});await assert.rejects(third,/Denied/);
 console.log('Native bridge: artifact IDs, recipe IDs, cancellation and errors passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
