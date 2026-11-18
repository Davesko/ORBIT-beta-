/* Kobold: skills, methods, tips and questions shared with the Kobold assistant on the other Mac (kobold-orbit/1). */
(()=>{
const view=el('section','autopilot-app kobold-app');view.id='koboldApp';view.hidden=true;view.setAttribute('aria-label','Kobold');
$('autopilotApp').after(view);
const nav=el('button','rail-button','');nav.id='navKobold';nav.setAttribute('aria-pressed','false');const icon=el('span');icon.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM2 18v-1a5 5 0 0 1 9-3M17 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM22 18v-1a5 5 0 0 0-9-3M9 20h6M12 17v6"/></svg>';nav.append(icon,document.createTextNode('Kobold'));
$('navAutopilot').after(nav);
const st={filter:'all',type:'info',draft:'',last:'',timer:null};
const op=async(name,args)=>(await call('project_app',{op:name,args:args||{}})).result;
const ago=ts=>{if(!ts)return 'még soha';const m=Math.max(0,Math.round((Date.now()/1000-ts)/60));return m<1?'most':m<60?m+' perce':Math.round(m/60)+' órája';};
const clock=ts=>new Date(ts*1000).toLocaleString('hu-HU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
const TYPE={skill:'SKILL',info:'INFO',question:'KÉRDÉS',answer:'VÁLASZ',receipt:'NYUGTA',profile:'NÉVJEGY'};
const STATUS={sent:'elküldve',delivered:'megérkezett',read:'elolvasva',adopted:'átvéve',rejected:'elutasítva',worked:'bevált',failed:'nem vált be',unsupported:'nem érti',held:'visszatartva',received:'új',unverified:'ismeretlen eredet',kept:'megjegyezve'};
function chip(label,active,fn,extra){const b=el('button','improve-chip'+(active?' active':'')+(extra?' '+extra:''),label);b.type='button';b.onclick=fn;return b;}
function card(m,refresh){
 const c=el('article','kobold-card '+(m.direction==='in'?'in':'out')+(m.status==='held'||m.status==='unverified'?' warn':''));
 c.append(el('small','',(m.direction==='in'?'◀ KOBOLD':'ORBIT ▶')+' · '+clock(m.at)+' · '+(TYPE[m.type]||m.type)+(m.kind?' · '+m.kind:'')));
 c.append(el('strong','',m.title||''));if(m.text)c.append(el('p','',m.text));
 c.append(el('small','kobold-state',STATUS[m.status]||m.status));if(m.note)c.append(el('small','kobold-note',m.note));
 const a=el('div','improve-actions');
 if(m.direction==='in'&&m.type==='skill'&&['received','read'].includes(m.status)){a.append(button(m.kind==='data'?'Megtanulom':m.kind==='műhely'?'Beépítem projektként':'Átveszem',async()=>{const r=await op('kobold_adopt',{id:m.id});toast(r.note);st.last='';refresh();}),button('Elutasít',async()=>{await op('kobold_mark',{id:m.id,status:'rejected'});st.last='';refresh();},'secondary'));if(m.kind==='procedure')a.append(button('Projektként beépítem',async()=>{const r=await op('kobold_project',{id:m.id});toast(r.note);st.last='';refresh();},'secondary'));}
 if(m.direction==='in'&&m.type==='info'&&m.status==='received'){a.append(button('Megjegyzem',async()=>{await op('kobold_mark',{id:m.id,status:'kept'});st.last='';refresh();}),button('Elvetem',async()=>{await op('kobold_mark',{id:m.id,status:'rejected'});st.last='';refresh();},'secondary'));}
 if(m.direction==='in'&&['answer','question'].includes(m.type)&&m.status==='received')a.append(button('Elolvastam',async()=>{await op('kobold_mark',{id:m.id,status:'read'});st.last='';refresh();},'secondary'));
 if(a.childNodes.length)c.append(a);return c;
}
function build(d,refresh){
 const f=document.createDocumentFragment();
 const head=el('div','autopilot-head');head.append(el('span','eyebrow','KOBOLD-KAPCSOLAT · kobold-orbit/1'),el('h1','','Kobold'),
  el('p','hint',(d.syncthing&&d.syncthing.id?'Syncthing: '+(d.syncthing.running?'fut':'nem fut')+(d.syncthing.peers?' · '+d.syncthing.peers+' gép csatlakozva':' · a Kobold gépe még nincs összekötve')+' · ':'Syncthing nincs telepítve · ')+(d.peer.online?'● Kobold elérhető'+(d.peer.host?' ('+d.peer.host+')':'')+' · életjel '+ago(d.peer.seen):d.peer.seen?'○ Kobold most nem elérhető · utoljára '+ago(d.peer.seen):'○ Még nem érkezett jel Koboldtól.')));
 if(d.syncthing&&d.syncthing.id){const idrow=el('div','ap-hub-add');const idbox=el('input');idbox.type='text';idbox.readOnly=true;idbox.value=d.syncthing.id;idrow.append(el('span','improve-when','Ennek a gépnek a Syncthing-azonosítója:'),idbox,button('Másolás',()=>{navigator.clipboard?.writeText(d.syncthing.id).catch(()=>{});toast('Másolva. A Kobold gépén a Syncthingben: Távoli eszköz hozzáadása.');},'secondary'));head.append(idrow);}
 f.append(head);
 // Pairing and transports.
 const setup=el('section','ap-hub-box');setup.append(el('div','ap-hub-title'));setup.firstChild.append(el('h3','','Kapcsolat'),el('span','improve-when','postaláda: '+d.folder));
 if(!d.paired){const row=el('div','ap-hub-add');const code=el('input');code.type='text';code.placeholder='Kobold párosító kódja (64 karakter), vagy hagyd üresen új kódhoz';
  row.append(code,button('Párosítás',async()=>{const r=await op('kobold_pair',{code:code.value.trim()});if(!code.value.trim()){await navigator.clipboard?.writeText(r.code).catch(()=>{});toast('Új kód készült és a vágólapra került. Illeszd be Kobold Párosítás mezőjébe.');}else toast('Párosítva.');st.last='';refresh();}));setup.append(row);}
 else setup.append(el('p','improve-why','✓ Párosítva. Az üzenetek aláírva mennek, a kód csak ezen a gépen van.'));
 const git=el('div','ap-hub-add');const remote=el('input');remote.type='text';remote.placeholder='Közös git-repó (pl. git@github.com:felhasznalo/kobold-orbit-exchange.git)';remote.value=d.git.remote||'';
 git.append(remote,button(d.git.remote?'Szinkron most':'Git bekötése',async()=>{const r=d.git.remote&&remote.value===d.git.remote?await op('kobold_sync'):await op('kobold_git',{remote:remote.value});toast('Git: '+((r.git&&r.git.git)||r.git||'kész'));st.last='';refresh();},'secondary'));
 setup.append(git);if(d.git.state)setup.append(el('small','',' Git: '+d.git.state.git+' · '+ago(d.git.state.at)));
 f.append(setup);
 // Timeline with filters.
 const counts={all:d.items.length,in:d.items.filter(x=>x.direction==='in').length,out:d.items.filter(x=>x.direction==='out').length,held:d.items.filter(x=>x.status==='held'||x.status==='unverified').length};
 const bar=el('div','improve-bar');bar.append(chip('Mind · '+counts.all,st.filter==='all',()=>{st.filter='all';st.last='';refresh();}),chip('Kapott · '+counts.in,st.filter==='in',()=>{st.filter='in';st.last='';refresh();}),
  chip('Küldött · '+counts.out,st.filter==='out',()=>{st.filter='out';st.last='';refresh();}),chip('Visszatartva · '+counts.held,st.filter==='held',()=>{st.filter='held';st.last='';refresh();},counts.held?'sos':''));
 f.append(bar);
 const grid=el('div','kobold-grid');const line=el('section','kobold-line');
 const shown=d.items.filter(m=>m.type!=='receipt'&&(st.filter==='all'||st.filter===m.direction||st.filter==='held'&&(m.status==='held'||m.status==='unverified')));
 if(!shown.length)line.append(el('p','improve-empty','Még nincs üzenet ebben a nézetben.'));
 for(const m of shown)line.append(card(m,refresh));
 const side=el('aside','ap-hub-box kobold-side');
 const br=d.brain||{};side.append(el('h3','','Együttműködés'));
 side.append(el('small','','Ami most elakad nálam (naponta megosztom):'));
 if(!(br.needs||[]).length)side.append(el('p','improve-empty','Most nincs visszatérő hiba.'));
 for(const n of (br.needs||[]).slice(0,5)){const row=el('div','improve-event');row.append(el('strong','',n.count+'×'),el('span','',n.area+': '+n.error.slice(0,90)));side.append(row);}
 if((br.help||[]).length){side.append(el('small','','Segítségkéréseim:'));for(const h of br.help.slice(0,5)){const row=el('div','improve-event');row.append(el('strong','',h.answer?'válaszolt':'vár'),el('span','',h.area+(h.answer?' · '+h.answer.slice(0,90):'')));side.append(row);}}
 if((br.feedback||[]).length){side.append(el('small','','Visszajelzés a Koboldtól átvettekről:'));for(const f of br.feedback.slice(0,5)){const row=el('div','improve-event');row.append(el('strong','',f.ok+'/'+f.uses),el('span','','sikeres futás'));side.append(row);}}
 side.append(el('h3','','Kobold tudja'));
 const prof=d.peer_profile;if(!prof)side.append(el('p','improve-empty','A névjegye még nem érkezett meg.'));
 else{for(const k of (prof.skills||[]).slice(0,30)){const row=el('div','improve-event');row.append(el('strong','',k.kind==='data'?'adat':'módszer'),el('span','',k.title));row.onclick=()=>{st.type='question';st.draft='Hogyan működik nálad ez: '+k.title+'?';st.last='';refresh();};side.append(row);}}
 side.append(el('h3','','Saját skilljeim'));const auto=el('label','improve-auto');const box=el('input');box.type='checkbox';box.checked=d.auto_skills;box.onchange=async()=>{await op('kobold_auto_skills',{on:box.checked});};auto.append(box,el('span','',' Új vagy frissült skill magától megy'));side.append(auto);
 for(const k of d.skills.slice(0,40)){const row=el('div','ap-hub-row');const sent=d.shared[k.id]===k.version;row.append(el('span','ap-hub-text',k.title),button(sent?'Újra':'Küldés',async()=>{const r=await op('kobold_send_skill',{id:k.id});toast(r.status==='sent'?'Elküldve Koboldnak.':'Visszatartva: '+r.errors.join('; '));st.last='';refresh();},'secondary'));side.append(row);}
 grid.append(line,side);f.append(grid);
 // Composer.
 const comp=el('div','ap-hub-add kobold-compose');const sel=el('select');options(sel,[{value:'info',label:'Info'},{value:'question',label:'Kérdés'}],st.type);sel.onchange=()=>{st.type=sel.value;};
 const input=el('input');input.type='text';input.placeholder='Írj Koboldnak…';input.value=st.draft;input.oninput=()=>{st.draft=input.value;};
 const go=async()=>{const r=await op('kobold_send',{type:sel.value,text:input.value});toast(r.status==='sent'?'Elküldve.':'Visszatartva: '+r.errors.join('; '));st.draft='';st.last='';refresh();};
 input.onkeydown=e=>{if(e.key==='Enter')act(go);};comp.append(sel,input,button('Küldés',()=>act(go)));f.append(comp);
 return f;
}
async function refresh(){
 if(view.hidden)return;
 if(document.activeElement&&view.contains(document.activeElement)&&document.activeElement.tagName==='INPUT'&&st.last)return;
 let d;try{d=await op('kobold_overview');}catch(e){return;}
 const key=JSON.stringify([d.paired,d.peer,d.syncthing,d.items.map(i=>[i.id,i.status]),d.shared,d.git,d.auto_skills,st.filter,st.type,st.draft]);
 if(key===st.last)return;st.last=key;const top=view.scrollTop;view.replaceChildren(build(d,refresh));view.scrollTop=top;
}
const base=switchApp;
switchApp=function(v){base(v);const on=v==='kobold';view.hidden=!on;nav.classList.toggle('active',on);nav.setAttribute('aria-pressed',String(on));
 if(on){st.last='';refresh();if(!st.timer)st.timer=setInterval(()=>{if(!document.hidden)refresh();},5000);}else if(st.timer){clearInterval(st.timer);st.timer=null;}};
nav.onclick=()=>switchApp('kobold');
})();
