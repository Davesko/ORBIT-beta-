/* Geometry stays independent from rendering and native UI. */
const SpaceMath=(()=>{
 const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
 const iso=(x,y,z=0)=>[495+x*28,57+y*28-z];
 const uniso=(x,y)=>[(x-495)/28,(y-57)/28];
 function zoomAt(camera,factor,point){const scale=clamp(camera.scale*factor,.2,4),ratio=scale/camera.scale;return {cx:point.x+(camera.cx-point.x)/ratio,cy:point.y+(camera.cy-point.y)/ratio,scale};}
 const pan=(camera,dx,dy)=>({...camera,cx:camera.cx-dx,cy:camera.cy-dy});
 function fit(rooms){if(!rooms.length)return {cx:500,cy:325,scale:1};const ps=rooms.flatMap(r=>[iso(r.x,r.y,48),iso(r.x+r.width,r.y,48),iso(r.x,r.y+r.height),iso(r.x+r.width,r.y+r.height)]);const xs=ps.map(p=>p[0]),ys=ps.map(p=>p[1]);const left=Math.min(...xs)-85,right=Math.max(...xs)+85,top=Math.min(...ys)-40,bottom=Math.max(...ys)+80;return {cx:(left+right)/2,cy:(top+bottom)/2,scale:clamp(Math.min(1000/(right-left),650/(bottom-top)),.2,4)};}
 function seat(r,index,count){const cols=Math.min(4,Math.ceil(Math.sqrt(Math.max(1,count)))),rows=Math.ceil(Math.max(1,count)/cols);return {x:r.x+r.width*(index%cols+1)/(cols+1),y:r.y+Math.min(4.4,r.height*.61)+(rows===1?0:Math.floor(index/cols)*(r.height-5.3)/Math.max(1,rows-1))};}
 return {clamp,iso,uniso,zoomAt,pan,fit,seat};
})();
if(typeof module!=='undefined')module.exports=SpaceMath;
