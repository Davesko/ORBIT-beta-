/* Fejlődés: what ORBIT is doing for itself right now, what it did in the last day, and the open improvement cards in
   order of urgency. Solved cards leave by themselves. The panel refreshes while it is open, without flashing. */
(()=>{
const AREA={speed:'gyorsaság',reliability:'megbízhatóság',quality:'minőség',ux:'kezelhetőség',growth:'növekedés'};
const SIZE={S:'kicsi',M:'közepes',L:'nagy'};
const view={filter:'all',scope:'',open:new Set(),timer:null};
async function improveOp(op,args){return (await call('project_app',{op,args:args||{}})).result;}
function clock(ts){const d=new Date(ts*1000);return d.toLocaleTimeString('hu-HU',{hour:'2-digit',minute:'2-digit'});}
function toChat(text){switchApp('home');const input=$('commandInput');input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();toast('A javaslat a chatben van; küldd el, ha mehet.');}
function chip(label,active,onclick,extra){const b=el('button','improve-chip'+(active?' active':'')+(extra?' '+extra:''),label);b.type='button';b.onclick=onclick;return b;}
function card(idea,refresh){
 const c=el('article','improve-card improve-'+idea.status+' urgency-'+idea.urgency+(idea.working?' improve-working':''));
 const top=el('div','improve-top');const title=el('strong','',idea.title);top.append(title);
 const tags=el('span','improve-tags');
 if(idea.working)tags.append(el('span','improve-tag improve-live','most dolgozik rajta'));
 tags.append(el('span','improve-tag improve-urgency',idea.urgency_label),el('span','improve-tag',idea.scope_name+(idea.also?' +'+idea.also:'')));
 if(idea.status==='accepted'&&!idea.working)tags.append(el('span','improve-tag improve-state','megpróbálta'));
 top.append(tags);c.append(top);
 if(idea.source==='measured'&&idea.evidence)c.append(el('p','improve-why','Hiba: '+idea.evidence.split('\n')[0].slice(0,140)));
 else if(idea.why)c.append(el('p','improve-why',idea.why));
 const more=el('details','improve-more');more.open=view.open.has(idea.id);more.ontoggle=()=>{more.open?view.open.add(idea.id):view.open.delete(idea.id);};
 more.append(el('summary','','Részletek és műveletek'));
 if(idea.source==='measured'&&idea.why)more.append(el('p','improve-evidence',idea.why));
 else if(idea.evidence)more.append(el('p','improve-evidence','Alap: '+idea.evidence));
 more.append(el('p','improve-evidence',(AREA[idea.area]||idea.area||'')+' · '+(SIZE[idea.size]||idea.size||'')+' · '+(idea.source==='measured'?'mért hiba':'a modell ötlete')));
 const actions=el('div','improve-actions');
 actions.append(button(idea.status==='accepted'?'Újra a chatbe':'Megcsináltatom',async()=>{const r=await improveOp('improve_set',{id:idea.id,status:'accepted'});stop();$('modal').close();toChat(r.request);}));
 actions.append(button('Kész',async()=>{await improveOp('improve_set',{id:idea.id,status:'done'});refresh();},'secondary'));
 actions.append(button('Elvetem',async()=>{await improveOp('improve_set',{id:idea.id,status:'dismissed'});refresh();},'secondary'));
 more.append(actions);c.append(more);return c;
}
function build(data,refresh){
 const body=document.createDocumentFragment();
 // 1. Live: what it is doing for itself now.
 const live=el('section','improve-live-box');live.append(el('h3','','Most ezen dolgozik'));
 if(!data.activity.live.length)live.append(el('p','improve-empty',data.auto?'Most nincs saját munkája. Amint a gép szabad, magától keres fejlesztést és nekilát a legsürgősebbnek.':'Most nincs saját munkája. Amint a gép szabad, magától keres fejlesztési ötleteket.'));
 for(const a of data.activity.live){const row=el('div','improve-run '+(a.state==='most fut'?'running':'queued'));row.append(el('span','improve-dot'),el('strong','',a.kind),el('span','improve-run-text',a.text+(a.detail?' — '+a.detail:'')),el('span','improve-when',a.state));live.append(row);}
 body.append(live);
 // 2. The last day.
 const log=el('details','improve-log');log.open=view.open.has('log');log.ontoggle=()=>{log.open?view.open.add('log'):view.open.delete('log');};
 log.append(el('summary','','Az elmúlt 24 óra · '+data.activity.recent.length+' esemény'));
 if(!data.activity.recent.length)log.append(el('p','improve-empty','Még nem történt semmi.'));
 for(const a of data.activity.recent){const row=el('div','improve-event');row.append(el('time','',clock(a.at)),el('strong','',a.kind),el('span','',a.text+(a.times?' ×'+a.times:'')));log.append(row);}
 body.append(log);
 // 3. Controls.
 const bar=el('div','improve-bar');const c=data.counts;
 bar.append(chip('Mind · '+data.ideas.length,view.filter==='all',()=>{view.filter='all';refresh();}),chip('SOS · '+c.sos,view.filter==='sos',()=>{view.filter='sos';refresh();},'sos'),
            chip('Fontos · '+c.high,view.filter==='high',()=>{view.filter='high';refresh();}),chip('Ráér · '+(c.normal+c.low),view.filter==='rest',()=>{view.filter='rest';refresh();}));
 const pick=el('select');options(pick,[{value:'',label:'Minden projekt'}].concat(data.scopes.map(x=>({value:x.scope,label:x.name}))),view.scope);pick.onchange=()=>{view.scope=pick.value;refresh();};bar.append(pick);
 bar.append(button('Ötletelés most',async()=>{const r=await improveOp('improve_run',{scope:view.scope||'orbit'});toast(r.message||'Elindult.');refresh();},'secondary'));
 const auto=el('label','improve-auto');const box=el('input');box.type='checkbox';box.checked=!!data.auto;box.onchange=async()=>{await improveOp('improve_auto',{on:box.checked});toast(box.checked?'Bekapcsolva: szabadidejében a legsürgősebb javaslatot magától megvalósítja, és a chatben beszámol róla.':'Kikapcsolva: csak ötletel, a megvalósítást te indítod.');refresh();};
 auto.append(box,el('span','',' Magától meg is valósítja'));bar.append(auto);body.append(bar);
 // 4. The cards, most urgent first.
 const shown=data.ideas.filter(i=>(view.filter==='all'||view.filter===i.urgency||view.filter==='rest'&&(i.urgency==='normal'||i.urgency==='low'))&&(!view.scope||i.scope===view.scope));
 const list=el('section','improve-group');
 if(!shown.length)list.append(el('p','improve-empty',data.ideas.length?'Ebben a szűrésben nincs nyitott tétel.':'Nincs nyitott fejlesztés. Az új ötletek itt jelennek meg.'));
 for(const idea of shown)list.append(card(idea,refresh));body.append(list);
 if((data.developer||[]).length){const dev=el('details','improve-log');dev.open=view.open.has('dev');dev.ontoggle=()=>{dev.open?view.open.add('dev'):view.open.delete('dev');};dev.append(el('summary','','Fejlesztőre vár · '+data.developer.length+' (megpróbálta, de programkód-módosítás kell)'));for(const d of data.developer){const row=el('div','improve-event');row.append(el('time','',clock(d.updated)),el('strong','',d.scope_name),el('span','',d.title+' — '+(d.evidence||d.why||'').split('\n')[0].slice(0,140)));dev.append(row);}body.append(dev);}
 // 5. Solved in the last day; they leave by themselves.
 if(data.done.length){const done=el('details','improve-log');done.open=view.open.has('done');done.ontoggle=()=>{done.open?view.open.add('done'):view.open.delete('done');};done.append(el('summary','','Nemrég megoldva · '+data.done.length+' (egy nap után eltűnik)'));for(const d of data.done){const row=el('div','improve-event');row.append(el('time','',clock(d.updated)),el('strong','','✓'),el('span','',d.title+' · '+d.scope_name));done.append(row);}body.append(done);}
 return body;
}
function stop(){if(view.timer){clearInterval(view.timer);view.timer=null;}}
async function showImprove(){
 stop();const panel=el('div','improve-panel');let last='';
 const refresh=async()=>{
  if(!panel.isConnected&&last){stop();return;}
  let data;try{data=await improveOp('improve_list');}catch(e){return;}
  const key=JSON.stringify([data.activity,data.ideas.map(i=>[i.id,i.status,i.urgency,i.working,i.also]),data.done.map(d=>d.id),(data.developer||[]).length,data.auto,view.filter,view.scope]);
  if(key===last)return;last=key;
  const holder=panel.closest('dialog')||panel.parentElement,top=holder?holder.scrollTop:0,inner=panel.scrollTop;
  panel.replaceChildren(build(data,refresh));if(holder)holder.scrollTop=top;panel.scrollTop=inner;
 };
 await refresh();showModal('Fejlődés',panel);
 view.timer=setInterval(()=>{if(document.hidden)return;if(!$('modal').open||!panel.isConnected){stop();return;}refresh();},5000);
}
window.showImprove=showImprove;
const nav=$('navImprove');if(nav)nav.onclick=()=>act(showImprove);
})();
