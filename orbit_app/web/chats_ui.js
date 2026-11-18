/* Chats, search and the menu's folders. Each chat keeps its own history; the Earlier one holds what came before chats. */
let chatList=[];
async function chatOp(op,args){return (await call('project_app',{op,args:args||{}})).result;}
function openChat(id,keep){const changed=id!==chatSession;chatSession=id;try{localStorage.setItem('orbitChat',id);}catch(e){}
 if(changed&&!keep){if(typeof updateAttachment==='function'){if(typeof clearChatAttachments==='function')clearChatAttachments();else{commandImage=null;updateAttachment();}}commandState=null;commandCards.forEach(c=>c.node.remove());commandCards.clear();}
 loadChats();if(changed&&!keep){switchApp('home');pollCommand();}}
async function loadChats(){try{chatList=(await chatOp('chat_list')).chats;renderChats();}catch(e){}}
function chatAgo(t){const m=Math.floor((Date.now()/1000-t)/60);return m<1?'most':m<60?m+' perce':m<1440?Math.floor(m/60)+' órája':Math.floor(m/1440)+' napja';}
let chatListSignature='',chatSwiping=false,revealedChat=null;
function renderChats(){const box=$('railChatList');if(chatSwiping)return;
 const signature=JSON.stringify([chatSession,revealedChat,chatList]);if(signature===chatListSignature)return;chatListSignature=signature;box.replaceChildren();
 if(!chatList.length)box.append(el('small','rail-chat-empty','Még nincs chat.'));
 for(const c of chatList){
  const row=el('div','rail-chat'+(c.id===chatSession?' active':'')),front=el('div','rail-chat-front'),open=el('button','rail-chat-open',c.title);
  row.style?.setProperty('--chat-slide',revealedChat===c.id?'-82px':'0px');
  open.title=c.title+' · '+chatAgo(c.updated);let suppress=false;
  open.onclick=()=>{if(!suppress)openChat(c.id);};
  const more=el('button','rail-chat-more','⋯');more.setAttribute('aria-label','Chat kezelése: '+c.title);more.onclick=()=>chatMenu(c);
  const remove=button('Törlés',()=>act(()=>deleteChat(c)),'rail-chat-delete');remove.setAttribute('aria-label',c.title+' törlése');
  front.append(open,more);row.append(remove,front);box.append(row);
  let drag=null;
  front.onpointerdown=e=>{if(e.button!==0||e.target===more)return;drag={x:e.clientX,y:e.clientY,offset:revealedChat===c.id?-82:0,id:e.pointerId,moving:false};};
  front.onpointermove=e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
   if(!drag.moving){if(Math.abs(dy)>12&&Math.abs(dy)>Math.abs(dx)){drag=null;return;}if(Math.abs(dx)<12)return;drag.moving=true;chatSwiping=true;suppress=true;front.setPointerCapture(e.pointerId);}
   e.preventDefault();row.style.setProperty('--chat-slide',Math.max(-82,Math.min(0,drag.offset+dx))+'px');};
  const finish=e=>{if(!drag)return;const d=drag;drag=null;chatSwiping=false;
   if(d.moving){revealedChat=d.offset+e.clientX-d.x < -45?c.id:null;row.style.setProperty('--chat-slide',revealedChat===c.id?'-82px':'0px');setTimeout(()=>{suppress=false;},150);}else suppress=false;
  };
  front.onpointerup=finish;front.onpointercancel=()=>{drag=null;chatSwiping=false;suppress=false;row.style.setProperty('--chat-slide',revealedChat===c.id?'-82px':'0px');};
 }
 box.append(button('Törölt chatek',()=>act(showArchivedChats),'rail-chat-trash'));
}
async function deleteChat(c){
 if(chatSession===c.id&&($('commandInput').value.trim()||(typeof pendingChatAttachments==='function'&&pendingChatAttachments().length))){toast('Előbb küldd el vagy töröld a megírt üzenetet és a csatolmányokat.',true);return;}
 const result=await chatOp('chat_delete',{id:c.id});revealedChat=null;
 if($('modal').open)$('modal').close();if(chatSession===c.id)openChat('');await loadChats();
 $('chatUndo')?.remove();const notice=el('div','chat-undo');notice.id='chatUndo';notice.setAttribute('role','status');
 notice.append(el('span','','Chat törölve.'),button('Visszavonás',()=>act(async()=>{await chatOp('chat_restore',{id:result.restore_id});notice.remove();await loadChats();}),'secondary'),button('×',()=>notice.remove(),'quiet'));
 document.body.append(notice);setTimeout(()=>notice.remove(),30000);
}
async function showArchivedChats(){const data=await chatOp('chat_archived'),body=el('div');body.append(el('p','hint','A törölt beszélgetések innen visszaállíthatók. Az elkészült fájlok megmaradnak.'));
 for(const c of data.chats)body.append(button('Visszaállítás · '+c.title,()=>act(async()=>{await chatOp('chat_restore',{id:c.id});await loadChats();await showArchivedChats();}),'secondary'));
 if(!data.chats.length)body.append(el('p','','Nincs törölt chat.'));showModal('Törölt chatek',body);
}
function chatMenu(c){const body=el('div');
 if(c.id!=='earlier')body.append(field('Chat neve','chatRename','input',c.title),button('Átnevezés',async()=>{await chatOp('chat_rename',{id:c.id,title:$('chatRename').value});$('modal').close();await loadChats();}));
 body.append(el('p','hint','A törlés visszavonható. Az elkészült fájlok és videók megmaradnak.'),button('Chat törlése',()=>act(()=>deleteChat(c)),'pm-danger'));showModal(c.title,body);
}
const searchKinds={chat:'Chat',project:'Projekt',agent:'Ügynök',room:'Szoba',task:'Feladat',file:'Fájl',email:'Email',memory:'Memória'};
async function openSearchHit(hit){
 $('modal').close();
 if(hit.type==='chat'){openChat(hit.session);await pollCommand();commandCards.get(hit.turn)?.node.scrollIntoView({block:'center'});return;}
 if(hit.type==='email'){switchApp('email');mailOpenId=hit.id;await loadMail();return;}
 if(hit.type==='memory'){switchApp('memory');return;}
 if(hit.project&&hit.project!==project)await changeProject(hit.project);
 if(hit.type==='file'){if(hit.kind==='text'){switchApp('home');await openCanvas(hit.id);}else await call('open_artifact',{id:hit.id,requestProject:hit.project});return;}
 if(hit.type==='task'){automationSelected=hit.id;automationSignature='';taskProjectFilter='';taskStatusFilter='all';taskSearch='';switchApp('automations');await loadAutomations();renderAutomations();return;}
 switchApp('agents');if(typeof setProjectView==='function')setProjectView(false);if(hit.type==='agent'||hit.type==='agent_chat')activateAgent(hit.id);
}
function showChatSearch(){const body=el('div','chat-search'),input=el('input'),list=el('div','chat-search-list');input.id='chatSearchInput';input.placeholder='Chat, projekt, ügynök, fájl, feladat, email…';input.setAttribute('aria-label','Keresés az egész ORBIT-ban');
 let timer,sequence=0;input.oninput=()=>{clearTimeout(timer);const request=++sequence;timer=setTimeout(async()=>{
  list.replaceChildren(el('p','hint','Keresés…'));
  try{const r=await chatOp('search_all',{query:input.value});if(request!==sequence)return;list.replaceChildren();
   if(!r.results.length&&input.value.trim().length>1)list.append(el('p','hint','Nincs találat.'));
   for(const hit of r.results){const b=el('button','chat-search-hit');b.append(el('small','',searchKinds[hit.type]||hit.type),el('strong','',hit.title),el('small','',hit.excerpt));b.onclick=()=>act(()=>openSearchHit(hit));list.append(b);}
  }catch(e){if(request===sequence)list.replaceChildren(el('p','error-text',e.message));}
 },220);};
 body.append(input,el('p','hint','Helyi keresés a beszélgetésekben, projektekben, ügynökökben, szobákban, feladatokban, fájlokban, szinkronizált emailekben és memóriában.'),list);showModal('Keresés az ORBIT-ban',body);input.focus();
}
$('navSearch').onclick=showChatSearch;
$('navNewChat').onclick=()=>{if(typeof resetBriefForNewChat==='function')resetBriefForNewChat();if(typeof clearChatAttachments==='function')clearChatAttachments();openChat('');switchApp('home');pollCommand();$('commandInput').focus();};
// The menu's folders stay as the owner left them.
for(const id of ['railChats','railWork','railTools']){const d=$(id);try{const saved=localStorage.getItem('orbitRail:'+id);if(saved!==null)d.open=saved==='1';}catch(e){}
 d.addEventListener('toggle',()=>{try{localStorage.setItem('orbitRail:'+id,d.open?'1':'0');}catch(e){}});}
loadChats();setInterval(()=>{if(!document.hidden)loadChats();},20000);
