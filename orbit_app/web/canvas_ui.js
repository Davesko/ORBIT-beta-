/* The main chat's split screen: the file the assistant made, next to the conversation. */
let canvasTabs=[],canvasActive=null,canvasMode='code',canvasSeen=new Set(),canvasPrimed=false;
async function canvasOp(op,args){return (await call('project_app',{op,args:args||{}})).result;}
function canvasPanel(){let p=$('canvasPanel');if(p)return p;
 p=el('aside','canvas-panel');p.id='canvasPanel';p.hidden=true;p.setAttribute('aria-label','Megnyitott fájl');
 const handle=el('div','canvas-handle');handle.setAttribute('role','separator');handle.setAttribute('aria-label','Panel szélessége');p.append(handle);
 p.append(Object.assign(el('div','canvas-tabs'),{id:'canvasTabs'}),Object.assign(el('div','canvas-tools'),{id:'canvasTools'}),Object.assign(el('div','canvas-body'),{id:'canvasBody'}),Object.assign(el('div','canvas-foot'),{id:'canvasFoot'}));
 $('commandApp').append(p);
 handle.onpointerdown=e=>{handle.setPointerCapture(e.pointerId);const box=$('commandApp').getBoundingClientRect();
  handle.onpointermove=m=>{const share=Math.min(.75,Math.max(.28,(box.right-m.clientX)/box.width));$('commandApp').style.setProperty('--canvas-share',share);try{localStorage.setItem('orbitCanvasShare',share);}catch(x){}};
  handle.onpointerup=()=>{handle.onpointermove=null;handle.onpointerup=null;};};
 try{const share=localStorage.getItem('orbitCanvasShare');if(share)$('commandApp').style.setProperty('--canvas-share',share);}catch(x){}
 return p;}
function canvasOf(id){return canvasTabs.find(t=>t.id===id);}
async function openCanvas(id){const tab=canvasOf(id);
 if(!tab)canvasTabs.push(await canvasOp('canvas_read',{id}));
 canvasActive=id;const now=canvasOf(id);canvasMode=now.previewable&&!tab?'preview':canvasMode==='preview'&&now.previewable?'preview':'code';renderCanvas();}
function closeCanvas(id){const tab=canvasOf(id);if(tab?.dirty&&!tab.confirmed){tab.confirmed=true;toast('Nem mentett módosítás. Mentsd el, vagy zárd be újra.');return;}
 canvasTabs=canvasTabs.filter(t=>t.id!==id);if(canvasActive===id)canvasActive=canvasTabs[canvasTabs.length-1]?.id||null;renderCanvas();}
function canvasText(tab){const area=$('canvasEditor');return area&&canvasActive===tab.id?area.value:tab.content;}
async function canvasSave(tab){const area=$('canvasEditor');if(area)tab.content=area.value;const fresh=await canvasOp('canvas_save',{id:tab.id,content:tab.content});Object.assign(tab,fresh,{dirty:false,confirmed:false});toast('Elmentve.');renderCanvas();}
function closeAllCanvas(){
 const current=canvasOf(canvasActive);if(current)current.content=canvasText(current);
 const dirty=canvasTabs.filter(t=>t.dirty);
 const close=()=>{canvasTabs=[];canvasActive=null;renderCanvas();};
 if(!dirty.length){close();return;}
 const body=el('div');body.append(el('p','',dirty.length+' fájlban nem mentett módosítás van.'));
 body.append(button('Mindet mentem és bezárom',async()=>{for(const t of dirty){const fresh=await canvasOp('canvas_save',{id:t.id,content:t.content});Object.assign(t,fresh,{dirty:false});}close();$('modal').close();},'primary'),
  button('Módosítások elvetése és bezárás',()=>{close();$('modal').close();},'secondary'),button('Mégse',()=>$('modal').close(),'secondary'));
 showModal('Összes fájl bezárása',body);
}
function canvasLines(area,gutter){const n=area.value.split('\n').length;gutter.textContent=Array.from({length:n},(_,i)=>i+1).join('\n');gutter.scrollTop=area.scrollTop;}
function markdownPreview(text){const box=el('div','canvas-markdown');box.append(typeof richText==='function'?richText(text):el('pre','',text));return box;}
function renderCanvas(){const panel=canvasPanel(),tab=canvasOf(canvasActive),split=!!tab&&!assistantOpen;panel.hidden=!split;$('commandApp').classList.toggle('canvas-open',split);if(!tab)return;
 const tabs=$('canvasTabs');tabs.replaceChildren();
 for(const t of canvasTabs){const b=el('div','canvas-tab'+(t.id===canvasActive?' active':''));const open=el('button','',(t.dirty?'● ':'')+t.name);open.onclick=()=>{if(canvasActive!==t.id){const cur=canvasOf(canvasActive);if(cur)cur.content=canvasText(cur);canvasActive=t.id;renderCanvas();}};
  b.append(open,el('small','','v'+t.version));const x=el('button','canvas-x','×');x.setAttribute('aria-label',t.name+' bezárása');x.onclick=()=>closeCanvas(t.id);b.append(x);tabs.append(b);}
 const tools=$('canvasTools');tools.replaceChildren();
 tools.append(button('Összes bezárása',closeAllCanvas,'canvas-close-all'));
 if(tab.previewable){for(const [mode,label] of [['preview','Előnézet'],['code','Kód']]){const b=el('button','canvas-mode'+(canvasMode===mode?' active':''),label);b.setAttribute('aria-pressed',String(canvasMode===mode));b.onclick=()=>{tab.content=canvasText(tab);canvasMode=mode;renderCanvas();};tools.append(b);}}
 else tools.append(el('span','canvas-lang',tab.language));
 const body=$('canvasBody');body.replaceChildren();
 if(canvasMode==='preview'&&tab.language==='html'){
  if(tab.dirty)body.append(el('p','canvas-note','Az előnézet az utoljára mentett változatot mutatja.'));
  const frame=el('iframe','canvas-frame');frame.setAttribute('sandbox','allow-scripts');frame.title=tab.name;frame.src='orbit-media://artifact/'+encodeURIComponent(tab.id)+'?project='+encodeURIComponent(tab.project)+'&v='+tab.version+'&t='+Math.floor(tab.updated);body.append(frame);frame.onload=()=>frame.focus();
 }else if(canvasMode==='preview'&&tab.language==='markdown')body.append(markdownPreview(tab.content));
 else{const wrap=el('div','canvas-code'),gutter=el('pre','canvas-gutter'),area=el('textarea','canvas-editor');area.id='canvasEditor';area.value=tab.content;area.spellcheck=false;area.setAttribute('aria-label',tab.name+' szerkesztése');
  area.oninput=()=>{tab.dirty=area.value!==tab.saved;tab.confirmed=false;canvasLines(area,gutter);const o=$('canvasTabs').querySelector('.canvas-tab.active button');if(o)o.textContent=(tab.dirty?'● ':'')+tab.name;};
  area.onscroll=()=>{gutter.scrollTop=area.scrollTop;};
  area.onkeydown=e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='s'){e.preventDefault();act(()=>canvasSave(tab));}if(e.key==='Tab'){e.preventDefault();area.setRangeText(' ',area.selectionStart,area.selectionEnd,'end');area.dispatchEvent(new Event('input'));}};
  wrap.append(gutter,area);body.append(wrap);canvasLines(area,gutter);}
 if(tab.saved===undefined||!tab.dirty)tab.saved=tab.content;
 const foot=$('canvasFoot');foot.replaceChildren();
 const undo=button('Visszavonás',async()=>{Object.assign(tab,await canvasOp('canvas_undo',{id:tab.id}),{dirty:false,saved:undefined});renderCanvas();},'secondary');undo.disabled=!tab.can_undo;
 const copy=button('Másolás',async()=>{await navigator.clipboard?.writeText(canvasText(tab));toast('A vágólapon.');},'secondary');
 foot.append(undo,button('Mentés',()=>canvasSave(tab),'secondary'),copy,el('span','canvas-spacer',''),button(tab.language==='html'?'Megnyitás böngészőben':'Megnyitás',()=>canvasOp('canvas_open',{id:tab.id}),'secondary'),button('Bezárás',async()=>closeCanvas(tab.id),'secondary'));}
function fileCard(a){const card=el('button','file-card');card.append(el('span','file-card-icon',/\.html?$/i.test(a.name)?'▶':'▤'),el('span','file-card-name',a.name),el('small','',/\.html?$/i.test(a.name)?'Megnyitás és futtatás':'Megnyitás'));card.onclick=()=>act(()=>openCanvas(a.id));return card;}
/* A file made or changed just now opens by itself; opening the app does not reopen old ones. */
let canvasDone=null;
function canvasNotice(turns){const files=turns.flatMap(t=>(t.artifacts||[]).filter(a=>a.kind==='text').map(a=>({key:t.id+':'+a.id,id:a.id})));const last=turns.filter(t=>t.status==='done').map(t=>t.id).pop()||null;
 if(!canvasPrimed){files.forEach(f=>canvasSeen.add(f.key));canvasDone=last;canvasPrimed=true;return;}
 for(const f of files)if(!canvasSeen.has(f.key)){canvasSeen.add(f.key);const open=canvasOf(f.id);if(open&&!open.dirty)canvasOp('canvas_read',{id:f.id}).then(x=>{Object.assign(open,x,{saved:undefined});canvasActive=f.id;renderCanvas();}).catch(()=>{});else if(!open)act(()=>openCanvas(f.id));}
 canvasDone=last;}
