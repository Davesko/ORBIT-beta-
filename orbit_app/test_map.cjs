const assert=require('node:assert/strict');const M=require('./web/map_math.js');
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);
for(const [x,y] of [[0,0],[4.5,8],[-20,100]]){const p=M.iso(x,y),r=M.uniso(...p);close(r[0],x);close(r[1],y);}
const camera={cx:500,cy:325,scale:1},anchor={x:240,y:510};const zoom=M.zoomAt(camera,1.7,anchor);
close((anchor.x-camera.cx)*camera.scale,(anchor.x-zoom.cx)*zoom.scale);close((anchor.y-camera.cy)*camera.scale,(anchor.y-zoom.cy)*zoom.scale);
const clamped=M.zoomAt(camera,1000,anchor);assert.equal(clamped.scale,4);close((anchor.x-camera.cx)*camera.scale,(anchor.x-clamped.cx)*clamped.scale);
const moved=M.pan(camera,120,-60);assert.deepEqual(moved,{cx:380,cy:385,scale:1});assert.deepEqual(camera,{cx:500,cy:325,scale:1});
const room={x:0,y:0,width:8.5,height:7.5};const seats=Array.from({length:16},(_,i)=>M.seat(room,i,16));assert.equal(new Set(seats.map(p=>`${p.x},${p.y}`)).size,16);assert.ok(seats.every(p=>p.x>0&&p.x<8.5&&p.y>0&&p.y<7.5));
const fit=M.fit([room,{...room,x:48,y:42}]);assert.ok(fit.scale<1);for(const r of [room,{...room,x:48,y:42}])for(const p of [M.iso(r.x,r.y,48),M.iso(r.x+r.width,r.y+r.height)]){assert.ok(Math.abs(p[0]-fit.cx)*fit.scale<500);assert.ok(Math.abs(p[1]-fit.cy)*fit.scale<325);}
console.log('Map geometry: coordinate inversion, anchored zoom, clamping, pan, 16 distinct seats and full-map fit passed.');
