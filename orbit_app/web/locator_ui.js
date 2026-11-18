/* "Do I already have models?" — the running Ollama, Ollama model folders and GGUF files found on this Mac. */
async function locatorOp(op,args){return (await call('project_app',{op,args:args||{}})).result;}
async function locatorPick(host){
 const r=await call('models_pick_folder',{});if(r.cancelled)return;const res=r.result||r;toast(res.message||'Kész.');
 if(res.kind==='gguf')locatorRender(host,null,res.files);else locatorRefresh(host);}
function locatorFile(f){const row=el('div','locator-row');row.append(el('span','',f.name),el('small','',f.gb+' GB · '+f.path));
 row.append(button('Importálás',async()=>{const r=await locatorOp('locator_import',{path:f.path,name:f.name});toast(r.message);},'secondary'));return row;}
function locatorRender(host,d,files){
 host.replaceChildren();host.append(el('h2','finder-title','Meglévő modellek ezen a gépen'));
 if(d){
  const st=el('div','locator-row');
  if(d.ollama_running)st.append(el('span','','✓ Az Ollama fut · '+d.running_models.length+' modell az ORBIT-ban is elérhető'));
  else if(d.ollama_installed){st.append(el('span','','Az Ollama telepítve van, de nem fut.'));st.append(button('Ollama indítása',async()=>{toast((await locatorOp('locator_start')).message);setTimeout(()=>locatorRefresh(host),4000);},'primary'));}
  else{st.append(el('span','','Az Ollama nincs telepítve. A helyi modellek futtatásához ez az ingyenes app kell.'));st.append(button('Ollama letöltése',()=>call('project_app',{op:'finder_open',args:{target:'ollama'}}),'primary'));}
  host.append(st);
  for(const s of d.stores){const row=el('div','locator-row');row.append(el('span','',(s.default?'Ollama saját mappája':'Modellmappa')+' · '+s.models.length+' modell'),el('small','',s.path+' — '+s.models.slice(0,4).join(', ')+(s.models.length>4?'…':'')));
   if(s.connected)row.append(el('span','fit-badge fit-good','bekötve'));else if(!s.default)row.append(button('Bekötés',async()=>{const r=await locatorOp('locator_use',{path:s.path});toast(r.message);locatorRefresh(host);},'secondary'));host.append(row);}
  files=d.gguf;
 }
 if(files&&files.length){host.append(el('p','hint','GGUF modellfájlok (pl. LM Studio). Importálással az Ollamába kerülnek, ami másolatot készít.'));for(const f of files.slice(0,12))host.append(locatorFile(f));}
 if(d&&!d.stores.length&&!(files||[]).length&&!d.running_models.length)host.append(el('p','hint','Nem találtam modellt a szokásos helyeken. Ha máshol van, válaszd ki a mappáját.'));
 host.append(button('Mappa kiválasztása…',()=>act(()=>locatorPick(host)),'secondary'));}
async function locatorRefresh(host){host.replaceChildren(el('p','hint','Modellek keresése a gépen…'));try{locatorRender(host,await locatorOp('locator_scan'));}catch(e){host.replaceChildren(el('p','hint','A keresés nem sikerült: '+e.message));}}
