/* Moving scene themes (2026-11-12, owner: "mozgó animációs hátteret… Windows XP képernyővédő jellegű, modernizálva").
   One small canvas engine draws the backdrop behind the main chat and the workshop map: shooting stars, waves,
   falling code and campfire light. It runs at 30 fps at most, pauses in the background and holds a still frame
   when the app's motion switch is off or the system asks for reduced motion. */
const ThemeMotion=(()=>{
 const THEMES=['meteor','wave','coder','campfire'];
 const rnd=(a,b)=>a+Math.random()*(b-a);
 const SCENES={
  meteor:{
   init(s){s.stars=Array.from({length:Math.round(s.w*s.h/5200)},()=>({x:rnd(0,s.w),y:rnd(0,s.h),r:rnd(.4,1.4),p:rnd(0,6.3),sp:rnd(.6,2)}));
    s.comets=[];s.drift=Array.from({length:5},(_,i)=>({a:rnd(0,6.3),b:rnd(0,6.3),sa:rnd(.08,.16),sb:rnd(.06,.13),hue:[210,280,320,190,250][i],trail:[]}));s.next=0;},
   draw(s,c,t,dt){const g=c.createLinearGradient(0,0,s.w*.4,s.h);g.addColorStop(0,'#070a1c');g.addColorStop(.55,'#0d1236');g.addColorStop(1,'#1d1240');c.fillStyle=g;c.fillRect(0,0,s.w,s.h);
    const glow=c.createRadialGradient(s.w*.8,s.h*1.05,0,s.w*.8,s.h*1.05,s.h*.9);glow.addColorStop(0,'rgba(143,120,255,.22)');glow.addColorStop(1,'rgba(143,120,255,0)');c.fillStyle=glow;c.fillRect(0,0,s.w,s.h);
    for(const st of s.stars){const a=.35+.65*Math.abs(Math.sin(t/1000*st.sp+st.p));c.fillStyle=`rgba(230,236,255,${(a*.8).toFixed(3)})`;c.fillRect(st.x,st.y,st.r,st.r);}
    // Mystify-like glowing dots that draw soft curved trails.
    for(const d of s.drift){d.a+=d.sa*dt;d.b+=d.sb*dt;const x=s.w*(.5+.42*Math.sin(d.a)*Math.cos(d.b*.7)),y=s.h*(.5+.4*Math.sin(d.b)*Math.cos(d.a*.6));d.trail.push([x,y]);if(d.trail.length>90)d.trail.shift();
     c.lineCap='round';for(let i=1;i<d.trail.length;i++){const f=i/d.trail.length;c.strokeStyle=`hsla(${d.hue},90%,72%,${(f*.35).toFixed(3)})`;c.lineWidth=f*2.2;c.beginPath();c.moveTo(...d.trail[i-1]);c.lineTo(...d.trail[i]);c.stroke();}
     c.fillStyle=`hsla(${d.hue},100%,85%,.9)`;c.beginPath();c.arc(x,y,1.8,0,7);c.fill();}
    if(t>s.next){s.next=t+rnd(500,1600);const ang=rnd(.35,.6),sp=rnd(520,900);s.comets.push({x:rnd(-s.w*.1,s.w*.9),y:rnd(-s.h*.2,s.h*.35),vx:Math.cos(ang)*sp,vy:Math.sin(ang)*sp,life:0,max:rnd(.9,1.6),hue:[210,190,300,45][Math.floor(rnd(0,4))]});}
    s.comets=s.comets.filter(m=>m.life<m.max);for(const m of s.comets){m.life+=dt;m.x+=m.vx*dt;m.y+=m.vy*dt;const fade=Math.sin(Math.PI*m.life/m.max),len=.16;
     const tx=m.x-m.vx*len,ty=m.y-m.vy*len,gr=c.createLinearGradient(m.x,m.y,tx,ty);gr.addColorStop(0,`hsla(${m.hue},100%,92%,${fade})`);gr.addColorStop(1,`hsla(${m.hue},100%,70%,0)`);
     c.strokeStyle=gr;c.lineWidth=1.8;c.beginPath();c.moveTo(m.x,m.y);c.lineTo(tx,ty);c.stroke();c.fillStyle=`rgba(255,255,255,${fade})`;c.beginPath();c.arc(m.x,m.y,1.6,0,7);c.fill();}}
  },
  wave:{
   init(s){s.lines=24;},
   draw(s,c,t){const g=c.createLinearGradient(0,0,0,s.h);g.addColorStop(0,'#03121c');g.addColorStop(1,'#062a3a');c.fillStyle=g;c.fillRect(0,0,s.w,s.h);
    const T=t/1000;for(const [band,hue,base,amp] of [[0,195,.42,.16],[1,170,.62,.12],[2,220,.78,.09]]){
     for(let i=0;i<s.lines;i++){const f=i/s.lines;c.beginPath();for(let x=0;x<=s.w+10;x+=10){const u=x/s.w;
       const y=s.h*(base+amp*Math.sin(u*5.2+T*(.35+band*.12)+f*1.7)*Math.cos(u*1.6-T*.2+band)+f*.07+.02*Math.sin(u*14+T*1.3+f*3));x?c.lineTo(x,y):c.moveTo(x,y);}
      c.strokeStyle=`hsla(${hue+f*30},85%,${55+f*20}%,${(.05+.22*Math.sin(Math.PI*f)).toFixed(3)})`;c.lineWidth=1.1;c.stroke();}}
    const sh=c.createRadialGradient(s.w*.3,s.h*.3,0,s.w*.3,s.h*.3,s.w*.6);sh.addColorStop(0,'rgba(79,209,255,.10)');sh.addColorStop(1,'rgba(79,209,255,0)');c.fillStyle=sh;c.fillRect(0,0,s.w,s.h);}
  },
  coder:{
   init(s){const size=15;s.size=size;s.cols=Array.from({length:Math.ceil(s.w/size)},()=>({y:rnd(-s.h,s.h),sp:rnd(40,120),len:Math.round(rnd(8,26)),seed:Math.floor(rnd(0,1e6))}));
    s.glyphs='01{}[]()<>=+-*/;:#$&|!?abcdefxyzλ→⌘';s.lines=Array.from({length:7},()=>({y:rnd(.15,.9),x:rnd(.05,.6),txt:'',full:['const orbit = new Agent()','for (task of queue) run(task)','await model.think(prompt)','if (idle) improve()','git commit -m "ship it"','export default workshop','return ideas.filter(good)'][Math.floor(rnd(0,7))],at:0}));},
   draw(s,c,t,dt){c.fillStyle='#050b08';c.fillRect(0,0,s.w,s.h);c.font=`${s.size-2}px ui-monospace,SFMono-Regular,Menlo,monospace`;c.textBaseline='top';
    for(let i=0;i<s.cols.length;i++){const col=s.cols[i];col.y+=col.sp*dt;if(col.y-col.len*s.size>s.h){col.y=rnd(-200,0);col.sp=rnd(40,120);col.len=Math.round(rnd(8,26));}
     for(let j=0;j<col.len;j++){const y=col.y-j*s.size;if(y<-s.size||y>s.h)continue;const ch=s.glyphs[(col.seed+j*7+Math.floor(t/(j?900:140)))%s.glyphs.length];
      c.fillStyle=j===0?'rgba(170,255,205,.85)':`rgba(70,200,130,${(.28*(1-j/col.len)).toFixed(3)})`;c.fillText(ch,i*s.size,y);}}
    c.font='13px ui-monospace,SFMono-Regular,Menlo,monospace';for(const l of s.lines){l.at+=dt;const n=Math.min(l.full.length,Math.floor(l.at*14));l.txt=l.full.slice(0,n);
     if(l.at>l.full.length/14+4){l.at=0;l.y=rnd(.12,.9);l.x=rnd(.04,.6);}c.fillStyle='rgba(200,255,225,.16)';c.fillText('› '+l.txt+(Math.floor(t/500)%2?'▍':''),l.x*s.w,l.y*s.h);}
    const v=c.createRadialGradient(s.w/2,s.h/2,s.h*.2,s.w/2,s.h/2,s.w*.75);v.addColorStop(0,'rgba(0,0,0,0)');v.addColorStop(1,'rgba(0,0,0,.55)');c.fillStyle=v;c.fillRect(0,0,s.w,s.h);}
  },
  campfire:{
   init(s){s.embers=[];s.bokeh=Array.from({length:14},()=>({x:rnd(0,s.w),y:rnd(s.h*.2,s.h),r:rnd(18,60),p:rnd(0,6.3),sp:rnd(.2,.5)}));},
   draw(s,c,t,dt){const T=t/1000;const g=c.createLinearGradient(0,0,0,s.h);g.addColorStop(0,'#0b0705');g.addColorStop(.6,'#1a0f09');g.addColorStop(1,'#2a1408');c.fillStyle=g;c.fillRect(0,0,s.w,s.h);
    const flick=.75+.12*Math.sin(T*7.3)+.08*Math.sin(T*13.1+1)+.05*Math.sin(T*23.7);
    const fire=c.createRadialGradient(s.w*.5,s.h*1.08,0,s.w*.5,s.h*1.08,s.h*.95*flick);fire.addColorStop(0,'rgba(255,170,70,.75)');fire.addColorStop(.35,'rgba(255,110,40,.32)');fire.addColorStop(1,'rgba(255,90,30,0)');c.fillStyle=fire;c.fillRect(0,0,s.w,s.h);
    c.globalCompositeOperation='lighter';
    for(const b of s.bokeh){const a=.05+.04*Math.sin(T*b.sp+b.p);const gr=c.createRadialGradient(b.x,b.y,0,b.x,b.y,b.r);gr.addColorStop(0,`rgba(255,180,90,${a.toFixed(3)})`);gr.addColorStop(1,'rgba(255,180,90,0)');c.fillStyle=gr;c.fillRect(b.x-b.r,b.y-b.r,b.r*2,b.r*2);b.y-=dt*6;if(b.y<-b.r){b.y=s.h+b.r;b.x=rnd(0,s.w);}}
    if(s.embers.length<Math.round(s.w/5))s.embers.push({x:s.w*(.5+rnd(-.28,.28)),y:s.h+5,vy:rnd(28,80),ph:rnd(0,6.3),life:0,max:rnd(3,7),r:rnd(1.1,3)});
    s.embers=s.embers.filter(e=>e.life<e.max&&e.y>-10);for(const e of s.embers){e.life+=dt;e.y-=e.vy*dt;e.x+=Math.sin(T*1.7+e.ph)*14*dt;const a=Math.max(0,1-e.life/e.max)*(.6+.4*Math.sin(T*9+e.ph));
     c.fillStyle=`rgba(255,${Math.round(150+80*(1-e.life/e.max))},80,${a.toFixed(3)})`;c.beginPath();c.arc(e.x,e.y,e.r,0,7);c.fill();}
    c.globalCompositeOperation='source-over';}
  }
 };
 const layers=[];let raf=0,last=0;
 const theme=()=>document.documentElement.dataset.theme;
 const active=()=>THEMES.includes(theme());
 const still=()=>document.documentElement.dataset.motion==='off'||matchMedia('(prefers-reduced-motion: reduce)').matches;
 function mount(host){if(!host||host.querySelector(':scope>canvas.theme-motion'))return;const cv=document.createElement('canvas');cv.className='theme-motion';cv.setAttribute('aria-hidden','true');host.prepend(cv);layers.push({host,cv,s:null,key:''});}
 function size(L){const r=L.host.getBoundingClientRect(),dpr=Math.min(1.5,devicePixelRatio||1),w=Math.max(1,Math.round(r.width)),h=Math.max(1,Math.round(r.height)),key=theme()+w+'x'+h;
  if(key===L.key)return true;if(r.width<2||r.height<2)return false;L.key=key;L.cv.width=w*dpr;L.cv.height=h*dpr;L.cv.style.width=w+'px';L.cv.style.height=h+'px';L.s={w,h,dpr};SCENES[theme()].init(L.s);return true;}
 function draw(t,dt){for(const L of layers){if(!L.host.isConnected||!L.host.offsetParent)continue;if(!size(L))continue;const c=L.cv.getContext('2d');c.setTransform(L.s.dpr,0,0,L.s.dpr,0,0);SCENES[theme()].draw(L.s,c,t,dt);}}
 function loop(t){raf=requestAnimationFrame(loop);if(document.hidden||t-last<33)return;const dt=Math.min(.1,(t-(last||t))/1000);last=t;draw(t,dt);}
 function sync(){document.querySelectorAll('.command-atmosphere').forEach(mount);mount(document.getElementById('stationViewport'));
  cancelAnimationFrame(raf);raf=0;last=0;if(!active())return;
  if(still()){requestAnimationFrame(()=>{for(let i=0;i<40;i++)draw(performance.now()+i*33,.033);});return;}raf=requestAnimationFrame(loop);}
 new MutationObserver(sync).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme','data-motion']});
 addEventListener('resize',()=>{for(const L of layers)L.key='';if(active()&&still())sync();});
 // The chat backdrop is created when the chat opens: pick it up when it appears.
 let pending=0;new MutationObserver(()=>{if(pending)return;pending=setTimeout(()=>{pending=0;const fresh=[...document.querySelectorAll('.command-atmosphere')].some(h=>!h.querySelector(':scope>canvas.theme-motion'))||!document.querySelector('#stationViewport>canvas.theme-motion');if(fresh)sync();},700);}).observe(document.body,{childList:true,subtree:true});
 sync();
 return {THEMES,sync};
})();
