/* Publikálás-központ. Everything ORBIT has made (renders, Szimgyár simulations, generated clips) on one page.
   Three tabs: Videók (by type, one detail panel with a row per channel), Ütemterv (per-channel schedule
   and a proposal the owner confirms), Fiókok (connections). The project's own review list stays as a small fourth tab.
   A function scope: a function declared in a bare block would replace the app's global of that name. */
(()=>{
 let H=null,tab='videos',picked=null,typeFilter='all',stateFilter='new',sel={},drafts={},textTab='',opts={privacy:'public',kids:false},busy=false,sig='';
 let proposal=null,covers={},coverBusy=false,sortBy='score';
 const scoreClass=n=>n>=70?'high':n>=50?'mid':'low';
 const badge=(n,big)=>{const b=el('span','hub-score '+scoreClass(n)+(big?' big':''),String(n));b.title='Pontszám (0–100): az ORBIT becslése arra, mennyire esélyes a videó';return b;};
 const op=async(name,args={})=>(await call('project_app',{op:name,args})).result;
 const STATE={new:'Vár a közzétételre',scheduled:'Ütemezve',active:'Folyamatban',published:'Kint van',failed:'Hiba'};
 const POST={queued:'Sorban áll',uploading:'Feltöltés…',scheduled:'Ütemezve',published:'Kint van',failed:'Hiba',cancelled:'Visszavonva'};
 const ICON={youtube:'▶',instagram:'◎',facebook:'ƒ',tiktok:'♪'};
 const PLAT={youtube:'YouTube',instagram:'Instagram',facebook:'Facebook',tiktok:'TikTok'};
 const STATUS={connected:'Csatlakoztatva',waiting:'Bejelentkezésre vár…',expired:'Lejárt, újra kell csatlakoztatni',new:'Nincs csatlakoztatva'};
 const when=t=>t?new Date(t*1000).toLocaleString('hu-HU',{month:'short',day:'numeric',weekday:'short',hour:'2-digit',minute:'2-digit'}):'';
 const localInput=t=>{const d=new Date(t*1000),p=n=>String(n).padStart(2,'0');return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'T'+p(d.getHours())+':'+p(d.getMinutes());};
 const app=()=>$('publicationApp');
 const typing=()=>{const a=document.activeElement;return !!a&&$('hubBody')?.contains(a)&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName);};
 const typeOf=id=>H.types.find(t=>t.id===id)||{label:'Egyéb',icon:'▫'};
 const ACTIVE=['queued','uploading','scheduled','published'];

 function mount(){
  if($('hubBody'))return;
  const legacy=el('div','hub-legacy');legacy.id='hubLegacy';legacy.append(...app().children);
  const head=el('div','hub-head'),title=el('div');
  title.append(el('span','eyebrow','MINDEN ELKÉSZÜLT VIDEÓ / MINDEN CSATORNA'),el('h1','','Publikálás'),el('p','hint','Itt van minden, amit az ORBIT csinált. Válaszd ki a videót, jelöld be a csatornákat, add meg mikor menjen ki. Csak az kerül ki, amit te elindítasz vagy ütemezel.'));
  const tabs=el('div','publication-tabs');tabs.id='hubTabs';head.append(title);
  const body=el('div','hub-body');body.id='hubBody';
  app().append(head,tabs,body,legacy);
 }

 async function load(force){
  if(currentApp!=='publishing'||busy||tab==='project')return;
  busy=true;
  try{const d=await op('publish_snapshot');const s=JSON.stringify([d.counts,d.accounts,d.videos.map(v=>[v.id,v.state,v.posts,v.hidden,v.thumbs,v.thumb]),d.calendar]);if(s!==sig||force){sig=s;H=d;if(!typing()||force)render();}}
  catch(e){H=H||{error:e.message};render();}
  finally{busy=false;}
 }

 function render(){
  mount();
  const tabs=$('hubTabs');tabs.replaceChildren();
  const n=H?.counts||{};
  for(const [id,label] of [['videos','Videók'+(n.new?' · '+n.new+' vár':'')],['plan','Ütemterv'+(n.scheduled?' · '+n.scheduled:'')],['accounts','Fiókok'+(H?.accounts?' · '+H.accounts.length:'')],]){
   const b=el('button',tab===id?'selected':'',label);b.setAttribute('aria-pressed',String(tab===id));b.onclick=()=>{tab=id;render();if(id==='project'){publicationDetailKey='';loadPublication();}else load(true);};tabs.append(b);}
  $('hubLegacy').hidden=tab!=='project';const body=$('hubBody');body.hidden=tab==='project';
  if(tab==='project')return;
  const scroll=body.scrollTop;body.replaceChildren();
  if(!H){body.append(el('p','hint','Betöltés…'));return;}
  if(H.error){body.append(el('p','error-text',H.error));return;}
  (tab==='accounts'?accountsPage:tab==='plan'?planPage:videosPage)(body);
  body.scrollTop=scroll;
 }

 // ------------------------------------------------ Videók
 function videosPage(body){
  const shown=H.videos.filter(v=>!v.hidden);
  body.append(autoBar());
  const bar=el('div','hub-bar');
  const inType=shown.filter(v=>typeFilter==='all'||v.type===typeFilter);
  const stSel=el('select');
  const cnt=st=>shown.filter(v=>(typeFilter==='all'||v.type===typeFilter)&&v.state===st).length;
  options(stSel,[['new','Vár a közzétételre'],['scheduled','Ütemezve'],['active','Folyamatban'],['published','Kint van'],['failed','Hiba'],['all','Mind'],['hidden','Elrejtett']].map(([value,label])=>({value,label:label+' · '+(value==='all'?inType.length:value==='hidden'?H.videos.filter(v=>v.hidden&&(typeFilter==='all'||v.type===typeFilter)).length:cnt(value))})),stateFilter);
  stSel.onchange=()=>{stateFilter=stSel.value;picked=null;render();};
  const tySel=el('select');options(tySel,[{value:'all',label:'Minden típus'},...H.types.map(t=>({value:t.id,label:t.icon+' '+t.label+' · '+t.total}))],typeFilter);tySel.onchange=()=>{typeFilter=tySel.value;picked=null;render();};
  const soSel=el('select');options(soSel,[{value:'score',label:'Rendezés: legjobb pontszám elöl'},{value:'new',label:'Rendezés: legújabb elöl'}],sortBy);soSel.onchange=()=>{sortBy=soSel.value;picked=null;render();};
  bar.append(stSel,tySel,soSel,button('Régi, projekt szerinti lista',()=>{tab='project';render();publicationDetailKey='';loadPublication();},'text-button'));
  body.append(bar);
  if(!H.accounts.some(a=>a.status==='connected')){const note=el('div','hub-note');note.append(el('p','','Még nincs csatlakoztatott fiók. Adj hozzá YouTube-, Instagram-, Facebook- vagy TikTok-fiókot, és a videók innen mehetnek ki.'),button('Fiók hozzáadása →',()=>{tab='accounts';render();}));body.append(note);}
  const items=H.videos.filter(v=>(typeFilter==='all'||v.type===typeFilter)&&(stateFilter==='hidden'?v.hidden:!v.hidden&&(stateFilter==='all'||v.state===stateFilter)))
  items.sort(sortBy==='score'?(x,y)=>(y.score||0)-(x.score||0)||(y.created||0)-(x.created||0):(x,y)=>(y.created||0)-(x.created||0));
  if(!items.some(v=>v.id===picked)){picked=items[0]?.id||null;pick(items[0]);}
  const layout=el('div','hub-layout'),list=el('div','hub-list'),detail=el('div','hub-detail-pane');
  for(const v of items){
   const card=el('button','hub-item'+(v.id===picked?' selected':''));
   const poster=el('div','hub-poster'+(v.short===false?' wide':''));loadPoster(poster,v);
   const text=el('div','hub-item-text');
   const marks=el('span','hub-marks');for(const p of v.posts)marks.append(el('i','hub-mark '+p.status,ICON[p.platform]||'•'));
   text.append(el('strong','',v.title||v.name),el('small','',typeOf(v.type).label+' · '+(v.short===false?'hosszú':v.short?'Short':'')+(v.duration?' · '+Math.round(v.duration)+' mp':'')),el('small','',STATE[v.state]+(v.state==='scheduled'?' · '+when(Math.min(...v.posts.filter(p=>p.status==='scheduled').map(p=>p.scheduled))):'')),marks);
   card.append(poster,text,badge(v.score||0));card.onclick=()=>{picked=v.id;pick(v);render();};list.append(card);}
  if(!items.length)list.append(el('p','hint',stateFilter==='new'?'Nincs közzétételre váró videó ebben a típusban. Ami elkészül, itt jelenik meg.':'Nincs ilyen videó.'));
  layout.append(list,detail);body.append(layout);
  const v=items.find(x=>x.id===picked);if(v)detailPage(detail,v);else detail.append(el('div','publication-empty','Válassz egy videót.'));
 }

 function loadPoster(box,v){
  if(covers[v.id+':main']){const i=el('img');i.src=covers[v.id+':main'];box.append(i);return;}
  videoPoster({id:v.id,project:v.project}).then(url=>{if(!url||!box.isConnected)return;const i=el('img');i.src=url;box.append(i);}).catch(()=>{});
 }

 function pick(v){
  textTab='';sel={};
  if(!v)return;
  drafts={};for(const p of Object.keys(v.variants||{}))drafts[p]={...v.variants[p]};
  const routed=new Set(H.routes[v.project]||[]),done=new Set(v.posts.filter(p=>ACTIVE.includes(p.status)).map(p=>p.account));
  for(const a of H.accounts){
   if(a.status==='connected'&&!done.has(a.id)&&(a.types.includes(v.type)||routed.has(a.id))&&(a.platform==='youtube'||v.short!==false)){sel[a.id]={on:true,mode:'next',at:null,custom:''};}}
  opts={privacy:'public',kids:!!v.made_for_kids,accept:false};
  if(v.thumbs&&!covers[v.id])fetchCovers(v);
  fillSlots(v);
 }

 async function fillSlots(v){
  let after=0;
  for(const a of H.accounts){const s=sel[a.id];if(!s||!s.on||s.mode!=='next')continue;
   try{const r=await op('publish_next_slot',{account:a.id,after});s.at=r.when;after=r.when+7200;}catch(e){s.at=null;}}
  if(picked===v.id&&!typing())render();
 }

 async function fetchCovers(v){
  try{const r=await op('publish_thumb_get',{video:v.id});covers[v.id]=r.thumbs;if(r.thumbs[v.thumb])covers[v.id+':main']=r.thumbs[v.thumb];if(picked===v.id&&!typing())render();}catch(e){}
 }

 function currentTitle(v){const t=(drafts.youtube&&drafts.youtube.title)||(drafts[textTab]&&drafts[textTab].title)||v.title||'';return t;}
 // The cover text follows an edited title: a video that already has covers gets new ones as soon as the title field is left.
 async function regenCovers(v){
  if(coverBusy||!(v.thumbs>0))return;
  coverBusy=true;toast('A borítóképek az új címhez készülnek…');
  try{const r=await op('publish_thumbs',{video:v.id,hook:v.hook,title:currentTitle(v)});toast(r.message);}catch(e){toast(String(e&&e.message||e));}finally{coverBusy=false;}
  delete covers[v.id];delete covers[v.id+':main'];await load(true);await fetchCovers(v);
 }

 // Automatic scheduling: off until the owner switches it on; then the best-scored checked video always takes a channel's next free slot.
 function autoBar(){
  const a=H.auto||{enabled:false,min_score:55},box=el('div','hub-auto'+(a.enabled?' on':''));
  const left=el('div');left.append(el('b','','Automatikus ütemezés: '+(a.enabled?'BE':'ki')),el('small','hint',a.enabled?'A legjobb pontszámú, ellenőrzött videó kerül a csatornák következő szabad időpontjába. Csak '+a.min_score+' pont fölötti videó megy.':'Ki van kapcsolva: semmi nem ütemeződik, amíg te nem csinálod. Bekapcsolva az ORBIT a legjobb pontszámú videót teszi a következő szabad helyre.'));
  const right=el('div','hub-auto-ctl');
  const min=el('input');min.type='number';min.min=0;min.max=100;min.value=a.min_score;min.title='Legalacsonyabb pontszám, ami még mehet';min.onchange=()=>act(async()=>{await op('publish_auto',{min_score:Number(min.value)});await load(true);});
  right.append(el('small','','min. pont'),min,button(a.enabled?'Kikapcsolás':'Bekapcsolás',()=>act(async()=>{const r=await op('publish_auto',{enabled:!a.enabled});toast(r.message);await load(true);}),a.enabled?'secondary':''));
  box.append(left,right);return box;
 }

 function scoreCard(v){
  const box=el('details','hub-scorecard');box.open=false;
  const sum=el('summary');sum.append(badge(v.score||0,true),el('span','','Pontszám · '+(v.score_basis||'')));box.append(sum);
  for(const p of v.score_parts||[]){const r=el('div','hub-part');const bar=el('i');bar.style.width=Math.round(100*p.got/p.max)+'%';const track=el('span','hub-bar-track');track.append(bar);r.append(el('b','',p.label),track,el('small','',p.got+' / '+p.max+' · '+p.note));box.append(r);}
  box.append(el('p','hint','A pontszám becslés, nem mért eredmény: a streamer chatjének reakciója, a formátum, a kép, a cím és az ellenőrző döntése alapján. 40 pont alatt egy videó nem kerül automatikus ütemezésbe.'));
  return box;
 }

 function detailPage(box,v){
  const T=typeOf(v.type);
  const head=el('div','hub-detail-head');
  head.append(el('span','hub-badge',T.icon+' '+T.label),...(v.quality&&v.quality.status!=='verified'?[el('span','hub-badge warn','⚠ '+({needs_revision:'Javításra szorul a történet',invalid_review:'Az ellenőrzés nem értelmezhető',not_checked:'Nem ellenőrzött történet',not_verified:'Nem ellenőrzött történet'}[v.quality.status]||'Nem ellenőrzött')+(v.quality.note?' · '+v.quality.note:''))]:[]),el('span','hub-badge '+(v.short===false?'long':'short'),v.short===false?'Hosszú videó':v.short?'Short / Reel':'—'),el('small','',v.project_name+(v.duration?' · '+Math.round(v.duration)+' mp':'')));
  const media=el('div','publication-media'),video=el('video');video.controls=true;video.preload='metadata';video.setAttribute('playsinline','');media.append(video);
  const wait=el('p','hint','Előnézet betöltése…');media.append(wait);
  playableMedia({id:v.id,project:v.project}).then(url=>{if(!video.isConnected)return;video.src=url;video.load();wait.remove();}).catch(()=>{if(video.isConnected)wait.textContent='Az előnézet nem tölthető be.';});
  const side=el('div','hub-side');side.append(media);
  // Cover images (the text follows the title as edited below)
  const cov=el('div','hub-covers');cov.append(el('label','','Borítókép'));
  const row=el('div','hub-cover-row');
  const imgs=covers[v.id]||[];
  imgs.forEach((src,i)=>{const b=el('button','hub-cover'+(i===v.thumb?' on':''));const im=el('img');im.src=src;b.append(im);b.onclick=()=>act(async()=>{await op('publish_thumb_pick',{video:v.id,index:i});delete covers[v.id+':main'];await load(true);fetchCovers({...v,thumb:i});});row.append(b);});
  cov.append(row);
  cov.append(button(imgs.length?'↻ Új borítóképek':'✦ Borítóképek készítése',()=>act(async()=>{coverBusy=true;toast('A borítóképek készülnek…');try{const r=await op('publish_thumbs',{video:v.id,hook:v.hook,title:currentTitle(v)});toast(r.message);}finally{coverBusy=false;}delete covers[v.id];await load(true);v.thumbs=3;await fetchCovers(v);}),'secondary'));
  if(imgs.length)cov.append(button('Megnyitás Finderben',()=>op('publish_thumb_open',{video:v.id}),'text-button'));
  cov.append(el('p','hint',v.short===false?'A YouTube-videóhoz feltöltéskor a kiválasztott kép kerül borítónak.':'Shortnál a YouTube a saját képkockát használja; Instagramon és TikTokon az appban választhatsz borítót, ehhez a kép Finderből elérhető.'));
  side.append(cov);
  const form=el('div','hub-form');
  form.append(head,el('h2','',v.title||v.name),scoreCard(v));
  if(v.short===false)form.append(el('p','hint','Fekvő vagy 3 percnél hosszabb videó: csak YouTube-ra tehető ki.'));
  // One row per channel
  const chans=el('div','hub-channels');chans.append(el('label','','Csatornák'));
  const byAcc={};for(const p of v.posts)(byAcc[p.account||'x']=byAcc[p.account||'x']||[]).push(p);
  if(!H.accounts.length)chans.append(el('p','hint','Előbb adj hozzá fiókot a Fiókok lapon.'));
  for(const a of H.accounts){
   const mine=(byAcc[a.id]||[]).slice(-1)[0],r=el('div','hub-chan');
   const name=el('div','hub-chan-name');name.append(el('span','hub-icon',ICON[a.platform]||'•'),el('b','',a.label),el('small','',PLAT[a.platform]));
   r.append(name);
   const state=el('div','hub-chan-state');
   if(mine&&ACTIVE.includes(mine.status)){
    r.classList.add('is-'+mine.status);
    state.append(el('span','hub-pill '+mine.status,POST[mine.status]+(mine.status==='scheduled'?' · '+when(mine.scheduled):mine.finished?' · '+when(mine.finished):'')));
    if(mine.url&&!mine.legacy)state.append(button('Megnyitás',()=>op('publish_open',{id:mine.id}),'text-button'));
    if(!mine.legacy&&mine.status==='scheduled'){
     const t=el('input');t.type='datetime-local';t.value=localInput(mine.scheduled);t.onchange=()=>act(async()=>{const r2=await op('publish_reschedule',{id:mine.id,when:Math.round(new Date(t.value).getTime()/1000)});toast(r2.message);await load(true);});t.title='Időpont módosítása';state.append(t);}
    if(!mine.legacy&&mine.status==='scheduled')state.append(button('▶ Közzététel most',()=>act(async()=>{const r3=await op('publish_now',{id:mine.id});toast(r3.message);await load(true);}),'secondary'));
    if(!mine.legacy&&(mine.status==='scheduled'||mine.status==='queued'))state.append(button('Visszavonás',async()=>{await op('publish_cancel',{id:mine.id});await load(true);},'text-button'));
   }else if(a.status!=='connected'||(a.platform!=='youtube'&&v.short===false)){
    r.classList.add('off');state.append(el('small','',a.status!=='connected'?STATUS[a.status]:'Ide csak álló, rövid videó mehet'));
   }else{
    if(mine&&(mine.status==='failed'||mine.status==='cancelled')){
     state.append(el('span','hub-pill failed',POST[mine.status]));if(mine.error)state.append(el('small','error-text',mine.error));
     const chk=el('input');chk.type='checkbox';const lab=el('label','hint');lab.append(chk,document.createTextNode(' Ellenőriztem: nincs fent.'));
     state.append(lab,button('↻ Újra',async()=>{const r2=await op('publish_retry',{id:mine.id,confirmed_absent:chk.checked});toast(r2.message);await load(true);},'text-button'));
    }
    const s=sel[a.id]||(sel[a.id]={on:false,mode:'next',at:null,custom:''});
    const on=el('input');on.type='checkbox';on.checked=s.on;on.onchange=()=>{s.on=on.checked;if(s.on&&s.mode==='next'&&!s.at)fillSlots(v);render();};
    r.prepend(on);
    if(s.on){
     const t=el('input');t.type='datetime-local';t.value=s.mode==='custom'?s.custom:(s.at?localInput(s.at):'');
     t.title='Ütemezett időpont. Alapból a csatorna következő szabad helye.';
     t.onchange=()=>{s.mode='custom';s.custom=t.value;};
     state.append(el('small','','Ütemezés:'),t);
    }else state.append(el('small','','Nem megy ide'));
   }
   r.append(state);chans.append(r);}
  form.append(chans);
  // Text per platform
  const chosen=H.accounts.filter(a=>sel[a.id]?.on);
  const plats=[...new Set(chosen.map(a=>a.platform))];
  if(plats.length){
   if(!plats.includes(textTab))textTab=plats[0];
   const tt=el('div','hub-texttabs');tt.append(el('label','','Szöveg'));
   for(const p of plats){const b=el('button','hub-filter'+(textTab===p?' selected':''),(ICON[p]||'')+' '+PLAT[p]);b.onclick=()=>{textTab=p;render();};tt.append(b);}
   form.append(tt);
   const d=drafts[textTab]=drafts[textTab]||{title:v.title||'',caption:v.caption||''};
   const text=(label,key,rows,max)=>{const w=el('div'),l=el('label','hint',label),i=el(rows?'textarea':'input');if(rows)i.rows=rows;i.maxLength=max;i.value=d[key];i.oninput=()=>{d[key]=i.value;};if(key==='title')i.onchange=()=>regenCovers(v);w.append(l,i);return w;};
   if(textTab==='youtube')form.append(text('Cím','title',0,100));
   form.append(text(textTab==='youtube'?'Leírás és hashtagek':'Felirat és hashtagek','caption',5,2200));
   form.append(button('↺ Az ORBIT javaslata',()=>{drafts[textTab]={...v.variants[textTab]};render();},'text-button'));
  }
  const more=el('details','hub-more');more.append(el('summary','','További beállítások'));
  const priv=el('select');options(priv,[{value:'public',label:'Nyilvános'},{value:'unlisted',label:'Nem listázott / csak ismerősök'},{value:'private',label:'Privát'}],opts.privacy);priv.onchange=()=>{opts.privacy=priv.value;};
  const kids=el('select');options(kids,[{value:'no',label:'Nem gyermekeknek készült'},{value:'yes',label:'Gyermekeknek készült'}],opts.kids?'yes':'no');kids.onchange=()=>{opts.kids=kids.value==='yes';};
  const r2=el('div','hub-row');for(const [l,n] of [['Láthatóság',priv],['Célközönség',kids]]){const c=el('div');c.append(el('label','',l),n);r2.append(c);}more.append(r2);form.append(more);
  const unverified=v.quality&&v.quality.status!=='verified';
  if(unverified){const lab=el('label','hint'),chk=el('input');chk.type='checkbox';chk.checked=!!opts.accept;chk.onchange=()=>{opts.accept=chk.checked;render();};lab.append(chk,document.createTextNode(' Átnéztem a videót, vállalom, hogy a történet nem ellenőrzött.'));form.append(lab);}
  // Two plain actions: post now, or schedule (each channel's time is set in its row above).
  const send=async(now)=>{
   const plan=chosen.map(a=>{const s=sel[a.id],d2=drafts[a.platform]||{};
    let at=null;if(!now){if(s.mode==='custom'){at=Math.round(new Date(s.custom).getTime()/1000);if(!at)throw new Error('Adj meg időpontot.');}else{if(!s.at)throw new Error('Az időpont még töltődik, próbáld újra.');at=s.at;}}
    return {account:a.id,when:at,title:d2.title??v.title,caption:d2.caption??v.caption};});
   const r=await op('publish_post',{video:v.id,plan,privacy:opts.privacy,made_for_kids:opts.kids,accept_unverified:!!opts.accept});
   toast(r.message);await load(true);};
  const bar=el('div','hub-actions');bar.style.cssText='display:flex;gap:10px;flex-wrap:wrap;margin-top:12px';
  const nowBtn=button(chosen.length?'▶ Közzététel most · '+chosen.length+' csatorna':'Jelölj ki legalább egy csatornát',()=>act(()=>send(true)));
  const laterBtn=button(chosen.length?'🕒 Ütemezés · '+chosen.length+' csatorna':'Ütemezés',()=>act(()=>send(false)),'secondary');
  nowBtn.disabled=laterBtn.disabled=!chosen.length||(unverified&&!opts.accept);
  bar.append(nowBtn,laterBtn);form.insertBefore(bar,chans);
  const foot=el('div','hub-foot');
  foot.append(button(v.hidden?'Vissza a listába':'Nem teszem ki (elrejtés)',async()=>{await op('publish_hide',{video:v.id,hidden:!v.hidden});await load(true);},'text-button'),button('Megnyitás a Macen',()=>call('open_artifact',{id:v.id,requestProject:v.project}),'text-button'));
  form.append(foot);
  box.append(side,form);
 }

 // ------------------------------------------------ Ütemterv
 function planPage(body){
  const top=el('div','hub-plan-top');
  const txt=el('div');txt.append(el('h3','','Heti terv egy kattintással'),el('p','hint','Az ORBIT a csatornák saját időpontjaira osztja el azokat a videókat, amelyeket az adott csatorna fogad. Átnézed, kiveszed amit nem akarsz, és csak a jóváhagyás után ütemeződik.'));
  top.append(txt,button('✦ Javaslat a következő 7 napra',async()=>{const r=await op('publish_plan_suggest',{days:7});proposal=dict(r.items);if(!r.items.length)toast('Nincs mit javasolni: állítsd be a csatornáknál, milyen típusú videót fogadnak, vagy nincs több vár videó.',true);render();}));
  body.append(autoBar(),top);
  if(proposal)body.append(proposalBox());
  const lanes=el('div','hub-lanes');
  for(const a of H.accounts){
   const lane=el('section','hub-lane');
   const head=el('div','hub-lane-head');head.append(el('span','hub-icon',ICON[a.platform]||'•'),el('b','',a.label),el('small','',PLAT[a.platform]+(a.status==='connected'?'':' · '+STATUS[a.status])));
   lane.append(head);
   lane.append(el('p','hint','Időpontok: '+a.slots.join(', ')+' · napi legfeljebb '+a.per_day));
   lane.append(el('p','hint',a.types.length?'Fogad: '+a.types.map(t=>typeOf(t).label).join(', '):'Nincs beállítva, milyen videók mennek ide.'));
   lane.append(button('Beállítás',()=>planDialog(a),'text-button'));
   const mine=H.calendar.filter(c=>c.account===a.id);
   const next=mine.filter(c=>['scheduled','queued','uploading'].includes(c.status)),done=mine.filter(c=>!['scheduled','queued','uploading'].includes(c.status)).slice(-4);
   if(!mine.length)lane.append(el('p','hub-empty','Nincs ütemezett vagy friss közzététel.'));
   for(const c of [...next,...done]){const r=el('div','hub-cal '+c.status);r.append(el('span','hub-cal-time',when(c.when)),el('span','hub-cal-title',c.title),el('small','',POST[c.status]));
    if(c.status==='scheduled'){const t=el('input');t.type='datetime-local';t.value=localInput(c.when);t.onchange=()=>act(async()=>{await op('publish_reschedule',{id:c.id,when:Math.round(new Date(t.value).getTime()/1000)});await load(true);});r.append(t,button('▶ Most',()=>act(async()=>{const r3=await op('publish_now',{id:c.id});toast(r3.message);await load(true);}),'secondary'),button('✕',async()=>{await op('publish_cancel',{id:c.id});await load(true);},'text-button'));}
    if(c.error)r.append(el('small','error-text',c.error));
    lane.append(r);}
   lanes.append(lane);}
  if(!H.accounts.length)lanes.append(el('p','hint','Előbb adj hozzá fiókot a Fiókok lapon.'));
  body.append(lanes);
 }
 const dict=items=>({items:items.map((i,k)=>({...i,k})),off:new Set()});

 function proposalBox(){
  const box=el('div','hub-proposal');
  const keep=proposal.items.filter(i=>!proposal.off.has(i.k));
  box.append(el('h3','','Javaslat · '+keep.length+' közzététel'));
  let day='';
  for(const i of proposal.items){
   const d=new Date(i.when*1000).toLocaleDateString('hu-HU',{weekday:'long',month:'long',day:'numeric'});
   if(d!==day){day=d;box.append(el('div','hub-day',d));}
   const r=el('div','hub-prop'+(proposal.off.has(i.k)?' off':''));
   r.append(el('span','hub-cal-time',new Date(i.when*1000).toLocaleTimeString('hu-HU',{hour:'2-digit',minute:'2-digit'})),el('b','',(ICON[i.platform]||'')+' '+i.account_label),badge(i.score||0),el('span','hub-cal-title',i.video_title),el('small','',typeOf(i.type).label));
   const x=el('button','text-button',proposal.off.has(i.k)?'↶':'✕');x.onclick=()=>{proposal.off.has(i.k)?proposal.off.delete(i.k):proposal.off.add(i.k);render();};r.append(x);box.append(r);}
  const row=el('div','hub-row');
  row.append(button('Mind ütemezése ('+keep.length+')',async()=>{const r=await op('publish_plan_apply',{items:keep});toast(r.message,!!r.failed.length&&!r.done);proposal=null;await load(true);}),button('Elvetés',()=>{proposal=null;render();},'secondary'));
  box.append(row);return box;
 }

 function planDialog(a){
  const body=el('div','hub-connect');
  const parse=t=>[...new Set(String(t).split(/[,;\s]+/).map(x=>{const m=/^(\d{1,2})[:.](\d{2})$/.exec(x.trim());return m&&+m[1]<=23&&+m[2]<=59?String(m[1]).padStart(2,'0')+':'+m[2]:null;}).filter(Boolean))].sort();
  const slots=el('textarea');slots.rows=2;slots.value=a.slots.join(', ');slots.placeholder='00:00, 02:00, 04:00 … (beillesztheted a teljes listát)';
  const per=el('input');per.type='number';per.min=1;per.max=48;per.value=a.per_day;let perTouched=a.per_day!==a.slots.length;
  per.oninput=()=>{perTouched=true;};
  const sync=()=>{const n=parse(slots.value).length;count.textContent=n+' időpont naponta';if(!perTouched&&n)per.value=n;};
  slots.oninput=sync;
  const count=el('small','hint','');
  // "Every N hours" fills the list.
  const every=el('div','hub-row');
  const hrs=el('input');hrs.type='number';hrs.min=0.5;hrs.max=12;hrs.step=0.5;hrs.value=2;hrs.style.width='70px';
  const from=el('input');from.type='time';from.value='00:00';const to=el('input');to.type='time';to.value='22:00';
  every.append(el('span','hint','Vagy: minden'),hrs,el('span','hint','órában, '),from,el('span','hint','–'),to,button('Kitöltés',()=>{
   const out=[];let t=+from.value.slice(0,2)*60+ +from.value.slice(3),stop=+to.value.slice(0,2)*60+ +to.value.slice(3);const step=Math.round(Number(hrs.value)*60);
   if(!(step>=30)){toast('Az időköz legalább fél óra.',true);return;}
   while(t<=stop&&out.length<48){out.push(String(Math.floor(t/60)).padStart(2,'0')+':'+String(t%60).padStart(2,'0'));t+=step;}
   slots.value=out.join(', ');perTouched=false;sync();},'secondary'));
  const types=new Set(a.types);
  const chips=el('div','hub-targets');
  for(const t of H.types.filter(t=>t.id!=='other'||t.total)){const c=el('button','hub-target'+(types.has(t.id)?' on':''),t.icon+' '+t.label);c.onclick=()=>{types.has(t.id)?types.delete(t.id):types.add(t.id);c.classList.toggle('on');};chips.append(c);}
  body.append(el('label','','Közzétételi időpontok (ÓÓ:PP, vesszővel vagy sortöréssel)'),slots,count,every,el('label','','Legfeljebb ennyi videó naponta'),per,el('label','','Milyen típusú videókat fogad ez a csatorna?'),chips,
   el('p','hint','Ezek az időpontok adják a „következő szabad hely”-et és a heti terv rácsát. Egy napra legfeljebb 48 időpont adható meg; a napi korlát alapból az időpontok száma. A választott típusú új videókat a Videók lap alapból ide jelöli be.'),
   button('Mentés',async()=>{const list=parse(slots.value);if(!list.length){toast('Adj meg legalább egy időpontot (ÓÓ:PP).',true);return;}
    const r=await op('publish_account_plan',{id:a.id,slots:list,per_day:Number(per.value),types:[...types]});toast(r.message);$('modal').close();await load(true);}));
  sync();showModal(a.label+' · ütemezés',body);
 }

 // ------------------------------------------------ Fiókok
 function accountsPage(body){
  const add=el('div','hub-add');add.append(el('h3','','Új fiók'));
  for(const p of H.platforms){add.append(button((ICON[p.id]||'')+' '+p.label,async()=>{const r=await op('publish_account_add',{platform:p.id});toast(r.message);await load(true);connectDialog({id:r.id,platform:p.id,label:p.label+'-fiók',status:'new'});},'secondary'));}
  body.append(add);
  body.append(el('p','hint','Bármennyi csatorna felvehető: egy fiók egy csatorna egy platformon. Minden csatornának saját időpontjai és témái vannak az Ütemterv lapon, így egy videó több csatornára is kimehet, időben szétosztva. A belépések a macOS Kulcskarikájában maradnak; az ügynökök nem kapják meg.'));
  const grid=el('div','hub-accounts');
  for(const a of H.accounts){
   const card=el('section','hub-account '+a.status),top=el('div','hub-account-top');
   const name=el('input');name.value=a.label;name.maxLength=80;name.onchange=()=>act(async()=>{await op('publish_account_rename',{id:a.id,label:name.value});await load(true);});
   top.append(el('span','hub-icon',ICON[a.platform]||'•'),name);card.append(top);
   card.append(el('p','',a.platform_label+(a.handle?' · '+a.handle:'')),el('p','hub-status',STATUS[a.status]+(a.posts?' · '+a.posts+' közzétett videó':'')));
   if(a.error)card.append(el('p','error-text',a.error));
   if(a.legacy_project)card.append(el('p','hint','Egy projekthez korábban kötött csatorna: új belépés nélkül használható.'));
   card.append(el('p','hint',a.types.length?'Fogad: '+a.types.map(t=>typeOf(t).label).join(', ')+' · '+a.slots.join(', '):'Még nincs beállítva, mit fogad.'),button('Időpontok és típusok',()=>planDialog(a),'text-button'));
   const row=el('div','hub-row');
   if(a.status!=='connected')row.append(button(a.status==='waiting'?'Bejelentkezés újranyitása':'Csatlakoztatás',()=>connectDialog(a)));
   let armed=false;const off=el('button','text-button','Leválasztás');off.onclick=()=>{if(!armed){armed=true;off.textContent='Biztos? Kattints újra';setTimeout(()=>{armed=false;off.textContent='Leválasztás';},4000);return;}act(async()=>{const r=await op('publish_account_remove',{id:a.id});toast(r.message);await load(true);});};
   row.append(off);card.append(row);grid.append(card);}
  body.append(grid);
 }

 function connectDialog(a){
  const body=el('div','hub-connect');
  const finish=async(args)=>{const r=await op('publish_account_connect',{id:a.id,...args});toast(r.message);$('modal').close();await load(true);};
  if(a.platform==='youtube'){
   body.append(el('p','','Megnyílik a böngészőben a Google-bejelentkezés. Ott válaszd ki azt a Google-fiókot és csatornát, amelyiket ehhez a fiókhoz kötöd. Több csatornához fiókonként ismételd meg.'));
   if(!H.google_client)body.append(el('p','error-text','Előbb egyszer importáld a Google OAuth JSON-t: Kapcsolatok → YouTube.'));
   body.append(button('Google-bejelentkezés megnyitása',()=>finish({})));
  }else if(a.platform==='tiktok'){
   body.append(el('p','','A TikTok saját fejlesztői alkalmazást kér (developers.tiktok.com): Login Kit és Content Posting API bekapcsolva, visszatérési cím: http://localhost:8765/callback/'),
    el('p','hint','Amíg a TikTok nem auditálta az alkalmazásodat, a feltöltött videók csak privátként kerülhetnek fel; a TikTok-appban teheted nyilvánossá. A megtekintések lekéréséhez a „video.list” jogosultság is kell.'));
   const key=el('input');key.placeholder='Client key';const secret=el('input');secret.placeholder='Client secret';secret.type='password';
   body.append(key,secret,button('TikTok-bejelentkezés megnyitása',()=>finish({client_key:key.value.trim(),client_secret:secret.value.trim()})));
  }else{
   body.append(el('p','',a.platform==='instagram'?'Instagram üzleti vagy alkotói fiók kell. A Meta fejlesztői oldalán (developers.facebook.com) a saját alkalmazásodban hozz létre hozzáférési tokent „instagram_content_publish” és „instagram_manage_insights” engedéllyel, és illeszd be ide.':'A Meta fejlesztői oldalán hozz létre oldal-hozzáférési tokent „pages_manage_posts”, „publish_video” és „read_insights” engedéllyel, és illeszd be ide.'),
    el('p','hint','A token csak a macOS Kulcskarikájába kerül; az ügynökök és a projektek nem látják.'));
   const token=el('input');token.type='password';token.placeholder='Hozzáférési token';
   body.append(token,button('Ellenőrzés és mentés',()=>finish({token:token.value.trim()})));
  }
  showModal(a.label+' csatlakoztatása',body);
 }

 const openHub=()=>{mount();render();load(true);};
 $('navPublishing').addEventListener('click',()=>setTimeout(openHub,0));
 setInterval(()=>load(false),5000);
})();
