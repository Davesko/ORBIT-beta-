/* Modellek: what runs well on this machine, one click to download and use. */
let finderState=null,finderResults=null,finderTimer=null,finderRecommended=null,finderCategory='chat';
let finderVariants={},finderQuery='',finderSearchTimer=null,finderRequest=0,finderLoading=false,finderRecommendation=null;
async function finderOp(op,args){return (await call('project_app',{op,args:args||{}})).result;}
function finderBadge(f){const b=el('span','fit-badge fit-'+f.level,f.label);b.title='Kb. '+f.need_gb+' GB memóriát igényel';return b;}
function finderSpeed(f,measured){if(measured)return 'mért sebesség: '+measured.tokens_per_second+' token/mp';return f.speed?'becsült sebesség: ~'+f.speed+' token/mp':'';}
// The 15 s refresh redraws the page only when something changed: an identical redraw collapsed opened variant lists and
// made the page shorter, so the scroll position jumped back to the top while the owner was scrolling (11 Nov).
async function loadFinder(){const next=await finderOp('finder_status'),changed=JSON.stringify(next)!==JSON.stringify(finderState);finderState=next;if(changed)renderFinder();
 clearTimeout(finderTimer);if(currentApp==='finder')finderTimer=setTimeout(()=>act(loadFinder),finderState.pulling?2500:15000);}
function useModel(name){localStorage.setItem('orbitPersonalModel',name);$('commandModel').dataset.models='';toast('A fő chat ezt használja: '+name);switchApp('home');renderCommand();}
function installedCard(m){const card=el('div','finder-card'),head=el('div','finder-card-head');head.append(el('strong','',m.name),finderBadge(m.fit));card.append(head,el('small','',[m.fit.size_gb+' GB',m.storage,finderSpeed(m.fit,m.measured)].filter(Boolean).join(' · ')));
 const row=el('div','finder-actions');row.append(button('Használat a fő chatben',async()=>useModel(m.name),'secondary'),button('Sebességmérés',async()=>{await finderOp('finder_benchmark',{name:m.name});toast('A mérés elindult; pár perc múlva itt látod az eredményt.');},'secondary'),button('Törlés',async()=>finderRemove(m),'secondary'));card.append(row);return card;}
function finderRemove(m){const body=el('div');body.append(el('p','','A(z) '+m.name+' lekerül a gépről, és '+m.fit.size_gb+' GB hely szabadul fel. Később újra letölthető.'),button('Törlés',async()=>{toast((await finderOp('finder_delete',{name:m.name})).message);$('modal').close();$('commandModel').dataset.models='';await loadFinder();},'pm-danger'));showModal('Modell törlése',body);}
function variantRow(v){const row=el('div','finder-variant');row.append(el('span','finder-quant',v.quant),el('small','',v.fit.size_gb+' GB'),finderBadge(v.fit),el('small','',finderSpeed(v.fit)));
 const pull=button('Letöltés',async()=>{await finderOp('finder_pull',{name:v.name,size:v.size});toast('A letöltés elindult. Kész után megjelenik a modellek között.');await loadFinder();},'secondary');pull.disabled=v.fit.level==='no'||!!finderState?.pulling;row.append(pull);return row;}
function remoteCard(item){const card=el('div','finder-card'),head=el('div','finder-card-head');head.append(el('strong','',item.repo.split('/').pop().replace(/-GGUF$/i,'')));if(item.best)head.append(finderBadge(item.best.fit));
 card.append(head,el('small','',item.repo+' · '+item.downloads.toLocaleString('hu-HU')+' letöltés'));
 const box=el('div','finder-variants');card.append(box);
 if(item.best)box.append(variantRow(item.best));
 const showVariants=v=>{box.replaceChildren();if(!v.variants.length)box.append(el('p','hint','Nincs letölthető változat.'));v.variants.forEach(x=>box.append(variantRow(x)));};
 if(finderVariants[item.repo]){showVariants(finderVariants[item.repo]);return card;}
 const more=button(item.best?'További változatok':'Változatok és méretek',async()=>{const v=await finderOp('finder_variants',{repo:item.repo});finderVariants[item.repo]=v;showVariants(v);more.remove();},'secondary');card.append(more);return card;}
function generationCard(m,installed=false){
 const card=el('div','finder-card'),head=el('div','finder-card-head');
 head.append(el('strong','',m.name));
 if(m.ready)head.append(el('span','fit-badge fit-good','Telepítve'));
 card.append(head,el('small','',m.purpose+' · '+m.gb+' GB · '+m.engine));
 if(installed)return card;
 if(m.ready)return card;
 if(m.download_gb!==null&&m.download_gb<m.gb)card.append(el('small','','Hátralévő letöltés · '+m.download_gb+' GB'));
 if(!m.path)card.append(el('small','','Csatlakoztasd a külső modelltárat a letöltéshez.'));
 const download=button('Letöltés',async()=>{await finderOp('finder_generation_pull',{id:m.id});await loadFinder();},'secondary');
 download.disabled=!m.path||!!finderState.pulling;card.append(download);
 return card;
}
async function searchFinder(){
 clearTimeout(finderSearchTimer);
 const request=++finderRequest,query=finderQuery,category=finderCategory;
 finderLoading=true;renderFinder();
 try{
  const result=await finderOp('finder_search',{query,category});
  if(request===finderRequest)finderResults=result.items;
 }catch(error){
  if(request===finderRequest)throw error;
 }finally{
  if(request===finderRequest){finderLoading=false;renderFinder();}
 }
}
function renderFinder(){const pane=$('finderApp'),d=finderState;if(!d)return;const typing=document.activeElement?.id==='finderSearch',caret=typing?document.activeElement.selectionStart:null;const top=pane.scrollTop;pane.style.minHeight=pane.scrollHeight+'px';pane.replaceChildren();const m=d.machine;
 const head=el('div','tool-head'),title=el('div');title.append(el('h1','','Modellek'),el('p','hint','Telepített modellek és letölthető helyi modellek.'));head.append(title,button('Modelltár beállításai',()=>showModelHub(),'secondary'));pane.append(head);
 const chips=el('div','finder-machine');for(const t of [m.chip,m.ram_gb+' GB memória',m.disk_free_gb+' GB szabad · '+m.disk])chips.append(el('span','',t));pane.append(chips);const found=el('section','locator');pane.append(found);if(window.locatorCache)locatorRender(found,window.locatorCache);locatorOp('locator_scan').then(r=>{const same=JSON.stringify(r)===JSON.stringify(window.locatorCache);window.locatorCache=r;if(found.isConnected&&!same){const t=pane.scrollTop;locatorRender(found,r);pane.scrollTop=t;}}).catch(()=>{});
 if(d.pulling){const n=el('div','finder-note');n.append(el('strong','','Letöltés: '+d.pulling.name),el('small','',d.pulling.label));const bar=el('div','ap-bar'),fill=el('i');fill.style.width=(d.pulling.percent||0)+'%';bar.append(fill);n.append(bar,button('Leállítás',async()=>{await call('job_cancel',{id:d.pulling.job,requestProject:'universe'});await loadFinder();},'secondary'));pane.append(n);}
 if(d.failed&&!d.pulling)pane.append(el('p','ap-etsy-error','Nem sikerült letölteni: '+d.failed.name+'. '+d.failed.error));
 const generation=d.generation||[],installedGeneration=generation.filter(m=>m.ready);
 const installedCount=d.installed.length+installedGeneration.length;
 pane.append(el('h2','finder-title','Telepítve · '+installedCount));
 const mine=el('div','finder-grid');
 if(!installedCount)mine.append(el('p','hint','Még nincs telepített modell. Válassz egyet a keresőből.'));
 d.installed.forEach(x=>mine.append(installedCard(x)));
 installedGeneration.forEach(x=>mine.append(generationCard(x,true)));pane.append(mine);
 pane.append(el('h2','finder-title','Keresés'));
 const mode=el('div','finder-search-actions');
 for(const [key,label] of [['chat','Nyelvi modellek'],['video','Videómodellek'],['image','Képmodellek']]){
  const b=button(label,()=>{if(finderCategory===key)return;clearTimeout(finderSearchTimer);finderRequest++;finderLoading=false;finderCategory=key;finderQuery='';finderResults=null;renderFinder();},'secondary');
  b.setAttribute('aria-pressed',String(finderCategory===key));mode.append(b);
 }
 pane.append(mode);
 const search=el('input','tool-search');search.id='finderSearch';search.type='search';
 search.placeholder={chat:'Keresés, például llama, qwen, gemma…',video:'Keresés, például Wan 2.2, Mochi, képből videó…',image:'Keresés, például SDXL…'}[finderCategory];
 search.value=finderQuery;search.setAttribute('aria-label','Modell keresése');
 search.oninput=()=>{
  finderQuery=search.value;finderRequest++;clearTimeout(finderSearchTimer);
  if(finderQuery.trim())finderSearchTimer=setTimeout(()=>act(searchFinder),400);
  else{finderResults=null;finderLoading=false;renderFinder();}
 };
 search.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();act(searchFinder);}};
 pane.append(search);
 const searchActions=el('div','finder-search-actions');
 searchActions.append(button('Keresés',searchFinder,'secondary'));
 if(finderCategory==='chat'){
  searchActions.append(button('A gépemhez illő modellek keresése',async()=>{
   clearTimeout(finderSearchTimer);const request=++finderRequest;
   finderQuery='';finderResults=null;finderLoading=true;renderFinder();
   try{finderRecommended=(await finderOp('finder_recommend',{refresh:true})).items;}
   finally{if(request===finderRequest){finderLoading=false;renderFinder();}}
  },'primary'));
 }
 pane.append(searchActions);
 if(finderCategory==='chat'){
  pane.append(el('p','hint','A kompatibilitás becslés. A sebességet telepítés után megmérheted.'));
  if(!d.ollama){const n=el('div','finder-note');n.append(el('p','','Az Ollama jelenleg nem fut. A nyelvi modellek telepítéséhez indítsd el.'),button('Ollama letöltése',()=>finderOp('finder_open',{target:'ollama'}),'primary'));pane.append(n);}
 }else pane.append(el('p','hint','Ellenőrzött, helyben letölthető csomagok. A generáláshoz helyi ComfyUI és a modellhez tartozó munkafolyamat szükséges.'));
 const list=el('div','finder-grid');
 if(finderLoading)list.append(el('p','hint','Keresés folyamatban…'));
 else if(finderCategory!=='chat'){
  const matches=finderResults&&new Set(finderResults.map(m=>m.id));
  const models=generation.filter(m=>m.category===finderCategory&&(matches?matches.has(m.id):!m.ready)).sort((a,b)=>a.gb-b.gb);
  if(!models.length)list.append(el('p','hint',matches?'Nincs találat.':'Minden elérhető csomag telepítve van.'));
  for(const m of models)list.append(generationCard(m));
 }else if(finderResults){if(!finderResults.length)list.append(el('p','hint','Nincs találat.'));finderResults.forEach(i=>list.append(remoteCard(i)));}
 else{pane.append(el('h2','finder-title','Ajánlott a gépedhez'));
  if(!finderRecommended){list.append(el('p','hint','Keresem a géphez illő modelleket…'));
   if(!finderRecommendation)finderRecommendation=finderOp('finder_recommend').then(r=>{finderRecommended=r.items;}).catch(()=>{finderRecommended=[];}).finally(()=>{finderRecommendation=null;if(currentApp==='finder')renderFinder();});}
  else if(!finderRecommended.length)list.append(el('p','hint','Most nem sikerült ajánlást kérni. Próbáld a keresést.'));
  else finderRecommended.forEach(i=>list.append(remoteCard(i)));}
 pane.append(list);pane.style.minHeight='';pane.scrollTop=top;
 if(typing){search.focus({preventScroll:true});search.setSelectionRange(caret,caret);}}
(()=>{const base=switchApp;switchApp=function(view){base(view);const on=view==='finder';$('finderApp').hidden=!on;$('navModels').classList.toggle('active',on);$('navModels').setAttribute('aria-pressed',String(on));if(on)act(loadFinder);};$('navModels').onclick=()=>switchApp('finder');})();
