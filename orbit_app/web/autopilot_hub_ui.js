/* Autopilóta: one control centre over the whole app. What runs now, the owner's standing goals, missions, urgent
   improvements and what was finished, refreshed in place while the page is open. The business workshop and the full
   improvement list are one click away, so nothing is crowded onto this page. */
(()=>{
const hub=el('section','ap-hub');const app=$('autopilotApp');const lab=$('businessLabPanel');const head=app.querySelector('.autopilot-head');
const tabs=el('div','ap-hub-tabs');const allPane=el('section','ap-hub ap-all');let tab='overview',last='',timer=null,draft='',auto=null,lastAll='',lastD=null;
head.querySelector('.eyebrow').textContent='AUTOPILÓTA · ÖNMŰKÖDÉS';head.querySelector('h1').textContent='Autopilóta';
head.querySelector('.hint').textContent='Itt látod, min dolgozik az ORBIT magától, és itt kapcsolod ki-be az összes önműködő folyamatot, projektenként is. A fő chatből is irányíthatod („mi fut most magától?”).';
app.insertBefore(tabs,lab);app.insertBefore(hub,lab);app.insertBefore(allPane,lab);
const sure=(b,fn)=>async()=>{if(b.dataset.armed!=='1'){b.dataset.armed='1';b.textContent='Biztosan?';setTimeout(()=>{b.dataset.armed='';b.textContent=b.dataset.label;},3000);return;}await fn();};
const confirmButton=(label,fn)=>{const b=button(label,()=>{} ,'secondary');b.dataset.label=label;b.onclick=sure(b,fn);return b;};
const op=async(name,args)=>(await call('project_app',{op:name,args:args||{}})).result;
const ago=ts=>{const m=Math.max(0,Math.round((Date.now()/1000-ts)/60));return m<1?'most':m<60?m+' perce':Math.round(m/60)+' órája';};
const clock=ts=>new Date(ts*1000).toLocaleTimeString('hu-HU',{hour:'2-digit',minute:'2-digit'});
function chip(label,active,onclick){const b=el('button','improve-chip'+(active?' active':''),label);b.type='button';b.onclick=onclick;return b;}
function section(title,note){const s=el('section','ap-hub-box');const h=el('div','ap-hub-title');h.append(el('h3','',title));if(note)h.append(el('span','improve-when',note));s.append(h);return s;}
function show(){lab.hidden=tab!=='lab';hub.hidden=tab!=='overview';allPane.hidden=tab!=='all';}
function renderTabs(d){tabs.replaceChildren(chip('Áttekintés',tab==='overview',()=>{tab='overview';last='';show();refresh();}),chip('Minden önműködő'+(auto?' · '+auto.on+' be':''),tab==='all',()=>{tab='all';lastAll='';show();refresh();}),chip('Üzleti műhely',tab==='lab',()=>{tab='lab';show();renderTabs(d);}),
  chip('Fejlesztések'+(d?' · '+d.improve.total:''),false,()=>window.showImprove&&act(window.showImprove)));}
function build(d){
 const f=document.createDocumentFragment();
 if(auto)f.append(pauseStrip(auto,true));
 // Master switch and one sentence of state.
 const top=el('section','ap-hub-box ap-hub-master'+(d.mode?' on':''));const sw=el('label','ap-hub-switch');const box=el('input');box.type='checkbox';box.checked=d.mode;
 box.onchange=async()=>{await op('autopilot_mode',{on:box.checked});toast(box.checked?'Az Autopilóta dolgozik a céljaidon, amikor a gép szabad.':'Az Autopilóta megállt: magától semmit nem indít.');last='';refresh();};
 sw.append(box,el('strong','',d.mode?'Az Autopilóta be van kapcsolva':'Az Autopilóta áll'));top.append(sw);
 const running=d.live.filter(x=>x.running).length,active=d.goals.filter(g=>g.enabled).length;
 top.append(el('p','ap-hub-state',!d.mode?'Magától most semmit nem indít. Amit te indítasz, az ugyanúgy lefut.':running?'Most '+running+' munka fut'+(d.live.length>running?', '+(d.live.length-running)+' sorban áll.':'.'):active?'Most szabad a gép; a következő szabad percekben a céljaid egyikén dolgozik tovább.':'Nincs megadott cél. Írj egyet lent, vagy mondd el a fő chatben, min dolgozzon.'));
 f.append(top);
 // Live work.
 const live=section('Most fut',d.live.length?d.live.length+' munka':'');
 if(!d.live.length)live.append(el('p','improve-empty','Most semmi nem fut és semmi nem áll sorban.'));
 for(const x of d.live){const row=el('div','ap-hub-row '+(x.running?'running':'queued'));row.append(el('span','improve-dot'));const text=el('div','ap-hub-text');text.append(el('strong','',x.kind+(x.project?' · '+x.project:'')),el('span','',x.title));if(x.detail)text.append(el('small','',x.detail));row.append(text,el('span','improve-when',x.running?ago(x.since)+' indult':'sorban áll'));
  if(x.running&&x.kind!=='Chat-kérés')row.append(confirmButton('Leállítás',async()=>{await call('job_cancel',{requestProject:x.project_id,id:x.job});last='';refresh();}));live.append(row);}
 f.append(live);
 // Goals.
 const goals=section('Céljaim','ezeken dolgozik magától');
 if(!d.goals.length)goals.append(el('p','improve-empty','Még nincs cél. Például: „Dolgozz a saját animációkon, legyenek viccesebbek” vagy „Javítsd folyamatosan a visszatérő hibákat”.'));
 for(const g of d.goals){const row=el('div','ap-hub-row goal'+(g.enabled?'':' off'));const on=el('input');on.type='checkbox';on.checked=g.enabled;on.title=g.enabled?'Szüneteltetés':'Folytatás';on.onchange=async()=>{await op('autopilot_goal_set',{id:g.id,enabled:on.checked});last='';refresh();};
  const text=el('div','ap-hub-text');text.append(el('strong','',g.kind_label),el('span','',g.text),el('small','',(g.last_run?('Utoljára '+ago(g.last_run)+': '+(g.last_note||'')+' · eddig '+g.runs+' lépés'):'Még nem dolgozott rajta.')+(g.enabled?(g.next_in==null?' · Mára elvégezte a lépéseit, holnap folytatja.':g.next_in>0?' · Következő lépés szabad gépen kb. '+Math.ceil(g.next_in/60)+' perc múlva.':' · Szabad gépen most jön a következő lépése.'):'')));
  row.append(on,text,confirmButton('Törlés',async()=>{await op('autopilot_goal_remove',{id:g.id});last='';refresh();}));goals.append(row);}
 const add=el('div','ap-hub-add');const input=el('input');input.type='text';input.placeholder='Új cél egy mondatban…';input.value=draft;input.oninput=()=>{draft=input.value;};
 const save=async()=>{if(input.value.trim().length<8){toast('Írd le egy mondatban, min dolgozzon.');return;}await op('autopilot_goal_add',{text:input.value});draft='';last='';refresh();};
 input.onkeydown=e=>{if(e.key==='Enter')act(save);};add.append(input,button('Hozzáadás',()=>act(save)));goals.append(add);f.append(goals);
 // What it did, per project.
 if(d.projects&&d.projects.length){const pr=section('Projektenként','mit csinált az Autopilóta');for(const p of d.projects){const det=el('details','improve-log');det.open=hub.dataset['p_'+p.project]==='1';det.ontoggle=()=>{hub.dataset['p_'+p.project]=det.open?'1':'';};det.append(el('summary','',p.name+' · utoljára '+ago(p.items[0].at)));for(const x of p.items){const row=el('div','improve-event');row.append(el('time','',clock(x.at)),el('strong','',x.kind),el('span','',x.text));det.append(row);}pr.append(det);}f.append(pr);}
 // Missions.
 if(d.missions.length){const m=section('Küldetések','több lépéses, önállóan futó munkák');
  for(const x of d.missions){const label={active:'fut',paused:'szünetel',draft:'vázlat',done:'kész',failed:'megállt'}[x.status]||x.status;const row=el('div','ap-hub-row '+(x.status==='active'?'running':'queued'));row.append(el('span','improve-dot'));
   const text=el('div','ap-hub-text');text.append(el('strong','',x.project_name),el('span','',x.name),el('small','',label+(x.total?' · '+x.done+'/'+x.total+' lépés kész':'')+(x.step?' · most: '+x.step:'')+(x.error?' · '+x.error:'')));row.append(text);
   if(x.status==='active')row.append(button('Szünet',async()=>{await call('mission_pause',{requestProject:x.project,id:x.id});last='';refresh();},'secondary'));
   else if(x.status==='paused'||x.status==='draft')row.append(button(x.status==='draft'?'Indítás':'Folytatás',async()=>{await call(x.status==='draft'?'mission_start':'mission_resume',{requestProject:x.project,id:x.id});last='';refresh();},'secondary'));
   m.append(row);}f.append(m);}
 // Urgent improvements only; the whole list has its own view.
 const imp=section('Sürgős fejlesztések',d.improve.counts.sos+' SOS · '+d.improve.counts.high+' fontos · összesen '+d.improve.total);
 if(!d.improve.top.length)imp.append(el('p','improve-empty','Nincs sürgős tétel.'));
 for(const i of d.improve.top){const row=el('div','ap-hub-row '+(i.working?'running':'queued'));row.append(el('span','improve-tag improve-urgency urgency-'+i.urgency,i.urgency_label));const text=el('div','ap-hub-text');text.append(el('span','',i.title),el('small','',(i.evidence||i.why||'').split('\n')[0].slice(0,150)));row.append(text);imp.append(row);}
 imp.append(button('Összes fejlesztés megnyitása',()=>window.showImprove&&act(window.showImprove),'secondary'));f.append(imp);
 // Finished and recent, folded.
 const done=el('details','improve-log');done.append(el('summary','','Elkészült és történt az elmúlt napban · '+(d.finished.length+d.recent.length)));
 for(const x of d.finished){const row=el('div','improve-event');row.append(el('time','',clock(x.at)),el('strong','',x.kind),el('span','',x.text+(x.project?' · '+x.project:'')));done.append(row);}
 for(const x of d.recent){const row=el('div','improve-event');row.append(el('time','',clock(x.at)),el('strong','',x.kind),el('span','',x.text+(x.times?' ×'+x.times:'')));done.append(row);}
 done.open=hub.dataset.done==='1';done.ontoggle=()=>{hub.dataset.done=done.open?'1':'';};f.append(done);
 return f;
}
// The one switch over everything self-starting, and the full list grouped by project (owner 13 Nov: no new menu item).
function pauseStrip(a,withLink){
 // One clear state, one big stop button, and plain numbers of what is running, waiting, listening and held.
 const busy=a.running.length+(a.queued||[]).length,listening=(a.watchers||[]).reduce((n,w)=>n+w.listening,0),held=a.held_posts||0;
 const state=a.paused?(busy?'paused busy':'paused'):'running';
 const box=el('section','ap-hub-box ap-pause ap-state '+state);
 const head=el('div','ap-state-head');
 head.append(el('strong','ap-state-title',a.paused?'⏸ MINDEN ÁLL':'▶ FUT'));
 const nums=[a.running.length+' munka fut',(a.queued||[]).length+' vár',listening?listening+' csatornát figyel az élő adás figyelő':'nincs figyelés',held?held+' ütemezett feltöltés '+(a.paused?'tartva':'vár az időpontjára'):'nincs ütemezett feltöltés'];
 head.append(el('span','ap-state-nums',nums.join(' · ')));box.append(head);
 box.append(el('p','ap-hub-state',a.paused?(busy?'Szünet van, de még '+busy+' munka fut vagy vár. A „Mindent leállít” megszakítja őket.':'Semmi nem fut és semmi nem indul magától: se gyártás, se figyelés, se feltöltés. Amit te kérsz, az lefut.'):a.on+' önműködő folyamat van bekapcsolva. Egy kattintással mindent leállíthatsz.'));
 const row=el('div','ap-state-actions');
 const stopLabel=a.paused&&!busy?null:'⏹ Mindent leállít';
 if(stopLabel)row.append(confirmButton(stopLabel,async()=>{const r=await op('autonomy_halt');auto=r;toast(r.message);last='';lastAll='';refresh();}));
 if(a.paused)row.append(button('▶ Folytatás',()=>act(async()=>{auto=await op('autonomy_pause',{on:false});toast('Az önműködő folyamatok újra a saját beállításuk szerint futnak.');last='';lastAll='';refresh();})));
 box.append(row);
 if(withLink)box.append(button('Mind megtekintése →',()=>{tab='all';lastAll='';show();refresh();},'text-button'));
 return box;
}
function buildAll(a){
 const f=document.createDocumentFragment();f.append(pauseStrip(a,false));
 if(a.running.length){const r=section('Most fut magától',a.running.length+' munka');for(const x of a.running){const row=el('div','ap-hub-row running');row.append(el('span','improve-dot'));const text=el('div','ap-hub-text');text.append(el('strong','',x.project_name||'ORBIT'),el('span','',x.title));row.append(text,el('span','improve-when',ago(Date.now()/1000-x.seconds)+' indult'),confirmButton('Leállítás',async()=>{auto=await op('autonomy_stop',{job:x.id});lastAll='';refresh();}));r.append(row);}f.append(r);}
 if((a.queued||[]).length){const q=section('Vár a sorban',a.queued.length+' munka');for(const x of a.queued.slice(0,12)){const row=el('div','ap-hub-row');const text=el('div','ap-hub-text');text.append(el('strong','',x.project_name||'ORBIT'),el('span','',x.title));row.append(text,confirmButton('Törlés',async()=>{auto=await op('autonomy_stop',{job:x.id});lastAll='';refresh();}));q.append(row);}f.append(q);}
 for(const w of a.watchers||[]){const sec=section('Élő adás figyelő',w.enabled&&!a.paused?'be van kapcsolva':'nem figyel');const row=el('div','ap-hub-row');const text=el('div','ap-hub-text');text.append(el('strong','',w.listening+' csatornát figyel · '+w.live+' élő adás a listán'),el('span','',(w.listener?'A chat-hallgató fut. ':'A chat-hallgató áll. ')+w.moments+' pillanat vár feldolgozásra.'));row.append(text);if(w.enabled)row.append(confirmButton('Figyelő kikapcsolása',async()=>{auto=await op('autonomy_toggle',{id:'stream_watch:'+w.project,on:false});lastAll='';refresh();}));sec.append(row);f.append(sec);}
 for(const g of a.groups){const sec=section(g.name,g.items.filter(i=>i.on).length+' / '+g.items.length+' be');
  for(const i of g.items){const row=el('div','ap-hub-row goal'+(i.on?'':' off'));const cb=el('input');cb.type='checkbox';cb.checked=i.on;cb.disabled=!i.toggle||(!i.on&&/^(mail|agent):/.test(i.id));
   cb.title=cb.disabled?(i.note||'Itt nem kapcsolható'):(i.on?'Kikapcsolás':'Bekapcsolás');
   cb.onchange=()=>act(async()=>{try{auto=await op('autonomy_toggle',{id:i.id,on:cb.checked});}catch(e){cb.checked=!cb.checked;throw e;}lastAll='';last='';refresh();});
   const text=el('div','ap-hub-text');text.append(el('strong','',i.name),el('span','',i.what));
   const meta=[i.power_label];if(i.next&&i.on)meta.push('következő: '+new Date(i.next*1000).toLocaleString('hu-HU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}));if(i.last)meta.push('utoljára '+ago(i.last));if(i.note)meta.push(i.note);
   text.append(el('small','ap-power '+i.power,meta.join(' · ')));row.append(cb,text);sec.append(row);}
  f.append(sec);}
 if(!a.groups.length)f.append(el('p','improve-empty','Nincs önműködő folyamat.'));
 return f;
}
async function refresh(){
 if(!app.hidden&&tab==='all'){try{auto=await op('autonomy_overview');}catch(e){return;}const k=JSON.stringify(auto);if(k===lastAll)return;lastAll=k;const top=app.scrollTop;renderTabs(lastD);allPane.replaceChildren(buildAll(auto));app.scrollTop=top;return;}
 try{auto=await op('autonomy_overview');}catch(e){}
 if(app.hidden||tab!=='overview')return;
 if(document.activeElement&&hub.contains(document.activeElement)&&document.activeElement.tagName==='INPUT'&&document.activeElement.type==='text'&&last)return; // never rebuild under the owner's typing
 let d;try{d=await op('autopilot_overview');}catch(e){return;}
 const key=JSON.stringify([auto&&[auto.paused,auto.on,auto.running.length],d.mode,d.live.map(x=>[x.job,x.running,x.detail,x.waiting]),d.goals,d.missions,(d.projects||[]).map(p=>p.items[0].at),d.improve.counts,d.improve.top.map(i=>i.id),d.finished.length,d.recent.length]);
 if(key===last)return;last=key;lastD=d;const top=app.scrollTop;renderTabs(d);hub.replaceChildren(build(d));app.scrollTop=top;
}
const baseSwitch=switchApp;
switchApp=function(view){baseSwitch(view);if(view==='autopilot'){show();last='';refresh();if(!timer)timer=setInterval(()=>{if(!document.hidden)refresh();},5000);}else if(timer){clearInterval(timer);timer=null;}};
$('navAutopilot').onclick=()=>switchApp('autopilot');
const old=$('navImprove');if(old)old.hidden=true;   // the improvement list now opens from the Autopilot page
renderTabs(null);show();
})();
