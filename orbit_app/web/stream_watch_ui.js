/* Élő adás figyelő (owner, 14 Nov): the watcher project's own Műhely app. Live channels, the chat curve, the moments
   found at chat peaks and what to do with each. A function scope, so nothing here replaces the app's globals. */
(()=>{
 let W=null,poll=null,focus=null,sig='';
 const op=async(name,args={})=>(await call('project_app',{op:name,args:{project,...args}})).result;
 const on=()=>projectAppView?.app==='watch';
 const card=(title,cls='')=>{const c=el('section','cs-card '+cls);if(title)c.append(el('h3','',title));return c;};
 const clock=t=>t?new Date(t*1000).toLocaleTimeString('hu-HU',{hour:'2-digit',minute:'2-digit'}):'';
 const day=t=>t?new Date(t*1000).toLocaleString('hu-HU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
 const go=page=>{projectAppPage=page;render();$('projectAppView').scrollTop=0;};
 const run=(label,fn,cls='primary')=>button(label,async()=>{const r=await fn();if(r?.message)toast(r.message);await load(true);},cls);
 const STATUS={found:'Megtalálva',fetching:'Letöltés…',ready:'Kivágva',producing:'Short készül',produced:'Short kész',failed:'Nem sikerült'};

 async function load(force){
  try{const d=await op('watch_snapshot',{channel:focus});const s=JSON.stringify(d);if(s===sig&&!force)return schedule();sig=s;W=d;projectAppData=d;}
  catch(e){W={error:e.message};}
  if(!paTyping())render();
  schedule();
 }
 function schedule(){clearTimeout(poll);poll=setTimeout(()=>{if(on()&&currentApp==='agents')load();else schedule();},W?.settings?.enabled?5000:15000);}

 function render(){
  const box=$('projectAppView');if(!box||!on())return;
  const scroll=box.scrollTop;box.replaceChildren();box.classList.add('cs-app','ko-app');
  if(!W){box.append(el('p','hint','Betöltés…'));return;}
  if(W.error){box.append(el('p','pa-note',W.error));return;}
  const s=W.settings,n=W.counts,head=el('div','ko-head'),title=el('div','ko-title');
  title.append(el('h1','','Élő adás figyelő'),el('p','','A figyelt streamerek élő adásainak chatjét olvassa. Ahol a chat a saját szokásos tempójának többszörösére ugrik, ott történt valami: azt a jelenetet vágja ki, az előzményével és a reakcióval együtt.'));
  const meta=el('div','cs-meta');
  meta.append(el('span','cs-chip'+(s.enabled&&!W.paused?' live':''),W.paused?'Minden önműködő szünetel':s.enabled?(n.watching?'● Figyel · '+n.watching+' csatorna':'Bekapcsolva · most senki nem játssza'):'Kikapcsolva'));
  if(s.game)meta.append(el('span','cs-chip','Játék: '+s.game));
  head.append(title,meta);box.append(head);
  const tabs=el('nav','cs-tabs');for(const p of projectAppView.pages){const b=el('button','',p.label);if(p.id==='moments'&&n.ready)b.append(el('em','cs-badge',String(n.ready)));b.setAttribute('aria-selected',String(p.id===projectAppPage));b.onclick=()=>go(p.id);tabs.append(b);}box.append(tabs);
  const page=el('div','cs-page ko-page');box.append(page);
  if(s.enabled&&!W.gate_open)page.append(el('p','cs-banner','A figyelés a megjelenés napján ('+s.not_before+') indul. Addig a játék kategóriájában csak kiszivárgott anyag lehetne, azt nem figyeli. Főpróbához a Beállításokban töröld a játék nevét: akkor bármilyen élő adáson kipróbálható.'));
  ({overview,moments,channels,settings}[projectAppPage]||overview)(page);
  box.scrollTop=scroll;
 }

 function chart(points){
  const NS='http://www.w3.org/2000/svg',w=900,h=150,svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 '+w+' '+h);svg.setAttribute('class','sw-chart');svg.setAttribute('preserveAspectRatio','none');
  const max=Math.max(10,...points.map(p=>p.n)),x=i=>i*(w/Math.max(1,points.length-1)),y=v=>h-6-(v/max)*(h-16);
  const line=document.createElementNS(NS,'path');line.setAttribute('d',points.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(p.n).toFixed(1)).join(' '));line.setAttribute('class','sw-line');
  const area=document.createElementNS(NS,'path');area.setAttribute('d','M0 '+h+' '+points.map((p,i)=>'L'+x(i).toFixed(1)+' '+y(p.n).toFixed(1)).join(' ')+' L'+w+' '+h+' Z');area.setAttribute('class','sw-area');
  svg.append(area,line);
  const t0=points[0]?.t,t1=points[points.length-1]?.t;
  for(const m of W.moments.filter(m=>m.channel===W.focus&&m.at>=t0&&m.at<=t1)){const mark=document.createElementNS(NS,'line'),px=(m.at-t0)/(t1-t0||1)*w;mark.setAttribute('x1',px);mark.setAttribute('x2',px);mark.setAttribute('y1',0);mark.setAttribute('y2',h);mark.setAttribute('class','sw-mark');svg.append(mark);}
  return svg;
 }

 function momentCard(m){
  const c=el('div','sw-moment '+m.status),top=el('div','sw-moment-top');
  top.append(el('b','',m.channel),el('span','cs-chip',m.kind_label),el('span','sw-score','erősség '+Number(m.score).toFixed(1)),el('small','sw-viewers',m.viewers?'👁 '+people(m.viewers)+' néző':''),el('small','',day(m.at)+(m.duration?' · '+Math.round(m.duration)+' mp':'')+(m.game?' · '+m.game:'')));
  c.append(top,el('p','',m.why));
  if(m.error)c.append(el('p','error-text',m.error));
  const row=el('div','cs-row');row.append(el('span','sw-status',m.produced?'Short készül vagy kész · Publikálás oldal':STATUS[m.status]||m.status));
  if(m.status==='found'||m.status==='failed')row.append(run('Jelenet kivágása',()=>op('watch_fetch',{id:m.id}),'secondary'));
  if(m.artifact)row.append(button('▶ Megnézem',()=>call('open_artifact',{id:m.artifact}),'secondary'));
  if(m.status==='ready'&&!m.produced)row.append(run('Short készítése belőle',()=>op('watch_produce',{id:m.id})));
  if(!m.produced)row.append(run('Elvetés',()=>op('watch_dismiss',{id:m.id}),'text-button'));
  c.append(row);return c;
 }

 function overview(page){
  const s=W.settings,n=W.counts,tiles=el('div','ko-tiles');
  const tile=(num,label,to,cls='')=>{const t=el('button','ko-tile '+cls);t.append(el('b','',String(num)),el('span','',label));t.onclick=()=>go(to);return t;};
  tiles.append(tile(n.live,'csatorna élő most','channels'),tile(n.watching,'adást figyel','channels',n.watching?'hot':''),tile(n.today,'pillanat az elmúlt 24 órában','moments'),tile(n.ready,'kivágott jelenet vár rád','moments',n.ready?'ok':''));
  page.append(tiles);
  const sw=card(s.enabled?'A figyelő be van kapcsolva':'A figyelő ki van kapcsolva','ko-next');
  sw.append(el('p','',s.enabled?'Pár percenként megnézi, ki élő a listádból, és csak annak a chatjét olvassa, aki épp a megadott játékot játssza. Feltölteni semmit nem tölt fel.':'Bekapcsolva magától figyeli a listádon lévő streamereket, és a chat-csúcsoknál kivágja a jelenetet. A gépnek és az ORBIT-nak futnia kell közben.'),
   run(s.enabled?'Kikapcsolás':'Figyelő bekapcsolása',()=>op('watch_save',{patch:{enabled:!s.enabled}}),s.enabled?'secondary':'primary'));
  page.append(sw);
  if(W.focus&&W.chart.length){const c=card('Chat · '+W.focus+' · utolsó 30 perc (üzenet / 15 mp)');const pick=el('div','cs-row');for(const ch of W.channels.filter(x=>x.watching)){const b=el('button','cs-chip'+(ch.channel===W.focus?' live':''),ch.channel);b.onclick=()=>{focus=ch.channel;load(true);};pick.append(b);}
   c.append(pick,chart(W.chart),el('p','hint','A függőleges vonalak a megtalált pillanatok. A csúcsot a csatorna saját, előző tíz percéhez méri, így egy nagy chat nem jelez folyton.'));page.append(c);}
  const best=W.moments.filter(m=>m.status!=='failed').slice(0,4);
  if(best.length){const c=card('Legutóbbi pillanatok');for(const m of best)c.append(momentCard(m));c.append(button('Mind →',()=>go('moments'),'text-button'));page.append(c);}
  else page.append(el('p','hint',s.enabled?'Még nincs pillanat. Amint egy figyelt adás chatje megugrik, itt jelenik meg.':'Kapcsold be a figyelőt, és a megtalált pillanatok itt jelennek meg.'));
 }

 function moments(page){
  if(!W.moments.length){page.append(el('p','hint','Még nincs megtalált pillanat.'));return;}
  const sorted=[...W.moments].sort((a,b)=>(b.status==='ready')-(a.status==='ready')||b.at-a.at);
  for(const m of sorted)page.append(momentCard(m));
 }

 const people=n=>n?String(n).replace(/\B(?=(\d{3})+(?!\d))/g,' '):'';
 function channels(page){
  const c=card('Figyelt csatornák · nézőszám szerint (Twitch + YouTube)');
  c.append(el('p','hint','Állapot utoljára ellenőrizve: '+(W.checked?clock(W.checked):'még nem')+'. Csak bekapcsolt figyelőnél frissül.'));
  for(const ch of W.channels){const row=el('div','sw-channel'+(ch.watching?' on':''));
   row.append(el('b','',ch.channel.startsWith('yt:')?'▶ '+ch.channel.slice(3):ch.channel),el('span','sw-viewers',ch.live&&ch.viewers?'👁 '+people(ch.viewers):''),el('span','cs-chip'+(ch.watching?' live':''),ch.watching?'● Figyeli':ch.live?'Élő · '+(ch.game||'más játék'):'Nincs adásban'),el('small','',ch.live?(ch.title||'').slice(0,90)+(ch.recording?'':' · nincs nyilvános felvétel, nem vágható'):''),
    run('Levétel',()=>op('watch_save',{patch:{channels:W.settings.channels.filter(x=>x!==ch.channel)}}),'text-button'));c.append(row);}
  const add=el('div','cs-row'),input=el('input');input.placeholder='Twitch-csatorna neve vagy YouTube-link (youtube.com/@név)';
  add.append(input,run('Hozzáadás',()=>op('watch_save',{patch:{channels:[...W.settings.channels,input.value]}}),'secondary'));c.append(add);page.append(c);
 }

 function settings(page){
  const s=W.settings,c=card('Mit és hogyan figyeljen');
  const field=(label,node,hint)=>{const f=el('label','sw-field');f.append(el('span','',label),node);if(hint)f.append(el('small','hint',hint));c.append(f);};
  const text=(key,ph)=>{const i=el('input');i.value=s[key]??'';i.placeholder=ph||'';i.onchange=()=>act(async()=>{await op('watch_save',{patch:{[key]:i.value}});await load(true);});return i;};
  const num=(key,min,max,step=1)=>{const i=el('input');i.type='number';i.min=min;i.max=max;i.step=step;i.value=s[key];i.onchange=()=>act(async()=>{await op('watch_save',{patch:{[key]:Number(i.value)}});await load(true);});return i;};
  const flag=(key)=>{const i=el('input');i.type='checkbox';i.checked=!!s[key];i.onchange=()=>act(async()=>{await op('watch_save',{patch:{[key]:i.checked}});await load(true);});return i;};
  field('Játék (Twitch-kategória)',text('game','üresen: bármilyen játék'),'Csak akkor figyel egy csatornát, amikor épp ezt játssza. Üresen hagyva bármilyen élő adáson kipróbálható (főpróba).');
  field('Indulás napja',text('not_before','ÉÉÉÉ-HH-NN'),'A megjelenés napja; előtte a játék kategóriáját nem figyeli.');
  field('Érzékenység',num('sensitivity',2.5,10,.5),'Hányszoros kiugrás kell a csatorna saját szokásos chatjéhez képest. Kisebb szám: több, gyengébb pillanat.');
  field('Másodperc a csúcs előtt',num('before',5,90),'Ennyi előzmény kerül a klip elejére, hogy látszódjon, mi váltotta ki a reakciót.');
  field('Másodperc a csúcs után',num('after',3,60));
  field('Legfeljebb ennyi pillanat óránként, csatornánként',num('per_hour',1,30),'A legerősebbek maradnak meg.');
  field('A jeleneteket magától kivágja',flag('auto_fetch'),'A még futó adás saját felvételéből tölti le a részletet; nem rögzít folyamatosan.');
  field('Short is készüljön belőlük magától',flag('auto_produce'),'A Clip Farm csapata feliratozza és álló formátumra vágja. A közzététel mindig rád vár a Publikálás oldalon.');
  field('Fel nem használt jelenetek megőrzése (nap)',num('keep_days',1,60));
  page.append(c);
 }

 const loadBefore=loadProjectApp,renderBefore=renderProjectApp;
 loadProjectApp=async function(){if(on()){if(currentApp!=='agents')return;if(!W||W.error)await load(true);return;}return loadBefore();};
 renderProjectApp=function(){if(on()){if(!paTyping())render();return;}return renderBefore();};
 const syncBefore=syncProjectApp;
 syncProjectApp=function(){if(projectAppFor!==project){W=null;sig='';focus=null;}syncBefore();if(on())$('studioApp')?.classList.add('clip-mode');};
})();
