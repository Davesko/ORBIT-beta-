const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const calls=[];let fail=false;
const nodes=new Map();
const node=()=>({hidden:false,disabled:false,append(){},addEventListener(){}});
const ctx=vm.createContext({
 commandImage:null,commandSending:false,project:'other-project',chatSession:'chat',
 $:id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},el:node,
 updateAttachment(){},toast(){},document:{addEventListener(){},elementFromPoint(){return null;}},window:{},act:fn=>fn(),
 FileReader:class{readAsDataURL(blob){this.result='data:application/octet-stream;base64,'+Buffer.from(blob.bytes).toString('base64');this.onload();}},
 call:async(action,args)=>{
  calls.push({action,...args});
  if(action==='command_file_begin')return {token:'one-use-upload'};
  if(action==='command_file_chunk'&&fail)throw Error('Write failed');
  if(action==='command_file_end')return {token:'scoped-attachment',label:'clip.mp4'};
  return {};
 }
});
vm.runInContext(fs.readFileSync(__dirname+'/web/chat_drop.js','utf8'),ctx);
ctx.file={name:'clip.mp4',size:1024*1024+7,slice:(start,end)=>({bytes:Buffer.alloc(Math.min(end,1024*1024+7)-start,5)})};
(async()=>{
 const result=await vm.runInContext("importWebFile(file,{project:'original-project'})",ctx);
 assert.equal(result.token,'scoped-attachment');
 const parts=calls.filter(c=>c.action==='command_file_chunk');
 assert.deepEqual(parts.map(p=>p.offset),[0,524288,1048576]);
 assert.deepEqual(parts.map(p=>Buffer.from(p.data,'base64').length),[524288,524288,7]);
 assert.ok(calls.every(c=>c.requestProject==='original-project'),'a changed visible project must not redirect the import');
 assert.ok(calls.every(c=>!('source' in c)&&!('path' in c)),'web code cannot choose a native filesystem path');
 calls.length=0;fail=true;
 await assert.rejects(()=>vm.runInContext("importWebFile(file,{project:'original-project'})",ctx),/Write failed/);
 assert.equal(calls.at(-1).action,'command_file_abort');
 assert.ok(!calls.some(c=>c.action==='command_file_end'),'a partial file must never be imported');
 console.log('File drops: bounded chunks, exact offsets, original project and partial-file cleanup.');
})().catch(e=>{console.error(e);process.exit(1);});
