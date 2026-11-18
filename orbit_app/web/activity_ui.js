/* A minimal, always-on activity strip in the main chat (owner, 12 Nov): what ORBIT is doing right now, in every project. */
{
 const fmt=s=>{s=Math.max(0,Math.round(s||0));return s<60?s+' mp':s<3600?Math.floor(s/60)+' p':Math.floor(s/3600)+' ó '+Math.floor(s%3600/60)+' p';};
 let data=null,open=false,timer=null,busy=false;
 const host=document.querySelector('#commandApp .command-topline');
 if(host){
  const wrap=el('div','act-wrap'),pill=el('button','act-pill');pill.type='button';pill.setAttribute('aria-expanded','false');pill.setAttribute('aria-label','Mit csinál most az ORBIT');
  const panel=el('div','act-panel');panel.hidden=true;wrap.append(pill,panel);host.insertBefore(wrap,host.querySelector('.assistant-controls'));
  pill.onclick=e=>{e.stopPropagation();open=!open;panel.hidden=!open;pill.setAttribute('aria-expanded',String(open));draw();};
  document.addEventListener('click',e=>{if(open&&!wrap.contains(e.target)){open=false;panel.hidden=true;pill.setAttribute('aria-expanded','false');}});
  function draw(){
   const d=data;pill.replaceChildren();
   const dot=el('i','act-dot'+(d?.running?' live':''));pill.append(dot);
   if(!d){pill.append(el('span','','ORBIT'));return;}
   const top=d.items.find(i=>i.status==='running');
   const main=el('span','act-main',top?top.title:'Szabad');if(top?.project)main.title=top.project;pill.append(main);
   if(top?.stage)pill.append(el('span','act-stage',top.stage));
   const extra=d.running-(top?1:0)+d.queued;if(extra>0)pill.append(el('b','act-count','+'+extra));
   if(!open)return;
   panel.replaceChildren();
   if(!d.items.length)panel.append(el('p','act-empty','Most semmi nem fut és semmi nem vár. Az ORBIT szabad.'));
   for(const i of d.items){const r=el('div','act-row '+i.status);r.append(el('i','act-dot'+(i.status==='running'?' live':'')));
    const t=el('div','act-text');t.append(el('strong','',i.title),el('small','',[i.project,i.agent,i.stage].filter(Boolean).join(' · ')));
    r.append(t,el('span','act-time',i.status==='running'?fmt(i.seconds):'vár · '+fmt(i.seconds)));panel.append(r);}
   if(d.automations.length){panel.append(el('p','act-sub','Bekapcsolt automatizációk'));for(const a of d.automations)panel.append(el('p','act-auto','↻ '+a.name+(a.project?' · '+a.project:'')));}
  }
  // Polled on every page: the kobold in the header glows while anything runs (owner 12 Nov).
  async function poll(){
   clearTimeout(timer);
   if(!document.hidden&&!busy){busy=true;try{data=(await call('project_app',{op:'activity_now',args:{}})).result;}catch{}finally{busy=false;}
    document.documentElement.classList.toggle('orbit-busy',!!data?.running);
    const g=$('guardianTrigger');if(g)g.title=data?.running?'Az ORBIT dolgozik · '+(data.items.find(i=>i.status==='running')?.title||''):'';
    if(host.offsetParent!==null){draw();align();}}
   timer=setTimeout(poll,document.hidden?15000:data?.running?3000:6000);
  }
  // Under the kobold, wherever the header puts it (owner 12 Nov): the strip and the glow follow the kobold's real centre,
  // not the chat column's (the side menu shifts that one).
  const glow=el('span','kobold-glow');glow.setAttribute('aria-hidden','true');document.body.append(glow);
  function align(){
   // The kobold's button, not its picture: the picture slides up when it is opened, which moved the strip late (12 Nov).
   const g=$('guardianTrigger');if(!g)return;
   const r=g.getBoundingClientRect(),head=g.closest('header')?.getBoundingClientRect()||{top:0,bottom:80};
   const cx=r.left+r.width/2;
   // A back light: centred on the part of the kobold that is really visible, a little larger than the head, so it shines
   // around the silhouette from behind (owner 12 Nov).
   const pic=g.querySelector('img.g-peek')||g.querySelector('img'),p=pic?pic.getBoundingClientRect():r;
   const top=Math.max(head.top,p.top,0),bottom=Math.min(head.bottom||80,p.bottom),seen=Math.max(30,bottom-top);
   glow.style.left=cx+'px';glow.style.top=(top+seen*.55)+'px';glow.style.width=Math.round(Math.min(p.width,r.width)*1.15)+'px';glow.style.height=Math.round(seen*1.35)+'px';
   const line=host.getBoundingClientRect();
   if(host.offsetParent!==null&&line.width&&r.width){wrap.dataset.placed='1';
    const x=cx-line.left;wrap.style.left=x+'px';
    // Only the free room between the side label and the buttons: it never covers them.
    const label=host.querySelector('.eyebrow');let eb=null;if(label){const range=document.createRange();range.selectNodeContents(label);eb=range.getBoundingClientRect();}
    const ctl=host.querySelector('.assistant-controls')?.getBoundingClientRect();
    const room=2*Math.min(eb?cx-eb.right:x,ctl?ctl.left-cx:line.width-x)-24;
    wrap.style.maxWidth=Math.max(0,room)+'px';wrap.classList.toggle('narrow',room<300);wrap.style.visibility=room<90?'hidden':'';
   }
  }
  // Breathing: drifts smoothly between random levels at random speeds, so it never looks like a metronome.
  let level=.4,from=.4,to=.6,start=0,span=2200,last=0;
  const breathe=now=>{requestAnimationFrame(breathe);
   const busy=document.documentElement.classList.contains('orbit-busy'),still=document.documentElement.dataset.motion==='off'||matchMedia('(prefers-reduced-motion: reduce)').matches;
   if(!busy){glow.style.opacity='0';return;}
   if(still){glow.style.opacity='.45';return;}
   if(now-last<50)return;last=now;
   if(now-start>=span){from=level;to=.22+Math.random()*.6;start=now;span=1600+Math.random()*2800;}
   const u=Math.min(1,(now-start)/span),e=u*u*(3-2*u);level=from+(to-from)*e;
   glow.style.opacity=level.toFixed(3);glow.style.transform='translate(-50%,-50%) scale('+(.96+level*.08).toFixed(3)+')';};
  requestAnimationFrame(breathe);
  addEventListener('resize',align);const ro=new ResizeObserver(align);ro.observe(document.body);ro.observe(host);setInterval(align,2000);
  // The chat panel appearing (opening the kobold) places it in the same frame.
  new MutationObserver(()=>requestAnimationFrame(align)).observe($('commandApp'),{attributes:true,attributeFilter:['hidden','class','style']});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
  draw();setTimeout(poll,1500);setTimeout(align,300);
 }
}
