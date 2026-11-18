const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const nodes=new Map();let calls=0,polls=0;
class Element{constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.dataset={};this.classList={toggle(){}};}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}prepend(v){this.children.unshift(v);}remove(){if(this.id)nodes.delete(this.id);}setAttribute(k,v){this[k]=v;}replaceChildren(){this.children=[];}addEventListener(){}focus(){}}
const get=id=>{if(!nodes.has(id)){const n=new Element('div');n.id=id;}return nodes.get(id);};
const ctx=vm.createContext({$:id=>id==='commandBriefing'?nodes.get(id):get(id),el:(tag,cls,text)=>new Element(tag,text),button:(text,fn)=>Object.assign(new Element('button',text),{onclick:fn}),call:async()=>{calls++;return {result:{chats:[]}};},act:fn=>fn(),currentApp:'home',project:'universe',chatSession:'',localStorage:{getItem:()=>null,setItem(){}},document:{hidden:false},commandCards:new Map(),commandState:null,switchApp(){},pollCommand(){polls++;},setInterval(){},setTimeout,clearTimeout});
vm.runInContext(fs.readFileSync(__dirname+'/web/brief_ui.js','utf8'),ctx);
ctx.brief={id:7,summary:'1 teendő',items:[{email:'mail-1',task:'Válaszolj.',sender:'sender@example.com',subject:'Egyeztetés',days:0,account:'a'}]};
vm.runInContext('briefRender(brief)',ctx);assert.ok(nodes.has('commandBriefing'));
nodes.get('commandBriefing').children[0].children[1].onclick();assert.ok(!nodes.has('commandBriefing'));assert.equal(calls,0,'closing a reminder must not dismiss it globally');
vm.runInContext('briefRender(brief)',ctx);assert.ok(!nodes.has('commandBriefing'),'polling must respect dismissal in this chat');
vm.runInContext(fs.readFileSync(__dirname+'/web/chats_ui.js','utf8'),ctx);
vm.runInContext('openChat=()=>{};loadChats=()=>{};',ctx);
get('navNewChat').onclick();vm.runInContext('briefRender(brief)',ctx);assert.ok(nodes.has('commandBriefing'));assert.ok(polls>0,'new chat must poll even when the previous draft was already blank');
nodes.get('commandBriefing').children[0].children[1].onclick();get('navNewChat').onclick();vm.runInContext('briefRender(brief)',ctx);assert.ok(nodes.has('commandBriefing'),'each new chat restores outstanding reminders');
console.log('Mail reminders: dismissal is local, repeated new chats restore reminders and refresh the data.');
