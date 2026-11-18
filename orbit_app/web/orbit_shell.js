/* ORBIT 3 shell: Autopilot view, goblin hides when the pointer leaves the window, disk chip. */
(()=>{
 const baseSwitch=switchApp;
 switchApp=function(view){
  baseSwitch(view);
  const on=view==='autopilot';
  $('autopilotApp').hidden=!on;
  $('navAutopilot').classList.toggle('active',on);$('navAutopilot').setAttribute('aria-pressed',String(on));
  if(on)openVenture();
 };
 $('navAutopilot').onclick=()=>switchApp('autopilot');

 // When the quick chat closes the goblin plays its sinking scene instead of vanishing.
 const goblin=$('guardianTrigger');let wasAwake=goblin.classList.contains('awake');
 new MutationObserver(()=>{
  const awake=goblin.classList.contains('awake');
  if(awake===wasAwake)return;
  wasAwake=awake;
  // classList.add/remove rewrite the attribute even when nothing changes, which re-triggers this
  // observer; touch the class only when it really has to change, or the page loops forever.
  const sinking=goblin.classList.contains('sinking');
  if(!awake&&!sinking)goblin.classList.add('sinking');
  if(awake&&sinking)goblin.classList.remove('sinking');
 }).observe(goblin,{attributes:true,attributeFilter:['class']});
 goblin.addEventListener('animationend',e=>{if(e.animationName==='goblin-sink'&&goblin.classList.contains('sinking'))goblin.classList.remove('sinking');});
 // Blinking: every 5-7 s at random, sometimes twice in a row, like a living face. Web
 // Animations on the lids, so the observed goblin class never changes.
 const lids=goblin.querySelectorAll('.g-lid'),calm=matchMedia('(prefers-reduced-motion: reduce)');
 const blink=()=>lids.forEach(l=>l.animate([{transform:'scaleY(0)'},{transform:'scaleY(1)',offset:.4},{transform:'scaleY(1)',offset:.6},{transform:'scaleY(0)'}],{duration:170,easing:'ease-in-out'}));
 (function nextBlink(){
  setTimeout(()=>{
   if(!document.hidden&&!calm.matches){blink();if(Math.random()<.3)setTimeout(blink,260);}
   nextBlink();
  },5000+Math.random()*2000);
 })();
 // Leaving the window sends the goblin back to eyes-only unless the quick chat is pinned.
 document.documentElement.addEventListener('mouseleave',()=>{if(assistantOpen&&!assistantPinned)scheduleAssistantClose();});

 const gb=1024**3;
 function renderStorage(){
  const usage=state?.resources;let meter=$('resourceChip');if(!meter&&$('storageChip')){meter=document.createElement('span');meter.id='resourceChip';meter.className='resource-chip';$('storageChip').after(meter);}if(meter){meter.dataset.level=usage?.level||'unknown';meter.textContent=typeof usage?.cpu_percent==='number'?'● CPU '+usage.cpu_percent+'% · RAM '+(usage.memory_bytes/1024**3).toFixed(1)+' GB':'● Erőforrás: nincs mérés';meter.title='ORBIT és médiamotorok becsült folyamat-terhelése. A CPU a teljes gép kapacitásához viszonyított.';}

  const chip=$('storageChip'),info=typeof state==='object'&&state?state.storage:null;
  if(!chip)return;
  if(!info||typeof info.free_bytes!=='number'){chip.hidden=true;return;}
  const free=info.free_bytes/gb;
  chip.hidden=false;chip.textContent=(free>=10?Math.round(free):free.toFixed(1))+' GB szabad';
  chip.classList.toggle('critical',!!info.admission_paused);chip.classList.toggle('low',!info.admission_paused&&free<10);
  chip.title=info.admission_paused?'Kevés a hely: új gyártás és ciklus csak felszabadítás után indul.':'Szabad lemezhely';
  // Self-healing: show the last automatic repair for an hour.
  const h=state.health,ev=h?.recent&&h.last_event;
  chip.classList.toggle('healed',!!ev);
  if(ev){chip.textContent='🛠 '+chip.textContent;chip.title+='\nAutomatikus javítás '+new Date(ev.at*1000).toLocaleTimeString('hu-HU',{hour:'2-digit',minute:'2-digit'})+': '+ev.text;}
 }
 setInterval(renderStorage,5000);setTimeout(renderStorage,1500);

 // Owner-only fixes (a lost YouTube login) as a warning chip next to the disk chip.
 async function openYouTubeFor(pid){if(pid!==project)await changeProject(pid);$('modal').open&&$('modal').close();showYouTube();}
 function renderAttention(){
  const disk=$('storageChip');if(!disk)return;
  let chip=$('attentionChip');
  if(!chip){chip=document.createElement('button');chip.type='button';chip.id='attentionChip';chip.className='storage-chip attention-chip';disk.after(chip);
   chip.onclick=()=>{const items=(state?.attention)||[];if(items.length===1)return openYouTubeFor(items[0].project);
    const body=el('div','ap-detail');for(const a of items){body.append(el('p','',a.name+': '+a.text),button('YouTube újracsatlakoztatása · '+a.name,()=>openYouTubeFor(a.project),'secondary'));}
    showModal('Teendő',body);};}
  const items=(typeof state==='object'&&state?.attention)||[];
  chip.hidden=!items.length;if(!items.length)return;
  chip.textContent='⚠ YouTube: újracsatlakozás'+(items.length>1?' ('+items.length+')':'');
  chip.title=items.map(a=>a.name+': '+a.text).join('\n');
 }
 setInterval(renderAttention,5000);setTimeout(renderAttention,1600);
})();

/* Workshop map: the three layout controls sit on the map itself as small buttons. */
(function(){
 function sync(){
  const move=document.querySelector('.map-tools [data-tool="move"]');if(!move)return;
  const on=typeof editLayout!=='undefined'&&editLayout;
  move.setAttribute('aria-pressed',String(on));move.classList.toggle('on',on);
  move.querySelector('span').textContent=on?'Kész':'Áthelyezés';
 }
 function tool(id,icon,label,title,fn){
  const b=document.createElement('button');b.type='button';b.dataset.tool=id;b.title=title;b.setAttribute('aria-label',title);
  const i=document.createElement('i');i.textContent=icon;i.setAttribute('aria-hidden','true');const t=document.createElement('span');t.textContent=label;
  b.append(i,t);b.onclick=e=>{e.stopPropagation();fn();sync();};return b;
 }
 function mount(){
  const vp=$('stationViewport');if(!vp||vp.querySelector('.map-tools'))return;
  const bar=document.createElement('div');bar.className='map-tools';bar.setAttribute('role','toolbar');bar.setAttribute('aria-label','Műhely elrendezése');
  bar.append(
   tool('rooms','▱','Szobák','Szobák mérete, színe és berendezése',()=>showRooms()),
   tool('move','⤢','Áthelyezés','Szobák áthelyezése húzással – kattints újra, ha kész',()=>{editLayout=!editLayout;updateMapHint();toast(editLayout?'Húzd a szobákat a helyükre, majd kattints a Kész gombra.':'Az elrendezés mentve.');}),
   tool('looks','☺','Karakterek','Az ügynökök kinézete és a háttér',()=>showAppearance()));
  vp.append(bar);sync();
 }
 document.addEventListener('keydown',e=>{if(e.key==='Escape')setTimeout(sync,0);});
 setInterval(()=>{mount();sync();},1000);setTimeout(mount,300);
})();
