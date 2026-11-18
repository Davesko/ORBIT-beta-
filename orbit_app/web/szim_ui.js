/* Szimgyár (owner, 16 Nov): the project app of the physics-simulation factory. Pages: Gyártás (make videos now),
   Videótípusok (which recipes may be used), Preferenciák (looks, sounds, length), Videók (watch, approve or reject: the
   recipes learn from it). A function scope, so nothing here replaces the app's globals. */
(()=>{
 let S=null,poll=null,sig='',draft=null,ask={recipe:'',count:1,topic:''},open=null;
 const op=async(name,args={})=>(await call('project_app',{op:name,args:{project,...args}})).result;
 const on=()=>projectAppView?.app==='szim';
 const card=(title,cls='')=>{const c=el('section','cs-card '+cls);if(title)c.append(el('h3','',title));return c;};
 const go=page=>{projectAppPage=page;render();$('projectAppView').scrollTop=0;};
 const run=(label,fn,cls='primary')=>button(label,async()=>{const r=await fn();if(r?.message)toast(r.message);await load(true);},cls);
 const PAL={neon:'neon',tuz:'tűz',jeg:'jég',pasztell:'pasztell',szivarvany:'szivárvány',mono:'fekete-fehér'};
 const STATE={kesz:'új',jovahagyva:'jóváhagyva',elvetve:'elvetve'};
 const pretty=v=>PAL[v]||String(v).replaceAll('_',' ');

 async function load(force){
  try{const d=await op('szim_snapshot');const s=JSON.stringify(d);if(s!==sig||force){sig=s;S=d;projectAppData=d;if(!paTyping()||force)render();}}
  catch(e){S={error:e.message};render();}
  clearTimeout(poll);poll=setTimeout(()=>{if(on()&&currentApp==='agents')load();},S?.busy?.length?5000:20000);
 }
 function render(){
  const box=$('projectAppView');if(!box||!on())return;
  if(!['make','types','prefs','videos'].includes(projectAppPage))projectAppPage='make';
  const scroll=box.scrollTop;box.replaceChildren();box.classList.add('cs-app','ko-app');
  if(!S){box.append(el('p','hint','Betöltés…'));return;}
  if(S.error){box.append(el('p','pa-note',S.error));return;}
  draft=draft||JSON.parse(JSON.stringify(S.settings));
  const head=el('div','ko-head'),title=el('div','ko-title');
  title.append(el('h1','','Szimgyár'),el('p','','Fizikai szimulációs shortok: labdák, pályák, szabályok. A gép nyelvi modell nélkül, bevált receptekből gyártja őket, és a jóváhagyásaidból tanul.'));
  const meta=el('div','cs-meta');meta.append(el('span','cs-chip',S.videos.length+' videó'));
  if(S.busy.length)meta.append(el('span','cs-chip live','Készül: '+S.busy.length+' feladat'));
  head.append(title,meta);box.append(head);
  const tabs=el('nav','cs-tabs');for(const p of projectAppView.pages){const b=el('button','',p.label);b.setAttribute('aria-selected',String(p.id===projectAppPage));b.onclick=()=>go(p.id);tabs.append(b);}box.append(tabs);
  const page=el('div','cs-page ko-page');box.append(page);
  ({make,types,prefs,videos}[projectAppPage]||make)(page);
  box.scrollTop=scroll;
 }
 const enabled=id=>draft.recipes[id]!==false;

 function make(page){
  const c=card('Új videók');
  c.append(el('p','hint','Egy videó kb. 3–8 perc. A gyártás a Videótípusok és a Preferenciák szerint történik; közben nyugodtan használd az ORBIT-ot.'));
  const typeSel=el('select');options(typeSel,[{value:'',label:'Bármelyik bekapcsolt típus (a tanulás választ)'},...S.catalog.recipes.filter(r=>enabled(r.azon)).map(r=>({value:r.azon,label:r.ikon+' '+r.nev}))],ask.recipe);typeSel.onchange=()=>{ask.recipe=typeSel.value;};
  c.append(el('label','','Videótípus'),typeSel);
  const n=el('input');n.type='number';n.min=1;n.max=10;n.value=ask.count;n.oninput=()=>{ask.count=Number(n.value)||1;};c.append(el('label','','Hány videó'),n);
  const t=el('input');t.placeholder='Téma vagy kulcsszó (nem kötelező)';t.value=ask.topic;t.oninput=()=>{ask.topic=t.value;};c.append(el('label','','Téma'),t);
  c.append(run('Gyártás indítása',()=>op('szim_make',{recipe:ask.recipe,count:ask.count,topic:ask.topic})));
  c.append(run('Szabad ötlet (ügynökök, helyi modell)',()=>op('szim_ideas',{topic:ask.topic}),'secondary'));
  c.append(el('p','hint','Az első gomb bevált receptekből gyárt, modell nélkül. A második új ötletet találtat ki az ügynökökkel (ötlet, terv, bírálat, szimuláció): lassabb.'));
  page.append(c);
  if(S.busy.length){const b=card('Folyamatban');for(const j of S.busy)b.append(el('p','',(j.status==='running'?'▶ ':'… ')+j.label));page.append(b);}
  const last=S.videos.slice(0,3);if(last.length){const l=card('Legutóbbiak');for(const v of last)l.append(videoRow(v,true));page.append(l);}
 }

 function types(page){
  const c=card('Videótípusok');
  c.append(el('p','hint','Itt dől el, mely típusokból gyárthat a rendszer. A kikapcsolt típus nem készül. A típusokat a jóváhagyásaid szerint egyre jobban választja.'));
  page.append(c);
  for(const r of S.catalog.recipes){
   const st=S.stats[r.azon]||{made:0,approved:0,rejected:0},k=card('','se-form');
   const top=el('div','sw-moment-top');top.append(el('b','',r.ikon+' '+r.nev),el('span','cs-chip',`${st.made} videó · ${st.approved} jóváhagyva · ${st.rejected} elvetve`));
   const lab=el('label','se-colour'),ch=el('input');ch.type='checkbox';ch.checked=enabled(r.azon);ch.onchange=()=>{draft.recipes[r.azon]=ch.checked;};lab.append(ch,document.createTextNode(' Használható'));
   k.append(top,el('p','hint',r.leiras.slice(0,420)+(r.leiras.length>420?'…':'')),lab,button('Egy ilyen most',async()=>{const x=await op('szim_make',{recipe:r.azon,count:1});toast(x.message);await load(true);},'secondary'));
   page.append(k);
  }
  const row=el('div','cs-row');row.append(run('Típusok mentése',()=>op('szim_save',{settings:{recipes:draft.recipes}}).then(r=>{draft=null;return r;})));page.append(row);
 }

 function multi(c,label,key,list,hint){
  const w=el('div','se-pick');w.append(el('label','',label+(hint?' – '+hint:'')));
  for(const v of list){const on=draft[key].includes(v);const b=el('button','hub-target'+(on?' on':''),pretty(v));b.onclick=()=>{draft[key]=on?draft[key].filter(x=>x!==v):[...draft[key],v];render();};w.append(b);}
  c.append(w);
 }
 function prefs(page){
  const l=card('Kinézet');
  l.append(el('p','hint','Ha semmit sem jelölsz be egy listában, bármi jöhet. Ha bejelölsz valamit, csak abból választ a gyár.'));
  multi(l,'Színvilág','palettes',S.catalog.palettes);
  l.append(el('p','hint','Hang: nem kell állítani. Minden videó alá a legfelkapottabb (top viral) TikTok-dal kerül, az ütközéseken pedig a mai népszerű mém-hangok szólnak. A rendszer magától frissíti őket. Az első gyártás emiatt pár percig tovább tart.'));
  page.append(l);
  const h=card('Hossz és darabszám');
  for(const [key,label] of [['seconds_min','Legrövidebb videó (mp)'],['seconds_max','Leghosszabb videó (mp)'],['batch','Alapértelmezett darabszám egy gyártásnál']]){const i=el('input');i.type='number';i.value=draft[key];i.oninput=()=>{draft[key]=Number(i.value);};h.append(el('label','',label),i);}
  page.append(h);
  const row=el('div','cs-row');row.append(run('Preferenciák mentése',()=>op('szim_save',{settings:draft}).then(r=>{draft=null;return r;})),button('Visszavonás',()=>{draft=null;render();},'secondary'));page.append(row);
 }

 function videoRow(v,compact){
  const k=el('div','sw-moment'),top=el('div','sw-moment-top');
  top.append(el('b','',v.title),el('span','cs-chip',STATE[v.state]||v.state),el('small','',new Date(v.created*1000).toLocaleString('hu-HU')));
  k.append(top,el('p','hint',[v.recipe,v.seconds&&Math.round(v.seconds)+' mp',v.balls&&v.balls+' labda',v.quality&&'minőség '+v.quality+'/10'].filter(Boolean).join(' · ')));
  if(open===v.id){
   const media=el('div','publication-media'),video=el('video');video.controls=true;video.preload='metadata';video.setAttribute('playsinline','');video.style.maxHeight='520px';media.append(video);k.append(media);
   playableMedia({id:v.artifact,project}).then(u=>{if(video.isConnected){video.src=u;video.load();}}).catch(()=>media.append(el('p','hint','Az előnézet nem tölthető be.')));
  }
  const row=el('div','cs-row');
  row.append(button(open===v.id?'Bezár':'▶ Megnézem',()=>{open=open===v.id?null:v.id;render();},'secondary'),button('Megnyitás a Macen',()=>call('open_artifact',{id:v.artifact}),'secondary'));
  if(!compact){
   const note=el('input');note.placeholder='Megjegyzés (mi tetszett / mi hibás) – ebből tanul';note.value=v.note;
   const rate=state=>run(state==='jovahagyva'?'✓ Jó':state==='elvetve'?'✗ Elvetem':'↺ Visszaállít',()=>op('szim_rate',{id:v.id,state,note:note.value}),state==='jovahagyva'?'primary':'secondary');
   k.append(row,note);const r2=el('div','cs-row');r2.append(rate('jovahagyva'),rate('elvetve'));if(v.state!=='kesz')r2.append(rate('kesz'));k.append(r2);
  }else k.append(row);
  return k;
 }
 function videos(page){
  if(!S.videos.length){page.append(el('p','hint','Még nincs videó. A Gyártás oldalon indíthatsz.'));return;}
  for(const v of S.videos)page.append(videoRow(v,false));
 }

 const loadBefore=loadProjectApp,renderBefore=renderProjectApp;
 loadProjectApp=async function(){if(on()){if(currentApp!=='agents')return;if(!S||S.error)await load(true);return;}return loadBefore();};
 renderProjectApp=function(){if(on()){if(!paTyping())render();return;}return renderBefore();};
 const syncBefore=syncProjectApp;
 syncProjectApp=function(){if(projectAppFor!==project){S=null;sig='';draft=null;open=null;}syncBefore();if(on())$('studioApp')?.classList.add('clip-mode');};
})();
