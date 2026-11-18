/* Project apps: a project kind can bring its own Műhely view instead of the agent map (MiLLIONS for trading). */
let projectAppView=null,projectAppPage='overview',projectAppData=null,projectAppBusy=false,projectAppSig='',projectAppFor='',projectAppPending=false;
function paNum(x,d=2){const n=Number(x);return Number.isFinite(n)?n.toLocaleString('hu-HU',{minimumFractionDigits:d,maximumFractionDigits:d}):'–';}
function paPct(x){const n=Number(x);return Number.isFinite(n)?(n>0?'+':'')+paNum(n)+'%':'–';}
function paTime(t){if(!t)return '–';const d=new Date(t);return isNaN(d)?'–':d.toLocaleString('hu-HU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}
function paTone(x){const n=Number(x);return n>0?'up':n<0?'down':'';}
async function paCall(op,args={}){return (await call('project_app',{op,args})).result;}
function paViewKey(){return 'orbitProjectView:'+project;}
function paWanted(){try{const saved=localStorage.getItem(paViewKey());return saved?saved==='app':['millions','watch'].includes(state?.project_app?.app);}catch{return true;}}
/* Show the project's own app or the agent map; app.js calls render() after every snapshot. */
function syncProjectApp(){
 const app=state?.project_app,toggle=$('workshopView');
 if(projectAppFor!==project){projectAppFor=project;projectAppData=null;projectAppSig='';projectAppPage='overview';$('projectAppView').replaceChildren();}
 toggle.hidden=!app;
 const on=!!app&&paWanted();projectAppView=on?app:null;
 $('studioApp').classList.toggle('workspace-mode',on&&app.app==='workspace');
 if(app){$('viewMap').textContent='Agent';$('viewApp').textContent='▦ '+app.title;$('viewApp').setAttribute('aria-pressed',String(on));$('viewMap').setAttribute('aria-pressed',String(!on));}
 for(const id of ['stationViewport','workflowMonitor'])if($(id))$(id).classList.toggle('pa-hidden',on);
 document.querySelector('#studioApp .space-toolbar')?.classList.toggle('pa-hidden',on);document.querySelector('#studioApp .tool-dock')?.classList.toggle('pa-hidden',on);
 $('projectAppView').hidden=!on;
 if(on&&!projectAppData)loadProjectApp();
}
function setProjectView(app){try{localStorage.setItem(paViewKey(),app?'app':'map');}catch{}syncProjectApp();if(!app&&typeof fitStation==='function')setTimeout(fitStation,30);}
function paTyping(){const a=document.activeElement;return !!a&&$('projectAppView')?.contains(a)&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName);}
let paLastLoad=0;
async function loadProjectApp(){
 if(projectAppBusy||!projectAppView||currentApp!=='agents')return;
 projectAppBusy=true;paLastLoad=Date.now();
 // While the owner types an address or picks a setting, the fresh data waits until the field is left.
 try{const pid=project;const r=await paCall(projectAppView.app==='workspace'?'workspace_snapshot':'dashboard_snapshot'),sig=JSON.stringify(r);if(pid!==project)return;if(sig!==projectAppSig){projectAppSig=sig;projectAppData=r;if(paTyping())projectAppPending=true;else renderProjectApp();}}
 catch(e){projectAppData={error:e.message};renderProjectApp();}
 finally{projectAppBusy=false;}
}
async function paAct(op,args,done){await paCall(op,args).then(r=>{toast(r.message||'Kész.');return r;});projectAppSig='';await loadProjectApp();if(done)done();}
function renderProjectApp(){
 const box=$('projectAppView'),app=projectAppView;if(!box||!app)return;
 if(app.app==='workspace'){renderWorkspace(box,projectAppData);return;}
 const scroll=box.scrollTop;projectAppPending=false;
 box.replaceChildren();
 const head=el('div','pa-head'),title=el('div');title.append(el('div','eyebrow','PROJEKT-ALKALMAZÁS · '+app.title.toUpperCase()),el('p','hint',app.subtitle));
 const right=el('div','pa-head-right');right.append(el('span','pa-badge','GYAKORLÓ SZÁMLA · valódi pénz nincs benne'));
 if(projectAppData&&!projectAppData.error)right.append(paPowerSwitch(projectAppData));
 head.append(title,right);box.append(head);
 const tabs=el('div','pa-tabs');tabs.setAttribute('role','tablist');
 for(const p of app.pages){const b=el('button','',p.label);b.setAttribute('role','tab');b.setAttribute('aria-selected',String(p.id===projectAppPage));b.onclick=()=>{projectAppPage=p.id;renderProjectApp();box.scrollTop=0;};tabs.append(b);}
 box.append(tabs);
 const d=projectAppData;
 if(!app.installed){box.append(el('p','pa-note','A MiLLIONS nincs telepítve ezen a gépen.'));return;}
 if(!d){box.append(el('p','hint','MiLLIONS adatainak betöltése…'));return;}
 if(d.error){box.append(el('p','pa-note','A MiLLIONS most nem érhető el: '+d.error));return;}
 const page=el('div','pa-page');box.append(page);
 if(d.power?.on===false)page.append(paPowerOff(d));
 ({overview:paOverview,fast:paFastPage,copy:paCopyPage,market:paMarketPage,details:paDetails}[projectAppPage]||paOverview)(page,d);
 box.scrollTop=scroll;
}
const workshopState={pid:'',tab:'overview',frame:null,entry:'',load:0};
function workshopAssistant(){
 commandWorkspace=project;
 openAssistant(true);
 updateAttachment();
 $('commandInput').focus();
}
function workspaceFile(f,pid){
 const b=button(f.name,async()=>{
  if(f.path?.match(/\.html?$/i)){
   const box=el('div','workspace-web-preview'),frame=el('iframe','workspace-runtime');
   frame.title=f.name;frame.setAttribute('sandbox','allow-scripts');frame.setAttribute('referrerpolicy','no-referrer');
   frame.src=mediaURL({...f,project:pid});
   box.append(frame,button('Forrás szerkesztése',async()=>{$('modal').close();switchApp('home');await openCanvas(f.id);},'secondary'));
   showModal(f.name,box);
  }else if(['image','video','audio'].includes(f.kind))showModal(f.name,mediaCard({...f,project:pid}));
  else if(f.kind==='text'){switchApp('home');await openCanvas(f.id);}
  else await call('open_artifact',{id:f.id,requestProject:pid});
 },'workspace-file');b.title=f.path||f.name;return b;
}
function loadWorkspaceFrame(app){
 const box=$('workspaceRuntime');if(!box)return;
 workshopState.frame=null;workshopState.entry=app?.entry||'';
 if(!app){
  const empty=el('div','workspace-empty');
  empty.append(el('div','workspace-mark','◈'),el('h3','','Itt fut majd a projekted alkalmazása'),
   el('p','','Írd le az ORBIT-nak, milyen kezelőfelületet vagy eszközt szeretnél. A mentett alkalmazás itt jelenik meg.'),
   button('Alkalmazás tervezése az ORBIT-tal',workshopAssistant));
  box.replaceChildren(empty);return;
 }
 const frame=el('iframe','workspace-runtime');
 frame.title=app.imported?'Importált projektoldal':'Projektalkalmazás';
 frame.setAttribute('sandbox','allow-scripts');
 frame.setAttribute('referrerpolicy','no-referrer');
 frame.src='orbit-media://artifact/'+encodeURIComponent(app.id)+'?project='+encodeURIComponent(workshopState.pid)+'&v='+(++workshopState.load);
 workshopState.frame=frame;box.replaceChildren(frame);
}
let workspaceDataPending=false,workspaceLastApi=0;
window.addEventListener('message',async event=>{
 const frame=workshopState.frame,pid=workshopState.pid;
 if(!frame||event.source!==frame.contentWindow||event.origin!=='null'||pid!==project||currentApp!=='agents'||projectAppView?.app!=='workspace')return;
 const data=event.data;
 if(!data||data.orbitWorkspace!==true||typeof data.id!=='string'||data.id.length>80||!['read','save','api','images','image'].includes(data.op))return;
 const send=response=>{if(workshopState.frame===frame&&pid===project)event.source.postMessage({orbitWorkspaceReply:true,id:data.id,...response},'*');};
 if(data.op==='images'){send({ok:true,value:(projectAppData?.files||[]).filter(f=>f.kind==='image').map(({id,name})=>({id,name}))});return;}
 if(data.op==='image'){
  if(!(projectAppData?.files||[]).some(f=>f.id===data.artifact&&f.kind==='image'))return;
  if(workspaceDataPending){send({ok:false});return;}
  workspaceDataPending=true;
  try{send({ok:true,value:await call('artifact_preview',{id:data.artifact,requestProject:pid})});}
  catch{send({ok:false});}finally{workspaceDataPending=false;}
  return;
 }
 if(workspaceDataPending){send({ok:false,error:'Az előző mentés még folyamatban van.'});return;}
 workspaceDataPending=true;
 try{
  const api=data.op==='api',encoded=data.op==='read'?'':JSON.stringify(data.value??null);
  if(encoded.length>128*1024)throw new Error('Legfeljebb 128 KB JSON küldhető.');
  if(api){
   if(!Number.isInteger(data.index)||!projectAppData?.api_examples?.some(x=>x.index===data.index))throw new Error('Ismeretlen helyi API-művelet.');
   if(Date.now()-workspaceLastApi<1000)throw new Error('Várj a következő helyi API-kéréssel.');
   workspaceLastApi=Date.now();
  }
  const args=api?{index:data.index,body:encoded}:data.op==='read'?{}:{value:data.value??null};
  const {result}=await call('project_app',{op:api?'workspace_api':'workspace_app_data',args,requestProject:pid});send({ok:true,value:result});
 }catch(error){send({ok:false,error:error.message});}
 finally{workspaceDataPending=false;}
});
async function editWorkspaceNote(pid,notes){
 const open=await paCall('workspace_note');
 const file=await canvasOp('canvas_read',{id:open.id});
 if(pid!==project||!notes.isConnected)return;
 const editor=el('textarea','workspace-note-editor');editor.value=file.content;
 editor.setAttribute('aria-label','Projektjegyzet szövege');
 const save=button('Jegyzet mentése',async()=>{
  await canvasOp('canvas_save',{id:file.id,content:editor.value});toast('Projektjegyzet mentve.');
 });
 notes.replaceChildren(el('h3','','Projektjegyzet'),editor,save);
 editor.focus();
}
function workspaceTab(tab){
 workshopState.tab=tab;
 $('workspaceOverview').hidden=tab!=='overview';
 $('workspaceRuntime').hidden=tab!=='app';
 if(tab==='app'&&(!workshopState.frame||workshopState.entry!==projectAppData.app?.entry))loadWorkspaceFrame(projectAppData.app);
 $('workspaceNotes').hidden=tab!=='notes';
 for(const id of ['overview','app','notes'])$('workspaceTab-'+id).setAttribute('aria-pressed',String(tab===id));
}
function renderWorkspace(box,d){
 projectAppPending=false;
 if(!d||d.error){if(!box.firstChild)box.append(el('p','hint',d?.error||'A projekt betöltése…'));return;}
 const pid=d.project.id;
 if(workshopState.pid!==pid||!$('workspaceRuntime')){
  workshopState.pid=pid;workshopState.tab='overview';workshopState.entry='';workshopState.frame=null;workshopState.category='all';workshopState.query='';workshopState.limit=24;
  const head=el('div','workspace-top'),title=el('div','workspace-title'),actions=el('div','workspace-actions');
  title.append(el('small','eyebrow','PROJEKTVÁSZON'),el('h2','',d.project.name));
  actions.append(button('Beszélj az ORBIT-tal',workshopAssistant),button('Frissítés',async()=>{await loadProjectApp();if(workshopState.tab==='app')loadWorkspaceFrame(projectAppData.app);},'secondary'));
  head.append(title,actions);
  const strip=el('div','workspace-tabs');
  for(const [id,label] of [['overview','Áttekintés'],['app','Alkalmazás'],['notes','Jegyzet']]){
   const b=button(label,()=>workspaceTab(id),'secondary');b.id='workspaceTab-'+id;strip.append(b);
  }
  const status=el('span','workspace-status');status.id='workspaceRuntimeStatus';strip.append(status);
  const overview=el('section','workspace-overview');overview.id='workspaceOverview';
  const runtime=el('div','workspace-stage');runtime.id='workspaceRuntime';
  const notes=el('div','workspace-notes');notes.id='workspaceNotes';
  notes.append(el('h3','','Projektjegyzet'),el('p','','Tervek, következő lépések és munkajegyzetek egy helyen.'),
   button('Jegyzet szerkesztése',()=>editWorkspaceNote(pid,notes),'secondary'));
  const filter=el('input','workspace-search');filter.type='search';filter.placeholder='Keresés az anyagok között…';filter.setAttribute('aria-label','Keresés a projekt anyagai között');
  filter.oninput=()=>{workshopState.query=filter.value;workshopState.limit=24;renderWorkspaceLibrary(pid,projectAppData);};
  const details=el('div','workspace-detail');details.id='workspaceDetail';
  const categories=el('div','workspace-categories');categories.id='workspaceCategories';
  const library=el('div','workspace-library');library.id='workspaceLibrary';
  overview.append(details,filter,categories,library);
  box.replaceChildren(head,strip,overview,runtime,notes);
  workspaceTab('overview');
 }
 if(workshopState.tab==='app'&&(d.app?.entry||'')!==workshopState.entry)loadWorkspaceFrame(d.app);
 $('workspaceRuntimeStatus').textContent=d.app?.imported?'Importált weboldal':d.app?'Helyi alkalmazás':'Tervezés';
 const details=$('workspaceDetail'),bar=el('div','workspace-actions'),context=el('div','workspace-summary');
 const description=d.handoff?.offer||d.project.description;
 if(description)context.append(el('p','',description));
 const stats=[d.files.length+' anyag',d.progress?.total?d.progress.done+' / '+d.progress.total+' lépés':'',d.handoff?.runs?d.handoff.runs+' átvett futás':''].filter(Boolean);
 context.append(el('p','workspace-status',stats.join(' · ')));
 if(d.handoff?.runs){
  const states=d.handoff.run_states||{};
  const parts=Object.entries(states).map(([key,count])=>count+' '+({done:'befejezett',failed:'hibás',running:'folyamatban',cancelled:'leállított'}[key]||key));
  context.append(el('p','hint',(parts.length?parts.join(' · ')+' · ':'')+'Részletek az Autopilóta-előzmények alatt.'));
 }
 if(d.handoff?.direction)context.append(el('p','hint','Autopilóta-irány · '+d.handoff.direction));
 if(d.app)bar.append(button(d.app.imported?'Weboldal megnyitása':'Alkalmazás megnyitása',()=>workspaceTab('app')));
 if(d.api_examples?.length)bar.append(button('API-lekérdezések',()=>showProductApi({name:d.project.name,api_examples:d.api_examples,workshop:true}),'secondary'));
 bar.append(button('Jogosultságok',()=>{
  const pane=el('div','ap-detail');
  for(const agent of state?.agents||[]){
   const row=el('div','workspace-summary');
   row.append(el('strong','',agent.name),el('p','hint',(agent.tools||[]).join(' · ')||'Nincs eszköz hozzárendelve'),
    button('Ügynök beállításai',()=>{$('modal').close();editAgent(agent);},'secondary'));pane.append(row);
  }
  pane.append(button('Munkamappák és hozzáférés',()=>showAccess(),'secondary'));
  showModal('Projektjogosultságok',pane);
 },'secondary'),button('Automatizációk',()=>{taskProjectFilter=pid;switchApp('automations');loadAutomations();if(automationData)renderAutomations();},'secondary'));
 if(d.idea_id)bar.append(button('Autopilóta-adatok átvétele',async()=>{
  const {result}=await call('project_app',{op:'workspace_import',args:{idea_id:d.idea_id},requestProject:pid});toast(result.copied+' új fájl · '+result.runs+' forrásfutás');await loadProjectApp();
 },'secondary'),button('Autopilóta-irány',()=>ventureChat(d.idea_id),'secondary'));
 if(d.jobs.length){
  const activity=el('details','workspace-activity');activity.append(el('summary','','Legutóbbi munka'));
  for(const j of d.jobs)activity.append(el('p','hint',commandLabel(j.status)+' · '+j.prompt.slice(0,180)));
  activity.open=!!details.querySelector('details[open]');context.append(activity);
 }
 details.replaceChildren(context,bar);
 renderWorkspaceLibrary(pid,d);
}
const WORKSPACE_CATEGORIES={all:'Minden',web:'Weboldalak',image:'Képek',video:'Videók',audio:'Hangok',code:'Kód',api:'API-eredmények',notes:'Jegyzetek',document:'Dokumentumok',archive:'Autopilóta-előzmények'};
function renderWorkspaceLibrary(pid,d){
 const categories=$('workspaceCategories'),library=$('workspaceLibrary');
 const counts={};for(const f of d.files)counts[f.category]=(counts[f.category]||0)+1;
 categories.replaceChildren();
 for(const [id,label] of Object.entries(WORKSPACE_CATEGORIES)){
  if(id!=='all'&&!counts[id])continue;
  const b=button(label,()=>{workshopState.category=id;workshopState.limit=24;renderWorkspaceLibrary(pid,d);},'secondary');
  b.setAttribute('aria-pressed',String(id===workshopState.category));categories.append(b);
 }
 const query=workshopState.query.trim().toLocaleLowerCase('hu');
 const files=d.files.filter(f=>(workshopState.category==='all'?(f.category!=='archive'||!!query):f.category===workshopState.category)&&(!query||(f.name+' '+f.path).toLocaleLowerCase('hu').includes(query)));
 const items=el('div','workspace-artifacts');
 for(const f of files.slice(0,workshopState.limit)){
  const b=workspaceFile(f,pid);b.replaceChildren(el('strong','',f.name),el('small','',f.category==='archive'?f.path.replace('workspace/autopilot/',''):(WORKSPACE_CATEGORIES[f.category]||'Fájl')));
  items.append(b);
 }
 library.replaceChildren(items);
 if(!files.length)library.append(el('p','hint',query?'Nincs találat.':'Ebben a nézetben még nincs megnyitható anyag.'));
 if(files.length>workshopState.limit)library.append(button('További anyagok',()=>{workshopState.limit+=24;renderWorkspaceLibrary(pid,d);},'secondary'));
}

function paChip(label,on,detail){const c=el('span','pa-chip'+(on?' on':''),(on?'● ':'○ ')+label);if(detail)c.title=detail;return c;}
/* The main switch: off stops news, prices, trader search, research and trading, so nothing of MiLLIONS runs in the background. */
function paPowerSwitch(d){
 const on=d.power?.on!==false,b=el('button','pa-power'+(on?' on':''),on?'⏻ MiLLIONS: BE':'⏻ MiLLIONS: KI');
 b.setAttribute('role','switch');b.setAttribute('aria-checked',String(on));b.title=on?'Kikapcsolás: minden MiLLIONS-folyamat leáll':'Bekapcsolás';
 b.onclick=()=>on?paConfirmOff(d):paConfirmOn(d);return b;}
function paConfirmOff(d){
 const open=(d.paper_positions||[]).length;
 paConfirm('MiLLIONS kikapcsolása','Leáll minden: a friss hírek keresése (X-hírfiókok, portálok), az árfolyamfigyelés, a kereskedőkeresés, az AI-kutatás, a gyors AI és a másolás. A háttérben semmi nem fut tovább, és a Mac újraindításakor sem indul el.'+
  (open?' A '+open+' nyitott virtuális ügylet a mostani áron lezárul.':'')+' Az eddigi eredmények és beállítások megmaradnak.','Igen, kikapcsolom',()=>paRun(['power_off']));}
function paConfirmOn(d){
 const resume={fast:' A gyors AI is újraindul a korábbi beállításokkal.',copy:' A korábbi másolás is folytatódik.'}[d.power?.resume]||' Kereskedés nem indul magától: utána kiválaszthatod az Áttekintés lapon.';
 paConfirm('MiLLIONS bekapcsolása','Elindul a hírgyűjtés, az árfolyamfigyelés, a kereskedőkeresés és a kutatás.'+resume,'Igen, bekapcsolom',()=>paRun(['power_on']));}
function paPowerOff(d){
 const box=el('section','pa-hero off pa-off');const words=el('div');
 words.append(el('strong','','A MiLLIONS ki van kapcsolva'),el('p','','Nem keres híreket, nem figyeli az árakat, nem keres kereskedőt, nem kutat és nem kereskedik – a háttérben semmi nem fut.'+(d.power?.changed_at?' Kikapcsolva: '+paTime(d.power.changed_at)+'.':'')+' Lent a legutóbbi állapotot látod.'));
 box.append(el('span','pa-hero-icon','⏻'),words,button('Bekapcsolás',()=>paConfirmOn(d)));return box;}

/* For a layperson: what MiLLIONS is doing in one sentence, the money, and one clear button to start or stop. */
function paUsd(x,sign=false){const n=Number(x);return Number.isFinite(n)?(sign&&n>0?'+':'')+n.toLocaleString('hu-HU',{minimumFractionDigits:2,maximumFractionDigits:2})+' $':'–';}
function paRule(s){if(!s)return '';const r=s.strategy||{},bar=r.bar==='15m'?15:1,mins=(r.window||0)*bar,hold=(r.hold||0)*bar,t=v=>mins>=60||v>=60?paNum(v/60,1)+' óra':v+' perc';
 return s.symbol+': ha '+t(mins)+' alatt legalább '+paNum((r.threshold||0)*100,1)+'%-ot mozdul, '+(r.family==='momentum'?'a mozgás irányába':'a mozgással szemben')+' köt; legfeljebb '+paNum((r.stop||0)*100,1)+'% veszteséggel, '+paNum((r.stop||0)*200,1)+'% nyereségcéllal, legfeljebb '+t(hold)+'ra.';}
function paConfirm(title,text,label,go){const b=el('div','ap-detail');b.append(el('p','',text),el('p','hint','Mindez virtuális (gyakorló) pénzzel történik; valódi pénzed nincs benne.'),button(label,async()=>{$('modal').close();await go();}));showModal(title,b);}
async function paRun(ops){let last=null;for(const op of ops)last=await paCall(op);toast(last?.message||'Kész.');projectAppSig='';await loadProjectApp();}
/* Owner choices that must survive the 6-second refresh: typed address, drafts, filters, open details. */
const paForm={address:'',check:null,checking:false,size:100,auto:true,fast:null,newsGroup:'all',newsCoin:'',srcKind:'telegram',srcValue:'',srcName:'',open:new Set()};
function paPrice(v){const n=Number(v);if(!Number.isFinite(n))return '–';const d=n>=1000?0:n>=100?2:n>=1?3:n>=0.01?5:7;return n.toLocaleString('hu-HU',{minimumFractionDigits:d,maximumFractionDigits:d});}
function paAgo(t){const s=(Date.now()-new Date(t))/1000;if(!Number.isFinite(s))return '–';return s<60?Math.max(0,Math.round(s))+' mp':s<3600?Math.round(s/60)+' perce':s<86400?Math.round(s/3600)+' órája':Math.round(s/86400)+' napja';}
function paHM(ms){return new Date(ms).toLocaleTimeString('hu-HU',{hour:'2-digit',minute:'2-digit'});}
function paSide(dir){return Number(dir)>0||dir==='long'?'emelkedésre fogad':'esésre fogad';}
function paDetailsBox(key,summary,build){const b=el('details','pa-more');b.open=paForm.open.has(key);b.ontoggle=()=>{b.open?paForm.open.add(key):paForm.open.delete(key);};b.append(el('summary','',summary));build(b);return b;}
const SVGNS='http://www.w3.org/2000/svg';
function svg(tag,attrs={},text){const e=document.createElementNS(SVGNS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!=null)e.textContent=text;return e;}
/* A price or value line with level lines (entry, stop, target) and marks (entry/exit moments). Inline SVG, no library. */
function paChart(points,{h=200,lines=[],marks=[],fmt=paPrice,xfmt=paHM,area=true,label=''}={}){
 const w=640,pad={l:6,r:76,t:10,b:20},box=svg('svg',{viewBox:'0 0 '+w+' '+h,class:'pa-chart',role:'img','aria-label':label||'Grafikon'});
 const pts=(points||[]).filter(p=>Number.isFinite(Number(p[1])));
 if(pts.length<2){box.append(svg('text',{x:w/2,y:h/2,'text-anchor':'middle',class:'pa-axis'},'Még nincs elég adat a grafikonhoz.'));return box;}
 const t0=pts[0][0],t1=pts.at(-1)[0],vals=pts.map(p=>Number(p[1])).concat(lines.map(l=>Number(l.v)),marks.map(m=>Number(m.v))).filter(Number.isFinite);
 let lo=Math.min(...vals),hi=Math.max(...vals);const span=(hi-lo)||Math.abs(hi)*0.01||1;lo-=span*0.08;hi+=span*0.08;
 const x=t=>pad.l+(Math.min(t1,Math.max(t0,t))-t0)/((t1-t0)||1)*(w-pad.l-pad.r),y=v=>pad.t+(hi-v)/(hi-lo)*(h-pad.t-pad.b);
 for(let i=0;i<=3;i++){const v=lo+(hi-lo)*i/3;box.append(svg('line',{x1:pad.l,x2:w-pad.r,y1:y(v),y2:y(v),class:'pa-grid'}),svg('text',{x:w-pad.r+6,y:y(v)+4,class:'pa-axis'},fmt(v)));}
 box.append(svg('text',{x:pad.l,y:h-4,class:'pa-axis'},xfmt(t0)),svg('text',{x:w-pad.r,y:h-4,'text-anchor':'end',class:'pa-axis'},xfmt(t1)));
 const path=pts.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(1)+' '+y(Number(p[1])).toFixed(1)).join(' ');
 if(area)box.append(svg('path',{d:path+' L'+x(t1).toFixed(1)+' '+(h-pad.b)+' L'+x(t0).toFixed(1)+' '+(h-pad.b)+' Z',class:'pa-area'}));
 box.append(svg('path',{d:path,class:'pa-line'}));
 for(const l of lines){if(!Number.isFinite(Number(l.v)))continue;const yy=y(Number(l.v));
  // The level's name sits inside the plot above its line; the price axis keeps the right-hand column.
  box.append(svg('line',{x1:pad.l,x2:w-pad.r,y1:yy,y2:yy,class:'pa-level '+(l.cls||'')}),svg('text',{x:w-pad.r-4,y:yy-4,'text-anchor':'end',class:'pa-level-label '+(l.cls||'')},l.label+' '+fmt(Number(l.v))));}
 for(const m of marks){if(!Number.isFinite(Number(m.v)))continue;const c=svg('circle',{cx:x(m.t),cy:y(Number(m.v)),r:5,class:'pa-mark '+(m.cls||'')});c.append(svg('title',{},m.label));box.append(c);}
 return box;
}

/* For a layperson: what MiLLIONS is doing in one sentence, the money, and one clear button to start or stop. */
function paOverview(page,d){
 const r=d.results||{},mode=r.mode||'off',open=d.paper_positions||[],f=d.fast||{},s=f.stats||{};
 const hero=el('section','pa-hero '+mode),icon={off:'⏸',copy:'👥',fast:'⚡'}[mode];
 const say=mode==='copy'?['Egy sikeres kereskedőt másol – virtuális pénzzel.','Amit ő vesz vagy elad, azt a MiLLIONS is megteszi, a beállított méretben ('+(r.copy?.size_percent||100)+'%).'+(r.copy?.auto_best?' Ha tartósan jobb kereskedő akad, magától átvált.':'')]
  :mode==='fast'?['Önállóan, gyorsan kereskedik – virtuális pénzzel.',f.message||'Indul…']
  :open.length?['Nem köt új ügyletet.','De még '+open.length+' korábbi ügylet nyitva van, ezek értéke tovább változik. Lent egy gombbal lezárhatod őket.']:['Most pihen, nem kereskedik.','Válaszd ki lent, hogyan kereskedjen.'];
 const words=el('div');words.append(el('strong','',say[0]),el('p','',say[1]));hero.append(el('span','pa-hero-icon',icon),words);
 if(d.power?.on!==false)page.append(hero);  // switched off, the banner above already says what is (not) running
 const money=el('section','pa-money'),tone=paTone(d.change);
 money.append(el('small','','Virtuális egyenleg'),el('strong','',paUsd(d.equity)),el('span',tone,'Az indulás óta: '+paUsd(d.change,true)+' ('+paPct(d.change_percent)+')'),el('p','hint','Gyakorló számla: 10 000 $ virtuális pénzzel indult. Ez nem valódi pénz, és a múltbeli eredmény nem ígéret a jövőre.'));
 page.append(money);
 const act=el('section','pa-actions-big');
 if(mode!=='off'||open.length)act.append(button(mode!=='off'?'■ Leállítás':'■ Nyitott ügyletek lezárása',()=>paConfirm('Leállítás',[mode!=='off'?'A MiLLIONS nem köt több ügyletet.':'',open.length?'A '+open.length+' nyitott ügyletet lezárja a mostani áron.':'Nyitott ügylet nincs.'].filter(Boolean).join(' '),'Igen, leállítom',()=>paRun(['stop_all'])),'pa-stop'));
 if(mode==='off'&&d.power?.on!==false){
  const profile=(d.fast_profiles||{})[d.fast_settings?.profile]||{};
  const start=(emoji,title,text,ops,tab)=>{const b=el('button','pa-start');b.append(el('span','pa-start-icon',emoji),el('strong','',title),el('small','',text));
   const keep=tab==='fast'&&r.account_mode==='fast_ai';
   b.onclick=()=>paConfirm(title,text+(open.length&&!keep?' Előtte a '+open.length+' nyitott ügyletet lezárja a mostani áron.':''),'Igen, indítom',()=>paRun((open.length&&!keep?['stop_all']:[]).concat(ops)));
   const wrap=el('div','pa-start-wrap'),more=el('button','text-button','Beállítások és választás →');more.onclick=()=>{projectAppPage=tab;renderProjectApp();};wrap.append(b,more);return wrap;};
  act.append(start('👥','Sikeres kereskedő másolása','A MiLLIONS a legjobb, ellenőrzött nyilvános kereskedőt másolja. A Másolás lapon te is választhatsz, akár saját címet is.',['copy_best'],'copy'),
   start('⚡','Önálló gyors kereskedés','Gyors ügyletek a trend irányában: kitörés után limitárral lép be a visszatesztnél, friss hírre (X-hírfiókok is) azonnal. Profil: '+(profile.label||'Normál')+'.',['fast_start'],'fast'));}
 page.append(act);
 if(mode==='copy'){const c=(d.discovery?.candidates||[]).find(x=>x.address===r.copy?.leader),box=el('section','pa-card');
  box.append(el('h3','','Akit most másol'),el('p','',c?(c.name+': az elmúlt hónapban '+paPct(c.return_percent)+', a legnagyobb visszaesése '+paNum(c.drawdown_percent,1)+'%.'):(r.copy?.leader||'')+' – részletek a Másolás lapon.'));
  if(r.copy?.last_switch)box.append(el('p','hint',r.copy.last_switch.message));page.append(box);}
 if(mode==='fast'){const box=el('section','pa-card');box.append(el('h3','','Eddigi gyors ügyletek'),el('p','',(s.trades||0)+' lezárt ügylet'+(s.trades?' · '+paNum(s.win_rate,0)+'% nyereséges · összesen '+paUsd(s.net,true)+' (díjakkal)':'')));
  const go=el('button','text-button','Mit csinál pontosan? → Gyors AI lap');go.onclick=()=>{projectAppPage='fast';renderProjectApp();};box.append(go);page.append(box);}
 const list=el('section','pa-card');list.append(el('h3','',open.length?'Nyitott ügyletek · '+open.length:'Nyitott ügylet nincs'));
 for(const p of open){const row=el('div','pa-trade'),pnl=Number(p.unrealized_pnl);row.append(el('strong','',p.symbol),el('span','',paSide(p.direction)),el('span',paTone(pnl),'most '+paUsd(pnl,true)));list.append(row);}
 if(!open.length)list.append(el('p','hint','Amikor a MiLLIONS köt egy ügyletet, itt látod, és azt is, hogy éppen nyer vagy veszít rajta.'));
 page.append(list);
 page.append(paDetailsBox('help','Mi ez, és hogyan működik?',b=>b.append(
  el('p','','A MiLLIONS egy gyakorló kereskedő: virtuális pénzzel próbálja ki, hogy egy módszer tényleg hoz-e hasznot, mielőtt bárki valódi pénzt kockáztatna. Valódi pénzed nincs benne, és semmi nem történik a tudtod nélkül.'),
  el('p','','Két módja van. A másolás egy nyilvánosan sikeres kereskedő lépéseit követi; te választod ki, kit és mekkora méretben. A gyors AI magától köt rövid ügyleteket árfolyam-minták, friss hírek és a vevők–eladók erőviszonya alapján, és minden lépését megmutatja a Gyors AI lapon.'),
  el('p','','Bármikor leállíthatod a Leállítás gombbal: ilyenkor nem köt újat, és a nyitott ügyleteket a mostani áron lezárja.'))));
}

/* The fast AI: what it does now, where the money is, why it entered, how each trade went and what has worked. */
function paFastPage(page,d){
 const f=d.fast||{},running=d.results?.mode==='fast',profiles=d.fast_profiles||{},saved=d.fast_settings||{profile:'normal',families:{},coins:10};
 const draft=paForm.fast||(paForm.fast=JSON.parse(JSON.stringify(saved)));const profile=profiles[running?(f.settings?.profile||saved.profile):draft.profile]||profiles.normal||{};
 const now=el('section','pa-hero '+(running?'fast':'off'));const words=el('div');
 words.append(el('strong','',running?(f.phase==='in_trade'?'Ügyletben van':f.phase==='waiting_fill'?'Limitáras megbízás vár':f.phase==='blocked'?'Mára megállt':f.phase==='error'?'Hiba – most nem nyit új ügyletet':'Figyel és jó belépőre vár'):'A gyors AI most nincs bekapcsolva'),
  el('p','',running?(f.message||'Indul…'):'Lent beállíthatod, mennyire legyen merész, és elindíthatod. Közben minden lépését itt látod.'));
 if(running&&f.updated_at)words.append(el('small','hint','Frissítve '+paAgo(f.updated_at)+' · 3 másodpercenként'));
 now.append(el('span','pa-hero-icon',running?(f.phase==='in_trade'?'⚡':f.phase==='waiting_fill'?'⏳':f.phase==='error'?'⚠':'👀'):'⏸'),words);page.append(now);
 // Where the money is
 const equity=Number(d.equity)||10000,positions=running||f.positions?.length?(f.positions||[]):[],gross=positions.reduce((a,p)=>a+Number(p.notional),0);
 const alloc=el('section','pa-card');alloc.append(el('h3','','Hova rakja a pénzt'));
 const cap=Math.max(equity*(profile.gross||1),gross,equity),bar=el('div','pa-alloc');
 for(const p of positions){const seg=el('span','pa-alloc-seg '+(p.direction>0?'up':'down'),p.symbol);seg.style.width=(Number(p.notional)/cap*100)+'%';seg.title=p.symbol+' · '+paSide(p.direction)+' · '+paUsd(p.notional);bar.append(seg);}
 const mark=el('i','pa-alloc-mark');mark.style.left=(equity/cap*100)+'%';mark.title='A saját tőke ('+paUsd(equity)+')';bar.append(mark);alloc.append(bar);
 alloc.append(el('p','hint','A sáv a profil teljes keretét mutatja ('+(profile.gross||1)+'× a tőke, '+paUsd(cap)+'); a függőleges jel a saját tőke. Ami túlnyúlik rajta, az tőkeáttétel.'));
 if(positions.length)for(const p of positions)alloc.append(el('p','pa-alloc-row',p.symbol+' · '+paSide(p.direction)+' · '+paUsd(p.notional)+' ('+paNum(Number(p.notional)/equity,2)+'× tőke) · ha a veszteségkorlátig megy: −'+paUsd(p.risk_usd)));
 else alloc.append(el('p','','Most minden pénz szabad: '+paUsd(equity)+'. Egy ügyletben a számla '+paNum(Number(profile.risk||0.01)*100,1)+'%-át ('+paUsd(equity*Number(profile.risk||0.01))+') kockáztatná, ehhez a stop távolságától függően kb. '+paUsd(equity*Number(profile.risk||0.01)/0.008)+' értékű ügyletet nyitna.'));
 page.append(alloc);
 // Open trades with their chart
 for(const p of positions){const card=el('section','pa-card pa-pos');const side=p.direction>0;
  card.append(el('h3','',p.symbol+' · '+paSide(p.direction)+' · '+paAgo(p.opened_at)+' nyitva'),
   el('p','pa-pos-line',paUsd(p.notional)+' · belépő ár '+paPrice(p.entry)+' · most '+paPrice(p.price)),
   el('p','pa-pos-pnl '+paTone(p.pnl),'Most: '+paUsd(p.pnl,true)+' ('+(p.r>0?'+':'')+paNum(p.r,2)+'× a kockázat)'));
  const series=f.charts?.[p.symbol]||[];const opened=new Date(p.opened_at).getTime();
  card.append(paChart(series,{label:p.symbol+' ára',lines:[{v:p.entry,label:'Belépő',cls:'entry'},{v:p.stop_price,label:p.trailing?'Követő stop':'Veszteségkorlát',cls:'stop'},{v:p.take_price,label:'Nyereségcél (limit)',cls:'take'}],
   marks:[{t:opened,v:p.entry,label:'Belépett '+paHM(opened)+' · '+paPrice(p.entry),cls:side?'buy':'sell'}]}));
  const why=el('ul','pa-why');for(const x of p.reasons||[])why.append(el('li','',x));card.append(el('p','hint','Miért lépett be:'),why);page.append(card);}
 // Resting limit orders: the entries wait for the price to come back, which is cheaper and better timed than chasing.
 const orders=f.orders||[];
 if(orders.length){const card=el('section','pa-card');card.append(el('h3','','Limitáras megbízások · '+orders.length),el('p','hint','A belépő megbízás a kitörés szintjén vár: csak akkor teljesül, ha az ár visszajön rá. Ha addig nem jön vissza, lejár, és nem kerül pénzbe.'));
  for(const o of orders){const w=(f.watch||[]).find(x=>x.symbol===o.symbol),price=Number(w?.price),left=Math.max(0,(new Date(o.expires_at)-Date.now())/1000);
   card.append(el('p','pa-pos-line',o.symbol+' · '+(o.direction>0?'vétel':'eladás')+' '+paPrice(o.price)+'-on'+(Number.isFinite(price)?' · most '+paPrice(price)+' ('+paNum((Number(o.price)/price-1)*100,2)+'% távolság)':'')+' · még '+(left>=60?Math.round(left/60)+' perc':Math.round(left)+' mp')));
   if(f.charts?.[o.symbol])card.append(paChart(f.charts[o.symbol],{h:160,label:o.symbol+' ára',lines:[{v:Number(o.price),label:'Limit',cls:'entry'}]}));
   card.append(el('p','hint',(paFamilies[o.family]||o.family)+': '+o.why));}
  page.append(card);}
 // What it watches
 const watch=el('section','pa-card');watch.append(el('h3','','Mit figyel most'),el('p','hint','Csak a trend irányában kereskedik (1 és 4 órás átlag). Ha egy coin nagy forgalommal kitör az 1 órás sávjából, limitáras megbízást tesz a kitörés szintjére, és megvárja, amíg az ár visszajön rá. Erős, friss hírnél (X-hírfiókok, portálok) azonnal a legjobb áron áll be.'));
 const rows=f.watch||[];
 for(const w of rows){const row=el('div','pa-watch'+(w.active||w.signals?.length?' ready':''));const name=el('div','pa-watch-name');name.append(el('strong','',w.symbol),el('small','',paPrice(w.price)+' · '+paPct(w.change_percent)));
  const trend=el('span','pa-trend '+(w.trend>0?'up':w.trend<0?'down':''),w.trend>0?'↑ emelkedő trend':w.trend<0?'↓ csökkenő trend':'– nincs trend');
  row.append(name,trend,el('span','pa-watch-status',w.status));
  if(w.signals?.length){const list=el('ul','pa-why');for(const s of w.signals)list.append(el('li',s.direction>0?'up':'down',(s.direction>0?'↑ ':'↓ ')+s.label+': '+s.why));row.append(list);}
  watch.append(row);}
 if(!rows.length)watch.append(el('p','hint',running?'Az első kör adatai töltődnek…':'Bekapcsolás után itt látod a figyelt piacokat, a trendjüket és a belépési lehetőségeket.'));
 page.append(watch);
 const top=rows.find(w=>w.trend&&f.charts?.[w.symbol]&&!positions.some(p=>p.symbol===w.symbol)&&!orders.some(o=>o.symbol===w.symbol));
 if(top){const card=el('section','pa-card');card.append(el('h3','',top.symbol+' ára · utolsó 90 perc'),paChart(f.charts[top.symbol],{label:top.symbol+' ára'}));page.append(card);}
 const hist=(f.order_history||[]).filter(o=>o.status!=='open');
 if(hist.length){const card=el('section','pa-card'),t=el('table','pa-table'),hr=el('tr');card.append(el('h3','','Korábbi megbízások'));
  for(const h of ['Mikor','Piac','Irány','Limit','Eredmény'])hr.append(el('th','',h));t.append(hr);
  for(const o of hist){const tr=el('tr');tr.append(el('td','',paHM(new Date(o.created_at))),el('td','',o.symbol),el('td','',o.direction>0?'vétel':'eladás'),el('td','num',paPrice(o.price)),
   el('td','',{filled:'teljesült → ügylet',expired:'lejárt, nem jött vissza az ár',cancelled:'visszavonva',skipped:'kihagyva (keret)'}[o.status]||o.status));tr.title=o.why;t.append(tr);}
  card.append(t);page.append(card);}
 // Results
 const res=el('section','pa-card'),s=f.stats||{};res.append(el('h3','','A gyors ügyletek eredménye'),
  el('p','',(s.trades||0)+' lezárt ügylet'+(s.trades?' · '+paNum(s.win_rate,0)+'% nyereséges · átlagosan '+paNum(s.avg_r,2)+'× a kockázat · összesen '+paUsd(s.net,true)+' díjakkal':'')),
  paChart(f.equity||[],{h:160,fmt:v=>paUsd(v),label:'A számla értéke'}),el('p','hint','A számla értéke az elmúlt 24 órában (percenként). '+(f.risk?.basis?'Tét: '+f.risk.basis+'.':'')));
 page.append(res);
 // Journal
 const jr=el('section','pa-card');jr.append(el('h3','','Ügyletnapló'));
 const journal=f.journal||[];
 if(journal.length){const t=el('table','pa-table'),hr=el('tr');for(const h of ['Mikor','Piac','Irány','Méret','Eredmény','Miért','Kiszállás'])hr.append(el('th','',h));t.append(hr);
  for(const j of journal){const tr=el('tr');const pnl=j.pnl==null?null:Number(j.pnl);
   tr.append(el('td','',paHM(new Date(j.opened_at))+(j.closed_at?'–'+paHM(new Date(j.closed_at)):' –')),el('td','',j.symbol),el('td','',j.direction>0?'↑ emelkedés':'↓ esés'),el('td','num',paUsd(j.notional)),
    el('td','num '+paTone(pnl),pnl==null?'nyitva':paUsd(pnl,true)+' ('+paNum(j.r,2)+'R)'),el('td','',(j.families||[]).map(x=>paFamilies[x]||x).join(', ')),el('td','',j.exit_reason||'–'));
   tr.title=(j.reasons||[]).join('\n');t.append(tr);}
  jr.append(t,el('p','hint','Vidd az egeret egy sor fölé a belépés pontos okaiért. Az eredmény díjakkal és csúszással számolt; R = hányszorosa a vállalt kockázatnak.'));}
 else jr.append(el('p','hint','Még nincs gyors ügylet. A gyors AI csak akkor köt, ha a jelek elég erősek; csendes piacon órákig is várhat.'));
 page.append(jr);
 // What has worked
 const fam=el('section','pa-card');fam.append(el('h3','','Mi működik – a belépési módok saját eredménye'),el('p','hint','Minden belépési mód külön vezeti az eredményeit. Ha egy mód 15 ügylet után átlagosan veszteséges, magától szünetel. Itt ki is kapcsolhatod őket.'));
 const ft=el('table','pa-table'),fh=el('tr');for(const h of ['Belépési mód','Ügyletek','Találat','Átlag','Eredmény','Állapot'])fh.append(el('th','',h));ft.append(fh);
 for(const x of f.families||[]){const tr=el('tr');tr.append(el('td','',x.label),el('td','num',String(x.trades)),el('td','num',x.trades?paNum(100*x.wins/x.trades,0)+'%':'–'),el('td','num '+paTone(x.avg_r),x.trades?paNum(x.avg_r,2)+'R':'–'),
  el('td','num '+paTone(x.net),x.trades?paUsd(x.net,true):'–'),el('td','',!x.enabled?'kikapcsoltad':x.paused?'szünetel (veszteséges volt)':'aktív'));ft.append(tr);}
 if(f.families?.length)fam.append(ft);page.append(fam);
 // Settings
 const set=el('section','pa-card');set.append(el('h3','','Beállítások'));
 const seg=el('div','pa-seg');
 for(const [id,p] of Object.entries(profiles)){const b=el('button','',p.label);b.setAttribute('aria-pressed',String(draft.profile===id));b.onclick=()=>{draft.profile=id;renderProjectApp();};seg.append(b);}
 const chosen=profiles[draft.profile]||{};
 set.append(seg,el('p','pa-profile','Ügyletenként a számla '+paNum(Number(chosen.risk)*100,1)+'%-át kockáztatja (20 ügylet után a saját eredményei szerint, legfeljebb '+paNum(Number(chosen.risk_cap)*100,1)+'%) · legfeljebb '+chosen.leverage+'× tőkeáttétel ügyletenként, '+chosen.gross+'× összesen · '+chosen.positions+' ügylet vagy megbízás egyszerre · napi '+paNum(Number(chosen.daily_loss)*100,0)+'% veszteség után aznap megáll.'),
  el('p','hint','Gazdaságos végrehajtás: belépés és nyereségvétel limitárral (0,015% díj), a veszteségkorlát piaci áron (0,045% + csúszás). Egy nyerő ügylet költsége így 0,03%, egy stopolté 0,09%, a korábbi 0,2% helyett (TradingCalc). Nyereségcél: a coin szokásos 15 perces mozgásának 1,5-szöröse, veszteségkorlát a 2,5-szöröse, legfeljebb 90 perc. A likvidálási ár mindig legalább 3 stopnyira marad.'));
 const fams=el('div','pa-checks');
 for(const x of (f.families?.length?f.families:Object.keys(draft.families||{}).map(id=>({id,label:paFamilies[id]||id})))){const l=el('label','pa-check'),c=document.createElement('input');c.type='checkbox';c.checked=draft.families?.[x.id]!==false;c.onchange=()=>{draft.families=Object.assign({},draft.families,{[x.id]:c.checked});};l.append(c,el('span','',x.label));fams.append(l);}
 const coins=document.createElement('select');coins.className='pa-input';for(const n of [5,10,15,20]){const o=el('option','',n+' piac');o.value=n;o.selected=Number(draft.coins)===n;coins.append(o);}coins.onchange=()=>{draft.coins=Number(coins.value);};
 const cl=el('label','ap-field');cl.append(el('span','','Ennyi legforgalmasabb piacot figyel (+ amiről friss hír szól)'),coins);
 set.append(el('p','hint','Mire figyeljen:'),fams,cl);
 const acts=el('div','pa-actions');
 acts.append(button('Beállítások mentése',()=>paCall('save_fast_settings',{settings:JSON.stringify(draft)}).then(x=>{toast(x.message);paForm.fast=null;projectAppSig='';return loadProjectApp();})));
 const open=d.paper_positions||[];
 if(running)acts.append(button('■ Gyors AI leállítása',()=>paConfirm('Leállítás','A gyors AI nem köt több ügyletet, és a nyitott ügyleteit lezárja a mostani áron.','Igen, leállítom',()=>paRun(['stop_all'])),'pa-stop-small'));
 else acts.append(button('⚡ Mentés és indítás',()=>paConfirm('Gyors AI indítása',(chosen.label||'')+' profillal indul.'+(open.length&&d.results?.account_mode!=='fast_ai'?' Előtte a '+open.length+' nyitott ügyletet lezárja a mostani áron.':open.length?' A '+open.length+' nyitott gyors ügyletét tovább kezeli.':''),'Igen, indítom',async()=>{
  await paCall('save_fast_settings',{settings:JSON.stringify(draft)});paForm.fast=null;await paRun((d.results?.mode==='copy'||(open.length&&d.results?.account_mode!=='fast_ai')?['stop_all']:[]).concat(['fast_start']));})));
 set.append(acts);page.append(set);
}

/* Copying: whom (ranking or any public address), how big, and whether it may switch to a better trader. */
function paCopyPage(page,d){
 const r=d.results||{},copying=r.mode==='copy',cands=[...(d.discovery?.candidates||[])].sort((a,b)=>Number(b.score)-Number(a.score)),open=d.paper_positions||[];
 const now=el('section','pa-hero '+(copying?'copy':'off')),words=el('div'),leader=r.copy?.leader;
 const known=cands.find(c=>c.address===leader);
 words.append(el('strong','',copying?'Most ezt másolja: '+(known?known.name:leader?.slice(0,6)+'…'+leader?.slice(-4)):'A másolás most nincs bekapcsolva'),
  el('p','',copying?'Méret: '+(r.copy?.size_percent||100)+'% · '+(r.copy?.auto_best?'magától átvált, ha tartósan jobb kereskedő akad':'nem vált magától')+(r.copy?.since?' · '+paAgo(r.copy.since)+' óta':''):'Válassz lent egy kereskedőt a rangsorból, vagy adj meg egy nyilvános címet.'));
 now.append(el('span','pa-hero-icon',copying?'👥':'⏸'),words);page.append(now);
 if(copying&&r.copy?.error)page.append(el('p','pa-note','Utolsó adatkérés: '+r.copy.error));
 const set=el('section','pa-card');set.append(el('h3','','Hogyan másoljon'));
 const size=document.createElement('select');size.className='pa-input';for(const n of [25,50,75,100,150,200]){const o=el('option','',n+'%'+(n===100?' (arányos)':''));o.value=n;o.selected=paForm.size===n;size.append(o);}size.onchange=()=>{paForm.size=Number(size.value);};
 const sl=el('label','ap-field');sl.append(el('span','','Méret: a kereskedő tőkéjéhez mért kitettség hányszorosát kövesse'),size);
 const auto=el('label','pa-check'),ac=document.createElement('input');ac.type='checkbox';ac.checked=paForm.auto;ac.onchange=()=>{paForm.auto=ac.checked;};auto.append(ac,el('span','','Váltson magától, ha a rangsorban tartósan jobb kereskedő jelenik meg (1 nap után, 30%-kal jobb pontszámnál)'));
 set.append(sl,auto,el('p','hint','100%: ha a kereskedő a tőkéje felét teszi egy ügyletbe, a MiLLIONS is a virtuális számla felét. A kockázati korlát (Haladó lap) ettől függetlenül érvényes.'));
 page.append(set);
 const start=(address,name,ranked)=>paConfirm('Másolás indítása',name+' másolása '+paForm.size+'% méretben'+(paForm.auto?', automatikus váltással.':'.')+(open.length&&!(copying&&leader===address)?' A mostani '+open.length+' nyitott ügylet előbb lezárul a mostani áron.':'')+(ranked===false?' Figyelem: ez a számla nem felel meg a rangsor szabályainak.':''),
  'Igen, indítom',async()=>{const x=await paCall('copy_start',{symbol:address,settings:JSON.stringify({size_percent:paForm.size,auto_best:paForm.auto})});toast(x.message);projectAppSig='';await loadProjectApp();});
 const list=el('section','pa-card');list.append(el('h3','','Ellenőrzött kereskedők · '+cands.length+(d.discovery?.searching?' · új keresés folyamatban…':'')),el('p','hint',(d.discovery?.method||'')+' Frissítve: '+paTime(d.discovery?.updated_at)+'.'));
 for(const c of cands){const card=el('div','pa-trader'+(c.address===leader?' on':''));const info=el('div');
  info.append(el('strong','',c.name+(c.address===leader?' · most ezt másolja':'')),el('small','',c.address),
   el('p','','Havi hozam '+paPct(c.return_percent)+' · legnagyobb visszaesés '+paNum(c.drawdown_percent,1)+'% · egyenletesség '+paNum(c.consistency_percent,0)+'% · másolhatóság '+paNum(c.copyable_percent,0)+'% · pontszám '+paNum(c.score,2)));
  card.append(info,button(c.address===leader&&copying?'Beállítás frissítése':'Ezt másolom',()=>start(c.address,c.name,true),'secondary'));list.append(card);}
 if(!cands.length)list.append(el('p','hint','Most nincs friss, ellenőrzött jelölt; a piacfigyelő óránként keres.'));
 else{const best=button('A legjobbat másolja, automatikus váltással',()=>paConfirm('Legjobb kereskedő másolása','A rangsor első helyezettjét másolja '+paForm.size+'% méretben, és magától átvált, ha tartósan jobb akad.'+(open.length?' A nyitott ügyletek előbb lezárulnak.':''),'Igen, indítom',
  async()=>{const x=await paCall('copy_best',{settings:JSON.stringify({size_percent:paForm.size})});toast(x.message);projectAppSig='';await loadProjectApp();}));list.append(best);}
 page.append(list);
 const ext=el('section','pa-card');ext.append(el('h3','','Saját választás: bármely nyilvános számla'),el('p','hint','Másold be egy Hyperliquid-kereskedő nyilvános címét (0x…, például a Hyperliquid ranglistájáról). A MiLLIONS ugyanazokkal a szabályokkal ellenőrzi, mint a rangsort. Privát kulcsot soha ne adj meg.'));
 const input=document.createElement('input');input.className='pa-input pa-address';input.placeholder='0x…';input.value=paForm.address;input.setAttribute('aria-label','Nyilvános számlacím');input.oninput=()=>{paForm.address=input.value.trim();};
 const row=el('div','pa-actions');row.append(input,button(paForm.checking?'Ellenőrzés…':'Ellenőrzés',async()=>{paForm.checking=true;try{paForm.check=await paCall('trader_check',{symbol:paForm.address});}catch(e){paForm.check={error:e.message};}finally{paForm.checking=false;renderProjectApp();}},'secondary'));
 ext.append(row);
 const c=paForm.check;
 if(c?.error)ext.append(el('p','pa-note',c.error));
 else if(c){const box=el('div','pa-check-result');box.append(el('strong','',c.address),el('p','','Számlaérték '+paUsd(c.equity)+' · havi eredmény '+paUsd(c.pnl_month,true)+' ('+paPct(c.return_percent)+') · visszaesés '+paNum(c.drawdown_percent,1)+'% · egyenletesség '+paNum(c.consistency_percent,0)+'%'));
  const ul=el('ul','pa-checklist');for(const x of c.checks||[])ul.append(el('li',x.ok?'up':'down',(x.ok?'✓ ':'✗ ')+x.text));box.append(ul);
  box.append(el('p',c.ranked?'pa-ok':'pa-note',c.ranked?'Megfelel a rangsor minden szabályának.':'Nem kerülne a rangsorba: '+c.reason));
  if(c.curve?.length>1)box.append(paChart(c.curve.map(p=>[p[0],Number(p[1])]),{h:140,fmt:v=>paUsd(v),xfmt:t=>new Date(t).toLocaleDateString('hu-HU',{month:'short',day:'numeric'}),label:'Havi eredmény'}),el('p','hint','Az elmúlt hónap eredménygörbéje (dollár).'));
  if(c.positions?.length){const pl=el('ul','pa-why');for(const p of c.positions)pl.append(el('li','',p.coin+' · '+paSide(p.direction)+' · '+paUsd(p.value)));box.append(el('p','hint','Most nyitott ügyletei:'),pl);}
  box.append(button('Ennek a számlának a másolása',()=>start(c.address,c.address.slice(0,6)+'…'+c.address.slice(-4),c.ranked)));ext.append(box);}
 page.append(ext);
}

/* News first, from every source the owner keeps on (X news accounts included), then the market. */
const paFamilies={retest:'Visszateszt a trend irányában',news:'Friss hír',research:'Bevált kutatási szabály',
 breakout:'Kitörés (régi)',momentum:'Lendület (régi)',reversal:'Fordulat (régi)',orderbook:'Vételi/eladási nyomás (régi)',funding:'Finanszírozás (régi)'};
const PA_GROUP={x:'𝕏',portal:'Portál',official:'Hivatalos',custom:'Saját'};
function paMarketPage(page,d){
 const chips=el('div','pa-chips');
 chips.append(paChip('Piacfigyelő',d.monitor_running,'Árfolyamok, hírek és kereskedőkeresés'),paChip('Hírek frissek',d.news_fresh,'A hírgyűjtő utolsó köre: '+paTime(d.news_updated_at)),paChip('Kutatás',d.research_running,d.research?.phase||''));
 page.append(chips);
 const cols=el('div','pa-cols');cols.append(paNews(d),paMarket(d));page.append(cols);
 page.append(paSources(d));
}
function paNews(d){
 const box=el('section','pa-card');box.append(el('h3','','Hírek'),el('p','hint',(d.analyzed_count||0)+' AI-val elemezve · '+(d.pending_count||0)+' vár elemzésre · a friss hírek azonnal kapnak egy gyors értékelést, amit az AI-elemzés később pontosít.'));
 const filters=el('div','pa-seg small');
 for(const [id,label] of [['all','Mind'],['x','𝕏 hírfiókok'],['portal','Portálok'],['official','Hivatalos'],['custom','Saját']]){const b=el('button','',label);b.setAttribute('aria-pressed',String(paForm.newsGroup===id));b.onclick=()=>{paForm.newsGroup=id;renderProjectApp();};filters.append(b);}
 const coin=document.createElement('input');coin.className='pa-input';coin.placeholder='Coin (pl. SOL)';coin.value=paForm.newsCoin;coin.setAttribute('aria-label','Hírek szűrése coinra');
 box.append(filters,coin);
 const list=el('ol','pa-news');
 const draw=()=>{list.replaceChildren();const q=coin.value.trim().toUpperCase();paForm.newsCoin=coin.value;
  for(const n of (d.news_items||[]).filter(n=>(paForm.newsGroup==='all'||(n.group||'portal')===paForm.newsGroup)&&(!q||(n.assets||[]).some(a=>a.toUpperCase().includes(q)))).slice(0,40)){
   const li=el('li'),ai=n.analysis?.impact,quick=n.quick?.impact,impact=ai||quick;
   const label={positive:'Pozitív',negative:'Negatív',uncertain:'Bizonytalan'}[impact]||'–';
   li.append(el('span','pa-impact '+(impact==='positive'?'up':impact==='negative'?'down':'')+(ai?'':' quick'),(ai?'AI: ':'gyors: ')+label),
    el('span','pa-news-title',n.title),el('small','',(PA_GROUP[n.group]||'Portál')+' · '+n.source+' · '+paAgo(n.published_at)+(n.assets?.length?' · '+n.assets.map(a=>a==='MACRO'?'egész piac':a).join(', '):'')));
   li.title=n.analysis?.evidence||n.summary||'';list.append(li);}
  if(!list.children.length)list.append(el('li','hint','Nincs a szűrésnek megfelelő friss hír.'));};
 coin.oninput=draw;draw();box.append(list);return box;
}
function paMarket(d){
 const box=el('section','pa-card');box.append(el('h3','','Árfolyamok most'),el('p','hint','Kb. 3 másodpercenként frissül · '+paTime(d.market?.updated_at)+(d.market?.fresh===false?' · ELAVULT':'')+'. Finanszírozás: amit óránként az egyik oldal fizet a másiknak; magas érték = zsúfolt oldal.'));
 const find=document.createElement('input');find.className='pa-input';find.placeholder='Keresés (pl. BTC)';find.setAttribute('aria-label','Piac keresése');box.append(find);
 const table=el('table','pa-table'),rows=[...(d.market?.rows||[])].sort((a,b)=>Number(b.volume)-Number(a.volume));
 const draw=()=>{table.replaceChildren();const hr=el('tr');for(const h of ['Eszköz','Ár','24 óra','Forgalom','Finansz./óra'])hr.append(el('th','',h));table.append(hr);
  const q=find.value.trim().toUpperCase();for(const r of rows.filter(r=>!q||r.symbol.toUpperCase().includes(q)).slice(0,16)){const tr=el('tr');
   tr.append(el('td','',r.symbol),el('td','num',paPrice(r.price)),el('td','num '+paTone(r.change_percent),paPct(r.change_percent)),el('td','num',paNum(Number(r.volume)/1e6,1)+' M'),el('td','num',r.funding==null?'–':paNum(Number(r.funding)*100,4)+'%'));table.append(tr);}};
 find.oninput=draw;draw();box.append(table);return box;
}
function paSources(d){
 const box=el('section','pa-card'),list=d.news_source_list||[],status=Object.fromEntries((d.news_sources||[]).map(s=>[s.id||s.name,s]));
 box.append(el('h3','','Hírforrások'),el('p','hint','Az X-et ingyen nem lehet olvasni (az API fizetős, a nitter-tükrök megszűntek), ezért az X-hírfiókokat a saját nyilvános Telegram-csatornájukról olvassa – ott ugyanazokat a bejegyzéseket teszik közzé. Az X-hírfiókokat 30 másodpercenként, a portálokat 2 percenként nézi.'));
 const disabled=new Set(list.filter(s=>!s.enabled).map(s=>s.id));
 const save=custom=>paCall('save_news_sources',{settings:JSON.stringify({disabled:[...disabled],custom:custom.map(s=>({kind:s.kind,url:s.url,channel:s.channel,name:s.name}))})}).then(x=>{toast(x.message);projectAppSig='';return loadProjectApp();});
 const customs=list.filter(s=>s.group==='custom');
 for(const g of ['x','portal','official','custom']){const items=list.filter(s=>s.group===g);if(!items.length)continue;
  const grp=el('div','pa-src-group');grp.append(el('strong','',{x:'𝕏 X-hírfiókok (Telegram-tükörből)',portal:'Kripto-hírportálok',official:'Hivatalos források',custom:'Saját források'}[g]));
  for(const s of items){const st=status[s.id]||status[s.name]||{},row=el('label','pa-src'),c=document.createElement('input');c.type='checkbox';c.checked=s.enabled;
   c.onchange=()=>{c.checked?disabled.delete(s.id):disabled.add(s.id);save(customs);};
   row.append(c,el('span','',s.name+(s.handle?' '+s.handle:'')),el('small',st.ok===false?'down':'',!s.enabled?'kikapcsolva':st.ok===false?'hiba: '+(st.error||''):st.ok?(st.count||0)+' tétel · legfrissebb '+(st.newest_at?paAgo(st.newest_at):'–'):'még nem olvasta'));
   if(g==='custom'){const del=el('button','text-button','törlés');del.onclick=e=>{e.preventDefault();save(customs.filter(x=>x.id!==s.id));};row.append(del);}
   grp.append(row);}
  box.append(grp);}
 const add=el('div','pa-actions'),kind=document.createElement('select');kind.className='pa-input';
 for(const [v,l] of [['telegram','Telegram-csatorna (sok X-fiók ide is posztol)'],['rss','RSS-hírcsatorna']]){const o=el('option','',l);o.value=v;o.selected=paForm.srcKind===v;kind.append(o);}
 const value=document.createElement('input');value.className='pa-input';value.placeholder=paForm.srcKind==='rss'?'https://…/feed':'csatorna neve vagy t.me link';value.value=paForm.srcValue;value.oninput=()=>{paForm.srcValue=value.value;};
 const name=document.createElement('input');name.className='pa-input';name.placeholder='Megjelenő név';name.value=paForm.srcName;name.oninput=()=>{paForm.srcName=name.value;};
 kind.onchange=()=>{paForm.srcKind=kind.value;renderProjectApp();};
 add.append(kind,value,name,button('Forrás hozzáadása',()=>save(customs.concat([{kind:paForm.srcKind,url:paForm.srcValue,channel:paForm.srcValue,name:paForm.srcName}])).then(()=>{paForm.srcValue='';paForm.srcName='';renderProjectApp();}),'secondary'));
 box.append(el('p','hint','Saját forrás hozzáadása:'),add);
 return box;
}
function paDetails(page,d){
 const r=d.results||{},cands=[...(d.discovery?.candidates||[])].sort((a,b)=>Number(b.score)-Number(a.score));
 const rank=el('section','pa-card');rank.append(el('h3','','Kereskedőrangsor · '+cands.length),el('p','hint',(d.discovery?.method||'')+' Frissítve: '+paTime(d.discovery?.updated_at)+'.'));
 if(cands.length){const t=el('table','pa-table'),hr=el('tr');for(const h of ['Számla','Pontszám','Havi hozam','Visszaesés','Egyenletesség','Másolhatóság'])hr.append(el('th','',h));t.append(hr);
  for(const c of cands){const tr=el('tr');tr.append(el('td','',c.name+(c.address===r.copy?.leader?' · követett':'')),el('td','num',paNum(c.score)),el('td','num',paPct(c.return_percent)),el('td','num',paNum(c.drawdown_percent)+'%'),el('td','num',c.consistency_percent?paNum(c.consistency_percent,0)+'%':'–'),el('td','num',c.copyable_percent?paNum(c.copyable_percent,0)+'%':'–'));t.append(tr);}
  rank.append(t);}
 else rank.append(el('p','hint','Még nincs ellenőrzött jelölt.'));
 page.append(rank);
 const rs=el('section','pa-card');rs.append(el('h3','','Kutatás · igazolt szabályok: '+(r.eligible?.length||0)));
 rs.append(el('p','hint','Percgyertyás és 15 perces sáv: '+(r.swing_symbols||[]).join(', ')+'. Egy szabály akkor használható, ha az elkülönített teszten, dupla költséggel és legalább 7 nap új adaton is nyereséges.'));
 for(const e of r.eligible||[])rs.append(el('p','pa-ok','✓ '+paRule(e)+' · új adaton '+paPct(e.forward_net_percent)+' ('+e.forward_trades+' ügylet, '+paNum(e.forward_days,1)+' nap)'));
 const ul=el('ul','pa-reasons');for(const w of r.watching||[])ul.append(el('li','',w.id+' · új adaton '+paPct(w.forward_net_percent)+' ('+w.forward_trades+' ügylet, '+paNum(w.forward_days,1)+' nap)'+(w.reasons?.length?' – '+w.reasons[0]:'')));
 if(ul.children.length)rs.append(el('p','hint','Megfigyelés alatt:'),ul);
 page.append(rs);
 const risk=el('section','pa-card');risk.append(el('h3','','Virtuális kockázati keret'),el('p','hint','Új nyitást a korlát blokkolhat; meglévő pozíciót a korlát módosítása nem zár.'));
 const pos=document.createElement('input'),gross=document.createElement('input');
 for(const [inp,label] of [[pos,'Pozíciónként (%)'],[gross,'Összesített kitettség (%)']]){inp.type='number';inp.min=1;inp.max=500;inp.className='pa-input';const l=el('label','ap-field');l.append(el('span','',label),inp);risk.append(l);}
 paCall('risk_settings').then(x=>{pos.value=x.max_position_percent;gross.value=x.max_gross_percent;}).catch(()=>{});
 risk.append(el('div','pa-actions'));risk.lastChild.append(button('Keret mentése',()=>paAct('save_risk',{news:JSON.stringify({max_position_percent:String(pos.value),max_gross_percent:String(gross.value)})})),
  ...(d.paper_positions?.length?[button('Minden leállítása és lezárása',()=>paConfirm('Leállítás','A MiLLIONS nem köt több ügyletet, és a nyitott ügyleteket lezárja a mostani áron.','Igen, leállítom',()=>paRun(['stop_all'])),'secondary')]:[]),
  d.monitor_running?button('Piacfigyelő leállítása',()=>paAct('monitor_stop'),'secondary'):button('Piacfigyelő indítása',()=>paAct('monitor_start'),'secondary'),
  d.research_running?button('Kutatás leállítása',()=>paAct('research_stop'),'secondary'):button('Kutatás indítása',()=>paAct('research_start'),'secondary'));
 page.append(risk);
 const log=el('section','pa-card');log.append(el('h3','','Eseménynapló'));const pre=el('pre','pa-log','Betöltés…');log.append(pre);page.append(log);
 paCall('activity').then(x=>{pre.textContent=x.display||x.message;}).catch(e=>{pre.textContent=e.message;});
}
(()=>{
 const base=render;render=function(){base();syncProjectApp();};
 const baseSwitch=switchApp;switchApp=function(view){baseSwitch(view);if(view==='agents'&&projectAppView)loadProjectApp();};
 $('viewApp').onclick=()=>setProjectView(true);$('viewMap').onclick=()=>setProjectView(false);
 $('projectAppView').addEventListener('focusout',()=>setTimeout(()=>{if(projectAppPending&&!paTyping())renderProjectApp();},50));
 // Switched off, nothing changes in the background: a slow refresh is enough.
 setInterval(()=>{if(projectAppView&&currentApp==='agents'&&!document.hidden&&(projectAppData?.power?.on!==false||Date.now()-paLastLoad>60000))loadProjectApp();},6000);
})();
