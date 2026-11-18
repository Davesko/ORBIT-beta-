/* Stickman stúdió (owner, 16 Nov): the animation studio's own page in the Műhely's Projekt tab. One main stickman
   character who lands in a new, fully written story in every video, told to the viewer as "you"; one recurring second
   character; Shorts (vertical) and long landscape videos with their own lengths.
   A function scope, so nothing here replaces the app's globals. */
(()=>{
 let S=null,poll=null,lastLoad=0,sig='',draft=null,sheet=null,sheetBusy=false,pick={kind:null,seconds:null,minutes:null,topic:''};
 const op=async(name,args={})=>(await call('project_app',{op:name,args:{project,...args}})).result;
 const on=()=>projectAppView?.app==='series';
 const card=(title,cls='')=>{const c=el('section','cs-card '+cls);if(title)c.append(el('h3','',title));return c;};
 const go=page=>{projectAppPage=page;render();$('projectAppView').scrollTop=0;};
 const run=(label,fn,cls='primary')=>button(label,async()=>{const r=await fn();if(r?.message)toast(r.message);await load(true);},cls);
 const STEPS={hook:'Történet tervezése',art:'Helyszínek festése',script:'Narráció és jelenetek írása',continuity:'Tárgyak közelijei',sound:'Narráció és hang',render:'Animáció rajzolása'};
 const LABEL={hair:{signature:'Kip sapkája (pompon, hajtás, tincsek)',none:'nincs',tuft:'kócos tincs',spiky:'tüskés',bun:'konty',long:'hosszú',curly:'göndör',cap:'baseballsapka',beanie:'kötött sapka',helmet:'sisak',bald:'kopasz',ponytail:'lófarok',hood:'kapucni'},
  top:{hoodie:'kapucnis pulóver',tshirt:'póló',jacket:'dzseki',vest:'mellény',dress:'ruha',coat:'kabát',apron:'kötény',uniform:'egyenruha',sweater:'pulóver'},
  marks:{bandaid:'sebtapasz az arcán',pencil:'ceruza a sapkában',freckles:'szeplők',scar:'kis heg'},
  accessory:{none:'nincs',glasses:'szemüveg',scarf:'sál',badge:'kitűző',headphones:'fejhallgató',backpack:'hátizsák',lanyard:'nyakpánt',mustache:'bajusz',bowtie:'csokornyakkendő'},
  voices:{am_michael:'Michael · nyugodt, meleg férfi (alap)',am_adam:'Adam · mély férfi',am_eric:'Eric · magabiztos férfi',am_onyx:'Onyx · nagyon mély, lassú',bm_fable:'Fable · brit mesélő',bm_george:'George · brit, elegáns',am_liam:'Liam · fiatal férfi',af_heart:'Heart · meleg női',bf_emma:'Emma · nyugodt brit női',af_nova:'Nova · tiszta női'}};

 const arm=()=>{clearTimeout(poll);poll=setTimeout(()=>{if(on()&&currentApp==='agents')load();else arm();},S?.busy?6000:20000);};      // the timer is re-armed even while the page is not shown
 async function load(force){
  lastLoad=Date.now();
  try{const d=await op('series_stickman');const s=JSON.stringify(d);if(s!==sig||force){sig=s;S=d;projectAppData=d;if(!paTyping()||force)render();}}
  catch(e){S={error:e.message};render();}
  arm();
 }
 async function drawSheet(){
  if(sheetBusy)return;sheetBusy=true;
  try{sheet=(await op('series_stickman_sheet')).image;}catch(e){sheet=null;toast(e.message);}
  sheetBusy=false;if(on())render();
 }

 function render(){
  const box=$('projectAppView');if(!box||!on())return;
  if(Date.now()-lastLoad>4000&&!sheetBusy)setTimeout(()=>{if(on())load();},0);
  if(!['start','cast','episodes'].includes(projectAppPage))projectAppPage='start';
  const scroll=box.scrollTop;box.replaceChildren();box.classList.add('cs-app','ko-app');
  if(!S){box.append(el('p','hint','Betöltés…'));return;}
  if(S.error){box.append(el('p','pa-note',S.error));return;}
  const head=el('div','ko-head'),title=el('div','ko-title');
  title.append(el('h1','','Stickman stúdió'),el('p','',`Egy főszereplő, ${S.settings.main.name}, aki minden videóban egy teljesen új, kidolgozott történetbe kerül. A narrátor a nézőhöz beszél, mintha ő lenne a főszereplő („Hajnali kettő van. Konzerveket pakolsz…”).`));
  const meta=el('div','cs-meta');meta.append(el('span','cs-chip',S.episodes.length+' videó'));
  if(S.busy)meta.append(el('span','cs-chip live','Készül: '+(STEPS[S.step]||'videó')));
  head.append(title,meta);box.append(head);
  const tabs=el('nav','cs-tabs');for(const p of projectAppView.pages){const b=el('button','',p.label);b.setAttribute('aria-selected',String(p.id===projectAppPage));b.onclick=()=>go(p.id);tabs.append(b);}box.append(tabs);
  const page=el('div','cs-page ko-page');box.append(page);
  ({start,cast,episodes}[projectAppPage]||start)(page);
  box.scrollTop=scroll;
 }

 // ------------------------------------------------ Új videó
 function start(page){
  const cfg=S.settings,kind=pick.kind||cfg.kind;
  const c=card('Új videó');
  const row=el('div','se-pick');row.append(el('label','','Formátum'));
  for(const [id,label] of [['short','Short · álló 9:16'],['long','Hosszú · fekvő 16:9']]){const b=el('button','hub-target'+(kind===id?' on':''),label);b.onclick=()=>{pick.kind=id;render();};row.append(b);}
  c.append(row);
  const len=el('div','se-pick');
  if(kind==='short'){
   len.append(el('label','','Hossz (másodperc)'));
   const i=el('input');i.type='number';i.min=S.options.short.min;i.max=S.options.short.max;i.value=pick.seconds??cfg.short_seconds;i.oninput=()=>{pick.seconds=i.value;};len.append(i);
   len.append(el('span','hint',` ${S.options.short.min}–${S.options.short.max} mp · kb. ${Math.round((pick.seconds??cfg.short_seconds)*2.6)} szó narráció`));
  }else{
   len.append(el('label','','Hossz (perc)'));
   const i=el('input');i.type='number';i.min=S.options.long.min;i.max=S.options.long.max;i.value=pick.minutes??cfg.long_minutes;i.oninput=()=>{pick.minutes=i.value;};len.append(i);
   const m=Number(pick.minutes??cfg.long_minutes);len.append(el('span','hint',` ${S.options.long.min}–${S.options.long.max} perc · kb. ${Math.max(3,Math.round(m*60/70))} fejezet, ${Math.round(m*60*2.6)} szó`));
  }
  c.append(len);
  const topic=el('textarea');topic.rows=2;topic.placeholder='Saját téma (nem kötelező) – pl. „bezársz egy vidámparkba éjszakára, és reggelig ki kell jutnod”. Üresen: teljesen véletlen, új történet.';topic.value=pick.topic;topic.oninput=()=>{pick.topic=topic.value;};
  c.append(el('label','','Téma'),topic);
  const go_=run('Videó indítása',async()=>{await load(true);const r=await op('series_stickman_start',{kind,seconds:pick.seconds??cfg.short_seconds,minutes:pick.minutes??cfg.long_minutes,topic:pick.topic});pick.topic='';return r;});
  c.append(go_);
  if(S.busy&&(S.running||[]).length){
   const r0=S.running[0];c.append(el('p','hint',`Épp készül: ${r0.step} · ${r0.minutes} perce ${r0.status==='running'?'fut':'vár'}. Ha ez elakadt, leállíthatod.`));
   c.append(run('Folyamatban lévő videó leállítása',async()=>{for(const j of S.running)await call('job_cancel',{id:j.id,requestProject:project});toast('Leállítva. Pár másodperc múlva újat indíthatsz.');},'secondary'));
  }
  c.append(el('p','hint','Menet: történetterv → helyszínek festése (FLUX) → narráció és jelenetek fejezetenként → tárgyközelik → narráció, zene, effektek → animáció. Egy Short kb. 15–25 perc, egy 8 perces videó 1–2 óra a gépen.'));
  page.append(c);
  // Gyártósor (owner 16 Nov: until a deadline; 17 Nov: also by count, a whole night, mixed Short/long)
  const line=S.batch||{},g=card('Gyártósor · éjszakai és sorozatgyártás');
  const KIND={long:'hosszú, fekvő',short:'Short, álló',mix:'Short és hosszú váltogatva'};
  if(line.on){
   const until=new Date(line.until*1000).toLocaleTimeString('hu-HU',{hour:'2-digit',minute:'2-digit'});
   const goal=[line.count?line.count+' videó':'',line.deadline!==false?until+'-ig':''].filter(Boolean).join(' vagy ');
   g.append(el('p','',`Fut: egymás után készülnek a videók (${goal}) · ${KIND[line.kind]||''}${line.kind==='long'?' · '+line.minutes+' perc':line.kind==='short'?' · '+line.minutes+' mp':''}.`));
   g.append(el('p','',`Elindítva: ${(line.runs||[]).length}${line.count?' / '+line.count:''}, kész: ${line.made||0}. Egy videó kb. ${line.expected||'?'} perc a gépen.${line.deadline!==false?' Újat csak akkor kezd, ha még belefér.':''} A gép nem alszik el, amíg a sor fut (lehajtott fedélnél a MacBook mégis elalhat: tedd töltőre és hagyd nyitva).`));
   g.append(run('Gyártósor leállítása',()=>op('series_stickman_batch_stop'),'secondary'));
  }else{
   if(line.note)g.append(el('p','hint','Legutóbb: '+line.note));
   g.append(el('p','hint','Amint egy videó elkészül, indul a következő (mindig új, véletlen történettel, ha nem adsz témát). A kész videók a Publikálás oldalon várnak, feltölteni a sor nem tölt fel. Az Autopilóta Önműködés listájában is látszik, a főkapcsolóval szüneteltethető.'));
   const f={kind:'short',minutes:50,mode:'count',count:10,until:'07:00',topic:''};
   const r=el('div','se-pick');
   const k=el('select');options(k,[{value:'short',label:'Short, álló'},{value:'long',label:'Hosszú, fekvő'},{value:'mix',label:'Váltogatva (Short, hosszú)'}],f.kind);
   const m=el('input');m.type='number';m.value=f.minutes;m.style.width='80px';
   const ml=el('label','','Hossz (mp)');
   k.onchange=()=>{f.kind=k.value;m.hidden=ml.hidden=k.value==='mix';ml.textContent=k.value==='long'?'Hossz (perc)':'Hossz (mp)';m.value=f.minutes=k.value==='long'?8:50;};
   m.oninput=()=>{f.minutes=m.value;};
   r.append(el('label','','Mit gyártson'),k,ml,m);g.append(r);
   const r2=el('div','se-pick');
   const mode=el('select');options(mode,[{value:'count',label:'Ennyi videót'},{value:'time',label:'Egy időpontig'},{value:'night',label:'Egész éjszaka (reggelig)'}],f.mode);
   const cnt=el('input');cnt.type='number';cnt.min=1;cnt.max=40;cnt.value=f.count;cnt.style.width='80px';cnt.oninput=()=>{f.count=cnt.value;};
   const tm=el('input');tm.value=f.until;tm.style.width='80px';tm.oninput=()=>{f.until=tm.value;};
   const unit=el('span','hint','videó');
   const sync=()=>{f.mode=mode.value;cnt.hidden=unit.hidden=f.mode!=='count';tm.hidden=f.mode==='count';if(f.mode==='night'&&!/^0?[4-9]:/.test(f.until))tm.value=f.until='07:00';};
   mode.onchange=sync;sync();
   r2.append(el('label','','Meddig'),mode,cnt,unit,tm);g.append(r2);
   const topic=el('textarea');topic.rows=2;topic.placeholder='Téma (nem kötelező). Üresen minden videó teljesen új, véletlen történet.';topic.oninput=()=>{f.topic=topic.value;};
   g.append(topic);
   g.append(run('Gyártósor indítása',()=>op('series_stickman_batch',{kind:f.kind,minutes:f.minutes,topic:f.topic,count:f.mode==='count'?f.count:0,until:f.mode==='count'?'':f.until})));
   g.append(el('p','hint','Egy Short kb. 15–35 perc, egy 8 perces videó 1–2,5 óra ezen a gépen: 10 Short nagyjából egy éjszaka. Éjszakai módban a határidő a következő reggel; újat csak akkor kezd, ha még belefér.'));
  }
  page.append(g);
  const pilot=card('Mechanikai próba');
  pilot.append(el('p','hint','12 mp: két kéz egy fali kerék pontos fogópontjain, a kerék elfordul, a lámpa vált, a kattanás az érintkezésnél szól, egyetlen közös kamera. A mérések a kész képből és hangból készülnek; ez a vezérelt jelenetmotor bizonyítéka, nem történet.'));
  pilot.append(run('Próba készítése',async()=>{const r=await op('series_stickman_pilot');toast(r.message,!r.passed);const box=el('div');for(const c of r.checks)box.append(el('p',c.passed?'hint':'error-text',(c.passed?'✓ ':'✗ ')+c.name.replace(/_/g,' ')+' · '+c.value+' (határ: '+c.limit+')'));showModal('Mechanikai próba · mérések',box);},'secondary'));
  page.append(pilot);
  const d=card('Alapértelmezett hosszak');
  d.append(el('p','hint','Ezekkel indul a videó, ha a kérés (vagy az Autopilóta) nem mond mást.'));
  const r2=el('div','se-pick');
  const sh=el('input');sh.type='number';sh.min=S.options.short.min;sh.max=S.options.short.max;sh.value=cfg.short_seconds;
  const lo=el('input');lo.type='number';lo.min=S.options.long.min;lo.max=S.options.long.max;lo.value=cfg.long_minutes;
  const kd=el('select');options(kd,[{value:'short',label:'Alapból Short'},{value:'long',label:'Alapból hosszú videó'}],cfg.kind);
  r2.append(el('label','','Short (mp)'),sh,el('label','','Hosszú (perc)'),lo,kd);d.append(r2);
  d.append(run('Mentés',()=>op('series_stickman_save',{settings:{short_seconds:sh.value,long_minutes:lo.value,kind:kd.value}}),'secondary'));
  page.append(d);
 }

 // ------------------------------------------------ Szereplők
 function designForm(role,title,hint){
  const cfg=S.settings;draft=draft||{main:{...cfg.main},support:{...cfg.support},narrator:cfg.narrator};
  const d=draft[role],f=card(title,'se-form');if(d.hat_band===undefined)d.hat_band='#F1E6CF';f.append(el('p','hint',hint));
  const name=el('input');name.value=d.name;name.maxLength=20;name.oninput=()=>{d.name=name.value;};f.append(el('label','','Név (a feliratokban és itt)'),name);
  const sel=(label,key,list)=>{const s=el('select');options(s,list.map(v=>({value:v,label:LABEL[key][v]||v})),d[key]);s.onchange=()=>{d[key]=s.value;};f.append(el('label','',label),s);};
  sel('Haj vagy fejfedő','hair',S.options.hair);sel('Felső','top',S.options.top);sel('Kiegészítő','accessory',S.options.accessory);
  const mk=el('div','se-pick');mk.append(el('label','','Védjegyek'));
  for(const m of S.options.marks||[]){const on=(d.marks||[]).includes(m);const b=el('button','hub-target'+(on?' on':''),LABEL.marks[m]||m);b.onclick=()=>{d.marks=on?(d.marks||[]).filter(x=>x!==m):[...(d.marks||[]),m];render();};mk.append(b);}
  f.append(mk);
  const colours=el('div','se-pick');
  for(const [key,label] of [['top_colour','Felső színe'],['second_colour','Másodszín'],['hair_colour','Haj / sapka színe'],['hat_band','Sapka hajtása'],['skin','Fej színe']]){const i=el('input');i.type='color';i.value=d[key];i.oninput=()=>{d[key]=i.value.toUpperCase();};const w=el('label','se-colour');w.append(document.createTextNode(label+' '),i);colours.append(w);}
  f.append(colours);
  const eyes=el('select');options(eyes,[{value:'dot',label:'pontszem (semleges)'},{value:'round',label:'kerek szem'},{value:'sleepy',label:'félig lehunyt, fáradt'}],d.eyes);eyes.onchange=()=>{d.eyes=eyes.value;};f.append(el('label','','Szem'),eyes);
  const about=el('textarea');about.rows=2;about.value=d.about;about.oninput=()=>{d.about=about.value;};f.append(el('label','',role==='main'?'Ki ő (az író ebből tudja, milyen a karakter)':'Ki ő, milyen a személyisége'),about);
  return f;
 }
 function cast(page){
  const cfg=S.settings;
  const p=card('Karakterlap');
  p.append(el('p','hint','Kódból rajzolt stickmanek: minden videóban pixelre ugyanígy néznek ki. Mentés után frissítsd a lapot.'));
  if(sheet){const img=el('img','se-sheet');img.src=sheet;img.alt='Karakterlap';p.append(img);}
  p.append(button(sheetBusy?'Rajzolom…':(sheet?'↻ Karakterlap frissítése':'Karakterlap rajzolása'),drawSheet,'secondary'));
  page.append(p);
  const grid=el('div','cs-grid3');
  grid.append(designForm('main','Főszereplő','Ő a csatorna arca: minden videóban ő a „te”. A narráció sosem mondja ki a nevét.'));
  grid.append(designForm('support','Visszatérő társ','Minden történetben más szerepben bukkan fel (kolléga, idegen, szomszéd), de mindig ugyanúgy néz ki.'));
  page.append(grid);
  const v=card('Narrátor');
  const voice=el('select');options(voice,S.options.voices.map(x=>({value:x,label:LABEL.voices[x]||x})),draft.narrator);voice.onchange=()=>{draft.narrator=voice.value;};
  v.append(el('p','hint','Egy nyugodt mesélőhang, ahogy a referenciákban. Ha a Chatterbox Turbo telepítve van, ezt a hangszínt klónozza élethűre.'),voice);page.append(v);
  const row=el('div','cs-row');
  row.append(run('Szereplők mentése',async()=>{const r=await op('series_stickman_save',{settings:{main:draft.main,support:draft.support,narrator:draft.narrator}});draft=null;sheet=null;drawSheet();return r;}),
   button('Visszavonás',()=>{draft=null;render();},'secondary'));
  page.append(row);
  if(!sheet&&!sheetBusy)drawSheet();
 }

 // ------------------------------------------------ Videók
 function episodes(page){
  if(!S.episodes.length){page.append(el('p','hint','Még nincs stickman videó. A kész videók a Publikálás oldalon várnak, itt pedig a történetük gyűlik, hogy a következő mindig új legyen.'));return;}
  for(const e of S.episodes){const k=el('div','sw-moment');const top=el('div','sw-moment-top');
   top.append(el('b','',e.title||'Videó'),el('span','cs-chip',e.kind==='long'?'Hosszú · '+Math.round((e.seconds||0)/60)+' perc':'Short · '+(e.seconds||0)+' mp'),el('small','',e.finished?new Date(e.finished*1000).toLocaleDateString('hu-HU'):''));
   k.append(top,el('p','',e.premise||''));page.append(k);}
 }

 const loadBefore=loadProjectApp,renderBefore=renderProjectApp;
 loadProjectApp=async function(){if(on()){if(currentApp!=='agents')return;if(!S||S.error)await load(true);return;}return loadBefore();};
 renderProjectApp=function(){if(on()){if(!paTyping())render();return;}return renderBefore();};
 const syncBefore=syncProjectApp;
 syncProjectApp=function(){if(projectAppFor!==project){S=null;sig='';draft=null;sheet=null;}syncBefore();if(on())$('studioApp')?.classList.add('clip-mode');};
})();
