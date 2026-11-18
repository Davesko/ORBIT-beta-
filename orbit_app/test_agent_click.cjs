const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const handlers={},selected=[];const fakeNode={classList:{add(){},remove(){}},replaceChildren(){},setAttribute(){},getScreenCTM(){return{inverse(){return{}}}},setPointerCapture(){},releasePointerCapture(){},addEventListener(name,handler){handlers[name]=handler}};
const ctx=vm.createContext({Map,Set,Math,JSON,SpaceMath:{iso:(x,y)=>[x,y]},$:()=>fakeNode,document:{addEventListener(){},elementFromPoint(){return null}},state:{agents:[],connections:[]},selectAgent:id=>selected.push(id),setTimeout:()=>{},showConnection(){},DOMPoint:class{constructor(x,y){this.x=x;this.y=y}matrixTransform(){return this}}});
vm.runInContext(fs.readFileSync(__dirname+'/web/station.js','utf8'),ctx);vm.runInContext('screenPoint=(x,y)=>({x,y});installNavigation();agentPositions.set("agent-1",[10,10]);',ctx);
const target={closest(selector){return selector==='[data-agent]'?{dataset:{agent:'agent-1'}}:null}};
const event={button:0,pointerId:5,clientX:10,clientY:10,target};handlers.pointerdown(event);handlers.pointerup(event);assert.deepEqual(selected,['agent-1']);
handlers.pointerdown(event);handlers.pointermove({...event,clientX:60});handlers.pointerup({...event,clientX:60});assert.deepEqual(selected,['agent-1']);console.log('Agent click: pointer capture no longer swallows selection; a real drag does not open chat.');
