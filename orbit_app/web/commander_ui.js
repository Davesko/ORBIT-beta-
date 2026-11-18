let chatSession=(()=>{try{return localStorage.getItem('orbitChat')??'earlier';}catch(e){return 'earlier';}})();
/* The main assistant is a separate application surface, with evidence-backed actions. */
let commandSending=false,commandWorkspace=null;
let currentApp='home',commandState=null,commandKey='',commandImage=null,homeBusy=false,assistantOpen=false,assistantPinned=false;
function switchApp(view){currentApp=view;if($('growthApp'))$('growthApp').hidden=view!=='growth';if($('navGrowth')){$('navGrowth').classList.toggle('active',view==='growth');$('navGrowth').setAttribute('aria-pressed',String(view==='growth'));}if($('publicationApp'))$('publicationApp').hidden=view!=='publishing';if($('navPublishing')){$('navPublishing').classList.toggle('active',view==='publishing');$('navPublishing').setAttribute('aria-pressed',view==='publishing');}if($('automationApp'))$('automationApp').hidden=view!=='automations';if($('navAutomations')){$('navAutomations').classList.toggle('active',view==='automations');$('navAutomations').setAttribute('aria-pressed',view==='automations');}$('studioApp').hidden=view!=='agents';$('commandApp').hidden=view!=='home'&&!assistantOpen;$('navHome').classList.toggle('active',view==='home');$('navAgents').classList.toggle('active',view==='agents');$('navHome').setAttribute('aria-pressed',view==='home');$('navAgents').setAttribute('aria-pressed',view==='agents');if(view==='home'||assistantOpen)pollCommand();}
function commandLabel(status){return ({queued:'Sorban áll',running:'Gondolkodik',executing:'A csapat dolgozik',review:'Átnézésre vár',queued_apply:'Végrehajtásra vár',applying:'Dolgozik',done:'Elkészült',failed:'Megállt',attention:'Pontosításra vár',cancelled:'Leállítva',rejected:'Elvetve'})[status]||status;}
async function pollCommand(){if((currentApp!=='home'&&!assistantOpen)||homeBusy)return;homeBusy=true;const pid=project,want=chatSession;try{const data=await call('command_state',{global:true,session:want});if(want!==chatSession)return;delete data.requestId;commandState=data;if(typeof syncAssistantPreferences==='function')syncAssistantPreferences(data.preferences||[]);renderCommand();updateChatClocks();}catch(e){$('commandLive').hidden=false;$('commandLive').textContent=e.message;delete $('commandLive').dataset.key;}finally{homeBusy=false;}}
const commandCards=new Map();
function humanAction(a){
 const dir=commandState?.directory||{},agents=dir.agents||[],projects=dir.projects||[];
 const person=agents.find(x=>x.id===a.agent)?.name||a.agent?.name||'a kijelölt ügynök';
 const target=projects.find(x=>x.id===a.project)?.name||'';
 const file=String(a.path||'').split('/').pop();
 const titles={short_style_save:'Videó és felirat beállítása',agent_run:'Feladat kiosztása',graph_run:'Csapat indítása',write_file:'Fájl mentése',run_command:'Fejlesztési művelet',agent_save:'Ügynök beállítása',room_save:'Szoba beállítása',connection_save:'Ügynökök összekapcsolása',project_create:'Új projekt',project_save:'Projekt módosítása',automation_save:'Ütemezés beállítása',start_shorts:'Videó készítése',generate_image:'Kép készítése',generate_video:'Videó generálása a helyi Wan modellel',recipe_save:'Munkafolyamat mentése',show_artifact:'Alkotás megnyitása',memory_save:'Preferencia megjegyzése',preferences_save:'Megjelenés módosítása',app_action:'Alkalmazásművelet',adapter_export:'Átadás másik programnak'};
 if(a.type==='app_action'){const names={agent_archive:'Ügynök törlése',agent_restore:'Ügynök visszaállítása',room_archive:'Szoba törlése',room_restore:'Szoba visszaállítása',recipe_pause:'Automatizáció szüneteltetése',recipe_run:'Automatizáció indítása',job_cancel:'Feladat leállítása'};if(names[a.operation])return {title:names[a.operation],text:'A kért műveletet a kijelölt projektben hajtja végre. A törlés visszaállítható.',target};}
 const descriptions={short_style_save:'Elmenti a videó tényleges hosszát és feliratpozícióját. A következő gyártás és az ellenőrzés ezeket használja.',agent_run:'Külön feladatot kap '+person+'. Az eredménye ide érkezik vissza.',graph_run:person+' és a hozzá kapcsolódó csapat dolgozik a kérésen.',write_file:'Elmenti vagy frissíti ezt a fájlt: '+file+'. Meglévő fájlról biztonsági másolat készül.',run_command:'A megadott fejlesztési parancsot futtatja. A pontos parancsot a részleteknél ellenőrizheted.',generate_image:'A helyi képgeneráló elkészíti a képet, majd ide és az Alkotásokba menti.',generate_video:'A helyi Wan a leírás alapján MP4-et készít, és ide menti.',start_shorts:'Elindítja a videós munkafolyamatot. A kész videót itt is megkapod.',show_artifact:'Megmutat egy már elkészült képet, videót vagy hangot.',memory_save:a.display||'Eltárolja ezt a tartós preferenciát a személyes memóriában.',preferences_save:'Frissíti a kért színtémát, hátteret vagy karaktereket.'};
 return {title:a.label||titles[a.type]||'Beállítás módosítása',text:a.explanation||descriptions[a.type]||(target?'A kért beállításokat frissíti ebben a projektben: '+target+'.':'Elvégzi a kérésedhez tartozó belső alkalmazásműveletet.'),target};
}
function richText(text){
 const root=el('div','rich-text');let code=false,pre=null,list=null;
 function inline(parent,line){const tokens=line.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g);for(const token of tokens){if(token.startsWith('**'))parent.append(el('strong','',token.slice(2,-2)));else if(token.startsWith('`'))parent.append(el('code','',token.slice(1,-1)));else {const m=token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);if(m){const a=el('a','',m[1]);a.href=m[2];a.target='_blank';a.rel='noopener noreferrer';parent.append(a);}else parent.append(document.createTextNode(token));}}}
 for(const line of String(text||'').split('\n')){if(line.trim().startsWith('```')){code=!code;list=null;if(code){pre=el('pre','command-code');root.append(pre);}continue;}if(code){pre.textContent+=line+'\n';continue;}if(/^\s*---+\s*$/.test(line)){root.append(el('hr'));list=null;continue;}const h=line.match(/^#{1,6}\s+(.+)$/);if(h){const title=el('h4');inline(title,h[1]);root.append(title);list=null;continue;}const item=line.match(/^\s*(?:[-*]|\d+[.)])\s+(.+)$/);if(item){if(!list){list=el('ul');root.append(list);}const li=el('li');inline(li,item[1]);list.append(li);continue;}list=null;if(line.trim()){const p=el('p');inline(p,line);root.append(p);}}
 return root;
}
function actionCard(a,key,review=false){const human=humanAction(a),d=el('details','command-action');d.dataset.detailKey=key;const summary=el('summary');summary.append(el('span','',human.title),el('small','',human.target));d.append(summary,el('p','action-explanation',human.text));
 if(a.type==='write_file')d.append(el('p','action-file',String(a.path||'').split('/').pop()));
 const technical=el('details','technical-details');technical.dataset.detailKey=key+':technical';technical.append(el('summary','','Technikai részletek'),el('pre','command-code',a.type==='write_file'?(a.diff||a.content||''):a.type==='run_command'?(a.cwd+'\n\n'+a.command):JSON.stringify(a,null,2)));d.append(technical);if(review)d.open=true;return d;}
function localVideoTurn(turn){return turn.actions?.some(a=>a.type==='generate_video');}
function videoPromptKey(prompt){
 return prompt.replace(/^\s*wan[^:\n]{0,60}\s+modellel\s*:\s*/i,'').normalize('NFC').toLowerCase().trim().replace(/\s+/g,' ');
}
function earlierLocalVideo(turn,turns){
 if(turn.route?.task!=='video'||!['failed','cancelled','attention'].includes(turn.status))return null;
 const key=videoPromptKey(turn.prompt);
 return turns.findLast(t=>t.created<turn.created&&t.project===turn.project&&t.status==='done'&&localVideoTurn(t)&&
  t.artifacts?.some(a=>a.kind==='video')&&videoPromptKey(t.prompt)===key);
}
function drawCommandTurn(turn,earlierVideo){const group=el('section','command-turn-group');group.dataset.turnId=turn.id;
 const user=el('div','command-turn user');user.append(el('span','turn-label','TE'),el('div','turn-text',turn.prompt));
 for(const attachment of turn.attachments||(turn.attachment?[turn.attachment]:[]))user.append(button('◈ '+attachment.name,()=>act(()=>call('open_artifact',{id:attachment.id,requestProject:turn.project})),'secondary'));
 group.append(user);
 const reply=el('div','command-turn assistant'),heading=el('div','command-turn-heading');const failed=turn.linked_jobs?.some(j=>['failed','blocked'].includes(j.status)),busy=turn.linked_jobs?.some(j=>['queued','running'].includes(j.status));const display=failed?'failed':busy&&turn.status==='done'?'executing':busy?'running':turn.status;
 heading.append(el('span','turn-label','◒ ORBIT'),el('span','turn-status '+display,commandLabel(display)));reply.append(heading);if(turn.route?.model)reply.append(el('div','route-label',routeLabel(turn.route)));const clock=el('small','chat-clock');clock.dataset.started=turn.timing?.started||'';clock.dataset.finished=turn.timing?.finished||'';clock.dataset.created=turn.created;clock.dataset.status=turn.status;reply.append(clock);if(turn.skills_used?.length&&!localVideoTurn(turn))reply.append(el('p','hint','Munkamódszer: '+turn.skills_used.map(s=>s.title+' · v'+s.version).join(', ')));if(turn.provider_fallback?.length)reply.append(el('p','hint','Tartalék szolgáltató vagy modell átvette a feladatot.'));
 const streaming=['queued','running','queued_apply','applying'].includes(turn.status);
 if(streaming){
  const live=el('p','command-progress-line');live.append(el('i','command-progress-dot'),el('span','command-progress-phase'));
  reply.append(live,el('div','reply-stream'));
 }else if(turn.status==='cancelled')reply.append(richText('Ez a próbálkozás leállt.'));
 else if(turn.response)reply.append(richText(turn.response));

 if(earlierVideo)reply.append(button('Korábban elkészült videó megtekintése',()=>{
  commandCards.get(earlierVideo.id)?.node.querySelector('.inline-media-card')?.scrollIntoView({block:'center'});
 },'secondary'));

 if(turn.status==='attention'||(turn.status==='queued'&&turn.generation?.provider==='scheduler'&&turn.generation?.phase?.toLowerCase().includes('modell')))reply.append(button('Folytatás a kiválasztott modellel',async()=>{await call('command_continue',{turn:turn.id,model:$('commandModel').value,global:true,requestProject:turn.project});await pollCommand();},'secondary'));
 if(['failed','cancelled'].includes(turn.status))reply.append(button('Újrapróbálás',async()=>{await call('command_send',{prompt:turn.prompt,model:$('commandModel').value,attachments:(turn.attachments||[turn.attachment]).filter(Boolean).map(a=>a.id),workspace:turn.workspace,requestProject:turn.project,global:true,session:chatSession});await pollCommand();},'secondary'));
 if(turn.status==='failed')reply.append(button('Újrapróbálás automatikus modellel',async()=>{localStorage.setItem('orbitPersonalModel','auto');$('commandModel').value='auto';await call('command_send',{prompt:turn.prompt,model:'auto',attachments:(turn.attachments||[turn.attachment]).filter(Boolean).map(a=>a.id),workspace:turn.workspace,requestProject:turn.project,global:true,session:chatSession});await pollCommand();},'secondary'));
 if(turn.actions?.length){const plan=el('div','command-plan');plan.append(el('div','eyebrow',(turn.status==='review'?'EZ FOG TÖRTÉNNI':'A KÉRÉSED LÉPÉSEI')+' · '+turn.actions.length));turn.actions.forEach((a,i)=>plan.append(actionCard(a,'action:'+i)));if(turn.status==='review'){const buttons=el('div','plan-buttons');buttons.append(button('Átnézem és elindítom',()=>reviewCommand(turn),'primary'),button('Most nem',async()=>{await call('command_reject',{id:turn.id,global:true});await pollCommand();},'secondary'));plan.append(buttons);}reply.append(plan);}
 if(turn.emails?.length&&typeof mailCards==='function')reply.append(mailCards(turn.emails));if(turn.artifacts?.length){const media=turn.artifacts.filter(a=>a.kind!=='text'),files=turn.artifacts.filter(a=>a.kind==='text');if(media.length){const grid=el('div','inline-media-grid');media.forEach(a=>grid.append(mediaCard(a,localVideoTurn(turn)&&a.kind==='video')));reply.append(grid);}if(files.length){const row=el('div','file-cards');files.forEach(a=>row.append(fileCard(a)));reply.append(row);}}
 if(turn.linked_jobs?.length){const done=turn.linked_jobs.filter(j=>j.status==='done').length,bad=turn.linked_jobs.find(j=>['failed','blocked'].includes(j.status));reply.append(el('p',bad?'error-text':'linked-production',bad?'Egy feladat megállt: '+(bad.error||'Nézd meg a részleteket.'):done+'/'+turn.linked_jobs.length+' feladat elkészült'+(busy?' · A csapat dolgozik.':'')));}
 for(const child of turn.linked_jobs||[]){if(child.kind==='chat'&&['failed','cancelled'].includes(child.status))reply.append(button((child.agent_name||'Ügynök')+' · Újrapróbálás',async()=>{await call('command_retry_agent',{turn:turn.id,id:child.id});await pollCommand();},'secondary'));if(child.kind==='chat'&&child.status==='done'&&child.result){const result=el('details','command-action');result.dataset.detailKey='result:'+child.id;result.append(el('summary','',(child.agent_name||'Ügynök')+' válasza'),richText(child.result));reply.append(result);}}
 const audit=commandState.audit.filter(a=>a.turn_id===turn.id).reverse();if(audit.length){const d=el('details','command-audit');d.dataset.detailKey='audit';d.append(el('summary','','Elvégzett lépések · '+audit.length));for(const a of audit){const entry=el('div','command-audit-entry');entry.append(el('strong','',a.label),el('small','',new Date(a.created*1000).toLocaleTimeString('hu-HU')));if(a.detail){const raw=el('details','technical-details');raw.dataset.detailKey='audit:'+a.id;raw.append(el('summary','','Technikai napló'),el('pre','command-code',a.detail));entry.append(raw);}d.append(entry);}reply.append(d);}group.append(reply);return group;}
function updateLiveReply(card,turn){
 const phase=card.node.querySelector('.command-progress-phase');
 if(phase)phase.textContent=turn.generation?.phase||commandLabel(turn.status);
 const view=card.node.querySelector('.reply-stream'),next=turn.status==='running'?turn.reply_preview||'':'';
 if(!view||!next||next===card.target)return;
 card.target=next;
 if(!next.startsWith(view.textContent))view.textContent='';
 if(matchMedia('(prefers-reduced-motion: reduce)').matches){view.textContent=next;return;}
 if(card.frame)return;
 function tick(){
  card.frame=0;
  if(!view.isConnected)return;
  const current=view.textContent.length,goal=card.target;
  if(current>=goal.length)return;
  const end=Math.min(goal.length,current+Math.max(1,Math.ceil((goal.length-current)/7)));
  // Slice on code-point boundaries so a streamed emoji is never shown as half a character.
  const clean=end<goal.length&&/[\uD800-\uDBFF]/.test(goal[end-1])?end+1:end;
  view.textContent=goal.slice(0,clean);
  const scroll=$('commandScroll');
  if(scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<115)scroll.scrollTop=scroll.scrollHeight;
  if(clean<goal.length)card.frame=setTimeout(tick,26);
 }
 tick();
}
function renderCommand(){if(!commandState)return;if(typeof canvasNotice==='function')canvasNotice(commandState.turns);if(typeof memoryNotice==='function')memoryNotice(commandState.memory_note);if(typeof briefRender==='function')briefRender(commandState.briefing);const log=$('commandMessages'),scroll=$('commandScroll'),oldTop=scroll.scrollTop,expanded=!!log.querySelector('details[open]'),nearBottom=scroll.scrollHeight-oldTop-scroll.clientHeight<100;const active=commandState.turns.find(t=>['queued','running','queued_apply','applying'].includes(t.status));$('commandWelcome').hidden=commandState.turns.length>0;
 const liveKey=active?active.id+':'+active.status:'';if($('commandLive').dataset.key!==liveKey){$('commandLive').dataset.key=liveKey;$('commandLive').replaceChildren();$('commandLive').hidden=!active;if(active)$('commandLive').append(el('i','pulse'),el('span','',commandLabel(active.status)+' · a kérésed feldolgozása folyamatban'),button('Leállítás',async()=>{await call('job_cancel',{id:active.job,requestProject:active.project});await pollCommand();},'command-stop'));}if(active&&$('commandLive').querySelector('span'))$('commandLive').querySelector('span').textContent=active.generation?.phase||commandLabel(active.status)+' · a kérésed feldolgozása folyamatban';$('commandSend').disabled=commandSending;$('commandSend').setAttribute('aria-label',active?'Kérés sorba állítása':'Küldés a fő asszisztensnek');$('commandInput').placeholder=active?'Írhatsz új kérést is · sorba állítom…':'Kérj bármit. Tervezz, alkoss, irányíts…';
 const ids=new Set();let changed=false;for(const turn of commandState.turns){ids.add(turn.id);const {reply_preview,generation,...stable}=turn,earlierVideo=earlierLocalVideo(turn,commandState.turns);const signature=JSON.stringify(stable)+JSON.stringify(commandState.audit.filter(a=>a.turn_id===turn.id))+JSON.stringify(commandState.directory||{})+(earlierVideo?.id||'');const old=commandCards.get(turn.id);if(old?.signature===signature){updateLiveReply(old,turn);continue;}
 const opened=new Set(old?[...old.node.querySelectorAll('details[open]')].map(d=>d.dataset.detailKey):[]);const node=drawCommandTurn(turn,earlierVideo);for(const d of node.querySelectorAll('details'))if(opened.has(d.dataset.detailKey))d.open=true;if(old)old.node.replaceWith(node);else log.append(node);const card={node,signature};commandCards.set(turn.id,card);updateLiveReply(card,turn);changed=true;}
 for(const [id,card]of commandCards){if(!ids.has(id)){card.node.remove();commandCards.delete(id);}}
 if(changed)scroll.scrollTop=nearBottom&&!expanded?scroll.scrollHeight:oldTop;
 $('commandScope').textContent='◎ Minden projekt';const localOnly=commandState.ai_policy?.local_only!==false;const signature=JSON.stringify([localOnly,models.map(m=>m.name)]);if($('commandModel').dataset.models!==signature){$('commandModel').dataset.models=signature;const available=models.filter(m=>!/(embed|rerank)/i.test(m.name)&&(!localOnly||!(m.storage==='Cloud'||/^(groq|gemini|openrouter|deepseek)\//.test(m.name))));const saved=localStorage.getItem('orbitPersonalModel')||'auto';options($('commandModel'),[{value:'auto',label:'Automatikus · feladathoz választ'},...available.map(m=>({value:m.name,label:displayModel(m.name)+' · kézi'}))],available.some(m=>m.name===saved)?saved:'auto');}}
function reviewCommand(turn){const body=el('div');body.append(el('p','','Ezeket a változtatásokat fogja elvégezni. A fájlok korábbi változatát megőrzi. A pontos tartalom a Technikai részletek alatt olvasható.'));turn.actions.forEach((a,i)=>body.append(actionCard(a,'review:'+i,true)));body.append(button('Elindítom a változtatásokat',async()=>{await call('command_approve',{id:turn.id,global:true});$('modal').close();await pollCommand();}),button('Vissza',()=>$('modal').close(),'secondary'));showModal('Változtatások áttekintése',body);}

async function sendCommand(spoken=false){if(commandSending||chatAttachmentBusy)return;const files=pendingChatAttachments(),first=files[0],prompt=$('commandInput').value.trim()||(files.length?'Nézd át a csatolmányokat és foglald össze a lényegüket.':'');if(!prompt)return;commandSending=true;$('commandSend').disabled=true;try{
 const sent=await call('command_send',{prompt,model:$('commandModel').value,image:first?.image||null,attachments:files.map(f=>f.token).filter(Boolean),global:true,spoken:spoken===true,session:chatSession,workspace:commandWorkspace===project,open_file:commandWorkspace===project||assistantOpen?undefined:canvasActive||undefined,requestProject:!files.length&&!assistantOpen&&commandWorkspace!==project&&canvasActive?(canvasOf(canvasActive)?.project||project):project});
 openChat(sent.session,true);$('commandInput').value='';clearChatAttachments();await pollCommand();
 }finally{commandSending=false;$('commandSend').disabled=!!chatAttachmentBusy;}}
function updateAttachment(){
 const panel=$('commandAttachment'),files=typeof pendingChatAttachments==='function'?pendingChatAttachments():(commandImage?[commandImage]:[]),busy=typeof chatAttachmentBusy==='number'&&chatAttachmentBusy;
 panel.hidden=!files.length&&!busy&&commandWorkspace!==project;panel.replaceChildren();
 if(commandWorkspace===project)panel.append(el('span','','▦ Projektvászon · '+(state?.project?.name||'')),button('×',()=>{commandWorkspace=null;updateAttachment();},'remove-attachment'));
 for(const file of files){const chip=el('div','chat-file-chip');chip.append(el('span','','◈ '+(file.label||'Csatolt fájl')),button('×',()=>{if(commandImage===file)commandImage=null;commandAttachments=commandAttachments.filter(f=>f!==file);updateAttachment();},'remove-attachment'));panel.append(chip);}
 if(busy)panel.append(el('span','','Csatolás folyamatban · '+busy+' fájl…'));
}
async function showAccess(){const data=await call('command_state'),body=el('div');body.append(el('p','','A fő asszisztens ezeket a mappákat olvashatja, és jóváhagyás után szerkesztheti. Új helyet a Mac mappaválasztójával adhatsz hozzá.'));for(const [i,path] of data.roots.entries()){const row=el('div','item-card');row.append(el('p','mono',path));if(i)row.append(button('Hozzáférés visszavonása',async()=>{await call('command_revoke',{path});await showAccess();},'danger-link'));body.append(row);}body.append(button('Mappa hozzáadása',async()=>{await call('command_pick_folder');await showAccess();}));showModal('Munkamappák',body);}
async function showModelHub(){const info=await call('model_hub'),body=el('div','model-hub');body.append(el('h3','',info.message),el('p','hint',info.config.base||'Nincs külső modelltár beállítva.'));for(const m of info.models){const card=el('div','item-card'),embedding=/embed|rerank/i.test(m.name);card.append(el('h3','',m.name),el('p','hint',(m.size/1e9).toFixed(1)+' GB · '+m.storage+(embedding?' · beágyazási modell, nem chat':'')));if(!embedding)card.append(button('Használat a fő chatben',()=>{localStorage.setItem('orbitPersonalModel',m.name);$('commandModel').dataset.models='';$('modal').close();switchApp('home');renderCommand();},'secondary'));body.append(card);}for(const m of info.media_models||[]){const card=el('div','item-card');card.append(el('h3','',m.name),el('p','hint',m.purpose+' · '+(m.ready?'Készen áll':'Nem elérhető')+' · '+(m.size/1e6).toFixed(0)+' MB'));body.append(card);}const flux=el('div','item-card');flux.append(el('h3','','FLUX.1 Schnell'),el('p','hint',info.flux_ready?'Helyi képgeneráló · készen áll':'A helyi képgeneráló jelenleg nem elérhető.'));body.append(flux,button('Kapcsolatok és hibrid AI',()=>act(showConnections),'secondary'),button('További modellek',showModels,'secondary'));showModal('Helyi modellek és SSD',body);}
$('navHome').onclick=()=>switchApp('home');$('navAgents').onclick=()=>switchApp('agents');$('navCreations').onclick=()=>act(showGallery);$('navAccess').onclick=()=>act(showAccess);$('commandScope').onclick=()=>act(showAssistantProfile);$('commandSend').onclick=()=>act(sendCommand);$('commandInput').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();if(!$('commandSend').disabled)act(sendCommand);}};$('commandModel').onchange=()=>localStorage.setItem('orbitPersonalModel',$('commandModel').value);$('commandAttach').onclick=()=>act(pickChatAttachment);document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>{$('commandInput').value=b.dataset.prompt;$('commandInput').focus();});
setInterval(()=>{if(!document.hidden)pollCommand();},650);$('projectSelect').addEventListener('change',()=>{commandWorkspace=null;commandImage=null;updateAttachment();setTimeout(pollCommand,100);});switchApp('home');

function routeLabel(route){if(route.model==='local/wan21')return 'Helyi videógenerálás · '+(route.engine||'Wan 2.1');if(route.policy==='typed_control')return 'Alkalmazásvezérlés · '+(route.task==='automation'?'Feladatkezelő':route.task==='image'?'Képgenerálás':'Meglévő munkafolyamat');const names={chat:'Beszélgetés',code:'Kód és automatizálás',vision:'Képelemzés',image:'Képgenerálás',video:'Videógyártás'};return (route.automatic?'AUTO / ':'')+(names[route.task]||'Helyi AI')+' · '+(route.task==='image'?route.model+' → '+route.engine:route.model)+(route.fallback?' · megfelelő helyi modell':'');}
function mediaURL(a){return 'orbit-media://artifact/'+encodeURIComponent(a.id)+'?project='+encodeURIComponent(a.project||project);}
const mediaBlobs=new Map();
async function playableMedia(a){const key=mediaURL(a);if(!mediaBlobs.has(key))mediaBlobs.set(key,fetch(key).then(async response=>{if(!response.ok)throw new Error('Média nem olvasható');const blob=await response.blob();return URL.createObjectURL(blob);}).catch(error=>{mediaBlobs.delete(key);throw error;}));return mediaBlobs.get(key);}
function mediaCard(a,preview=false){
 const card=el('figure','inline-media-card');
 const media=el(a.kind==='image'?'img':a.kind==='audio'?'audio':'video');
 function showError(){
  card.classList.add('media-error');
  if(!card.querySelector('.media-error-label'))card.append(el('p','media-error-label','Az előnézet nem olvasható. A Megnyitás gombbal megnyithatod a Macen.'));
 }
 media.addEventListener('error',showError);
 if(a.kind==='image'){
  media.alt=a.name;media.loading='lazy';media.src=mediaURL(a);
 }else{
  media.controls=true;media.preload=preview?'auto':'none';media.setAttribute('playsinline','');
  const load=button(a.kind==='audio'?'Hang lejátszása':'Videó lejátszása',()=>attach(true),'secondary');
  async function attach(play){
   load.disabled=true;load.textContent='Betöltés…';card.setAttribute('aria-busy','true');
   try{
    media.src=await playableMedia(a);load.remove();
    card.classList.remove('media-error');card.querySelector('.media-error-label')?.remove();
    if(play)media.play().catch(()=>{});
   }catch{
    load.disabled=false;load.textContent='Előnézet újrapróbálása';showError();
   }finally{card.removeAttribute('aria-busy');}
  }
  card.append(load);
  if(preview)void attach(false);
 }
 const caption=el('figcaption');
 caption.append(el('span','',a.kind==='image'?'Elkészült kép':a.kind==='video'?'Elkészült videó':'Elkészült hang'),
  button('Megnyitás ↗',()=>call('open_artifact',{id:a.id,requestProject:a.project||project}),'media-open'));
 card.append(media,caption);
 return card;
}
let guardianTimer=null,guardianCloseTimer=null;
function openAssistant(pin=false){clearTimeout(guardianCloseTimer);assistantOpen=true;assistantPinned=assistantPinned||pin;$('commandApp').hidden=false;$('commandApp').classList.add('assistant-overlay');$('guardianTrigger').classList.add('awake');$('guardianTrigger').setAttribute('aria-expanded','true');if(typeof renderCanvas==='function')renderCanvas();pollCommand();}
function closeAssistant(){commandWorkspace=null;updateAttachment();clearTimeout(guardianTimer);clearTimeout(guardianCloseTimer);assistantOpen=false;assistantPinned=false;$('commandApp').classList.remove('assistant-overlay');$('commandApp').hidden=currentApp!=='home';$('guardianTrigger').classList.remove('awake');$('guardianTrigger').setAttribute('aria-expanded','false');if(typeof renderCanvas==='function')renderCanvas();}
function scheduleAssistantClose(){clearTimeout(guardianCloseTimer);guardianCloseTimer=setTimeout(()=>{if(!assistantPinned&&!$('commandApp').matches(':hover')&&!$('guardianTrigger').matches(':hover')&&!$('commandApp').contains(document.activeElement))closeAssistant();},500);}
$('guardianTrigger').addEventListener('pointerenter',()=>{clearTimeout(guardianTimer);guardianTimer=setTimeout(()=>openAssistant(),220);});$('guardianTrigger').addEventListener('pointerleave',()=>{clearTimeout(guardianTimer);scheduleAssistantClose();});$('guardianTrigger').onclick=()=>{if(assistantOpen&&assistantPinned)closeAssistant();else{openAssistant(true);$('commandInput').focus();}};$('commandApp').addEventListener('pointerenter',()=>clearTimeout(guardianCloseTimer));$('commandApp').addEventListener('pointerleave',scheduleAssistantClose);$('assistantClose').onclick=closeAssistant;document.addEventListener('keydown',e=>{if(e.key==='Escape'&&assistantOpen&&!$('modal').open)closeAssistant();});

function updateChatClocks(){for(const clock of document.querySelectorAll('.chat-clock')){const active=['queued','running','queued_apply','applying'].includes(clock.dataset.status);const start=Number(clock.dataset.started||clock.dataset.created),end=Number(clock.dataset.finished)||(active?Date.now()/1000:start);if(!Number.isFinite(start)||!start||!clock.dataset.status)continue;const seconds=Math.max(0,Math.floor(end-start));clock.textContent=(clock.dataset.status==='queued'?'Várakozás':active?'Dolgozik':'Időtartam')+' · '+(clock.dataset.format==='agent'?formatAgentDuration(seconds):Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0'));}}setInterval(updateChatClocks,1000);
