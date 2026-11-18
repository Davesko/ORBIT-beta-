/* Videoklip stúdió (owner, 12 Nov): the music video project's own Műhely app. Every field is editable and saved by itself;
   the AI director, FLUX pictures and the location search run as background jobs and fill the same clip. */
{
 let clipId=null,clipData=null,clipTimer=null,clipPoll=null;
 const huf=n=>Math.round(Number(n)||0).toLocaleString('hu-HU')+' Ft';
 const tc=s=>{s=Math.max(0,Math.round(Number(s)||0));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');};
 const op=async(name,args={})=>(await call('project_app',{op:name,args})).result;
 const img=id=>{const i=el('img');i.src=mediaURL({id,project});i.loading='lazy';i.alt='';return i;};

 async function clipLoad(){
  let same=false;
  try{const d=await op('clip_snapshot',{clip:clipId});const sig=JSON.stringify(d);same=sig===clipLoad.sig&&!!clipData&&!clipData.error;clipLoad.sig=sig;clipData=d;clipId=d.clip?.id||null;projectAppData=d;}
  catch(e){clipData={error:e.message};}
  if(!same)clipRender();
  clearTimeout(clipPoll);if(clipData?.running?.length)clipPoll=setTimeout(()=>{if(projectAppView?.app==='clip'&&!paTyping())clipLoad();else if(projectAppView?.app==='clip')clipPoll=setTimeout(clipLoad,4000);},5000);
 }
 // A field edit is saved half a second after the last key; the clip on screen is updated in place.
 function patch(fields,redraw=false){
  if(!clipData?.clip)return;Object.assign(clipData.clip,fields);
  clearTimeout(clipTimer);clipTimer=setTimeout(async()=>{try{const r=await op('clip_save',{clip:clipData.clip.id,patch:fields});clipData.clip=r.clip;clipData.budget=r.budget;$('clipSaved')&&($('clipSaved').textContent='Mentve');if(redraw)clipRender();else updateTotals();}catch(e){toast(e.message,true);}},redraw?10:500);
  $('clipSaved')&&($('clipSaved').textContent='Mentés…');
 }
 function updateTotals(){const b=clipData?.budget;if(!b)return;document.querySelectorAll('[data-clip-total]').forEach(n=>n.textContent=huf(b.total));}
 const input=(value,on,ph='',cls='')=>{const i=el('input',cls);i.value=value??'';i.placeholder=ph;i.oninput=()=>on(i.value);return i;};
 const area=(value,on,ph='',rows=4,cls='')=>{const t=el('textarea',cls);t.value=value??'';t.placeholder=ph;t.rows=rows;t.oninput=()=>on(t.value);return t;};
 const grow=t=>{const fit=()=>{t.style.height='auto';t.style.height=Math.max(t.scrollHeight+2,38)+'px';};t.addEventListener('input',fit);requestAnimationFrame(fit);return t;};
 const card=(title,cls='')=>{const c=el('section','cs-card '+cls);if(title)c.append(el('h3','',title));return c;};
 const ai=(label,fn,cls='primary')=>button(label,()=>act(async()=>{const r=await fn();toast(r?.message||'Elindult.');await clipLoad();}),cls+' cs-ai');
 // The budget is added up here as well, so every figure follows a key stroke at once (owner 12 Nov: "nem real time").
 function sums(c){const by={};let sub=0;for(const l of c.budget.lines){const v=(Number(l.qty)||0)*(Number(l.rate)||0);sub+=v;const k=l.category||'Egyéb';by[k]=(by[k]||0)+v;}
  const reserve=sub*(Number(c.budget.contingency)||0)/100,total=Math.round(sub+reserve),cap=c.budget.cap||null;return {subtotal:Math.round(sub),reserve:Math.round(reserve),total,by_category:by,cap,over:!!(cap&&total>cap)};}
 function liveBudget(c){const b=sums(c);if(clipData)clipData.budget=Object.assign(clipData.budget||{},b);document.querySelectorAll('[data-clip-total]').forEach(n=>n.textContent=huf(b.total));
  const cats=document.getElementById('csCats');if(cats)drawCats(cats,b);const capNote=document.getElementById('csCapNote');if(capNote)drawCap(capNote,b);return b;}
 function drawCats(host,b){host.replaceChildren();for(const [k,v] of Object.entries(b.by_category)){const r=el('div','cs-cat');r.append(el('span','',k),el('b','',huf(v)));const bar=el('i');bar.style.width=(b.subtotal?v/b.subtotal*100:0)+'%';r.append(bar);host.append(r);}}
 function drawCap(host,b){host.className=b.cap?(b.over?'cs-over':'cs-under'):'';host.textContent=b.cap?(b.over?'Túllépi a keretet '+huf(b.total-b.cap)+'-tal. Kérj új tervet, vagy vegyél ki tételeket.':'A keretben marad · '+huf(b.cap-b.total)+' marad.'):'';}
 // A picture opens large; arrows or keys step through the same set (owner 12 Nov).
 function lightbox(list,index){
  list=list.filter(x=>x.id);if(!list.length)return;let i=Math.max(0,Math.min(index,list.length-1));
  const box=el('div','cs-lightbox'),pic=el('img'),cap=el('p','cs-lb-cap'),prev=button('‹',()=>go(-1),'cs-lb-nav prev'),next=button('›',()=>go(1),'cs-lb-nav next'),close=button('×',()=>end(),'cs-lb-close');
  const show=()=>{pic.src=mediaURL({id:list[i].id,project});cap.textContent=(list.length>1?(i+1)+' / '+list.length+' · ':'')+(list[i].caption||'');prev.hidden=next.hidden=list.length<2;};
  const go=d=>{i=(i+d+list.length)%list.length;show();};
  const key=e=>{if(e.key==='Escape')end();if(e.key==='ArrowRight')go(1);if(e.key==='ArrowLeft')go(-1);};
  const end=()=>{document.removeEventListener('keydown',key,true);box.remove();};
  box.onclick=e=>{if(e.target===box)end();};document.addEventListener('keydown',key,true);
  box.append(pic,cap,prev,next,close);document.body.append(box);show();
 }
 const zoomable=(node,list,i)=>{node.classList.add('cs-zoom');node.title='Nagyítás';node.onclick=e=>{e.stopPropagation();lightbox(list,i);};return node;};

 function clipRender(){
  const box=$('projectAppView'),app=projectAppView;if(!box||!app||app.app!=='clip')return;
  const scroll=box.scrollTop,kept=new Map([...box.querySelectorAll('[data-keep]')].map(n=>[n.dataset.keep,n]));box.replaceChildren();box.classList.add('cs-app');
  const d=clipData;
  if(!d){box.append(el('p','hint','A videoklip-tervek betöltése…'));return;}
  if(d.error){box.append(el('p','pa-note',d.error));return;}
  // Header: the clips as pills, the open clip's title, its total and what the AI is doing.
  const head=el('header','cs-head'),pills=el('div','cs-pills');
  for(const c of d.clips){const b=el('button','cs-pill'+(c.id===clipId?' on':''),c.title||'Névtelen');b.onclick=()=>{clipId=c.id;clipLoad();};pills.append(b);}
  const addBox=el('span','cs-add'),addIn=el('input','cs-add-input');addIn.placeholder='A klip címe, Enter';addIn.hidden=true;
  const create=()=>act(async()=>{const r=await op('clip_create',{title:addIn.value.trim()||'Új videoklip'});clipData=r;clipId=r.clip.id;projectAppPage='overview';clipRender();});
  addIn.onkeydown=e=>{if(e.key==='Enter')create();if(e.key==='Escape'){addIn.hidden=true;}};
  addBox.append(button('＋ Új klip',()=>{addIn.hidden=false;addIn.focus();},'cs-pill add'),addIn);pills.append(addBox);
  head.append(pills);box.append(head);
  if(!d.clip){const empty=card('','cs-empty');empty.append(el('h2','','Az első videoklipod'),el('p','','Add meg a zenét és egy irányt; a Rendező koncepciót, sztorit, moodboardot, storyboardot, helyszíneket és költségvetést készít. Mindent átírhatsz.'),button('Új videoklip indítása',()=>act(async()=>{const r=await op('clip_create',{title:'Új videoklip'});clipData=r;clipId=r.clip.id;projectAppPage='song';clipRender();}),'primary'));box.append(empty);return;}
  const c=d.clip,title=el('div','cs-title');
  title.append(input(c.title,v=>patch({title:v}),'A klip címe','cs-title-input'),input(c.artist,v=>patch({artist:v}),'Előadó','cs-artist-input'));
  const meta=el('div','cs-meta'),total=el('span','cs-chip money');total.dataset.clipTotal='1';total.textContent=huf(d.budget?.total);
  meta.append(total,el('span','cs-chip',c.song?.name?('♫ '+c.song.name):'Nincs zene'),el('span','cs-saved','Mentve'));meta.lastChild.id='clipSaved';
  if(d.running.length)meta.append(el('span','cs-chip live',d.running.map(r=>({clip_song:'Zene elemzése',clip_think:'A Rendező gondolkodik',clip_images:'Képek készülnek',clip_locations:'Helyszínkeresés'})[r.task]+(r.status==='queued'?' · sorban':'…')).join(' · ')));
  const bar=el('div','cs-titlebar');bar.append(title,meta);box.append(bar);
  const badge={concept:c.concepts.length||'',moodboard:c.moodboard.length?c.moodboard.filter(m=>m.artifact).length+'/'+c.moodboard.length:'',storyboard:c.storyboard.length?c.storyboard.filter(x=>x.artifact).length+'/'+c.storyboard.length:'',
   locations:c.locations.filter(l=>l.picked).length?'✓':c.locations.length||'',budget:d.budget?.cap?(d.budget.over?'!':'✓'):''};
  const tabs=el('nav','cs-tabs');for(const p of app.pages){const b=el('button','',p.label);if(badge[p.id])b.append(el('em','cs-badge'+(badge[p.id]==='!'?' bad':''),String(badge[p.id])));b.setAttribute('aria-selected',String(p.id===projectAppPage));b.onclick=()=>{projectAppPage=p.id;clipRender();box.scrollTop=0;};tabs.append(b);}box.append(tabs);
  const page=el('div','cs-page');box.append(page);
  if(c.replanning)page.append(el('p','cs-banner','✦ A Rendező a(z) „'+c.replanning+'” koncepcióra tervezi újra a sztorit, a moodboardot, a storyboardot és a költségvetést. A korábbi terv a Koncepció fülön, a „Korábbi tervek” alatt visszaállítható.'));
  for(const f of d.failed||[]){const bad=el('div','cs-banner bad');bad.append(el('span','','Nem sikerült: '+({clip_think:'a tervezés',clip_concepts:'az új koncepciók',clip_images:'a képek',clip_locations:'a helyszínkeresés',clip_song:'a zene elemzése'}[f.task]||f.task)+' · '+String(f.error||'').slice(0,160)),
   ai('Újra',()=>op({clip_think:'clip_full',clip_concepts:'clip_concepts',clip_images:'clip_images',clip_locations:'clip_locations'}[f.task]||'clip_full',{clip:c.id}),'secondary'));page.append(bad);}
  ({overview,song,concept,moodboard,storyboard,locations,budget,notes}[projectAppPage]||overview)(page,c,d);
  // The song player that was on screen stays the same element, so playback is not reset (owner 12 Nov).
  for(const fresh of box.querySelectorAll('[data-keep]')){const old=kept.get(fresh.dataset.keep);if(old)fresh.replaceWith(old);}
  box.scrollTop=scroll;
 }

 function quickStart(c,d){
  const q=card('Kezdjük el','cs-quick');q.append(el('p','hint','Három dolog kell, utána egy gombbal megkapod a teljes tervet: koncepciókat, sztorit, moodboardot, storyboardot, helyszíneket és költségvetést.'));
  const s1=el('div','cs-qstep');s1.append(el('b','','1'),el('div',''));s1.lastChild.append(el('strong','','Zene'),el('p','',c.song?.name?('♫ '+c.song.name+(c.song.duration?' · '+tc(c.song.duration):' · elemzés…')):'Még nincs zene.'),
   button(c.song?.name?'Másik zene':'Zene importálása',()=>act(async()=>{const r=await call('import_media_file');if(r.cancelled)return;const before=new Set(d.audio.map(a=>a.id));const fresh=(await op('clip_snapshot',{clip:c.id})).audio.find(a=>!before.has(a.id));if(fresh){clipData=await op('clip_song',{clip:c.id,artifact:fresh.id});clipRender();}}),'secondary'));
  const s2=el('div','cs-qstep');s2.append(el('b','','2'),el('div',''));s2.lastChild.append(el('strong','','Irány'),area(c.direction,v=>patch({direction:v}),'Hangulat, stílus, kik szerepeljenek, mit kerülj — a Rendező ezt keretként kezeli, az ötletet ő találja ki.',3));
  const s3=el('div','cs-qstep');s3.append(el('b','','3'),el('div',''));const capIn=input(c.budget.cap||'',v=>{c.budget.cap=Number(String(v).replace(/\D/g,''))||null;patch({budget:c.budget});},'pl. 250000','cs-num');capIn.type='number';
  s3.lastChild.append(el('strong','','Keret (Ft)'),capIn);
  q.append(s1,s2,s3,el('div','cs-row'));q.lastChild.append(ai('✦ Tervezd meg teljesen',()=>op('clip_full',{clip:c.id})));
  return q;
 }
 function overview(page,c,d){
  if(!c.concepts.length){page.append(quickStart(c,d));return;}
  const go=id=>{projectAppPage=id;clipRender();$('projectAppView').scrollTop=0;};
  const head=(title,id,extra)=>{const h=el('div','cs-dh');h.append(el('h3','',title));if(extra)h.append(extra);if(id)h.append(button('Megnyitás →',()=>go(id),'text-button'));return h;};
  const k=c.concepts[c.chosen||0]||{},b=sums(c);
  const moodList=c.moodboard.filter(m=>m.artifact).map(m=>({id:m.artifact,caption:m.note||m.prompt}));
  const boardList=c.storyboard.filter(s=>s.artifact).map(s=>({id:s.artifact,caption:tc(s.start)+'–'+tc(s.end)+' · '+(s.shot||'')+' · '+(s.description||'')}));
  // 1. Hero: the key picture, the idea in one line, the song and the money at a glance.
  const hero=el('section','cs-dash-hero');const cover=moodList[0]||(k.artifact?{id:k.artifact,caption:k.title}:null);
  const pic=el('div','cs-dash-cover');if(cover)pic.append(zoomable(img(cover.id),moodList.length?moodList:[cover],0));else pic.append(el('span','','♫'));
  const text=el('div','cs-dash-text');
  text.append(el('small','cs-kicker',(k.title?'KONCEPCIÓ · '+k.title:'KONCEPCIÓ')+(c.replanning?' · újratervezés…':'')),el('h2','',c.story?.logline||k.logline||''));
  if(c.mood)text.append(el('p','cs-mood','Hangulat: '+c.mood));
  if(c.palette?.length){const sw=el('div','cs-swatches');for(const col of c.palette){const i=el('i');i.style.background=col;i.title=col;sw.append(i);}text.append(sw);}
  const facts=el('div','cs-facts');
  const fact=(label,value,id)=>{const f=el('button','cs-fact');f.append(el('small','',label),el('b','',value));if(id)f.onclick=()=>go(id);facts.append(f);};
  fact('Zene',c.song?.name?(tc(c.song.duration)+' · '+(c.song.bpm?Math.round(c.song.bpm)+' BPM':'?')):'nincs','song');
  fact('Költség',huf(b.total)+(b.cap?' / '+huf(b.cap):''),'budget');
  fact('Snittek',String(c.storyboard.length),'storyboard');
  fact('Helyszín',(c.locations.find(l=>l.picked)?.name||c.location_needs.map(n=>n.type).filter(Boolean).join(', ')||'—').slice(0,40),'locations');
  text.append(facts);
  const acts=el('div','cs-actions');acts.append(ai('✦ Tervezd meg teljesen',()=>op('clip_full',{clip:c.id})),ai('Képek rajzolása',()=>op('clip_images',{clip:c.id}),'secondary'),
   button('Gyártási dosszié',()=>act(async()=>{const r=await op('clip_export',{clip:c.id});toast(r.message);await call('open_artifact',{id:r.artifact,requestProject:project});}),'secondary'));text.append(acts);
  hero.append(pic,text);page.append(hero);
  const grid=el('div','cs-dash');page.append(grid);
  // 2. Story with its beats along the song.
  const story=card('','cs-d-story');story.append(head('Sztori','concept'),el('p','',(c.story?.synopsis||'').slice(0,600)||'Még nincs sztori.'));
  if(c.story?.beats?.length){const tl=el('ol','cs-beatline');for(const x of c.story.beats){const li=el('li');li.append(el('b','',x.time||''),el('span','',x.text||''));tl.append(li);}story.append(tl);}
  grid.append(story);
  // 3. Budget against the ceiling, by category.
  const money=card('','cs-d-money');money.append(head('Költségvetés','budget'));
  const bigm=el('div','cs-d-total');bigm.append(el('strong','',huf(b.total)));if(b.cap){bigm.append(el('span','',' / '+huf(b.cap)));const bar=el('div','cs-capbar'+(b.over?' over':''));const fill=el('i');fill.style.width=Math.min(100,b.total/b.cap*100)+'%';bar.append(fill);money.append(bigm,bar);}else money.append(bigm);
  const cats=el('div','cs-cats');drawCats(cats,b);money.append(cats);grid.append(money);
  // 4. Moodboard strip.
  const mood=card('','cs-d-mood');mood.append(head('Moodboard','moodboard',el('em','cs-badge',moodList.length+'/'+c.moodboard.filter(m=>m.prompt||m.artifact).length)));
  const strip=el('div','cs-strip');moodList.slice(0,8).forEach((m,i)=>strip.append(zoomable(img(m.id),moodList,i)));if(!moodList.length)strip.append(el('p','hint','Még nincsenek képek.'));mood.append(strip);grid.append(mood);
  // 5. Storyboard as a film strip along the song.
  const board=card('','cs-d-board');board.append(head('Storyboard','storyboard'));
  const film=el('div','cs-film');c.storyboard.forEach((s,i)=>{const f=el('figure','cs-frame');const p=el('div','cs-frame-pic');if(s.artifact)p.append(zoomable(img(s.artifact),boardList,boardList.findIndex(x=>x.id===s.artifact)));else p.append(el('span','',String(i+1)));
   f.append(p,el('figcaption','',tc(s.start)+' · '+(s.shot||'')));film.append(f);});if(!c.storyboard.length)film.append(el('p','hint','Még nincs storyboard.'));board.append(film);grid.append(board);
  // 6. Places and crew.
  const place=card('','cs-d-place');place.append(head('Helyszínek','locations'));
  const picked=c.locations.filter(l=>l.picked);for(const l of picked)place.append(el('p','cs-d-line','✓ '+l.name+(l.price_day?' · '+huf(l.price_day)+'/nap':'')));
  if(!picked.length)for(const n of c.location_needs)place.append(el('p','cs-d-line','○ '+(n.type||'')+' · '+(n.city||'')+' · '+(n.days||1)+' nap'));
  if(!picked.length&&!c.location_needs.length)place.append(el('p','hint','Még nincs helyszín.'));grid.append(place);
  const crew=card('','cs-d-crew');crew.append(head('Stáb és szereplők','budget'));
  const people=c.budget.lines.filter(l=>['Stáb','Szereplők'].includes(l.category));for(const l of people)crew.append(el('p','cs-d-line',l.item+' · '+(l.qty||1)+' '+(l.unit||'')));if(!people.length)crew.append(el('p','hint','Még nincs stáb.'));grid.append(crew);
  // 7. Where it stands, and the log.
  const steps=card('','cs-d-steps');steps.append(head('Hol tart'));
  const moodDone=moodList.length,sbDone=boardList.length;
  for(const [ok,label,id] of [[!!c.song?.artifact,'Zene','song'],[!!c.direction,'Irány','song'],[!!c.concepts.length,'Koncepció','concept'],[c.moodboard.length&&moodDone>=c.moodboard.filter(m=>m.prompt).length,'Moodboard','moodboard'],[c.storyboard.length&&sbDone===c.storyboard.length,'Storyboard','storyboard'],[c.locations.some(l=>l.picked),'Helyszín','locations'],[c.budget.lines.length&&!b.over,'Költségvetés','budget']]){const r=el('button','cs-step'+(ok?' ok':''));r.append(el('b','',ok?'✓':'○'),el('span','',label));r.onclick=()=>go(id);steps.append(r);}
  grid.append(steps);
  if(c.log?.length){const log=card('','cs-d-log');log.append(head('Napló'));for(const l of c.log.slice(0,6))log.append(el('p','',new Date(l.at*1000).toLocaleString('hu-HU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})+' · '+l.text));grid.append(log);}
 }

 function song(page,c,d){
  const music=card('Zene');
  if(c.song?.artifact){const a={id:c.song.artifact,project,kind:'audio',name:c.song.name};const player=mediaCard(a);player.dataset.keep='song-'+a.id;music.append(player);}
  const row=el('div','cs-row'),pick=el('select');pick.append(new Option('Válassz zenét a projekt fájljai közül…',''));for(const a of d.audio)pick.append(new Option(a.name,a.id,false,a.id===c.song?.artifact));
  pick.onchange=()=>pick.value&&act(async()=>{clipData=await op('clip_song',{clip:c.id,artifact:pick.value});clipRender();toast('A zene elemzése elindult.');});
  row.append(pick,button('Zene importálása a Macről',()=>act(async()=>{
   // The media picker (WAV, MP3, M4A, AIFF, FLAC… up to 2 GB): the text importer refused audio files (12 Nov).
   const r=await call('import_media_file');if(r.cancelled)return;
   const before=new Set(d.audio.map(a=>a.id));const fresh=(await op('clip_snapshot',{clip:c.id})).audio.find(a=>!before.has(a.id));
   if(fresh){clipData=await op('clip_song',{clip:c.id,artifact:fresh.id});clipRender();toast('A zene a klipre került; az elemzés elindult.');}else{await clipLoad();toast('Importálva; válaszd ki a listából.');}
  }),'secondary'));music.append(row);
  if(c.song?.duration){
   const info=el('p','hint',tc(c.song.duration)+' · '+(c.song.bpm?Math.round(c.song.bpm)+' BPM':'tempó ismeretlen')+' · '+c.song.parts.length+' rész');music.append(info);
   // Energy over time, with the detected parts under it.
   const energy=c.song.energy||[],w=600,h=70,svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox',`0 0 ${w} ${h+26}`);svg.classList.add('cs-energy');
   if(energy.length){const pts=energy.map((v,i)=>`${(i/(energy.length-1||1)*w).toFixed(1)},${(h-v*h).toFixed(1)}`).join(' ');svg.innerHTML=`<polygon points="0,${h} ${pts} ${w},${h}" class="area"/><polyline points="${pts}" class="line"/>`;}
   svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('preserveAspectRatio','none');
   // The parts as a row of boxes: each label fits its own box (shortened, full text on hover), nothing runs out (owner 12 Nov).
   const parts=el('div','cs-parts');for(const p of c.song.parts){const box=el('div','cs-part'+(/Refrén/.test(p.label)?' hot':''));box.style.flexGrow=String(Math.max(.5,p.end-p.start));
    box.title=p.label+' · '+tc(p.start)+'–'+tc(p.end);box.append(el('b','',p.label.split(' ')[0]),el('span','',tc(p.start)));parts.append(box);}
   music.append(svg,parts);
  }else if(c.song?.artifact)music.append(el('p','hint','Elemzés folyamatban…'));
  page.append(music);
  const dir=card('Irány · mit szeretnél');dir.append(el('p','hint','Hangulat, történet, stílus, kerülendő dolgok, költségkeret, szereplők — bármi, amit a Rendezőnek tudnia kell.'),area(c.direction,v=>patch({direction:v}),'Például: éjszakai Budapest, magányos főszereplő, VHS-hatás, max. 800 ezer Ft, egy forgatási nap.',5));
  const focus=input('',()=>{},'Opcionális: mire figyeljen most (pl. „csak a sztorit írd újra, legyen sötétebb”)','cs-focus');
  const go=el('div','cs-row');go.append(focus,ai('✦ Gondold végig',()=>op('clip_think',{clip:c.id,focus:focus.value})));dir.append(go);page.append(dir);
  const lyr=card('Dalszöveg');lyr.append(area(c.song?.lyrics,v=>{c.song.lyrics=v;patch({lyrics:v});},'Másold be a dalszöveget; a Rendező a sorokhoz igazítja a képeket.',8));page.append(lyr);
 }

 function concept(page,c){
  const list=card('Koncepciók');const grid=el('div','cs-grid3');
  const conceptList=c.concepts.filter(k=>k.artifact).map(k=>({id:k.artifact,caption:k.title+' · '+(k.look||k.logline||'')}));
  c.concepts.forEach((k,i)=>{const b=el('article','cs-concept'+((c.chosen||0)===i?' on':''));const pv=el('div','cs-concept-pic');if(k.artifact)pv.append(zoomable(img(k.artifact),conceptList,conceptList.findIndex(x=>x.id===k.artifact)));else pv.append(el('span','',k.look?'✧':''));
   const more=el('details','cs-more');more.append(el('summary','','Részletek'),el('p','',k.logline),k.look?el('p','cs-look','Látvány: '+k.look):'',el('em','',k.why||''));
   b.append(pv,el('small','',(c.chosen||0)===i?(c.replanning?'ÚJRATERVEZÉS…':'EZ A TERV ALAPJA'):'Koncepció '+(i+1)),el('strong','',k.title),more);
   if((c.chosen||0)!==i)b.append(ai('Ebből tervezz',()=>op('clip_plan_concept',{clip:c.id,concept:k.id}),'secondary'));grid.append(b);});
  if(!c.concepts.length)grid.append(el('p','hint','Még nincs koncepció. A Zene és irány fülön kérd meg a Rendezőt.'));
  const more=el('div','cs-row'),mf=input('',()=>{},'Opcionális: milyen irányba (pl. „merészebb”, „humoros”, „természetben”)','cs-focus');
  more.append(mf,ai('✦ Több koncepció',()=>op('clip_concepts',{clip:c.id,focus:mf.value}),'secondary'),ai('Előnézeti képek',()=>op('clip_images',{clip:c.id,which:'concepts'}),'secondary'));list.append(el('p','hint','Az „Ebből tervezz” a koncepcióhoz igazítja a sztorit, a moodboardot, a storyboardot, a helyszíneket és a költségvetést, és újrarajzolja a képeket. A mostani terv változatként megmarad.'),grid,more);page.append(list);
  if(c.versions?.length){const v=card('Korábbi tervek');for(const x of c.versions){const r=el('div','cs-row cs-version');r.append(el('span','',new Date(x.at*1000).toLocaleString('hu-HU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})+' · '+x.title),button('Visszaállítás',()=>act(async()=>{const res=await op('clip_restore',{clip:c.id,version:x.id});clipData.clip=res.clip;clipData.budget=res.budget;clipRender();toast('Visszaállítva.');}),'secondary'));v.append(r);}page.append(v);}
  const st=card('Sztori');st.append(el('label','','Egy mondatban'),input(c.story?.logline,v=>{c.story.logline=v;patch({story:c.story});},'Logline'),el('label','','Történet'),area(c.story?.synopsis,v=>{c.story.synopsis=v;patch({story:c.story});},'A klip története',6));
  st.append(el('label','','Ütemek a zenéhez'));const beats=el('div','cs-beats');
  const drawBeats=()=>{beats.replaceChildren();(c.story.beats||[]).forEach((b,i)=>{const r=el('div','cs-beat');r.append(input(b.time,v=>{b.time=v;patch({story:c.story});},'0:00-0:20','cs-time'),area(b.text,v=>{b.text=v;patch({story:c.story});},'Mi történik',2),button('×',()=>{c.story.beats.splice(i,1);patch({story:c.story});drawBeats();},'text-button'));beats.append(r);});};
  drawBeats();st.append(beats,button('＋ Ütem',()=>{(c.story.beats=c.story.beats||[]).push({time:'',text:''});drawBeats();},'secondary'));
  st.append(ai('✦ Írd újra a sztorit',()=>op('clip_think',{clip:c.id,focus:'Írd újra a sztorit és az ütemeket a kiválasztott koncepció alapján: '+(c.concepts[c.chosen||0]?.title||'')}),'secondary'));page.append(st);
  const refs=card('Referenciák');const rl=el('div','cs-refs');
  const drawRefs=()=>{rl.replaceChildren();c.references.forEach((r,i)=>{const row=el('div','cs-ref');row.append(input(r.title,v=>{r.title=v;patch({references:c.references});},'Film, klip, fotós'),input(r.url,v=>{r.url=v;patch({references:c.references});},'Link (opcionális)'),input(r.note,v=>{r.note=v;patch({references:c.references});},'Miért'),button('×',()=>{c.references.splice(i,1);patch({references:c.references});drawRefs();},'text-button'));rl.append(row);});};
  drawRefs();refs.append(rl,button('＋ Referencia',()=>{c.references.push({title:'',url:'',note:'',owner:true});drawRefs();},'secondary'));page.append(refs);
 }

 function moodboard(page,c){
  const top=card('Paletta');const sw=el('div','cs-palette');
  const drawPal=()=>{sw.replaceChildren();(c.palette||[]).forEach((col,i)=>{const cell=el('span','cs-swatch'),p=el('input');p.type='color';p.value=col;p.oninput=()=>{c.palette[i]=p.value;patch({palette:c.palette});};
   const del=button('×',()=>{c.palette.splice(i,1);patch({palette:c.palette});drawPal();},'cs-swatch-del');del.title='Szín törlése';cell.append(p,del);sw.append(cell);});const add=button('＋',()=>{(c.palette=c.palette||[]).push('#888888');patch({palette:c.palette});drawPal();},'secondary');sw.append(add);};drawPal();top.append(sw);page.append(top);
  const board=card('Moodboard','cs-board-card');
  // More mood pictures for the concept, steered by the owner's own words (owner 12 Nov).
  const gen=el('div','cs-gen'),gp=area('',()=>{},'Milyen képeket szeretnél még? Pl. „közeli a két lányról a busz hátsó ablakánál, hajnali kék fény” — üresen a Rendező dönt.',2),cnt=el('select');
  for(const n of [1,2,3,4,6])cnt.append(new Option(n+' kép',n,false,n===3));
  const gr=el('div','cs-row');gr.append(cnt,ai('✦ Új moodboard-képek',()=>op('clip_moods',{clip:c.id,prompt:gp.value,count:Number(cnt.value)})));gen.append(gp,gr);board.append(gen);
  const acts=el('div','cs-row');acts.append(ai('Hiányzó képek rajzolása',()=>op('clip_images',{clip:c.id,which:'moodboard'}),'secondary'),button('＋ Üres kép-ötlet',()=>{c.moodboard.push({prompt:'',note:'',artifact:null,owner:true});patch({moodboard:c.moodboard},true);},'secondary'));board.append(acts);
  const grid=el('div','cs-masonry');
  const moodList=c.moodboard.filter(m=>m.artifact).map(m=>({id:m.artifact,caption:m.note||m.prompt}));
  c.moodboard.forEach((m,i)=>{if(!m.prompt&&!m.artifact&&!m.owner)return;const t=el('figure','cs-tile');const pic=el('div','cs-tile-pic');if(m.artifact)pic.append(zoomable(img(m.artifact),moodList,moodList.findIndex(x=>x.id===m.artifact)));else pic.append(el('span','','Még nincs kép'));
   t.append(pic,area(m.prompt,v=>{m.prompt=v;patch({moodboard:c.moodboard});},'Mit mutasson a kép (angolul a képmodellnek)',2,'cs-prompt'),input(m.note,v=>{m.note=v;patch({moodboard:c.moodboard});},'Jegyzet'),button('Törlés',()=>{c.moodboard.splice(i,1);patch({moodboard:c.moodboard},true);},'text-button'));grid.append(t);});
  if(!c.moodboard.length)grid.append(el('p','hint','A Rendező tervével érkeznek a kép-ötletek, vagy írj sajátot.'));
  board.append(grid);page.append(board);
 }

 function storyboard(page,c){
  const sb=card('Storyboard');const acts=el('div','cs-row');acts.append(ai('Hiányzó kockák rajzolása',()=>op('clip_images',{clip:c.id,which:'storyboard'})),button('＋ Snitt',()=>{const last=c.storyboard[c.storyboard.length-1];c.storyboard.push({start:last?last.end:0,end:(last?last.end:0)+5,shot:'',description:'',camera:'',location:'',artifact:null,note:''});patch({storyboard:c.storyboard},true);},'secondary'));sb.append(acts);
  const list=el('div','cs-shots');
  const boardList=c.storyboard.filter(s=>s.artifact).map((s)=>({id:s.artifact,caption:tc(s.start)+'–'+tc(s.end)+' · '+(s.shot||'')+' · '+(s.description||'')}));
  c.storyboard.forEach((s,i)=>{const r=el('article','cs-shot');const pic=el('div','cs-shot-pic');if(s.artifact)pic.append(zoomable(img(s.artifact),boardList,boardList.findIndex(x=>x.id===s.artifact)));else pic.append(el('span','',String(i+1)));
   const f=el('div','cs-shot-fields'),times=el('div','cs-row');
   const num=(v,k)=>{const n=input(v,x=>{s[k]=Number(x)||0;patch({storyboard:c.storyboard});},k==='start'?'kezdet (mp)':'vége (mp)','cs-num');n.type='number';n.step='0.5';return n;};
   times.append(el('b','cs-shot-no','#'+(i+1)),num(s.start,'start'),num(s.end,'end'),input(s.shot,v=>{s.shot=v;patch({storyboard:c.storyboard});},'Plán (közeli, totál…)'),input(s.camera,v=>{s.camera=v;patch({storyboard:c.storyboard});},'Kamera (dolly, kézi…)'));
   f.append(times,area(s.description,v=>{s.description=v;patch({storyboard:c.storyboard});},'Mi látszik a képen',2),input(s.location,v=>{s.location=v;patch({storyboard:c.storyboard});},'Helyszín'),input(s.note,v=>{s.note=v;patch({storyboard:c.storyboard});},'Jegyzet'),button('Törlés',()=>{c.storyboard.splice(i,1);patch({storyboard:c.storyboard},true);},'text-button'));
   r.append(pic,f);list.append(r);});
  if(!c.storyboard.length)list.append(el('p','hint','A Rendező a zene részeihez igazított snittlistát készít; vagy vegyél fel sajátot.'));
  sb.append(list);page.append(sb);
 }

 function locations(page,c,d){
  // The storyboard the way a crew shoots it: per real place, so each place is booked for what it has to deliver.
  if(d?.shooting?.length>0&&c.storyboard?.length){const order=card('Forgatási sorrend','cs-order');order.append(el('p','hint','A storyboard beállításai helyszínenként: egy helyen minden felvehető egyszerre.'));
   for(const g of d.shooting){const r=el('div','cs-order-row');r.append(el('strong','',g.place),el('span','',g.shots.length+' beállítás · #'+g.shots.join(', #')),el('b','',tc(g.seconds)+' vágott anyag'));if(g.cameras.length)r.append(el('small','',g.cameras.slice(0,4).join(' · ')));if(/^(Külső helyszín|Fő helyszín)/.test(g.place))r.append(el('small','cs-order-warn','Ehhez még nincs helyszínigény: vedd fel lent, hogy a keresés és a költségvetés is számoljon vele.'));order.append(r);}
   page.append(order);}
  const needs=card('Milyen helyszín kell');const nl=el('div','cs-needs');
  const draw=()=>{nl.replaceChildren();(c.location_needs||[]).forEach((n,i)=>{const r=el('div','cs-need');const days=input(n.days,v=>{n.days=Number(v)||1;patch({location_needs:c.location_needs});},'nap','cs-num');days.type='number';
   r.append(input(n.type,v=>{n.type=v;patch({location_needs:c.location_needs});},'Típus (loft, tető, erdő…)'),input(n.city,v=>{n.city=v;patch({location_needs:c.location_needs});},'Város'),days,grow(area(n.description,v=>{n.description=v;patch({location_needs:c.location_needs});},'Mire kell',1,'cs-grow')),button('×',()=>{c.location_needs.splice(i,1);patch({location_needs:c.location_needs});draw();},'text-button'));nl.append(r);});};
  draw();needs.append(nl,el('div','cs-row'));needs.lastChild.append(button('＋ Helyszínigény',()=>{(c.location_needs=c.location_needs||[]).push({type:'',city:'Budapest',days:1,description:''});draw();},'secondary'),ai('Keresés Magyarországon',()=>op('clip_locations',{clip:c.id})));page.append(needs);
  const found=card('Talált helyszínek');found.append(el('p','hint','Webes találatok bérelhető helyszínekre. Az ár csak akkor szerepel, ha a találatban benne volt; a kiválasztott hely ára átkerül a költségvetésbe. Foglalni a helyszínnel neked kell.'));
  const grid=el('div','cs-grid2');
  c.locations.forEach(l=>{const t=el('article','cs-loc'+(l.picked?' on':''));t.append(el('small','',(l.type||'')+' · '+(l.place||'')),el('strong','',l.name),el('p','',l.snippet||''),el('code','',l.url||''),el('b','',l.price_day?huf(l.price_day)+' / nap':'Ár nem szerepelt'));
   t.append(grow(area(l.note,v=>{l.note=v;patch({locations:c.locations});},'Jegyzet (pl. felhívtam, szabad jún. 14.)',2,'cs-grow')));
   t.append(button(l.picked?'✓ Kiválasztva':'Ezt választom',()=>act(async()=>{const r=await op('clip_pick_location',{clip:c.id,location:l.id});clipData.clip=r.clip;clipData.budget=r.budget;clipRender();}),l.picked?'primary':'secondary'));grid.append(t);});
  if(!c.locations.length)grid.append(el('p','hint','Még nincs találat.'));
  found.append(grid);page.append(found);
 }

 function budget(page,c,d){
  // What a real shoot needs and this budget lacks (the people the direction names, a camera): added on the owner's click.
  if(d.missing?.length){const warn=el('div','cs-banner');warn.append(el('span','','Hiányzik a költségvetésből: '+d.missing.map(l=>l.item+' ('+l.qty+' '+l.unit+')').join(', ')+'. '),
   button('Pótlás',()=>act(async()=>{clipData=await op('clip_budget_fill',{clip:c.id});clipRender();toast('Hozzáadtam a hiányzó tételeket.');}),'secondary'));page.append(warn);}
  // Over the ceiling: one click runs the same fitting as a new plan (indie rates, cheap places, least needed lines out).
  if(d.budget?.over){const fit=el('div','cs-banner bad');fit.append(el('span','','A költségvetés túllépi a keretet. A saját tételeidhez nem nyúlok. '),
   button('Keretbe illesztés',()=>act(async()=>{const r=await op('clip_fit',{clip:c.id});clipData=r;clipRender();toast(r.message);}),'secondary'));page.append(fit);}
  const b=d.budget,sum=card('','cs-budget-sum');
  const big=el('div','cs-big');big.append(el('small','','Teljes költség, tartalékkal'),el('strong','',huf(b.total)));big.lastChild.dataset.clipTotal='1';
  const cap=el('label','cs-cap');const capIn=input(c.budget.cap||'',v=>{c.budget.cap=Number(String(v).replace(/\D/g,''))||null;liveBudget(c);patch({budget:c.budget});},'nincs megadva','cs-num');capIn.type='number';cap.append('Keret: ',capIn,' Ft');big.append(cap);
  const capNote=el('p');capNote.id='csCapNote';drawCap(capNote,sums(c));big.append(capNote);
  const cats=el('div','cs-cats');cats.id='csCats';drawCats(cats,sums(c));
  const res=el('label','cs-reserve');const pct=input(c.budget.contingency,v=>{c.budget.contingency=Number(v)||0;liveBudget(c);patch({budget:c.budget});},'%','cs-num');pct.type='number';res.append('Tartalék ',pct,' %');
  sum.append(big,cats,res);page.append(sum);
  const table=card('Tételek');table.append(el('p','hint','A napidíjak magyar piaci becslések; írd át a valós ajánlatokra. Semmit nem foglal és nem fizet.'));
  const head=el('div','cs-line head');for(const h of ['Kategória','Tétel','Menny.','Egység','Egységár','Összesen',''])head.append(el('span','',h));table.append(head);
  c.budget.lines.forEach((l,i)=>{const r=el('div','cs-line');const cat=el('select');for(const k of d.categories)cat.append(new Option(k,k,false,k===l.category));cat.onchange=()=>{l.category=cat.value;patch({budget:c.budget},true);};
   const line=el('b','',huf((l.qty||0)*(l.rate||0)));const relive=()=>{line.textContent=huf((Number(l.qty)||0)*(Number(l.rate)||0));liveBudget(c);patch({budget:c.budget});};
   const q=input(l.qty,v=>{l.qty=Number(v)||0;relive();},'','cs-num'),rate=input(l.rate,v=>{l.rate=Number(v)||0;relive();},'','cs-num');q.type=rate.type='number';
   cat.onchange=()=>{l.category=cat.value;liveBudget(c);patch({budget:c.budget});};
   r.append(cat,input(l.item,v=>{l.item=v;patch({budget:c.budget});},'Tétel'),q,input(l.unit,v=>{l.unit=v;patch({budget:c.budget});},'nap'),rate,line,button('×',()=>{c.budget.lines.splice(i,1);liveBudget(c);patch({budget:c.budget},true);},'text-button'));table.append(r);});
  const add=el('div','cs-row'),pickRole=el('select');pickRole.append(new Option('＋ Tétel a díjtáblából…',''));for(const [k,v] of Object.entries(d.rates))pickRole.append(new Option(k+' · '+huf(v),k));
  pickRole.onchange=()=>{const k=pickRole.value;if(!k)return;c.budget.lines.push({category:/színész|statiszta|táncos/i.test(k)?'Szereplők':/bérlés|szett|csomag|gimbal|füst/i.test(k)?'Technika':/catering|busz/i.test(k)?'Logisztika':/vágó|szín/i.test(k)?'Utómunka':'Stáb',item:k,qty:1,unit:'nap',rate:d.rates[k],owner:true});patch({budget:c.budget},true);};
  add.append(pickRole,button('＋ Üres tétel',()=>{c.budget.lines.push({category:'Egyéb',item:'',qty:1,unit:'db',rate:0,owner:true});patch({budget:c.budget},true);},'secondary'));table.append(add);page.append(table);
 }

 function notes(page,c){
  const n=card('Jegyzetek','cs-notes');n.append(el('p','hint','Szabad jegyzet: ötletek, telefonszámok helyett névjegyek, döntések, teendők. A Rendező is olvassa.'),area(c.notes,v=>patch({notes:v}),'Írj ide bármit…',18,'cs-notepad'));page.append(n);
  const danger=card('');danger.append(button('Klip archiválása',()=>act(async()=>{clipData=await op('clip_archive',{clip:c.id});clipId=null;clipRender();toast('Archiválva.');}),'danger-link'));page.append(danger);
 }

 // Hook into the project app: this kind loads and draws itself.
 const loadBefore=loadProjectApp,renderBefore=renderProjectApp;
 loadProjectApp=async function(){if(projectAppView?.app==='clip'){if(currentApp!=='agents')return;if(!clipData||clipData.error)await clipLoad();return;}$('projectAppView')?.classList.remove('cs-app');return loadBefore();};
 renderProjectApp=function(){if(projectAppView?.app==='clip'){if(!paTyping())clipRender();return;}$('projectAppView')?.classList.remove('cs-app');return renderBefore();};
 const syncBefore=syncProjectApp;
 syncProjectApp=function(){if(projectAppFor!==project){clipData=null;clipId=null;}syncBefore();
  // The clip app takes the whole window, like the workspace app: no agent panel, no big heading (owner 12 Nov).
  $('studioApp')?.classList.toggle('clip-mode',projectAppView?.app==='clip');};
}
