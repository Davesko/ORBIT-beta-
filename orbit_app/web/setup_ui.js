/* The first start, and a word when no model is there yet to answer. */
async function setupOp(op,args){return (await call('project_app',{op,args:args||{}})).result;}
function setupStep(n,total,title,body,next){const box=el('div','setup-step');box.append(el('small','setup-count',n+' / '+total),body);if(next)box.append(next);showModal(title,box);}
function setupWelcome(st){const body=el('div');body.append(el('p','','Az ORBIT a saját gépeden fut: beszélgetés, fájlok, email és háttérmunka egy helyen. Amit megtud rólad, itt marad, és minél többet használod, annál jobban ismer.'),field('Hogyan szólítsalak?','setupName','input',''));
 setupStep(1,3,'Üdv az ORBIT-ban',body,button('Tovább',async()=>{const name=$('setupName').value;await setupOp('setup_finish',{name});setupModel(await setupOp('setup_status'));}));$('setupName').focus();}
function setupModel(st){const body=el('div'),m=st.machine;body.append(el('p','','A géped: '+m.chip+', '+m.ram_gb+' GB memória, '+m.disk_free_gb+' GB szabad hely.'));
 const finish=button(st.models?'Tovább':'Később',async()=>setupDone());
 if(!st.ollama){const found=el('section','locator');body.append(found);locatorRefresh(found);body.append(el('p','','A helyi AI-hoz kell az ingyenes Ollama. Ha már telepítve van, a fenti gombbal indítsd el; ha nincs, töltsd le, majd nyomd meg az Újra gombot.'),button('Ollama letöltése',()=>setupOp('finder_open',{target:'ollama'}),'primary'),button('Újra',async()=>setupModel(await setupOp('setup_status')),'secondary'));}
 else if(st.models)body.append(el('p','','Van már helyi modelled, indulhatsz.'));
 if(st.ollama&&!st.models){const found=el('section','locator');body.append(el('p','','Van már letöltött modelled? Megkeresem a gépen, és bekötöm, így nem kell újra letölteni.'),found);locatorRefresh(found);}
 else{const list=el('div','finder-grid');list.append(el('p','hint','Keresem a géphez illő modelleket…'));body.append(el('p','','Válassz egy modellt, a letöltés a háttérben fut. A kisebb gyorsabban válaszol.'),list);
  finderState={pulling:null};setupOp('finder_recommend').then(r=>{list.replaceChildren();r.items.slice(0,3).forEach(i=>list.append(remoteCard(i)));if(!r.items.length)list.append(el('p','hint','Most nem sikerült ajánlást kérni; a Modellek oldalon később választhatsz.'));}).catch(()=>{list.replaceChildren(el('p','hint','Nincs internetkapcsolat; a Modellek oldalon később választhatsz.'));});}
 setupStep(2,3,'Helyi AI-modell',body,finish);}
function setupDone(){const body=el('div');body.append(el('p','','Így kezdheted:'));const ul=el('ul','setup-list');for(const t of ['Írd a fő chatbe: „Építs egy snake játékot”. A játék megnyílik a beszélgetés mellett.','Az Email menüben kösd össze a fiókodat.','A Memória oldalon látod, mit tanult rólad.','A Kapcsolatok oldalon felhős modelleket is hozzáadhatsz, ha szeretnél.'])ul.append(el('li','',t));body.append(ul);
 setupStep(3,3,'Készen vagy',body,button('Kezdés',async()=>{$('modal').close();switchApp('home');$('commandInput').focus();},'primary'));}
async function setupCheck(){let st;try{st=await setupOp('setup_status');}catch(e){return;}
 const missing=!st.models&&!st.cloud;let note=$('noModelNote');
 if(missing&&!note){note=el('div','no-model-note');note.id='noModelNote';note.append(el('span','','Még nincs modell, ami válaszolna.'),button('Modell választása',async()=>switchApp('finder'),'secondary'));$('commandLive').before(note);}
 if(!missing&&note)note.remove();
 if(!st.done&&!$('modal').open)setupWelcome(st);}
setupCheck();setInterval(()=>{if(!document.hidden&&currentApp==='home')setupCheck();},30000);
