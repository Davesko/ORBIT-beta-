/* Autopilot page: one app-wide durable business workspace, independent from current project. */
let ventureState=null,ventureBusy=false,ventureSig='',ventureSel=null,ventureProject=null,ventureProjectSig='',ventureProjectAt=0;
const ventureMetricsAt=new Map();
let ventureMetricsPending=false;
function refreshVentureMetrics(id){
 const key=id||'revenue';
 if(ventureMetricsPending||Date.now()-(ventureMetricsAt.get(key)||0)<3600000)return;
 ventureMetricsAt.set(key,Date.now());ventureMetricsPending=true;
 call('enterprise_status',{scope:'business_lab',refresh_metrics:true,idea_id:id}).catch(()=>{}).finally(()=>{ventureMetricsPending=false;});
}
let ventureHead,ventureHeadRequest=0,ventureHeadBusy=false,ventureHeadSig='',ventureDetailAt=0,ventureDetailReady=false;
let ventureDetailError='',ventureHeadError='',ventureToggling=false;
async function refreshVentureHead(force=false){
 if((ventureHeadBusy&&!force)||currentApp!=='autopilot')return;
 const request=++ventureHeadRequest;ventureHeadBusy=true;
 try{
  const r=await call('enterprise_status',{scope:'business_lab',head:true});
  if(request!==ventureHeadRequest)return;
  const m=r.mission;
  const sig=JSON.stringify(m&&[m.status,m.next_run,m.run,m.paused_for_video,m.waiting_for_ssd,m.steps.map(s=>[s.node,s.state])]);
  const changed=sig!==ventureHeadSig;
  if(changed&&ventureHead!==undefined)ventureDetailAt=0;
  ventureHead=r.mission;
  if(changed||ventureHeadError){ventureHeadSig=sig;ventureHeadError='';if(currentApp==='autopilot')renderVenture();}
 }catch(e){if(request===ventureHeadRequest){ventureHeadError=e.message;if(currentApp==='autopilot'&&ventureHead===undefined)renderVenture();}}
 finally{if(request===ventureHeadRequest)ventureHeadBusy=false;}
}
async function loadVenture(force=false){
 if(ventureBusy||currentApp!=='autopilot'||(!force&&Date.now()-ventureDetailAt<30000))return;
 ventureBusy=true;ventureDetailAt=Date.now();
 try{
  const r=await call('enterprise_status',{scope:'business_lab',compact:true});
  ventureState=r.mission;ventureDetailReady=true;
  const sig=JSON.stringify(r.mission);
  if(sig!==ventureSig||ventureDetailError){ventureSig=sig;ventureDetailError='';if(currentApp==='autopilot')renderVenture();}
  if(currentApp!=='autopilot')return;
  if(ventureSel?.kind==='project'&&Date.now()-ventureProjectAt>30000)loadProject();
  const current=ventureSel?.kind==='project'?ventureSel.id:ventureState?.focus?.idea_id;
  loadEtsy(current);refreshVentureMetrics(current);
 }catch(e){ventureDetailError=e.message;if(currentApp==='autopilot')renderVenture();}
 finally{ventureBusy=false;}
}
function openVenture(){
 renderVenture();refreshVentureHead();loadVenture();
}
/* Any earlier project or research can be opened in place of the current build; null goes back to it. */
function openProject(id){
 ventureSel=id&&id!==ventureState?.focus?.idea_id?{kind:'project',id}:null;ventureProject=null;ventureProjectSig='';ventureProjectAt=0;
 renderVenture();$('autopilotApp')?.scrollTo({top:0,behavior:'smooth'});
 if(ventureSel)loadProject();
}
function openResearch(it){ventureSel={kind:'idea',name:it.name};ventureProject=null;renderVenture();$('autopilotApp')?.scrollTo({top:0,behavior:'smooth'});}
async function loadProject(){
 const id=ventureSel?.id;if(!id)return;ventureProjectAt=Date.now();
 try{const r=await call('enterprise_status',{scope:'business_lab',idea_id:id});const sig=JSON.stringify(r.project);if(ventureSel?.id===id&&sig!==ventureProjectSig){ventureProjectSig=sig;ventureProject=r.project;renderVenture();}}
 catch(e){if(ventureSel?.id===id){ventureProject={error:e.message};renderVenture();}}
}
function workTime(seconds){const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60);return h?h+' óra '+m+' perc':seconds<60?'kevesebb mint 1 perc':m+' perc';}
const WORK_PART={research:'kutatás',build:'építés',review:'ellenőrzés',drawing:'rajzolás'};
function workLine(w){if(!w?.total)return null;const box=el('div','ap-work');box.title='A feladatok tényleges futási ideje, a sorban várakozás nélkül';
 const head=el('div','ap-work-head');head.append(el('strong','','⏱ '+workTime(w.total)),el('span','','ennyit dolgozott ezen a projekten az AI'));if(w.running)head.append(el('span','ap-work-now','most is dolgozik'));box.append(head);
 const parts=Object.entries(w.parts||{}).sort((a,b)=>b[1]-a[1]).map(([k,v])=>(WORK_PART[k]||k)+' '+workTime(v)+(k==='drawing'&&w.drawn?' ('+w.drawn+' kép)':''));if(parts.length)box.append(el('small','',parts.join(' · ')));return box;}
function ventureDuration(seconds){const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60);return h?h+' óra '+m+' perce':m+' perce';}
const TYPE_HU={toolkit:'Bővítmény vagy sablon',saas:'Automatizált szoftver',service:'Szolgáltatás',dropshipping:'Dropshipping',trading:'Kereskedési stratégia',digital:'Digitális termék'};
const STEP_NOW={research:['Tervező','megtervezi a következő lépést'],build:['Építő','elkészíti a fájlokat'],review:['Tesztelő','ellenőrzi az eredményt']};
function ventureNow(m){
 if(!m)return ['Kikapcsolva','Kapcsold be, vagy írd a fő chatbe: „Indítsd el az autopilótát”.'];
 if(m.status!=='active')return ['Szünetel','A munka mentve, innen folytatja. Indítás: a gombbal vagy a fő chatben.'];
 if(m.paused_for_video)return ['Vár','Videógyártás fut; utána pontosan innen folytatja.'];
 if(m.waiting_for_ssd)return ['Vár','A modelleket tároló SSD nem válaszol, ezért nem indít új lépést; amint elérhető, innen folytatja. Teendő: Kiadás, a kábel ki és vissza; ha nem segít, a Mac újraindítása.'];
 const st=(m.steps||[]).find(x=>['waiting','dispatching'].includes(x.state));
 const cm=m.cycle_mode||'',kept=cm.startsWith('maintain:')?(m.portfolio||[]).find(p=>p.idea_id===cm.slice(9)):null;
 const what=kept?'a kész „'+kept.name+'” továbbfejlesztésén':cm==='explore'?'új, teljesen automatizált ötletek felkutatásán':m.focus?'„'+m.focus.name+'” megvalósításán':'új, teljesen automatizált ötletek felkutatásán';
 if(st){const [who,doing]=STEP_NOW[st.node]||[st.node,'dolgozik'];return ['Dolgozik',who+' '+doing+' – '+what+'.'];}
 return ['Dolgozik','A következő kör hamarosan indul'+(m.next_run?' ('+new Date(m.next_run*1000).toLocaleTimeString('hu-HU',{hour:'2-digit',minute:'2-digit'})+')':'')+'.'];
}
function shortName(name){return String(name||'').split(/\s+[–-]\s+/)[0];}
const ventureFolders=new Set(['activity']);
function ventureFolder(key,title,content){
 const folder=el('details','venture-folder');folder.open=ventureFolders.has(key);
 folder.ontoggle=()=>folder.open?ventureFolders.add(key):ventureFolders.delete(key);
 folder.append(el('summary','',title),content);return folder;
}
function ventureChat(idea=null,start=false){
 commandWorkspace=null;updateAttachment();
 switchApp('home');
 const input=$('commandInput');
 const prefix=start?'Autopilóta indítása · ':idea?'Autopilóta irány · projekt '+idea+': ':'Autopilóta irány · következő projekt: ';
 if(input.value.trim()&&!input.value.startsWith(prefix)){toast('A meglévő chatpiszkozatod megmaradt.');input.focus();return;}
 input.value=prefix;input.focus();input.setSelectionRange(input.value.length,input.value.length);
}
async function openVentureWorkshop(f){
 const {result}=await call('project_app',{op:'workspace_import',args:{idea_id:f.idea_id}});
 await changeProject(result.project);switchApp('agents');setProjectView(true);
}
function renderVenture(){
 const pane=$('businessLabPanel');if(!pane)return;
 pane.replaceChildren();
 const m=ventureState,known=ventureHead!==undefined||ventureDetailReady;
 const live=ventureHead===undefined?m:ventureHead&&{...m,...ventureHead};
 const active=live?.status==='active',page=el('div','ap-simple');
 const [state,line]=known?ventureNow(live):[ventureHeadError?'Állapot nem elérhető':'Betöltés…',ventureHeadError||'Kapcsolódás az Autopilótához.'];
 const top=el('section','ap-now'+(active?' on':''));
 const hero=el('div','venture-hero'),portrait=el('img','venture-goblin');
 portrait.src='assets/guardian-pixel-peek.png';portrait.alt='ORBIT kobold';
 const intro=el('div','venture-intro');
 intro.append(el('small','eyebrow','ORBIT / AUTOPILÓTA'),el('h1','','A kobold műhelye'),el('p','ap-now-line',line));
 hero.append(portrait,intro);top.append(hero);
 const head=el('div','ap-now-head'),badge=el('div','venture-state'),actions=el('div','venture-controls');
 badge.append(el('span','ap-dot'),el('strong','',state));
 const sw=button(active?'Leállítás':'Indítás',async()=>{
  ventureToggling=true;
  try{
   await call('enterprise_save',{settings:{scope:'business_lab',enabled:!active}});
   await refreshVentureHead(true);ventureDetailAt=0;loadVenture(true);
   toast(active?'Az Autopilóta leállt, a munka mentve.':'Az Autopilóta dolgozik.');
  }finally{ventureToggling=false;if(currentApp==='autopilot')renderVenture();}
 },'primary');
 sw.disabled=!known||ventureToggling;sw.setAttribute('aria-pressed',String(active));
 const direction=button(active?'Irány megadása':'Indítás saját iránnyal',()=>ventureChat(null,!active),'secondary');
 direction.disabled=!known||ventureToggling;
 const today=button('Mai összefoglaló',async()=>{
  const r=await call('enterprise_status',{scope:'business_lab',day_summary:true});
  const box=el('div','ap-detail');box.append(el('pre','ap-day',r.text||'Nincs adat.'));showModal('Mai összefoglaló',box);
 },'secondary');
 actions.append(sw,direction,today);head.append(badge,actions);top.append(head);
 const track=el('ol','venture-track'),steps=new Map((live?.steps||[]).map(x=>[x.node,x.state]));
 for(const [key,label] of [['research','Kutatás'],['build','Építés'],['review','Ellenőrzés']]){
  const status=steps.get(key)||'',node=el('li',['waiting','dispatching'].includes(status)?'current':status==='done'?'complete':'');
  node.append(el('i','',status==='done'?'✓':String(track.children.length+1)),el('span','',label));track.append(node);
 }
 top.append(track);
 if(m?.next_direction)top.append(el('p','ap-notice','Következő projekt · '+m.next_direction));
 if(m?.explore_reason)top.append(el('p','ap-notice',m.explore_reason));
 const pc=m?.pace;
 if(pc){const st=pc.steps||{},parts=[['research','tervezés'],['build','építés'],['review','ellenőrzés']].filter(([k])=>st[k]!=null).map(([k,l])=>l+' '+fmtMin(st[k]));
  const line=el('p','hint ap-pace','Tempó az elmúlt '+pc.hours+' órában: '+pc.cycles+' kör, átlag '+pc.minutes+' perc/kör'+(parts.length?' · '+parts.join(' · '):''));
  const tk=Object.entries(pc.tokens||{});
  const hits=tk.reduce((n,[,v])=>n+(v.cache_hits||0),0),later=tk.reduce((n,[,v])=>n+(v.later_rounds||0),0);
  if(later)line.textContent+=' · gyorsítótár-találat: '+hits+'/'+later+' kör';
  if(tk.length)line.title='Mért tokenhasználat (legnagyobb bemenet / legnagyobb válasz):\n'+tk.map(([k,v])=>({research:'tervezés',build:'építés',review:'ellenőrzés'}[k]||k)+': '+v.max_prompt+' / '+v.max_output+(v.capped?' · '+v.capped+'× elérte a válaszkeretet':'')+(v.later_rounds?' · gyorsítótár: '+v.cache_hits+'/'+v.later_rounds+' kör':'')).join('\n');
  top.append(ventureFolder('pace','Mért munkaidő és modellhasználat',line));}
 page.append(top);
 if(!ventureDetailReady||ventureDetailError){
  const loading=el('section','ap-block venture-loading');
  loading.setAttribute('role','status');
  loading.append(el('p','hint',ventureDetailError?'A projektek betöltése: '+ventureDetailError:'A projektek és a munkanapló betöltése…'));
  if(ventureDetailError)loading.append(button('Újrapróbálás',()=>loadVenture(true),'secondary'));
  page.append(loading);
 }
 if(!ventureDetailReady){pane.append(page);return;}
 const strip=projectStrip(m);if(strip)page.append(strip);

 // Wide screens: the opened project on the left, the owner's to-dos and the ideas on the right.
 const main=el('div','ap-colmain'),side=el('div','ap-colside'),sel=ventureSel;
 let shown=null,feed=null;
 if(sel?.kind==='project'){
  main.append(viewingBanner(sel));
  if(!ventureProject)main.append(el('section','ap-block ap-loading','A projekt betöltése…'));
  else if(ventureProject.error)main.append(el('section','ap-block',ventureProject.error));
  else{shown=ventureProject;main.append(projectCard(ventureProject,false));if(ventureProject.idea)main.append(researchCard(ventureProject.idea,true));feed=projectFeed(ventureProject.cycles,'Mi történt ezen a projekten');}
 }else if(sel?.kind==='idea'){
  const it=(m?.ideas||[]).find(i=>i.name===sel.name);
  main.append(viewingBanner(sel));
  if(it){main.append(researchCard(it,false));if(it.idea_id&&it.saved!==false)main.append(button('Megnyitás a műhelyben',()=>openVentureWorkshop(it),'secondary'));feed=projectFeed((m.cycles||[]).filter(c=>it.cycles.includes(c.cycle)),'A kutatás körei','Ezek a körök ('+it.cycles.map(c=>c+'.').join(', ')+') régebbiek a legutóbbi 30-nál; a kutatás eredménye fent látható.');}
  else main.append(el('section','ap-block','Ez az ötlet már nem szerepel a listában.'));
 }else if(m?.focus){shown=m.focus;main.append(projectCard(m.focus,true));}
 if(shown?.owner_actions?.length){
  const f=shown,wait=el('section','ap-block ap-owner');wait.append(el('h2','','Rád vár · '+f.owner_actions.length),el('p','hint',(sel?'„'+shortName(f.name)+'” projekt. ':'')+'Ezeket az ORBIT nem csinálja meg helyetted (közzététel, fiók, fizetés, valódi pénz). Mindegyikhez kész vázlat tartozik.'));
  for(const a of f.owner_actions){const b=el('button','ap-row-btn');b.append(el('span','',(OWNER_KIND[a.kind]||'•')+' '+a.title+(a.count>1?' (×'+a.count+')':'')));b.onclick=()=>showOwnerAction(a,f);wait.append(b);}
  side.append(ventureFolder('owner:'+f.idea_id,'Teendők · '+f.owner_actions.length,wait));
 }
 if(!feed){
  feed=el('section','ap-block ap-feed-block');feed.append(el('h2','','Mi történt'));
  if(m?.feed?.length){
   const ol=el('ol','ap-feed');
   for(const item of m.feed.slice(0,25)){
    const c=(m.cycles||[]).find(x=>x.cycle===item.cycle);
    const li=el('li','ap-feed-item'+(item.status==='running'?' now':''));li.tabIndex=0;li.setAttribute('role','button');
    li.append(el('span','ap-feed-icon',item.icon),el('span','ap-feed-text',item.text),el('small','',ventureTime(item.at)));
    li.onclick=li.onkeydown=e=>{if(e.type==='keydown'&&!['Enter',' '].includes(e.key))return;e.preventDefault?.();if(c)showCycle(c);};
    ol.append(li);
   }
   feed.append(ol);
  }else feed.append(el('p','hint','Még nem történt semmi. Indítás után itt látod körről körre, mit csinált.'));
 }
 main.append(ventureFolder('activity','Munkanapló',feed));

 const ideas=el('section','ap-block ap-ideas-block');ideas.append(el('h2','','Megvizsgált ötletek · '+(m?.ideas?.length||0)),el('p','hint','Kattints egy ötletre: a kutatását, vagy ha már épült belőle valami, a teljes projektet nyitja meg.'));
 if(m?.ideas?.length){
  const built=new Map((m.projects||[]).map(p=>[p.idea_id,p]));
  for(const it of m.ideas){
   const p=it.idea_id&&built.get(it.idea_id),b=el('button','ap-row-btn');
   b.setAttribute('aria-pressed',String(sel?.kind==='idea'?sel.name===it.name:sel?.kind==='project'?sel.id===it.idea_id:!!m.focus&&m.focus.idea_id===it.idea_id));
   b.append(el('span','',it.name),el('span','ap-type',p?'📁 Projekt':TYPE_HU[it.business_type]||'Ötlet'),el('small','',(it.score?'⭐ '+it.score.total+'/25 '+(it.score.measured?'(mért) · ':'(becslés) · '):'még nincs pontozva · ')+it.cycles.length+' kör'+(m.focus?.idea_id===it.idea_id?' · most ezt építi':'')));
   b.onclick=()=>p?openProject(it.idea_id):openResearch(it);ideas.append(b);
  }
 }else ideas.append(el('p','hint','Az első kidolgozott ötlet után itt jelenik meg.'));
 ideas.append(el('p',m?.revenue?'ap-revenue':'hint',m?.revenue?'💶 Igazolt bevétel (Stripe): '+m.revenue:'Igazolt bevétel: még nincs. Ha bekötöd a Stripe-ot (csak olvasás) a Kapcsolatok oldalon, itt valódi szám jelenik meg.'));
 side.append(ventureFolder('ideas','Ötletek és bevételi adatok',ideas));
 page.append(main,side);
 pane.append(page);
}
function projectStrip(m){
 const list=m?.projects||[];if(!list.length)return null;
 const nav=el('nav','ap-projects');nav.setAttribute('aria-label','Projektek');
 const allWork=list.reduce((sum,p)=>sum+(p.work?.total||0),0);
 nav.append(el('h2','','Projektek · '+list.length+(allWork?' · összes munkaidő: '+workTime(allWork):'')));
 const row=el('div','ap-project-row'),open=ventureSel?.kind==='project'?ventureSel.id:ventureSel?null:m.focus?.idea_id;
 for(const p of list){
  const b=el('button','ap-project-tab '+p.state);b.setAttribute('aria-pressed',String(p.idea_id===open));b.title=p.name;
  const bar=el('div','ap-bar'),fill=el('i');fill.style.width=Math.round(100*p.done/Math.max(1,p.total))+'%';bar.append(fill);
  b.append(el('small','ap-project-state',p.state_label),el('strong','',shortName(p.name)),bar,el('small','',p.done+'/'+p.total+' lépés · '+p.cycles+' kör'+(p.last?' · '+ventureTime(p.last):'')));
  if(p.work)b.append(el('small','ap-project-work','⏱ '+workTime(p.work.total)+(p.work.running?' · most is dolgozik':'')));
  b.onclick=()=>openProject(p.idea_id);row.append(b);
 }
 nav.append(row);return nav;
}
function viewingBanner(sel){
 const box=el('div','ap-viewing'),cur=ventureState?.focus,p=sel.kind==='project'?ventureProject:null;
 const name=sel.kind==='project'?(p&&!p.error?p.name:(ventureState?.projects||[]).find(x=>x.idea_id===sel.id)?.name||''):sel.name;
 box.append(el('p','',(sel.kind==='project'?'Korábbi projektet nézel: „':'Kutatást nézel: „')+shortName(name)+'”.'+(cur?' Az Autopilóta közben a(z) „'+shortName(cur.name)+'” projekten dolgozik.':'')));
 const tools=el('div','ap-previews');
 tools.append(button('← Vissza a mostanihoz',()=>openProject(null),'secondary'));
 const it=sel.kind==='idea'?(ventureState?.ideas||[]).find(i=>i.name===sel.name):null,id=p&&!p.error&&!p.current?p.idea_id:it?.idea_id;
 if(id)tools.append(button(sel.kind==='project'?'▶︎ Az Autopilóta ezen dolgozzon':'▶︎ Valósítsa meg ezt az ötletet',()=>confirmFocus(id,name),'secondary'));
 box.append(tools);return box;
}
function confirmFocus(id,name){
 const box=el('div','ap-detail'),cur=ventureState?.focus;
 box.append(el('p','','Az Autopilóta a következő körtől a(z) „'+shortName(name)+'” projekten dolgozik'+(cur?'; a(z) „'+shortName(cur.name)+'” munkája mentve marad, és bármikor visszaválthatsz rá.':'.')),
  el('p','hint','Csak azt változtatja meg, min dolgozik. Nem tesz közzé semmit, és nem ír senkinek.'),
  button('Igen, váltson',async()=>{await call('enterprise_save',{settings:{scope:'business_lab',focus:id}});$('modal').close();ventureSig='';ventureSel=null;ventureProject=null;await loadVenture(true);renderVenture();toast('Az Autopilóta mostantól a(z) „'+shortName(name)+'” projekten dolgozik.');}));
 showModal('Váltás · '+shortName(name),box);
}
function projectCard(f,current){
 const card=el('section','ap-block ap-project-card');
 const h=el('div','ap-block-head');h.append(el('h2','',current?'Most ezt építi':(ventureState?.projects||[]).find(p=>p.idea_id===f.idea_id)?.state_label||'Projekt'),el('span','ap-type',f.type_label||'Szolgáltatás'));
 card.append(h,el('div','ap-idea',f.name));
 const tools=el('div','venture-primary-actions');
 tools.append(button('Megnyitás a műhelyben',()=>act(()=>openVentureWorkshop(f)),'primary'),button('Projekt iránya a chatben',()=>ventureChat(f.idea_id),'secondary'));
 card.append(tools);
 if(f.operator_direction)card.append(el('p','ap-notice','Mentett irány · '+f.operator_direction));
 const bar=el('div','ap-bar');const fill=el('i');fill.style.width=Math.round(100*f.done/Math.max(1,f.total))+'%';bar.append(fill);
 card.append(bar,el('p','hint',f.done+' / '+f.total+' lépés kész'));
 const wl=workLine(f.work);if(wl)card.append(wl);
 if(f.ready&&f.has_api)card.append(el('p','ap-ready','✅ A termék átment a saját öntesztjein és a helyi API-próbán'+(f.health?.real?', és a valós mintán '+f.health.real_ok+'/'+f.health.real+' kézzel ellenőrzött tétel egyezik':'')+' – kipróbálható a ▶︎ Kipróbálás gombbal. '+(f.health?.real?'':'Valódi adaton még nincs mérve; ')+'élesítés előtt nézd át, hogy az oldal csak azt ígéri-e, amit a kód tud.'));
 const hl=healthLine(f.health);if(hl)card.append(hl);
 if(current&&f.eta&&f.eta.text){const e=el('p','ap-eta','⏱ '+f.eta.text);e.title='Az ORBIT a feladatok mért idejéből számolja';card.append(e);}
 const tl=timelineBars(f.timeline);if(tl)card.append(tl);
 if(f.next)card.append(el('p','hint ap-next',(current?'Következő lépés: ':'Következő lépés, ha folytatja: ')+f.next.title+(f.next.fix?.length?' · javítandó: '+f.next.fix.map(x=>x==='smoke.json'?'élő próba':x).join(', '):'')));
 const chips=el('div','ap-chips');
 for(const ms of f.milestones){const [label,cls]=MS_STATE[ms.state]||MS_STATE.pending;const c=el('button','ap-chip '+cls,ms.title);c.title=label+' · '+ms.desc;c.onclick=()=>showMilestone(ms,f);chips.append(c);}
 card.append(chips);
 const results=el('div','venture-files');
 const meas=measureCard(f.measurements||{});if(meas)results.append(meas);
 const dg=designGallery(f.designs);if(dg)results.append(dg);
 const ey=etsyBlock(f);if(ey)results.append(ey);
 const pv=previewButtons(f);if(pv)results.append(pv);
 if(f.api_examples?.length)results.append(button('API kipróbálása',()=>showProductApi(f),'secondary'));
 results.append(folderButton(f));
 card.append(ventureFolder('files:'+f.idea_id,'Fájlok, előnézetek és tesztek',results));
 card.append(ventureFolder('launch:'+f.idea_id,'Közzététel és értékesítés',launchBlock(f)));
 if(current&&f.queue?.length)card.append(el('p','hint','Utána: '+f.queue.join(' · ')));
 return card;
}
function researchCard(it,collapsed){
 const box=el('section','ap-block ap-research');
 if(collapsed){const d=el('details');d.append(el('summary','','🔎 Az ötlet kutatása és üzleti terve'),ideaBlock(it));box.append(d);return box;}
 box.append(el('h2','','Kutatás · '+(TYPE_HU[it.business_type]||'Ötlet')),ideaBlock(it));
 return box;
}
function projectFeed(cycles,title,empty){
 const box=el('section','ap-block ap-feed-block');box.append(el('h2','',title+(cycles?.length?' · '+cycles.length+' kör':'')));
 if(!cycles?.length){box.append(el('p','hint',empty||'Ehhez még nincs mentett kör.'));return box;}
 const ol=el('ol','ap-feed');
 for(const c of cycles){
  const ms=c.milestone,text=ms?(ms.title||ms.milestone_id||'Építés')+' · '+(ms.status==='partial'?'részben kész':'elkészült'):c.idea?'Kutatás: '+c.idea.name:c.status==='running'?'Folyamatban':ventureBlocker(c);
  const li=el('li','ap-feed-item'+(c.status==='running'?' now':''));li.tabIndex=0;li.setAttribute('role','button');
  li.append(el('span','ap-feed-icon',ms?'🔨':c.idea?'🔎':c.status==='running'?'⏳':'⚠️'),el('span','ap-feed-text',c.cycle+'. kör · '+text),el('small','',ventureTime(c.finished||c.created)));
  li.onclick=li.onkeydown=e=>{if(e.type==='keydown'&&!['Enter',' '].includes(e.key))return;e.preventDefault?.();showCycle(c);};
  ol.append(li);
 }
 box.append(ol);return box;
}
const VENTURE_FIELDS=[['category','Kategória'],['problem','Probléma'],['offer','Automatizált megoldás'],['buyer','Célközönség'],['revenue_model','Bevételi modell (nem igazolt)'],['architecture','Architektúra'],['autonomy','Önellenőrzés és önjavítás'],['tech_stack','Technológia'],['costs','Futási költség'],['revenue_potential','Bevételi potenciál'],['validation','48 órás validáció'],['automation_level','Automatizáltság (%)'],['human_steps','Emberi lépések'],['hypothesis','Feltevés'],['progress','Mit javított'],['next_action','Következő lépés']];
const VENTURE_DECISION={continue:'Tovább fejleszti',pivot:'Irányt vált',ready_for_validation:'Valódi tesztre kész'};
function ventureTime(t){return t?new Date(t*1000).toLocaleString('hu-HU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';}
function ventureBlocker(c){
 const e=c.build?.error||c.error||'';
 if(/időkeret|nem válaszolt/i.test(e))return 'A helyi AI túl lassan válaszolt – később újrapróbálja.';
 if(/kapcsolódni/i.test(e))return 'A helyi AI épp nem volt elérhető.';
 if(/Hiányos üzleti terv/i.test(e))return 'A terv egy mezője hiányzott – a javított ellenőrzés ezt már elfogadja.';
 return e?e.slice(0,140):'Nem készült terv ebben a körben.';
}
function ideaBlock(it){
 const box=el('div','ap-detail');
 box.append(el('div','ap-idea',it.name));
 if(it.decision)box.append(el('p','hint',(VENTURE_DECISION[it.decision]||it.decision)+(it.cycles?' · '+it.cycles.map(c=>c+'.').join(', ')+' kör':'')+(it.saved===false?' · nem mentett vázlat (az ellenőrzés akkor elutasította)':'')));
 if(it.score?.note)box.append(el('p','ap-notice',it.score.note));
 if(it.score)box.append(el('p','hint','Kritikus pontszáma: '+it.score.total+'/25 · kereslet '+it.score.demand+', verseny '+it.score.competition+', haszon '+it.score.margin+', automatizálhatóság '+it.score.automation+', gyors tesztelhetőség '+it.score.speed+(it.score.solved?', már létező megoldás '+it.score.solved+'/5':'')+'. Építésre: legalább 15 pont (vagy több ötlet közül a legjobb, legalább 10), legalább 3-as automatizálhatóság, és ne oldja meg már ingyenes vagy hivatalos eszköz.'));
 if(it.names?.length>1)box.append(el('p','hint','Korábbi nevei: '+it.names.filter(n=>n!==it.name).join(' · ')));
 const dl=el('dl');
 for(const [k,label] of VENTURE_FIELDS)if(it[k]!==undefined&&it[k]!==null&&it[k]!==''&&!/^Még nincs meghatározva/.test(String(it[k])))dl.append(el('dt','',label),el('dd','',String(it[k])));
 box.append(dl);
 if(it.evidence?.length){box.append(el('h4','','Bizonyítékok'));const ul=el('ul');for(const x of it.evidence)ul.append(el('li','',x));box.append(ul);}
 for(const f of it.files||[]){
  if(typeof f==='string'){box.append(el('p','hint','📄 '+f.split('/').pop()));continue;}
  const d=el('details','ap-file');d.append(el('summary','','📄 '+f.name),el('pre','',f.preview||''));box.append(d);
 }
 return box;
}
const OWNER_KIND={money:'💰',publish:'🌐',account:'🔑',contact:'✉️',legal:'⚖️'};
const MS_STATE={skipped:['– kihagyva','done'],done:['✓ kész','done'],partial:['◐ részben','now'],revise:['↺ javítandó','error'],pending:['következő','']};
const VERDICT_HU={running:['⏳ A teszt fut','now'],passed:['✅ Átment','done'],failed:['❌ Nem ment át','error'],low_traffic:['⚠️ Kevés látogató','error']};
function launchBlock(f){
 const st=f.launch,box=el('div','ap-launch'+(st?.status==='live'?' live':''));
 if(f.has_api)box.append(el('p','hint','A Cloudflare-cím a termékbemutatót és az érdeklődők gyűjtését szolgálja. A nyilvános API-hoz külön szerver kell; helyben az API kipróbálása gombbal futtathatod.'));
 else if(f.type!=='digital')box.append(el('p','hint','Ez a projekt jelenleg webes ajánlatként nyitható meg. A termék használhatóságát a futtatható szolgáltatás és annak ellenőrzése igazolja.'));

 if(!f.previews?.length){box.append(el('p','hint',f.type==='digital'?'A termékeket a piactér adja el (nyomtat, fizettet, szállít): a kész grafikákat és a termékadatlapokat te töltöd fel a Feltöltési csomag szerint.':'Élesíteni akkor lehet, ha elkészült a weboldal (index.html).'));return box;}
 if(st?.status!=='live'){
  box.append(el('p','hint',st?.status==='stopped'?'Levéve. Az eddigi mérések és a várólista a Cloudflare-fiókodban megmaradtak.':'Még nincs élesítve.'));
  box.append(button('Bemutató közzététele',()=>confirmLaunch(f),'primary'));
  if(st?.stats)box.append(statsView(st));
  const rq=requestsView(f);if(rq)box.append(rq);
  if(f.traffic?.length)box.append(trafficView(f));return box;
 }
 const head=el('div','ap-launch-head');head.append(el('strong','','🟢 Élő bemutató'),el('code','ap-url',st.url));
 const copy=el('button','ap-chip','Cím másolása');copy.onclick=()=>{navigator.clipboard?.writeText(st.url);toast('A cím a vágólapon.');};head.append(copy);
 box.append(head);
 const up=f.live_update;
 if(up?.stale){const n=el('div','ap-stale');n.append(el('p','','⚠️ Az élő oldal régebbi változatot mutat ('+ventureTime(up.since)+'); azóta az Autopilóta továbbfejlesztette'+(up.changed?.length?': '+up.changed.join(', '):'')+'.'),button('🔄 Új változat élesítése',()=>confirmLaunch(f,true),'primary'));box.append(n);}
 box.append(statsView(st));
 const rq=requestsView(f);if(rq)box.append(rq);
 const tools=el('div','ap-previews');
 tools.append(button('Frissítés',async()=>{await call('enterprise_save',{settings:{scope:'business_lab',refresh_launch:f.idea_id}});ventureSig='';await loadVenture(true);},'secondary'),
  button('Leállítás',()=>{const b=el('div','ap-detail');b.append(el('p','','Leveszed a(z) „'+f.name+'” oldalát a netről? A mérések és a várólista a Cloudflare-fiókodban megmaradnak.'),button('Igen, leveszem',async()=>{await call('enterprise_save',{settings:{scope:'business_lab',unlaunch:f.idea_id}});$('modal').close();ventureSig='';await loadVenture(true);toast('Az oldal le van véve.');}));showModal('Leállítás',b);},'secondary'));
 box.append(tools,trafficView(f));return box;
}
function requestsView(f){
 if(!f.requests?.length)return null;
 const box=el('div','ap-requests');
 box.append(el('h3','','Kérések a várólistáról · '+f.requests.length),el('p','hint','Amit a látogatók kértek. A levelet az ORBIT előkészíti, elküldeni te tudod; az e-mail-címek csak ezen a gépen vannak.'));
 for(const r of f.requests){
  const a=(f.owner_actions||[]).find(x=>x.concierge===r.key),row=el('button','ap-row-btn');
  row.append(el('span','',r.site||'(nincs cím)'),el('span','ap-type',r.label),el('small','',r.src+' · '+ventureTime(r.at)+(r.email?' · '+r.email:'')));
  if(a)row.onclick=()=>showOwnerAction(a,f);else{row.disabled=true;row.title=r.status==='sent'?'Elküldve '+ventureTime(r.sent):'Nincs teendő';}
  box.append(row);
 }
 return box;
}
function designURL(id){return 'orbit-media://artifact/'+encodeURIComponent(id)+'?project=orbit-business-lab';}
function designGallery(d){
 if(!d?.items?.length)return null;
 const box=el('div','ap-designs');
 box.append(el('h3','','Grafikák · '+d.done+'/'+d.total+' kész'+(d.failed?' · '+d.failed+' nem sikerült':'')),
  el('p','hint','Az ORBIT a helyi képmodellel rajzolja meg őket, egyszerre egyet, amikor az Autopilóta épp nem használja a modellt.'+(d.book?' A színezőkből nyomtatható PDF-füzet is készült (designs/coloring-book.pdf).':'')));
 const grid=el('div','ap-design-grid');
 for(const x of d.items){
  const tile=el('figure','ap-design'+(x.done?' done':x.error?' bad':''));tile.title=x.title+' · '+x.kind+(x.error?'\n'+x.error:'');
  if(x.done&&x.artifact){const img=document.createElement('img');img.loading='lazy';img.alt=x.title;img.src=designURL(x.artifact);tile.append(img);tile.tabIndex=0;tile.onclick=()=>{const b=el('div','ap-preview');const big=document.createElement('img');big.className='ap-design-big';big.alt=x.title;big.src=designURL(x.artifact);b.append(big,el('p','hint',x.kind+' · nyomdakész PNG a designs mappában'));showModal(x.title,b);};}
  else tile.append(el('span','ap-design-wait',x.error?'⚠️':'⏳'));
  tile.append(el('figcaption','',x.title));grid.append(tile);
 }
 box.append(grid);return box;
}
function trafficView(f){
 const box=el('div','ap-traffic');
 if(!f.traffic?.length){box.append(el('p','hint','A forgalmi csomagot (csatornák, kész szövegek) a validációs lépés készíti el.'));return box;}
 const total=f.traffic.reduce((a,c)=>a+(c.budget_eur||0),0);
 // Folded: the ready-made posts made the live block ~1600 px tall on the full-width page.
 const d=el('details','ap-traffic-fold'),sum=el('summary');sum.append(el('h3','','Forgalom indítása · '+f.traffic.length+' csatorna'+(total?' · javasolt keret: '+total+' €':'')));d.append(sum);box.append(d);
 d.append(el('p','hint','Ezeket te indítod. A linkek forrásjelölést tartalmaznak, így a mérés csatornánként mutatja az eredményt.'));
 for(const c of f.traffic){
  const row=el('div','ap-channel');row.append(el('strong','',(c.type==='paid'?'💰 ':'📣 ')+c.name+(c.budget_eur?' · max. '+c.budget_eur+' €':'')));
  if(c.audience)row.append(el('small','',c.audience));
  row.append(el('pre','',c.copy+(c.link?'\n\n'+c.link:'')));
  const cp=el('button','ap-chip','Szöveg + link másolása');cp.onclick=()=>{navigator.clipboard?.writeText(c.copy+(c.link?'\n\n'+c.link:''));toast('Vágólapra másolva.');};row.append(cp);
  d.append(row);
 }
 return box;
}
function statsView(st){
 const s=st.stats,box=el('div','ap-measure');
 if(!s){box.append(el('p','hint','Az első mérés legfeljebb egy órán belül megjelenik.'));return box;}
 if(s.error){box.append(el('p','hint','A mérések lekérése most nem sikerült: '+s.error));return box;}
 const c=s.counts||{},v=s.verdict||{},[label]=VERDICT_HU[v.status]||['–'];
 const dl=el('dl');
 const buy=st.mode==='buy';
 const rows=[['Teszt',label+(v.hours!==undefined?' · '+v.hours+' órája':'')],['Látogatók',c.view||0]];
 if(!buy)rows.push(['Feliratkozók',(c.signup||0)+' ('+(v.signup_rate||0)+'%)']);
 rows.push(['Kattintás a gombokra',c.cta||0],[buy?'Kattintás a Megveszem gombra':'Kattintás fizetős csomagra',(c.paid||0)+' ('+(v.paid_rate||0)+'%)']);
 for(const [k,val] of rows)dl.append(el('dt','',k),el('dd','',String(val)));
 box.append(el('h3','','Valódi mérés'),dl);
 const src=Object.entries(s.sources||{});
 if(src.length)box.append(el('p','hint','Források: '+src.map(([n,x])=>n+' '+(x.view||0)+' látogató / '+(buy?(x.paid||0)+' vásárlási kattintás':(x.signup||0)+' feliratkozó')).join(' · ')));
 box.append(el('p','hint',buy?'Átmegy, ha legalább 100 látogatóból legalább 2% a Megveszem gombra kattint. A valódi eladást a Stripe-bevétel igazolja.':'Átmegy, ha legalább 100 látogatóból legalább 8% feliratkozik és legalább 2% a fizetős csomagra kattint.'));
 return box;
}
function confirmLaunch(f,update){
 const box=el('div','ap-detail');
 box.append(el('p','',update?'Az ORBIT a(z) „'+f.name+'” élő oldalát lecseréli a mostani változatra, ugyanazon a címen.':'Az ORBIT a(z) „'+f.name+'” weboldalát kiteszi a netre a Cloudflare-fiókodba (ingyenes csomag).'),
  el('ul'));
 const ul=box.lastChild;for(const t of update?['A cím és a mérések megmaradnak','Előtte nézd meg az új oldalt a ▶︎ Kipróbálás gombbal','A fizetést a vásárlási linked kezeli; az ORBIT nem küld senkinek üzenetet','Bármikor leveheted a Leállítás gombbal']:['Saját címet kap: …workers.dev','Kész termékoldal: a Megveszem gombok a vásárlási linkedre mutatnak, várólista nincs','Adatkezelési oldal és süti nélküli látogatás- és kattintásmérés','A fizetést a vásárlási linked kezeli; az ORBIT nem küld senkinek üzenetet','Bármikor leveheted a Leállítás gombbal'])ul.append(el('li','',t));
 // The owner's checkout link (Stripe Payment Link, Gumroad, a marketplace page); ORBIT points the buy buttons at it.
 const link=document.createElement('input');link.type='url';link.className='ap-input';link.placeholder='https://buy.stripe.com/… vagy a termék piactéri oldala';link.value=f.checkout||'';link.setAttribute('aria-label','Vásárlási link');
 const lab=el('label','ap-field');lab.append(el('span','','Vásárlási link (Stripe fizetési link, Gumroad vagy piactéri termékoldal)'),link);
 box.append(lab,el('p','hint','A link a te fiókodhoz tartozik; az ORBIT csak a Megveszem gombokat irányítja rá. Fizetési linket a Stripe-ban (Payment Links) vagy a Gumroadon egy perc alatt készíthetsz.'));
 box.append(el('p','hint','A forgalmat (hirdetés, posztok) te indítod; az ORBIT ehhez a „Rád vár” listában ad kész szövegeket.'),
  button(update?'Igen, frissítem':'Igen, élesítem',async()=>{if(link.value.trim()!==(f.checkout||''))await call('enterprise_save',{settings:{scope:'business_lab',checkout:{idea_id:f.idea_id,url:link.value.trim()}}});const r=await call('enterprise_save',{settings:{scope:'business_lab',launch:f.idea_id}});$('modal').close();ventureSig='';await loadVenture(true);toast((update?'Frissítve: ':'Élő: ')+r.launch.url);}),
  el('p','hint','Ehhez kell egy Cloudflare-token a Kapcsolatok oldalon (Workers Scripts és Workers KV Storage: Edit).'));
 showModal((update?'Élő oldal frissítése · ':'Élesítés · ')+f.name,box);
}
function fmtMin(x){return (x<10?x.toFixed(1).replace('.',','):Math.round(x))+' perc';}
function healthLine(h){
 if(!h||h.files==null)return null;
 const good=h.ok&&(h.live==null||h.live_ok===h.live)&&(!h.real||h.real_ok===h.real);
 const text=(good?'✅ ':'⚠️ ')+'Termék: '+h.files_ok+'/'+h.files+' fájl fut hibátlanul'+(h.live!=null?' · élő próba '+h.live_ok+'/'+h.live+' kérés':'')+(h.real?' · valós minta '+h.real_ok+'/'+h.real:'')+(h.failed?.length?' · hibás: '+h.failed.map(x=>x==='smoke.json'?'élő próba':x).join(', '):'');
 const p=el('p','ap-health '+(good?'ok':'bad'),text);p.title='Az ORBIT legutóbbi homokozós futtatása'+(h.at?' · '+ventureTime(h.at):'');return p;
}
function timelineBars(list){
 if(!list?.length)return null;
 const box=el('div','ap-timeline');box.setAttribute('role','img');
 box.setAttribute('aria-label','Az utolsó '+list.length+' építés hibátlan fájljai: '+list.map(e=>e.files_ok+'/'+e.files).join(', '));
 for(const e of list){
  const good=e.ok&&(e.live==null||e.live_ok===e.live),bar=el('i',good?'ok':'bad');
  bar.style.height=Math.max(8,Math.round(100*(e.files?e.files_ok/e.files:0)))+'%';
  bar.title=e.cycle+'. kör · '+(e.milestone||'')+(e.minutes!=null?' · '+fmtMin(e.minutes):'')+'\n'+e.files_ok+'/'+e.files+' fájl hibátlan'+(e.live!=null?' · élő próba '+e.live_ok+'/'+e.live:'')+(e.failed?.length?'\nhibás: '+e.failed.map(x=>x==='smoke.json'?'élő próba':x).join(', '):'');
  box.append(bar);
 }
 const wrap=el('div','ap-timeline-wrap');wrap.append(el('small','hint','Utolsó építések – oszlop: hibátlanul futó fájlok aránya, zöld: minden fut és az élő próba is sikeres'),box);return wrap;
}
function folderButton(f){const box=el('div','ap-chips');box.append(button('📁 Elkészült fájlok megnyitása',()=>call('venture_folder',{idea_id:f.idea_id}),'secondary'),button('▶︎ Kipróbálás',()=>tryProduct(f),'secondary'));return box;}
async function tryProduct(f){
 toast('Az ORBIT elindítja a(z) „'+f.name+'” kódját a homokozóban…');
 const r=await call('venture_try',{idea_id:f.idea_id}),c=r.check||{},box=el('div','ap-detail');
 box.append(el('p','',r.summary||'Nincs futtatható fájl.'));
 for(const x of c.results||[]){const d=el('details','ap-file');d.append(el('summary','',(x.ok?'✅ ':'❌ ')+x.file),el('pre','',x.output||''));box.append(d);}
 for(const x of (c.smoke||{}).results||[])box.append(el('p','',(x.ok?'✅ ':'❌ ')+x.request+' → '+(x.status??'nincs válasz')+(x.ms!=null?' · '+x.ms+' ms':'')+(x.error?' · '+x.error:'')));
 box.append(el('p','hint','Elzárt futtatás: nincs internet, csak a termék saját mappájába írhat, nem látja a kulcsaidat. Semmi nincs közzétéve.'));
 showModal('Kipróbálás · '+f.name,box);
}
function showProductApi(f){
 const box=el('div','ap-detail');
 const endpoints=document.createElement('select');endpoints.setAttribute('aria-label','API-végpont');
 for(const example of f.api_examples){
  const option=el('option','',example.method+' '+example.path+' · '+(example.index+1)+'. minta');option.value=example.index;endpoints.append(option);
 }
 const input=document.createElement('textarea');input.rows=8;input.setAttribute('aria-label','JSON bemenet');
 const result=el('pre','');result.setAttribute('aria-live','polite');
 const chosen=()=>f.api_examples.find(x=>x.index===Number(endpoints.value));
 const reset=()=>{const x=chosen();input.hidden=x.method==='GET';input.value=JSON.stringify(x.body??{},null,2);result.textContent='';};
 const send=button('Kérés futtatása',async()=>{
  send.disabled=true;endpoints.disabled=true;result.textContent='A helyi szerver indul…';
  try{
   const {result:r}=f.workshop?await paCall('workspace_api',{index:chosen().index,body:input.value,record:true}):await call('venture_try',{idea_id:f.idea_id,api_index:chosen().index,body:input.value});
   let body=r.body||r.error||'';try{body=JSON.stringify(JSON.parse(body),null,2);}catch{}
   result.textContent=(r.status!=null?'HTTP '+r.status+' · '+r.ms+' ms':'Hiba')+'\n'+body;
  }catch(error){result.textContent=error.message;}finally{send.disabled=false;endpoints.disabled=false;}
 });
 endpoints.onchange=reset;
 endpoints.value=(f.api_examples.find(x=>x.method==='POST')||f.api_examples[0]).index;
 reset();
 box.append(el('p','hint','A termék helyi szervere egy ideiglenes másolatban fut. Használj mintát vagy adj meg saját JSON-t. Minden kérés után leáll; internetes adatforrások helyett helyi mintákat használ.'),endpoints,input,send,result);
 showModal('Helyi API · '+f.name,box);
}
function previewButtons(f){
 if(!f.previews?.length)return null;
 const box=el('div','ap-previews');
 for(const p of f.previews){const b=el('button','ap-chip now','👁 '+p.name);b.title='Előnézet: '+p.name;b.onclick=()=>showPreview(f,p);box.append(b);}
 return box;
}
function showPreview(f,p){
 const box=el('div','ap-preview');
 const frame=document.createElement('iframe');frame.className='ap-frame';frame.setAttribute('sandbox','');frame.setAttribute('referrerpolicy','no-referrer');frame.title='Előnézet: '+p.name;frame.srcdoc=p.html;
 const bar=el('div','ap-preview-bar');
 const sizes=[['Asztali','100%'],['Mobil','390px']];
 for(const [label,w] of sizes){const b=el('button','ap-chip',label);b.onclick=()=>{frame.style.width=w;};bar.append(b);}
 if(p.artifact)bar.append(button('Megnyitás böngészőben',()=>call('open_artifact',{id:p.artifact,requestProject:'orbit-business-lab'}),'secondary'));
 box.append(bar,frame,el('p','hint','Biztonságos előnézet szkriptek nélkül. A gombok és űrlapok a böngészős megnyitásnál működnek. Semmi nincs közzétéve.'));
 showModal(f.name+' · '+p.name,box);
}
function measureCard(m){
 const rows=[];
 if(m.backtest){const b=m.backtest,a=b.full,o=b.out_of_sample;rows.push(['Backtest · '+b.spec.coin+' '+b.spec.interval,a.return_pct+'% (tartás: '+a.buy_hold_pct+'%)'],['Mintán kívül',o.return_pct+'% · max. visszaesés '+a.max_drawdown_pct+'%'],['Kötések · találati arány',a.trades+' · '+a.win_rate_pct+'%'],['Minősítés',b.verdict==='promising'?'ígéretes':'gyenge']);}
 if(m.paper){const p=m.paper;rows.push(['Virtuális teszt',p.status==='running'?p.virtual_value+' USD (1000-ről, '+p.bars+' gyertya)':p.status==='waiting'?'elindult, új árfolyamra vár':'hiba: '+(p.error||'')]);}
 if(m['economics-result']){const e=m['economics-result'];rows.push(['Haszon / rendelés',e.profit_per_order+' '+e.currency+' ('+e.margin_pct+'%)'],['Max. hirdetési költség / eladás',e.breakeven_ad_cost+' '+e.currency]);}
 if(!rows.length)return null;
 const box=el('div','ap-measure');box.append(el('h3','','Az ORBIT saját mérése'));const dl=el('dl');for(const [k,v] of rows)dl.append(el('dt','',k),el('dd','',String(v)));box.append(dl);
 box.append(el('p','hint','Mért adatok, nem ígéret és nem befektetési tanács. Valódi pénz csak a te döntéseddel.'));return box;
}
function showMilestone(ms,f){
 const box=el('div','ap-detail');
 const mark=async done=>{await call('enterprise_save',{settings:{scope:'business_lab',milestone_done:{idea_id:f.idea_id,milestone:ms.id,done}}});$('modal').close();ventureSig='';await loadVenture(true);toast(done?'Késznek jelölve; az Autopilóta a következő lépéssel folytatja.':'Visszavonva; az Autopilóta újra ezen a lépésen dolgozik.');};
 if(f&&ms.by_owner)box.append(el('p','ap-notice','✔ Ezt a lépést te jelölted késznek.'),button('↩ Visszavonás',()=>mark(false),'secondary'));
 else if(f&&ms.state!=='done'&&ms.state!=='skipped')box.append(button('✔ Ezt én elkészítettem',()=>mark(true),'secondary'),el('p','hint','Ha ezt a lépést te magad megcsináltad, jelöld késznek: az Autopilóta a következővel folytatja, és nem írja újra.'));
 box.append(el('p','hint',(MS_STATE[ms.state]||MS_STATE.pending)[0]+(ms.cycles.length?' · '+ms.cycles.map(c=>c+'.').join(', ')+' kör':'')),el('h4','','Cél'),el('p','',ms.desc));
 if(ms.summary)box.append(el('h4','','Mi készült el'),richText(ms.summary));
 for(const f of ms.files||[]){const d=el('details','ap-file');d.append(el('summary','','📄 '+f.name),el('pre','',f.preview||''));box.append(d);}
 const errs=Object.entries(ms.code_errors||{});
 if(errs.length){box.append(el('h4','','Nem futott le hibátlanul'));for(const [file,err] of errs)box.append(el('p','','❌ '+file+' → '+err));box.append(el('p','hint','A következő kör ezt javítja elsőként.'));}
 if(ms.note)box.append(el('p','hint',ms.note));
 if(ms.review)box.append(el('h4','','Tesztelő'),richText(ms.review));
 showModal('Mérföldkő · '+ms.title,box);
}
function showOwnerAction(a,f){
 const box=el('div','ap-detail');
 if(a.relaunch&&f)box.append(button(a.relaunch==='update'?'🔄 Új változat élesítése':'🚀 Élesítés',()=>confirmLaunch(f,a.relaunch==='update'),'primary'));
 if(a.concierge&&f)box.append(button('📋 Levél másolása',()=>{navigator.clipboard?.writeText(a.draft||'');toast('A levél a vágólapon; küldd el a saját leveleződből.');},'primary'),button('✔ Elküldtem',async()=>{await call('enterprise_save',{settings:{scope:'business_lab',concierge_sent:{idea_id:f.idea_id,key:a.concierge}}});$('modal').close();ventureSig='';await loadVenture(true);toast('Megjelölve elküldöttként.');},'secondary'));
 box.append(...(a.kind==='money'?[el('p','ap-notice','💰 Valódi pénzt érint. Az ORBIT ezt soha nem hajtja végre automatikusan – a döntés és a végrehajtás a tiéd.')]:[]),el('p','',a.why||''),...(a.variants?.length?[el('p','hint','Összevonva hasonló teendőkkel: '+a.variants.join(' · '))]:[]),el('h4','','Előkészítve'),el('pre','',a.draft||'Nincs vázlat.'),el('p','hint','Ezt az ORBIT nem hajtja végre helyetted. Ha megcsináltad, a következő körök erre építenek.'));
 showModal('Rád vár · '+a.title,box);
}
function cycleBlock(c){
 const box=el('div','ap-detail');
 box.append(el('p','hint',ventureTime(c.created)+(c.finished?' – '+ventureTime(c.finished):'')+' · '+(c.status==='done'?'lezárt kör':c.status==='running'?'folyamatban':'elakadt kör')));
 box.append(el('h4','',c.milestone?'1 · Tervező':'1 · Piackutató'),c.research?richText(c.research):el('p','hint','Nincs mentett kutatás.'));
 box.append(el('h4','','2 · Építő'));
 if(c.milestone){box.append(el('p','','🔨 '+c.milestone.title+' · '+(c.milestone.status==='partial'?'részben kész':'elkészült')),richText(c.milestone.summary||''));if(c.milestone.files?.length)box.append(el('p','hint','Fájlok: '+c.milestone.files.join(', ')));}
 else if(c.idea)box.append(ideaBlock(c.idea));else box.append(el('p','hint',ventureBlocker(c)));
 box.append(el('h4','',c.milestone?'3 · Tesztelő':'3 · Kritikus'),c.review?richText(c.review):el('p','hint',c.status==='running'?'Még nem értékelte.':'Ebben a körben nem jutott el az értékelésig.'));
 return box;
}
function showCycle(c){showModal(c.cycle+'. kör · mit dolgozott az ORBIT',cycleBlock(c));}
function showVenture(summary){
 const body=el('div','ap-summary');
 if(summary)body.append(richText(summary));
 showModal('Autopilóta · összefoglaló',body);
}
setInterval(()=>{if(currentApp==='autopilot'&&!document.hidden){refreshVentureHead();loadVenture();}},5000);
