/* Elérés: the views of every account connected to ORBIT, filterable by account. The old per-project YouTube analysis
   stays as the second tab. A function scope: a function declared in a bare block would replace the app's global. */
(()=>{
 let R=null,tab='all',filter='',busy=false,sig='';
 const op=async(name,args={})=>(await call('project_app',{op:name,args})).result;
 const ICON={youtube:'▶',instagram:'◎',facebook:'ƒ',tiktok:'♪'};
 const n=v=>typeof v==='number'&&Number.isFinite(v)?new Intl.NumberFormat('hu-HU').format(v):'—';
 const day=t=>t?new Date(t).toLocaleDateString('hu-HU',{month:'short',day:'numeric'}):'';
 const ago=t=>{if(!t)return 'még nincs mérés';const m=Math.round((Date.now()/1000-t)/60);return m<2?'most':m<90?m+' perce':Math.round(m/60)+' órája';};
 const app=()=>$('growthApp');
 function mount(){
  if($('reachTabs'))return;
  const tabs=el('div','reach-tabs');tabs.id='reachTabs';const body=el('div');body.id='reachBody';
  app().insertBefore(tabs,$('growthTask'));app().insertBefore(body,$('growthTask'));
 }
 async function load(force){
  if(currentApp!=='growth'||busy||tab!=='all')return;
  busy=true;
  try{const d=await op('publish_reach',{account:filter});const s=JSON.stringify(d);if(s!==sig||force){sig=s;R=d;render();}}
  catch(e){R=R||{error:e.message};render();}
  finally{busy=false;}
 }
 function render(){
  mount();
  const tabs=$('reachTabs');tabs.replaceChildren();
  for(const [id,label] of [['all','Megtekintések · minden fiók'],['project','YouTube-elemzés · projekt']]){
   const b=el('button',tab===id?'primary':'secondary',label);b.onclick=()=>{tab=id;sig='';render();if(id==='all')load(true);};tabs.append(b);}
  app().classList.toggle('reach-on',tab==='all');
  const body=$('reachBody');body.replaceChildren();body.hidden=tab!=='all';
  if(tab!=='all')return;
  if(!R){body.append(el('p','hint','Betöltés…'));return;}
  if(R.error){body.append(el('p','error-text',R.error));return;}
  if(!R.accounts.length){body.append(el('p','growth-empty','Még nincs csatlakoztatott fiók. A Publikálás → Fiókok lapon add hozzá a YouTube-, Instagram-, Facebook- és TikTok-fiókjaidat.'));return;}
  const chips=el('div','reach-filter');
  const all=el('button','reach-chip'+(!filter?' on':''),'Minden fiók · '+n(R.accounts.reduce((x,a)=>x+(a.views||0),0)));all.onclick=()=>{filter='';sig='';load(true);};chips.append(all);
  for(const a of R.accounts){const b=el('button','reach-chip'+(filter===a.id?' on':''),(ICON[a.platform]||'')+' '+a.label+' · '+n(a.views));b.onclick=()=>{filter=a.id;sig='';load(true);};chips.append(b);}
  body.append(chips);
  const head=el('div','growth-section-head');
  head.append(el('p','hint','Frissítve: '+ago(R.fetched)+(R.running?' · mérés folyamatban…':'')+' · automatikusan 3 óránként'),button('↻ Mérés most',()=>act(async()=>{const r=await op('publish_reach_refresh',{account:filter});toast(r.message);setTimeout(()=>load(true),1500);}),'secondary'));
  body.append(head);
  const t=R.totals,m=el('div','reach-metrics');
  for(const [l,v,h] of [['Megtekintés összesen',t.views],['Növekedés · 28 nap',t.gain28,'gyűlik'],['Videók',t.videos],['Követők / feliratkozók',t.subscribers],['Kedvelés',t.likes],['Komment',t.comments]]){
   const c=el('div','reach-metric');c.append(el('small','',l),el('strong','',v===null||v===undefined?(h||'—'):n(v)));m.append(c);}
  body.append(m);
  const max=Math.max(1,...R.series.map(x=>x.views||0));
  const chart=el('div','reach-chart');chart.setAttribute('role','img');chart.setAttribute('aria-label','Napi megtekintés-növekedés az elmúlt 28 napban');
  for(const x of R.series){const i=el('i',x.views===null?'none':'');i.style.height=Math.max(2,100*(x.views||0)/max)+'%';i.title=day(x.day)+': '+(x.views===null?'nincs mérés':n(x.views));chart.append(i);}
  body.append(chart,el('p','hint',R.since?'A napi bontás az ORBIT saját mérései alapján épül ('+day(R.since)+' óta); minden napi mérés a fiók összes megtekintésének változása.':'A napi bontás az első két mérés után jelenik meg.'));
  if(!filter){
   const acc=el('div','reach-acc');
   for(const a of R.accounts){const d=el('div');d.append(el('b','',(ICON[a.platform]||'')+' '+a.label),el('span','',n(a.views)+' megtekintés · '+n(a.videos)+' videó · '+n(a.subscribers)+' követő'));
    d.append(el('br'),el('small',a.error?'error-text':'hint',a.error||(a.status!=='connected'?'A fiók nincs csatlakoztatva':'Mérve: '+ago(a.fetched))));acc.append(d);}
   body.append(acc);}
  else{const a=R.accounts.find(x=>x.id===filter);if(a?.error)body.append(el('p','error-text',a.error));}
  const table=el('div','reach-table'),hd=el('div','reach-row head');for(const x of ['Videó','Fiók','Megtekintés','Kedvelés','Komment','Dátum'])hd.append(el('span','',x));table.append(hd);
  for(const i of R.items){const r=el('div','reach-row'),title=el('span','t');
   const link=i.url?button(i.title||i.id,()=>op('publish_open_url',{url:i.url}),'text-button'):el('span','',i.title||i.id);title.append(link);if(i.orbit)title.append(el('span','reach-orbit','ORBIT'));
   r.append(title,el('span','',(ICON[i.platform]||'')+' '+i.account_label),el('span','',n(i.views)),el('span','',n(i.likes)),el('span','',n(i.comments)),el('span','',day(i.published)));table.append(r);}
  body.append(table);
  if(!R.items.length)body.append(el('p','growth-empty','Még nincs lekért videó. Nyomd meg a „Mérés most” gombot.'));
 }
 $('navGrowth').addEventListener('click',()=>setTimeout(()=>{mount();render();load(true);},0));
 setInterval(()=>load(false),R&&R.running?4000:10000);
})();
