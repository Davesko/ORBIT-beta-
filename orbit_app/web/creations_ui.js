/* Alkotások page: goblin intro, truthful first steps and the project's folders.
   The existing gallery modal (showGallery) stays the place to browse files. */
(()=>{
 let busy=false,sig='';
 const FOLDER_TITLES={ready:'Kész videók',sources:'Források',transcripts:'Átiratok',production:'Gyártás',project:'Projektfájlok',creative:'Képek, kreatív',other:'Egyéb'};
 const shortsProject=()=>(state?.projects||[]).find(p=>/shorts/i.test(p.name))?.id||project;
 async function load(){
  if(busy||currentApp!=='creations')return;busy=true;
  try{
   const sp=shortsProject();
   const [gallery,pub,venture]=await Promise.all([
    call('gallery_list',{folder:null,offset:0}).catch(()=>null),
    call('publication_list',{requestProject:sp}).catch(()=>null),
    // Only the mission's status is shown here: the light head (0.1 s), not the full Autopilot view.
    call('enterprise_status',{scope:'business_lab',head:true}).catch(()=>null)]);
   const data={gallery,pub,venture:venture?.mission||null,models:state?.media_models||[],project:state?.project?.name,sp};
   const next=JSON.stringify([gallery?.counts,gallery?.project,pub?.connected,pub?.items?.length,pub?.style?.publish_to_youtube,pub?.style?.review_before_upload,data.venture?.status,data.models.map(m=>m.ready)]);
   if(next!==sig){sig=next;render(data);}
  }finally{busy=false;}
 }
 function step(n,done,text,action){
  const row=el('div','fs-step'+(done?' done':''));row.append(el('span','fs-mark',done?'✓':String(n)),el('span','fs-text',text));if(!done&&action)row.append(action);return row;
 }
 function render(d){
  const pane=$('creationsBody');if(!pane)return;pane.replaceChildren();
  const layout=el('div','ap-layout'),main=el('section','cr-main'),aside=el('aside','ap-aside');

  const intro=el('div','ap-card cr-intro'),img=el('img');img.src='assets/guardian-pixel-peek.png';img.alt='';img.className='cr-goblin';
  const t=el('div');t.append(el('h2','','Szia, én vagyok a koboldod'),el('p','','Fent középen mindig ott vagyok. Mutass rám bármelyik oldalon, és gyorsan kérhetsz tőlem videót, képet vagy állapotjelentést.'));intro.append(img,t);main.append(intro);

  const models=d.models.length>0&&d.models.every(m=>m.ready),yt=!!d.pub?.connected,video=(d.pub?.items||[]).length>0;
  const style=d.pub?.style||{},chosen=!!style.publish_to_youtube,auto=d.venture?.status==='active';
  const steps=[models,yt,video,chosen,auto],doneCount=steps.filter(Boolean).length;
  const card=el('div','ap-card');const head=el('div','ap-row');head.append(el('h2','','Első lépések'),el('b','',doneCount+' / 5 kész'));card.append(head);
  const bar=el('div','fs-bar');bar.setAttribute('aria-hidden','true');for(const s of steps)bar.append(el('span',s?'on':''));card.append(bar);
  const go=(label,fn)=>button(label,fn,'secondary');
  card.append(step(1,models,'Helyi AI modellek telepítve',go('Modellek',()=>$('navModels').click())));
  card.append(step(2,yt,'YouTube-fiók összekapcsolva',go('Kapcsolatok',()=>$('navConnections').click())));
  card.append(step(3,video,'Első videó elkészült',go('Videó kérése',()=>{switchApp('home');const i=$('commandInput');i.value='Készíts egy YouTube Shorts videót ';i.focus();})));
  card.append(step(4,chosen,'Döntsd el, mi történjen a kész videókkal'));
  card.append(step(5,auto,'Kapcsold be az autopilótát, és hagyd dolgozni',go('Megnyitás',()=>switchApp('autopilot'))));
  main.append(card);

  const mode=style.publish_to_youtube?(style.review_before_upload!==false?'review':'auto'):'local';
  const fs=el('fieldset','ap-card cr-modes');fs.append(el('legend','','Mi történjen a kész videókkal?'+(d.sp?' · '+((state?.projects||[]).find(p=>p.id===d.sp)?.name||''):'')));
  const grid=el('div','cr-mode-grid');
  for(const [value,title,desc] of [['review','Előbb megnézem','Feltöltés csak a jóváhagyásod után.'],['auto','Töltse fel magától','Nyilvános feltöltés ellenőrzés után.'],['local','Csak mentse el','A videók a gépen maradnak.']]){
   const label=el('label','cr-mode'+(value===mode?' on':'')),input=el('input');input.type='radio';input.name='crMode';input.value=value;input.checked=value===mode;
   input.onchange=()=>act(async()=>{await call('publication_settings',{mode:value,requestProject:d.sp});sig='';toast('Mentve a projekt új gyártásaihoz.');await load();});
   const txt=el('span');txt.append(el('strong','',title),el('small','',desc));label.append(input,txt);grid.append(label);
  }
  fs.append(grid);main.append(fs);

  const folders=el('div','ap-card');const fh=el('div','ap-row');fh.append(el('h2','','Alkotások'),el('b','',d.project||''));folders.append(fh,el('p','hint','A kiválasztott projekt mappái. A fejlécben válthatsz projektet.'));
  const fg=el('div','cr-folders'),counts=d.gallery?.counts||{};
  for(const [key,title] of Object.entries(FOLDER_TITLES)){const n=counts[key]||0;if(!n&&key!=='ready')continue;const b=el('button','cr-folder');b.append(el('strong','',title),el('small','',n+' fájl'));b.onclick=()=>act(()=>showGallery(key));fg.append(b);}
  folders.append(fg,button('↗ Összes alkotás',()=>act(()=>showGallery()),'secondary'));aside.append(folders);

  const office=el('button','ap-card cr-office');const oi=el('img');oi.src='assets/workshop/desk-editing.png';oi.alt='';office.append(oi,el('strong','','Ügynökök · pixel-iroda'),el('small','','Szobák, ügynökök, összekötés, folyamat indítása'));office.onclick=()=>switchApp('agents');aside.append(office);
  const tip=el('div','ap-card');tip.append(el('p','hint','Napokig tartó futáshoz tartsd töltőn a Macet, és ne csukd le a fedelét. Az ORBIT jelez, ha kevés a hely.'));aside.append(tip);

  layout.append(main,aside);pane.append(layout);
 }
 const baseSwitch=switchApp;
 switchApp=function(view){
  baseSwitch(view);
  const on=view==='creations';$('creationsApp').hidden=!on;
  $('navCreations').classList.toggle('active',on);$('navCreations').setAttribute('aria-pressed',String(on));
  if(on){sig='';load();}
 };
 $('navCreations').onclick=()=>switchApp('creations');
 $('projectSelect').addEventListener('change',()=>{sig='';setTimeout(load,200);});
 setInterval(load,6000);
})();
