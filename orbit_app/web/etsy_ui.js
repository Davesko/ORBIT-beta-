// Etsy: a kész grafikák feltöltése a tulajdonos boltjába. Piszkozatként ingyenes; élesíteni csak ő kapcsolhatja be.
let etsyData={},etsyAt={};
async function etsyOp(op,args){return (await call('project_app',{op,args:args||{}})).result;}
function loadEtsy(idea,force){if(!idea||(!force&&Date.now()-(etsyAt[idea]||0)<15000))return Promise.resolve();etsyAt[idea]=Date.now();
 return etsyOp('etsy_status',{idea}).then(d=>{if(JSON.stringify(etsyData[idea])!==JSON.stringify(d)){etsyData[idea]=d;renderVenture();}}).catch(()=>{});}
function etsyCopy(text){const b=el('button','ap-chip','Másolás');b.onclick=()=>{navigator.clipboard?.writeText(text);toast('A vágólapon.');};return b;}
function etsySetup(f){const d=etsyData[f.idea_id]||{},body=el('div','ap-etsy-setup');
 body.append(el('p','','Egyszer kell beállítani, utána az ORBIT maga tölti fel a kész grafikákat a boltodba. A jelszavad az Etsynél marad, az ORBIT nem látja.'));
 const step=(n,text)=>{const s=el('div','ap-etsy-step');s.append(el('strong','',n+'. '+text));body.append(s);return s;};
 const one=step(1,'Hozd létre az ORBIT címét');one.append(el('p','hint','Egy rövid, nyilvános bemutató oldal a Cloudflare-fiókodban. Ez lesz az Etsy-alkalmazás weboldala és visszatérési címe is, ezért nem kell külön weboldal.'));const line=el('div','ap-etsy-line');one.append(line);
 const showUrl=url=>{line.replaceChildren(el('code','ap-url',url),etsyCopy(url));};
 if(d.callback)showUrl(d.callback);else line.append(button('Cím létrehozása',async()=>{const r=await etsyOp('etsy_callback');showUrl(r.callback);await loadEtsy(f.idea_id,true);},'secondary'));
 const two=step(2,'Hozz létre egy Etsy-alkalmazást');two.append(el('p','hint','A Website URL és a Callback URL mezőbe is ezt a címet másold. Kell hozzá egy megnyitott Etsy-bolt, és az alkalmazást személyes használatra kérd; a jóváhagyás napokig, néha hetekig is tarthat.'),button('Etsy fejlesztői oldal megnyitása',()=>etsyOp('etsy_open',{target:'apps'}),'secondary'));
 const three=step(3,'Add meg az alkalmazás kulcsát');three.append(field('Keystring','etsyKeystring','input',''),field('Shared secret','etsySecret','input',''));
 three.append(button(d.configured?'Kulcs cseréje':'Kulcs mentése',async()=>{await call('connections_save',{settings:{provider:'etsy',enabled:true,key:$('etsyKeystring').value.trim()+':'+$('etsySecret').value.trim()}});$('etsyKeystring').value='';$('etsySecret').value='';toast('A kulcs elmentve.');await loadEtsy(f.idea_id,true);},'secondary'));
 const four=step(4,'Lépj be az Etsybe');four.append(button('Belépés az Etsybe',async()=>{const r=await etsyOp('etsy_connect');toast(r.message);$('modal').close();await loadEtsy(f.idea_id,true);},'primary'));
 showModal('Etsy csatlakoztatása',body);}
function etsyPrice(f){const d=etsyData[f.idea_id],cur=d.shop?.currency||'',form=el('div');
 form.append(el('p','','Minden lap ezen az áron kerül fel. Üresen hagyva az Autopilóta javaslata marad, ha az a bolt pénznemében van. A már feltöltött listák ára nem változik.'),field('Ár ('+cur+')','etsyPriceInput','input',d.settings.price??''));
 form.append(button('Mentés',async()=>{await etsyOp('etsy_settings',{idea:f.idea_id,price:$('etsyPriceInput').value});$('modal').close();await loadEtsy(f.idea_id,true);}));showModal('Etsy-ár',form);}
function etsyLive(f){const d=etsyData[f.idea_id],count=d.drafts+d.left,form=el('div');
 form.append(el('p','','Bekapcsolva a piszkozatok maguktól élesednek, naponta legfeljebb '+d.daily_live+'. Ezután bárki megveheti őket a boltodban.'),
  el('p','','Minden élő lista az Etsy közzétételi díjával jár ('+d.fee+', négy hónapra), ezt az Etsy a boltod számlájára terheli. A megújítás ki van kapcsolva, magától nem számol fel újra.'),
  el('p','hint','Az Etsy 2026 októberében szigorította a képszabályokat (legalább egy valódi, nem módosított fotó). Hogy ez digitális termékre hogyan vonatkozik, nem tisztázott; élesítés előtt érdemes megnézni egy piszkozatot.'));
 const row=el('div','ap-etsy-line');row.append(button('Élesítés bekapcsolása',async()=>{await etsyOp('etsy_settings',{idea:f.idea_id,live:true});$('modal').close();await loadEtsy(f.idea_id,true);},'primary'),button('Mégse',async()=>$('modal').close(),'secondary'));form.append(row);showModal(count+' lap élesítése',form);}
function etsyBlock(f){loadEtsy(f.idea_id);const d=etsyData[f.idea_id];if(!d?.applicable)return null;
 const box=el('div','ap-etsy');box.append(el('h3','','🛍 Etsy-feltöltés'));
 if(!d.connected){box.append(el('p','hint',d.left+' lap készen áll. Csatlakozás után az ORBIT maga tölti fel őket piszkozatként, ez ingyenes.'));
  if(d.login==='error'&&d.login_error)box.append(el('p','ap-etsy-error',d.login_error));
  if(d.login==='waiting')box.append(el('p','hint','Várom az Etsy-belépést a böngészőből…'));
  box.append(button('Etsy csatlakoztatása',async()=>etsySetup(f),'primary'));return box;}
 const parts=[d.live+' élő',d.drafts+' piszkozat',d.left+' sorra kerül'];if(d.waiting)parts.push(d.waiting+' rajzra vár');
 box.append(el('p','','Bolt: '+(d.shop?.name||'')+' ('+(d.shop?.currency||'')+') · '+parts.join(' · ')));
 const auto=el('label','settings-switch'),autoBox=el('input');autoBox.type='checkbox';autoBox.checked=d.settings.auto;autoBox.onchange=()=>act(async()=>{await etsyOp('etsy_settings',{idea:f.idea_id,auto:autoBox.checked});await loadEtsy(f.idea_id,true);});auto.append(autoBox,el('span','','A kész grafikákat magától feltölti piszkozatként'));box.append(auto);
 box.append(el('p','hint',d.settings.live?'Élesítés bekapcsolva: naponta legfeljebb '+d.daily_live+' lista megy élőbe, listánként '+d.fee+' díjjal.':'A piszkozatokat csak te látod. Élőbe akkor mennek, ha bekapcsolod.'));
 const tools=el('div','ap-etsy-line');
 tools.append(d.settings.live?button('Élesítés kikapcsolása',async()=>{await etsyOp('etsy_settings',{idea:f.idea_id,live:false});await loadEtsy(f.idea_id,true);},'secondary'):button('Élesítés…',async()=>etsyLive(f),'secondary'),
  button('Ár…',async()=>etsyPrice(f),'secondary'),button('Piszkozatok az Etsyn',()=>etsyOp('etsy_open',{target:'drafts'}),'secondary'));
 if(d.rows.some(r=>r.stuck))tools.append(button('Sikertelenek újra',async()=>{await etsyOp('etsy_retry',{idea:f.idea_id});await loadEtsy(f.idea_id,true);},'secondary'));
 tools.append(button('Kilépés az Etsyből',async()=>{toast((await etsyOp('etsy_disconnect')).message);await loadEtsy(f.idea_id,true);},'secondary'));box.append(tools);
 const failed=d.rows.filter(r=>r.error);if(failed.length)box.append(el('p','ap-etsy-error',failed[0].title+': '+failed[0].error));
 const list=el('details','ap-etsy-list');list.append(el('summary','','Lapok állapota · '+d.total));
 for(const r of d.rows){const row=el('div','ap-etsy-row');row.append(el('span','',r.title),el('small','',r.label));if(r.listing){const o=el('button','ap-chip','Megnyitás');o.onclick=()=>act(()=>etsyOp('etsy_open',{target:'listing:'+r.listing}));row.append(o);}list.append(row);}
 box.append(list,el('small','ap-etsy-note','Az „Etsy” az Etsy, Inc. védjegye. Ez az alkalmazás az Etsy API-t használja, de az Etsy nem hagyta jóvá és nem tanúsította.'));return box;}
