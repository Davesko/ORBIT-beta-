/* Memória: what ORBIT has learned about its owner, drawn as a knowledge graph — the owner in the middle,
   the people, projects, tools, places and topics of their life around them, typed relations between them, and
   the memories each one comes from. Everything visible, editable and removable; it all stays on this Mac. */
const MEMORY_KIND={identity:'Személy',preference:'Preferencia',goal:'Cél',fact:'Tény',project:'Projekt'};
const ENTITY_KIND={user:'Te',person:'Személy',project:'Projekt',organization:'Szervezet',tool:'Eszköz',place:'Hely',topic:'Téma'};
const ENTITY_COLOR={user:'#f3d6ff',person:'#ff9fb0',project:'#ffcf88',organization:'#86c3ff',tool:'#86e0b1',place:'#c6a6ff',topic:'#8be4ff'};
const MEMORY_COLOR={identity:'#d9c2f2',preference:'#b9cdf5',goal:'#b2e6c9',fact:'#c9c5da',project:'#efd2a2'};
let memoryData=null,memoryGraphData=null,memoryKind='',memoryQuery='',memorySelected='',memoryHidden=new Set(),memoryGraphObserver=null,memoryStop=null;
let memoryView=(()=>{try{return localStorage.getItem('orbitMemoryView')||'graph';}catch(e){return 'graph';}})();
async function memoryOp(op,args){return (await call('project_app',{op,args:args||{}})).result;}
async function loadMemory(){
 const [list,graph]=await Promise.all([memoryOp('memory_list',{query:memoryView==='list'?memoryQuery:'',kind:memoryView==='list'?memoryKind:''}),memoryView==='graph'?memoryOp('memory_graph',{}):Promise.resolve(null)]);
 memoryData=list;if(graph)memoryGraphData=graph;renderMemory();}
/* Told in the chat when ORBIT just noted something from the owner's words. */
function memoryNotice(n){if(!n)return;let seen=0;try{seen=+localStorage.getItem('orbitMemoryNote')||0;}catch(e){}if(n.at<=seen)return;try{localStorage.setItem('orbitMemoryNote',n.at);}catch(e){}if(seen)toast('✦ Megjegyeztem: '+n.text);}
function memoryAgo(t){if(!t)return '';const d=Math.floor((Date.now()/1000-t)/86400);return d<1?'ma':d<30?d+' napja':Math.floor(d/30)+' hónapja';}
function memoryDate(t){return t?new Date(t*1000).toLocaleDateString('hu-HU',{month:'short',day:'numeric'}):'';}
function memoryEdit(m){const form=el('div'),kind=field('Fajta','memoryEditKind','select');options(kind.querySelector('select'),Object.entries(MEMORY_KIND).map(([value,label])=>({value,label})),m?.kind||'fact');
 form.append(field('Emlék','memoryEditText','textarea',m?.display||''),kind,button('Mentés',async()=>{await memoryOp('memory_save',{key:m?.key,display:$('memoryEditText').value,kind:$('memoryEditKind').value});$('modal').close();await loadMemory();}));
 if(m)form.append(button('Törlés',async()=>{await memoryOp('memory_delete',{key:m.key});$('modal').close();memorySelected='';await loadMemory();},'pm-danger'));
 showModal(m?'Emlék szerkesztése':'Új emlék',form);$('memoryEditText').focus();}
function setMemoryView(view){memoryView=view;try{localStorage.setItem('orbitMemoryView',view);}catch(e){}act(loadMemory);}

function renderMemory(){const pane=$('memoryApp'),d=memoryData;if(!d)return;const focused=document.activeElement?.id==='memorySearch';
 memoryGraphObserver?.disconnect();memoryStop?.();pane.replaceChildren();
 const head=el('div','tool-head'),title=el('div');title.append(el('h1','','Memória'),el('p','hint','Amit ORBIT megtanult rólad: ki vagy, min dolgozol, mit szeretsz. Minden tény mögött ott a beszélgetés, amiből jött. Minden ezen a gépen marad.'));
 const sw=el('label','settings-switch'),box=el('input');box.type='checkbox';box.checked=d.enabled;box.onchange=()=>act(async()=>{await memoryOp('memory_enable',{on:box.checked});await loadMemory();});sw.append(box,el('span','',d.enabled?'Tanulás bekapcsolva':'Tanulás kikapcsolva'));head.append(title,sw);pane.append(head);
 const g=memoryGraphData;
 const strip=el('div','mem-stats');
 const stat=(n,label)=>{const s=el('span','mem-stat');s.append(el('strong','',String(n)),el('small','',label));return s;};
 strip.append(stat(d.total,'emlék'));
 if(g)strip.append(stat(g.stats.entities,'entitás'),stat(g.stats.relations,'kapcsolat'));
 if(g&&g.stats.past)strip.append(stat(g.stats.past,'korábbi tény'));
 const state=el('span','mem-state');
 state.textContent=(d.enabled?(d.learned_at?'Utoljára tanult: '+new Date(d.learned_at*1000).toLocaleString('hu-HU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'Hamarosan kezd tanulni a beszélgetéseidből.'):'A tanulás szünetel.')+(d.waiting?' · még '+d.waiting+' üzenetet olvas el':'')+(g&&g.pending?' · '+g.pending+' emlék vár összekötésre':'');
 strip.append(state);pane.append(strip);
 const tools=el('div','tool-row mem-tools'),seg=el('div','mem-seg');
 for(const [v,label] of [['graph','◉ Gráf'],['list','☰ Lista']]){const b=el('button','mem-seg-btn'+(memoryView===v?' active':''),label);b.setAttribute('aria-pressed',String(memoryView===v));b.onclick=()=>setMemoryView(v);seg.append(b);}
 const search=el('input','tool-search');search.id='memorySearch';search.placeholder=memoryView==='graph'?'Keresés a gráfban… (kiemeli a találatokat)':'Keresés az emlékek között…';search.value=memoryQuery;search.setAttribute('aria-label','Keresés a memóriában');let timer;
 search.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{memoryQuery=search.value;if(memoryView==='graph')memoryRedraw?.();else act(loadMemory);},memoryView==='graph'?60:250);};
 tools.append(seg,search,button('＋ Új emlék',async()=>memoryEdit(null),'secondary'),button('Rendezés',async()=>{toast((await memoryOp('memory_tidy')).message);await loadMemory();},'secondary'),button('Újraolvasás',async()=>{const r=await memoryOp('memory_relink');toast(r.pending+' emléket olvas újra a háttérben a gráfhoz.');await loadMemory();},'secondary'),button('Munkamódszerek',()=>act(openSkills),'secondary'));
 pane.append(tools);
 if(memoryView==='graph'&&g){renderMemoryGraph(pane,g,d);}
 else renderMemoryList(pane,d);
 if(focused){search.focus();search.setSelectionRange(search.value.length,search.value.length);}}

function renderMemoryList(pane,d){
 if(d.profile){const card=el('button','memory-profile');card.append(el('strong','','Így ismerlek'),el('span','',d.profile.display));card.onclick=()=>memoryEdit(d.profile);pane.append(card);}
 const chips=el('div','tool-chips');for(const [value,label] of [['','Minden · '+d.total],...Object.entries(MEMORY_KIND).map(([k,v])=>[k,v+' · '+d.counts[k]])]){const c=el('button','tool-chip'+(memoryKind===value?' active':''),label);c.setAttribute('aria-pressed',String(memoryKind===value));c.onclick=()=>{memoryKind=value;act(loadMemory);};chips.append(c);}pane.append(chips);
 if(!d.memories.length)pane.append(el('p','hint',d.total?'Nincs találat.':'Még nincs emlék. Beszélgess a fő chatben, vagy adj hozzá egyet.'));
 const list=el('div','memory-list');for(const m of d.memories){const row=el('button','memory-row');row.append(el('span','memory-text',m.display));const meta=el('span','memory-meta');meta.append(el('span','memory-kind memory-'+m.kind,MEMORY_KIND[m.kind]||m.kind),el('small','',(m.source==='auto'?'automatikus':'kézi')+(m.uses?' · '+m.uses+'×':'')+' · '+memoryAgo(m.created||m.updated)));row.append(meta);row.onclick=()=>memoryEdit(m);list.append(row);}pane.append(list);}

/* Procedural memory is separate from personal facts. Procedures grant no extra tools. */
const SKILL_DESC_HU={'mail-review':'Levelek keresése, áttekintése és feltételes reggeli értesítés.','project-audit':'A megadott projekt ügynökeinek, beállításainak és hibáinak ellenőrzése.','shorts-story':'Forrásokra épülő Shorts-tervezés, történetvezetés és végellenőrzés.','evidence-research':'Friss, releváns források és ellenőrizhető kutatási eredmények.'};
function skillLibraryBox(){const box=el('section','memory-profile');box.append(el('strong','','Skillkönyvtárak a netről'),el('p','hint','Nyilvános SKILL.md-gyűjtemények. Az ORBIT csak a szövegüket olvassa (a bennük lévő programokat nem futtatja), és a projektjeidhez illőket munkamódszerként veszi át. A két ellenőrzött könyvtárból a nagyon illők rögtön használhatók, a többi piszkozat.'));const list=el('div','');box.append(list);
 const load=async()=>{list.textContent='Betöltés…';const d=await memoryOp('skilllib_overview');list.textContent='';for(const src of d.sources){list.append(el('small','',src.title+' · '+src.repo+' · '+src.skills+' skill'+(src.error?' · hiba: '+src.error:'')),el('br'));}
  if(d.matches.length){list.append(el('p','hint','A projektjeidhez illők:'));for(const m of d.matches){const row=el('div','tool-row');row.append(el('span','',m.name+' → '+m.project_name+' ('+Math.round(m.score*100)+'%)'));if(m.adopted)row.append(el('small','','átvéve'));else row.append(button('Átveszem piszkozatként',()=>act(async()=>{await memoryOp('skilllib_adopt',{id:m.id,project:m.project});await openSkills();}),'secondary'));list.append(row);}}
  const add=el('input');add.placeholder='https://github.com/szerzo/skill-gyujtemeny';const row=el('div','tool-row');row.append(add,button('Könyvtár hozzáadása',()=>act(async()=>{const r=await memoryOp('skilllib_add',{url:add.value.trim()});alert(r.note||r.error||'Kész');await load();}),'secondary'),button('Frissítés',()=>act(async()=>{await memoryOp('skilllib_refresh');await load();}),'secondary'),button('Keress most a projektjeimhez',()=>act(async()=>{const r=await memoryOp('skilllib_scout');alert(r.note);await openSkills();})));list.append(row);};
 load();return box;}
async function openSkills(){const d=await memoryOp('skill_list');const body=el('div','skill-library');body.append(el('p','hint','Újrahasználható munkamódszerek az ORBIT számára. A használható, bekapcsolt módszereket a kérés alapján választja ki. A piszkozatokat nem használja. Új API-skillt a Fő chatben taníthatsz („tanuld meg az időjárás API-t”), és az ORBIT magától is megtanul egyet, ha egy kéréshez kell: megkeresi a dokumentációt, élőben kipróbálja, és csak adatot olvas vele.'),button('＋ Saját munkamódszer',()=>editSkill(),'secondary'));body.append(skillLibraryBox());
 for(const skill of d.skills){const row=el('section','memory-profile');row.append(el('strong','',skill.title),el('p','hint',SKILL_DESC_HU[skill.id]||skill.description),el('small','',`v${skill.version} · ${skill.source==='builtin'?'Beépített':skill.source==='learned'?'Magától tanult':skill.source==='library'?'Skillkönyvtárból · '+(skill.library?.repo||''):'Saját'} · ${skill.status==='published'?'Használható':'Piszkozat'}`));if(skill.api)row.append(skillApiInfo(skill));const actions=el('div','tool-row');actions.append(button('Megnézem',()=>editSkill(skill,skill.source==='builtin'),'secondary'));const toggle=button(skill.enabled?'Bekapcsolva':'Kikapcsolva',()=>act(async()=>{await memoryOp('skill_toggle',{id:skill.id,enabled:!skill.enabled});await openSkills();}),'secondary');toggle.setAttribute('aria-pressed',String(skill.enabled));toggle.setAttribute('aria-label',skill.title+' használata');actions.append(toggle);row.append(actions);body.append(row);}
 showModal('Munkamódszerek / Skillek',body);}
function skillApiInfo(skill){const box=el('div','skill-api');const api=skill.api,test=skill.learned?.test||{};const host=(()=>{try{return new URL(api.base).hostname}catch{return api.base}})();
 box.append(el('small','',`API · ${host} · ${api.endpoints.length} végpont · csak olvasás · ${test.ok?'élő teszt sikeres':test.error?'teszt: '+test.error.slice(0,120):'még nincs teszt'}`));
 if(api.auth?.kind&&api.auth.kind!=='none'){const row=el('div','tool-row');const input=document.createElement('input');input.type='password';input.placeholder=skill.has_key?'Kulcs megadva · új kulcs cseréhez':'API-kulcs beillesztése';input.autocomplete='off';input.setAttribute('aria-label',skill.title+' API-kulcsa');
  row.append(input,button('Kulcs mentése',()=>act(async()=>{const r=await memoryOp('skill_key_save',{id:skill.id,key:input.value.trim()});input.value='';if(r.error)alert(r.error);else if(r.tested===false)alert('A kulcs elmentve, de a próbahívás nem sikerült: '+r.error);await openSkills();}),'secondary'));
  if(api.key_url){const a=document.createElement('a');a.href=api.key_url;a.target='_blank';a.rel='noopener';a.textContent='Kulcs igénylése';row.append(a);}box.append(row);}
 return box;}
function editSkill(skill=null,builtin=false){const body=el('div');body.append(field('Név','skTitle','input',skill?.title||''),field('Mikor használandó? · belső leírás','skDescription','textarea',skill?.description||''),field('Belső lépések · angolul, soronként egy','skSteps','textarea',(skill?.steps||[]).join('\n')),field('Belső ellenőrzés · angolul, soronként egy','skVerify','textarea',(skill?.verification||[]).join('\n')),field('Keresési címkék · vesszővel elválasztva','skTags','input',(skill?.tags||[]).join(', ')));const status=field('Állapot','skStatus','select');options(status.querySelector('select'),[{value:'draft',label:'Piszkozat · az ORBIT még nem használja'},{value:'published',label:'Használható · megjelenhet a feladathoz'}],skill?.status||'draft');body.append(status);
 if(builtin)body.append(el('p','hint','A beépített módszer saját másolatként menthető. A lépések és az ellenőrzések megmaradnak, a hozzáférési szabályok minden módszerre érvényesek.'));
 body.append(button(builtin?'Mentés saját másolatként':'Mentés',()=>act(async()=>{await memoryOp('skill_save',{skill:{...(skill&&!builtin?{id:skill.id}:{}),title:$('skTitle').value,description:$('skDescription').value,steps:$('skSteps').value.split('\n').map(x=>x.trim()).filter(Boolean),verification:$('skVerify').value.split('\n').map(x=>x.trim()).filter(Boolean),tags:$('skTags').value.split(',').map(x=>x.trim()).filter(Boolean),status:$('skStatus').value}});await openSkills();})),button('Vissza a munkamódszerekhez',()=>act(openSkills),'secondary'));
 showModal(builtin?'Beépített munkamódszer':skill?'Munkamódszer szerkesztése':'Új munkamódszer',body);}


/* The knowledge graph. A small force layout (repulsion, typed springs, the owner pinned in the middle) settles
   before the first frame; it only moves again while a node is dragged, and not at all with reduced motion. */
let memoryRedraw=null;
function memoryNorm(t){return String(t||'').normalize('NFKD').replace(/[̀-ͯ]/g,'').toLowerCase();}
function renderMemoryGraph(pane,g,d){
 const wrap=el('div','mem-graph'),stage=el('div','mem-stage'),side=el('aside','mem-side'),canvas=el('canvas','mem-canvas');
 canvas.setAttribute('role','img');canvas.setAttribute('aria-label','Memóriagráf: te középen, körülötted az entitások és az emlékek. A pontok kattinthatók; a lista nézet ugyanezt szövegesen mutatja.');
 const legend=el('div','mem-legend');
 const groups=['project','person','organization','tool','place','topic'];
 for(const k of groups){if(!g.nodes.some(n=>n.type==='entity'&&n.group===k))continue;const b=el('button','mem-legend-item'+(memoryHidden.has(k)?' off':''));const dot=el('i');dot.style.background=ENTITY_COLOR[k];b.append(dot,el('span','',ENTITY_KIND[k]));b.setAttribute('aria-pressed',String(!memoryHidden.has(k)));b.onclick=()=>{memoryHidden.has(k)?memoryHidden.delete(k):memoryHidden.add(k);b.classList.toggle('off');b.setAttribute('aria-pressed',String(!memoryHidden.has(k)));draw();};legend.append(b);}
 {const k='memories',b=el('button','mem-legend-item'+(memoryHidden.has(k)?' off':''));const dot=el('i','mem-legend-mem');b.append(dot,el('span','','Emlékek'));b.onclick=()=>{memoryHidden.has(k)?memoryHidden.delete(k):memoryHidden.add(k);b.classList.toggle('off');draw();};legend.append(b);}
 const zoomer=el('div','mem-zoom');
 stage.append(canvas,legend,zoomer);wrap.append(stage,side);pane.append(wrap);
 if(g.nodes.length<=1){side.append(el('p','hint','Még nincs mit összekötni. Beszélgess a fő chatben – az ORBIT magától tanul, és a gráf kirajzolódik.'));}
 const ctx=canvas.getContext('2d');if(!ctx){side.append(el('p','hint','A gráf itt nem rajzolható ki; használd a lista nézetet.'));return;}
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches||document.documentElement.dataset.motion==='off';
 // ---- layout -------------------------------------------------------------------------------------------
 const nodes=g.nodes.map(n=>({...n})),byId=new Map(nodes.map(n=>[n.id,n]));
 const links=g.links.filter(l=>byId.has(l.source)&&byId.has(l.target)).map(l=>({...l,a:byId.get(l.source),b:byId.get(l.target)}));
 const groupAngle={};groups.forEach((k,i)=>groupAngle[k]=i/groups.length*Math.PI*2);
 let seed=7;const rand=()=>(seed=(seed*16807)%2147483647)/2147483647;
 for(const n of nodes){
  n.r=n.type==='user'?26:n.type==='entity'?Math.min(22,9+Math.sqrt(n.degree||1)*2.6):Math.min(9,4.5+Math.sqrt(n.uses||0)*1.2);
  if(n.type==='user'){n.x=0;n.y=0;n.fixed=true;continue;}
  const ang=(n.type==='entity'?groupAngle[n.group]||0:rand()*Math.PI*2)+(rand()-.5)*1.2,rad=n.type==='entity'?170+rand()*60:300+rand()*90;
  n.x=Math.cos(ang)*rad;n.y=Math.sin(ang)*rad;n.vx=0;n.vy=0;
 }
 const rest={relation:220,derived:240,mention:85,memory:150};
 function tick(alpha){
  for(let i=0;i<nodes.length;i++){const a=nodes[i];for(let j=i+1;j<nodes.length;j++){const b=nodes[j];let dx=b.x-a.x,dy=b.y-a.y,d2=dx*dx+dy*dy||.01;if(d2>250000)continue;const d=Math.sqrt(d2),min=a.r+b.r+14;let f=(a.type==='memory'&&b.type==='memory'?1100:a.type==='entity'&&b.type==='entity'?5200:3000)/d2;if(d<min)f+=(min-d)*.08;dx/=d;dy/=d;if(!a.fixed){a.vx-=dx*f*alpha;a.vy-=dy*f*alpha;}if(!b.fixed){b.vx+=dx*f*alpha;b.vy+=dy*f*alpha;}}}
  for(const l of links){const a=l.a,b=l.b;let dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||.01;const k=(l.type==='mention'?.09:.05)*alpha,f=(d-(rest[l.type]||120))*k;dx/=d;dy/=d;if(!a.fixed){a.vx+=dx*f;a.vy+=dy*f;}if(!b.fixed){b.vx-=dx*f;b.vy-=dy*f;}}
  for(const n of nodes){if(n.fixed)continue;n.vx-=n.x*.004*alpha;n.vy-=n.y*.004*alpha;n.vx*=.82;n.vy*=.82;n.x+=n.vx;n.y+=n.vy;}
 }
 const settle=nodes.length>350?140:260;for(let i=0;i<settle;i++)tick(1-i/settle*.85);
 // ---- view ---------------------------------------------------------------------------------------------
 let scale=1,ox=0,oy=0,hover=null,drag=null,alpha=0,frame=0,fitted=false,moved=false;
 const selectedId=()=>memorySelected&&byId.has(memorySelected)?memorySelected:'';
 function fit(){const w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h)return;let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;for(const n of nodes){x0=Math.min(x0,n.x-n.r);y0=Math.min(y0,n.y-n.r);x1=Math.max(x1,n.x+n.r);y1=Math.max(y1,n.y+n.r);}scale=Math.max(.35,Math.min(1.15,Math.min(w/(x1-x0+160),h/(y1-y0+160))));ox=w/2-(x0+x1)/2*scale;oy=h/2-(y0+y1)/2*scale;fitted=true;}
 const visible=n=>n.type==='user'||(n.type==='memory'?!memoryHidden.has('memories'):!memoryHidden.has(n.group));
 function matches(n){const q=memoryNorm(memoryQuery).trim();return !q||memoryNorm(n.label).includes(q);}
 function neighbours(id){const s=new Set([id]);for(const l of links)if(l.source===id)s.add(l.target);else if(l.target===id)s.add(l.source);return s;}
 function draw(){
  const w=canvas.clientWidth,h=canvas.clientHeight,ratio=Math.min(window.devicePixelRatio||1,2);if(!w||!h)return;
  if(canvas.width!==Math.round(w*ratio)||canvas.height!==Math.round(h*ratio)){canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);}
  if(!fitted)fit();
  ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,w,h);
  // Labels follow the theme: a light theme gets dark text on a light halo.
  const css=getComputedStyle(document.documentElement),ink=(css.getPropertyValue('--theme-text')||'#f2eefc').trim(),paper=(css.getPropertyValue('--theme-bg')||'#0c0c14').trim(),soft=(css.getPropertyValue('--theme-muted')||'#cfcbe2').trim();
  const sel=selectedId(),focus=sel?neighbours(sel):null,q=memoryNorm(memoryQuery).trim();
  const dim=n=>(focus&&!focus.has(n.id))||(q&&!matches(n));
  ctx.save();ctx.translate(ox,oy);ctx.scale(scale,scale);
  // halo behind the owner
  const halo=ctx.createRadialGradient(0,0,10,0,0,260);halo.addColorStop(0,'rgba(190,140,255,.16)');halo.addColorStop(1,'rgba(190,140,255,0)');ctx.fillStyle=halo;ctx.beginPath();ctx.arc(0,0,260,0,Math.PI*2);ctx.fill();
  for(const l of links){
   if(!visible(l.a)||!visible(l.b))continue;
   const on=sel&&(l.source===sel||l.target===sel),faded=(focus&&!on)||(q&&!(matches(l.a)||matches(l.b)));
   ctx.globalAlpha=faded?.07:on?.95:l.type==='mention'?.28:l.type==='memory'?.22:.55;
   ctx.lineWidth=(l.type==='relation'?1.3+Math.min(3,(l.evidence||1)*.6):1)/Math.sqrt(scale);
   ctx.strokeStyle=l.type==='relation'?(l.invalid_at?'#77728d':'#b9a3ff'):l.type==='derived'?'#8f86c2':l.type==='memory'?'#6f6a88':'#8be4ff';
   ctx.setLineDash(l.invalid_at?[6,5]:l.type==='derived'?[2,4]:[]);
   ctx.beginPath();ctx.moveTo(l.a.x,l.a.y);
   if(l.type==='relation'||l.type==='derived'){const mx=(l.a.x+l.b.x)/2,my=(l.a.y+l.b.y)/2,dx=l.b.x-l.a.x,dy=l.b.y-l.a.y;ctx.quadraticCurveTo(mx-dy*.12,my+dx*.12,l.b.x,l.b.y);}
   else ctx.lineTo(l.b.x,l.b.y);ctx.stroke();ctx.setLineDash([]);
   if(l.type==='relation'&&!faded){const t=.82,mx=(l.a.x+l.b.x)/2-(l.b.y-l.a.y)*.12,my=(l.a.y+l.b.y)/2+(l.b.x-l.a.x)*.12;const px=(1-t)*(1-t)*l.a.x+2*(1-t)*t*mx+t*t*l.b.x,py=(1-t)*(1-t)*l.a.y+2*(1-t)*t*my+t*t*l.b.y,ang=Math.atan2(l.b.y-py,l.b.x-px),s=6/Math.sqrt(scale);ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.moveTo(px+Math.cos(ang)*s,py+Math.sin(ang)*s);ctx.lineTo(px+Math.cos(ang+2.5)*s,py+Math.sin(ang+2.5)*s);ctx.lineTo(px+Math.cos(ang-2.5)*s,py+Math.sin(ang-2.5)*s);ctx.fill();}
  }
  ctx.globalAlpha=1;
  for(const n of nodes){
   if(!visible(n))continue;const faded=dim(n);ctx.globalAlpha=faded?.16:1;
   const color=n.type==='user'?ENTITY_COLOR.user:n.type==='entity'?ENTITY_COLOR[n.group]||'#8be4ff':MEMORY_COLOR[n.group]||'#c9c5da';
   if(n.type!=='memory'&&!faded){ctx.shadowColor=color;ctx.shadowBlur=(n.type==='user'?28:14);}
   if(n.type==='user'){const gr=ctx.createRadialGradient(-8,-8,4,0,0,n.r);gr.addColorStop(0,'#ffffff');gr.addColorStop(1,'#b48cff');ctx.fillStyle=gr;}else ctx.fillStyle=color;
   ctx.beginPath();if(n.type==='memory'){const s=n.r;ctx.roundRect?ctx.roundRect(n.x-s,n.y-s,s*2,s*2,s*.6):ctx.rect(n.x-s,n.y-s,s*2,s*2);}else ctx.arc(n.x,n.y,n.r,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;
   if(n.type==='memory'&&n.source==='manual'){ctx.strokeStyle='#ffffff';ctx.lineWidth=1.2/scale;ctx.stroke();}
   if(n.id===sel||n===hover){ctx.strokeStyle='#ffffff';ctx.lineWidth=2/scale;ctx.beginPath();ctx.arc(n.x,n.y,n.r+5,0,Math.PI*2);ctx.stroke();}
  }
  // labels: the owner and entities always; memories when close, hovered or selected
  ctx.textAlign='center';ctx.textBaseline='top';
  // Most connected first; a label that would cover one already drawn waits for zoom, hover or selection.
  const taken=[];const order=[...nodes].sort((a,b)=>(b.id===sel)-(a.id===sel)||(b===hover)-(a===hover)||(a.type==='user'?-1:b.type==='user'?1:0)||(b.type==='entity')-(a.type==='entity')||(b.degree||0)-(a.degree||0));
  for(const n of order){
   if(!visible(n))continue;const faded=dim(n);if(faded&&n.id!==sel)continue;
   const show=n.type!=='memory'||n===hover||n.id===sel||(focus&&focus.has(n.id))||scale>2.1||(q&&matches(n));if(!show)continue;
   const size=(n.type==='user'?15:n.type==='entity'?12:11)/Math.sqrt(scale);ctx.font=(n.type==='memory'?'':'600 ')+size+'px -apple-system,system-ui,sans-serif';
   let text=n.type==='user'?n.label:String(n.label);if(n.type==='memory'&&text.length>46)text=text.slice(0,44)+'…';
   const y=n.y+n.r+4/scale,tw=ctx.measureText(text).width,box=[n.x-tw/2,y,n.x+tw/2,y+size*1.2];
   if(n.id!==sel&&n!==hover&&taken.some(b=>box[0]<b[2]&&box[2]>b[0]&&box[1]<b[3]&&box[3]>b[1]))continue;taken.push(box);
   ctx.lineWidth=3/scale;ctx.strokeStyle=paper;ctx.strokeText(text,n.x,y);ctx.fillStyle=n.type==='memory'?soft:ink;ctx.fillText(text,n.x,y);
  }
  // relation names on the selected node's edges
  if(sel){ctx.font=(11/Math.sqrt(scale))+'px -apple-system,system-ui,sans-serif';for(const l of links){if(!(l.source===sel||l.target===sel)||l.type==='mention'||!visible(l.a)||!visible(l.b))continue;const mx=(l.a.x+l.b.x)/2-(l.type==='memory'?0:(l.b.y-l.a.y)*.06),my=(l.a.y+l.b.y)/2+(l.type==='memory'?0:(l.b.x-l.a.x)*.06);const t=l.label+(l.invalid_at?' (korábban)':'');ctx.lineWidth=3/scale;ctx.strokeStyle=paper;ctx.strokeText(t,mx,my);ctx.fillStyle=l.invalid_at?soft:ink;ctx.fillText(t,mx,my);}}
  ctx.restore();ctx.globalAlpha=1;
 }
 memoryRedraw=draw;
 function animate(){if(alpha<.02||reduced){alpha=0;frame=0;draw();return;}tick(alpha);alpha*=.94;draw();frame=requestAnimationFrame(animate);}
 function reheat(){if(reduced)return;alpha=Math.max(alpha,.35);if(!frame)frame=requestAnimationFrame(animate);}
 memoryStop=()=>{if(frame)cancelAnimationFrame(frame);frame=0;memoryRedraw=null;};
 // ---- interaction --------------------------------------------------------------------------------------
 const world=e=>{const r=canvas.getBoundingClientRect();return {x:(e.clientX-r.left-ox)/scale,y:(e.clientY-r.top-oy)/scale,sx:e.clientX-r.left,sy:e.clientY-r.top};};
 const hit=p=>{let best=null,bd=1e9;for(const n of nodes){if(!visible(n))continue;const d=Math.hypot(n.x-p.x,n.y-p.y);if(d<=n.r+6/scale&&d<bd){best=n;bd=d;}}return best;};
 canvas.onpointerdown=e=>{const p=world(e),n=hit(p);drag={n,start:p,sx:p.sx,sy:p.sy,ox,oy,moved:false};canvas.setPointerCapture(e.pointerId);};
 canvas.onpointermove=e=>{const p=world(e);if(!drag){const n=hit(p);if(n!==hover){hover=n;canvas.style.cursor=n?'pointer':'grab';canvas.title=n?(n.type==='memory'?n.label:(ENTITY_KIND[n.group]||'')+' · '+n.label):'';draw();}return;}
  if(!drag.moved&&Math.hypot(p.sx-drag.sx,p.sy-drag.sy)<4)return;drag.moved=true;
  if(drag.n&&drag.n.type!=='user'){drag.n.x=p.x;drag.n.y=p.y;drag.n.vx=0;drag.n.vy=0;drag.n.pinned=true;reheat();draw();}
  else{moved=true;ox=drag.ox+(p.sx-drag.sx);oy=drag.oy+(p.sy-drag.sy);draw();}};
 canvas.onpointerup=e=>{if(drag&&!drag.moved)select(drag.n?drag.n.id:'');if(drag?.n?.pinned){drag.n.pinned=false;}drag=null;};
 canvas.onpointercancel=()=>{drag=null;};
 canvas.onwheel=e=>{e.preventDefault();const r=canvas.getBoundingClientRect(),sx=e.clientX-r.left,sy=e.clientY-r.top,k=Math.exp(-e.deltaY*.0015),ns=Math.max(.25,Math.min(3.5,scale*k));moved=true;ox=sx-(sx-ox)*ns/scale;oy=sy-(sy-oy)*ns/scale;scale=ns;draw();};
 canvas.ondblclick=e=>{const n=hit(world(e));if(!n)return;const w=canvas.clientWidth,h=canvas.clientHeight;scale=Math.max(scale,1.4);ox=w/2-n.x*scale;oy=h/2-n.y*scale;draw();};
 const zb=(label,aria,fn)=>{const b=el('button','mem-zoom-btn',label);b.setAttribute('aria-label',aria);b.onclick=fn;return b;};
 zoomer.append(zb('＋','Nagyítás',()=>{moved=true;scale=Math.min(3.5,scale*1.25);const w=canvas.clientWidth/2,h=canvas.clientHeight/2;ox=w-(w-ox)*1.25;oy=h-(h-oy)*1.25;draw();}),zb('−','Kicsinyítés',()=>{moved=true;scale=Math.max(.25,scale/1.25);const w=canvas.clientWidth/2,h=canvas.clientHeight/2;ox=w-(w-ox)/1.25;oy=h-(h-oy)/1.25;draw();}),zb('⤢','Teljes gráf',()=>{moved=false;fit();draw();}));
 // ---- side panel ---------------------------------------------------------------------------------------
 const names=new Map(nodes.map(n=>[n.id,n.label]));
 function memoryOf(node){return d.memories.find(m=>m.key===node.key)||{key:node.key,display:node.label,kind:node.group};}
 function chip(n){const b=el('button','mem-chip');const dot=el('i');dot.style.background=n.type==='entity'?ENTITY_COLOR[n.group]:n.type==='user'?ENTITY_COLOR.user:MEMORY_COLOR[n.group];b.append(dot,el('span','',n.type==='memory'&&n.label.length>70?n.label.slice(0,68)+'…':n.label));b.onclick=()=>select(n.id,true);return b;}
 function section(title,items){const s=el('section','mem-section');s.append(el('h3','',title));const box=el('div','mem-chips');box.append(...items);s.append(box);return s;}
 function relationRow(l,from){const other=l.source===from?l.b:l.a,out=l.source===from;const row=el('button','mem-rel'+(l.invalid_at?' past':''));const dot=el('i');dot.style.background=other.type==='entity'?ENTITY_COLOR[other.group]:other.type==='user'?ENTITY_COLOR.user:MEMORY_COLOR[other.group];row.append(el('span','mem-rel-label',out?l.label+' →':'← '+l.label),dot,el('span','mem-rel-target',other.label.length>60?other.label.slice(0,58)+'…':other.label));
  const when=l.invalid_at?'korábban · '+memoryDate(l.invalid_at)+'-ig':l.valid_from?'óta: '+memoryDate(l.valid_from):l.type==='derived'?(l.evidence||1)+' emlékből következtetve':'';if(when)row.append(el('small','',when));row.onclick=()=>select(other.id,true);return row;}
 function renderSide(){
  side.replaceChildren();const id=selectedId(),n=id?byId.get(id):null;
  if(!n){
   if(d.profile){const card=el('button','mem-profile');card.append(el('span','eyebrow','ÍGY ISMERLEK'),el('p','',d.profile.display));card.onclick=()=>memoryEdit(d.profile);side.append(card);}
   const user=byId.get('user');if(user){const rels=links.filter(l=>(l.source==='user'||l.target==='user')&&(l.type==='relation'||l.type==='derived'));if(rels.length){const s=el('section','mem-section');s.append(el('h3','','Ami a legfontosabb neked'));for(const l of rels.sort((a,b)=>(b.evidence||1)-(a.evidence||1)).slice(0,8))s.append(relationRow(l,'user'));side.append(s);}}
   const tl=el('section','mem-section');tl.append(el('h3','','Tanulási napló'));
   const icon={learned:'✦',linked:'⟷',superseded:'↺'};const verb={learned:'Megtanulta',linked:'Összekötötte',superseded:'Változott'};
   const entries=(g.timeline||[]).slice(0,14);if(!entries.length)tl.append(el('p','hint','Még nincs bejegyzés.'));
   for(const t of entries){const row=el('button','mem-log');const label=t.kind==='linked'?(t.detail||'').split(', ').map(x=>names.get(x)||x.replace(/^e:|^project:/,'')).join(', '):t.detail;row.append(el('span','mem-log-icon',icon[t.kind]||'•'),el('span','',verb[t.kind]+': '+label),el('small','',memoryAgo(t.at)));if(t.memory&&byId.has('m:'+t.memory))row.onclick=()=>select('m:'+t.memory,true);tl.append(row);}
   side.append(tl);
   side.append(el('p','hint mem-help','Húzd a pontokat, görgess a nagyításhoz, dupla kattintással középre hozod. A szaggatott vonal korábbi, azóta megváltozott tény.'));
   return;}
  const head=el('div','mem-side-head');const dot=el('i','mem-side-dot');dot.style.background=n.type==='entity'?ENTITY_COLOR[n.group]:n.type==='user'?ENTITY_COLOR.user:MEMORY_COLOR[n.group];
  head.append(dot,el('span','eyebrow',n.type==='user'?'TE':n.type==='entity'?(ENTITY_KIND[n.group]||'Entitás').toUpperCase():'EMLÉK · '+(MEMORY_KIND[n.group]||'').toUpperCase()));
  const close=el('button','mem-close','×');close.setAttribute('aria-label','Kijelölés megszüntetése');close.onclick=()=>select('');head.append(close);side.append(head);
  side.append(el('h2','mem-side-title',n.label));
  if(n.type==='memory'){const m=memoryOf(n);side.append(el('p','hint',(n.source==='auto'?'Automatikusan tanulta':'Te írtad be')+' · '+memoryAgo(n.created)+(n.uses?' · '+n.uses+'× használta válaszban':'')));side.append(button('Emlék szerkesztése',async()=>memoryEdit(m),'secondary'));
   const ents=links.filter(l=>l.source===n.id&&l.type==='mention').map(l=>l.b);if(ents.length)side.append(section('Ezekről szól',ents.map(chip)));
   const rels=links.filter(l=>l.type==='relation'&&(l.memories||[]).includes(n.id));if(rels.length){const s=el('section','mem-section');s.append(el('h3','','Ebből tanult kapcsolatok'));for(const l of rels){const r=el('p','mem-fact');r.textContent=l.a.label+' — '+l.label+' → '+l.b.label+(l.invalid_at?' (korábban)':'');s.append(r);}side.append(s);}
   return;}
  const rels=links.filter(l=>(l.source===id||l.target===id)&&l.type!=='mention'&&!(l.type==='memory'));
  if(rels.length){const s=el('section','mem-section');s.append(el('h3','','Kapcsolatok'));for(const l of rels.sort((a,b)=>(a.invalid_at?1:0)-(b.invalid_at?1:0)))s.append(relationRow(l,id));side.append(s);}
  const mems=links.filter(l=>(l.target===id&&l.type==='mention')||(l.source===id&&l.type==='memory')).map(l=>l.type==='memory'?l.b:l.a);
  if(mems.length)side.append(section(n.type==='user'?'Rólad szóló emlékek':'Emlékek, amelyek említik',mems.map(chip)));
  if(!rels.length&&!mems.length)side.append(el('p','hint','Ehhez még nem tartozik kapcsolat.'));}
 function select(id,center){memorySelected=id||'';const n=byId.get(memorySelected);if(n&&center){const w=canvas.clientWidth,h=canvas.clientHeight;ox=w/2-n.x*scale;oy=h/2-n.y*scale;}renderSide();draw();}
 renderSide();
 // Until the owner zooms or pans, the whole graph stays framed whatever the window size.
 memoryGraphObserver=new ResizeObserver(()=>{if(!moved)fit();draw();});memoryGraphObserver.observe(canvas);
 requestAnimationFrame(()=>{fit();draw();});
}

(()=>{const base=switchApp;switchApp=function(view){base(view);const on=view==='memory';$('memoryApp').hidden=!on;$('navMemory').classList.toggle('active',on);$('navMemory').setAttribute('aria-pressed',String(on));if(on)act(loadMemory);else memoryStop?.();};$('navMemory').onclick=()=>switchApp('memory');})();
