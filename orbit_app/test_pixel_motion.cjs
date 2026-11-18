const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/web/pixel_refine.js','utf8');const code=source.slice(source.indexOf('const PixelMotion='),source.indexOf('\nanimateStation='));const context=vm.createContext({});vm.runInContext(code,context);
const room={x:-12,y:8,width:10,height:8},seat={x:-7,y:12.4};let walked=false,sat=false;
for(let index=0;index<16;index++)for(let t=0;t<64000;t+=250){context.args=[room,seat,index,t,false,false];const p=vm.runInContext('PixelMotion.pose(...args)',context);assert(p.x>room.x&&p.x<room.x+room.width);assert(p.y>room.y&&p.y<room.y+room.height);walked||=p.walking;sat||=p.sitting;}
assert(walked&&sat);context.args=[room,seat,2,15000,true,false];let p=vm.runInContext('PixelMotion.pose(...args)',context);assert.equal(p.x,seat.x);assert.equal(p.y,seat.y);assert(p.sitting&&!p.walking);
context.args=[room,seat,2,15000,false,true];p=vm.runInContext('PixelMotion.pose(...args)',context);assert.equal(p.x,seat.x);assert.equal(p.y,seat.y);assert(!p.walking);
console.log('Pixel movement: room bounds, walking/rest phases, real working seats and reduced motion passed.');
