const characterBeforeAtelier=characterMarkup;
characterMarkup=PixelWorld.character=function(color,type) {
  const asset=AtelierArt.sprite(type);
  return asset ? AtelierArt.image(asset,-26,-49,52,56,'sprite-raster') : characterBeforeAtelier(color,type);
};

// The existing SVG room geometry, doors, labels and pointer targets stay editable.
const buildBeforeAtelier=buildStation;
buildStation=function() {
  buildBeforeAtelier();
  const defs=$('station').querySelector('defs');
  defs.insertAdjacentHTML('beforeend','<pattern id="atelierWoodFloor" width="170" height="170" patternUnits="userSpaceOnUse"><image href="assets/workshop/floor-wood.png" width="170" height="170" preserveAspectRatio="xMidYMid slice"/></pattern>');
};
const cameraBeforeAtelier=setCamera;
setCamera=function(value,persist=true){
  cameraBeforeAtelier(value,persist);
  $('zoomReset').textContent='Nézethez igazítás';
  $('zoomReset').title='Teljes térkép · nagyítás: '+Math.round(value.scale*100)+'%';
  $('zoomReset').setAttribute('aria-label','Teljes térkép nézethez igazítása');
};

function atelierStage(node) {
  let payload={};try{payload=JSON.parse(node.job?.payload||'{}');}catch{}
  const role=automationData?.automations.find(a=>a.id===automationSelected)?.workflow?.find(s=>s.agent===node.agent);
  return ({research:'Trend',producer:'Tervezés',source:'Források',transcript:'Átirat',selection:'Történet',layout:'Képkivágás',render:'Vágás',metadata:'Csomagolás',verify:'Ellenőrzés'})[payload.auto_step||role?.role] ||
    (payload.farm_research?'Trendkutatás':role?.label) ||
    ({Pulse:'Trend',Atlas:'Források',Echo:'Átirat',Scout:'Történet',Pixel:'Vágás',Lex:'Felirat és hang',Reach:'Csomagolás',Vega:'Ellenőrzés',KING:'Tervezés'})[node.name] || 'Feladat';
}
function atelierStatus(node,live) {
  return node.status==='planned'?'Előkészítve':live?statusLabel(node.status):'Előkészítve';
}
function atelierOpenNode(node) {
  if(node.job)openAutomationStep(node.job);
  else {const a=state.agents.find(a=>a.id===node.agent);if(a)editAgent(a);}
}
makeAutomationMap=function(automation) {
  const {nodes,live}=pixelAutomationGraph(automation),section=el('section','automation-map atelier-flow');
  section.setAttribute('aria-label','Az automatizáció ügynökei és tényleges állapota');
  const heading=el('div','atelier-flow-heading');
  heading.append(el('strong','',live?'A folyamat útja':'Előkészített ügynöklánc'),el('span','',nodes.filter(n=>n.status==='done').length+' / '+nodes.length+' lépés kész'));
  section.append(heading);
  if(!nodes.length){section.append(el('p','hint','A csapat a kezdő ügynök vagy lánc kiválasztása után jelenik meg.'));return section;}
  const scroll=el('div','atelier-flow-scroll'),track=el('div','atelier-flow-track'),desks=el('div','atelier-desk-row');
  scroll.setAttribute('tabindex','0');scroll.setAttribute('aria-label','Ügynöklánc · vízszintesen görgethető');
  scroll.style.setProperty('--flow-min-width',nodes.length*112+'px');
  nodes.forEach((node,index)=>{
    const a=state.agents.find(a=>a.id===node.agent),type=a?characterFor(a.id):'robot',color=a?.color||'#b395d6';
    const cls=node.status==='done'?'complete':node.status==='running'?'running':node.status==='failed'||node.status==='blocked'?'failed':node.status==='planned'?'planned':'waiting';
    const next=nodes[index+1],b=button('',()=>atelierOpenNode(node),'atelier-flow-node is-'+cls+(next?.parents.includes(node.id)?' has-next':''));
    b.setAttribute('aria-label',node.name+' · '+atelierStage(node)+' · '+atelierStatus(node,live));
    const avatar=el('span','atelier-flow-avatar');avatar.innerHTML=`<svg viewBox="-32 -59 64 72" aria-hidden="true">${PixelWorld.character(color,type)}</svg>`;
    b.append(avatar,el('strong','',atelierStage(node)),el('span','',node.name),el('span','flow-status',atelierStatus(node,live)));
    const nonAdjacent=(node.parents||[]).filter(id=>id!==nodes[index-1]?.id).map(id=>nodes.find(n=>n.id===id)?.name).filter(Boolean);
    if(nonAdjacent.length)b.append(el('small','flow-status','Előfeltétel: '+nonAdjacent.join(', ')));
    track.append(b);
    const scene=el('div','atelier-desk-scene is-'+cls),desk=el('img');desk.src=AtelierArt.root+(type==='wizard'?'desk-editing':'desk-research')+'.png';desk.alt='';desk.loading='lazy';
    const figure=el('div','atelier-desk-character');figure.innerHTML=`<svg viewBox="-32 -59 64 72" aria-hidden="true">${PixelWorld.character(color,type)}</svg>`;
    scene.append(desk,figure);desks.append(scene);
  });
  scroll.append(track,desks);section.append(scroll);
  const focus=nodes.find(n=>n.status==='running')||nodes.find(n=>n.status==='failed'||n.status==='blocked')||nodes.find(n=>n.status==='queued')||[...nodes].reverse().find(n=>n.status==='done')||nodes[0];
  const card=el('div','atelier-flow-focus');card.append(el('h3','',focus.name+' · '+atelierStage(focus)));
  const explanation=focus.job?.runtime?.label||focus.job?.label||focus.job?.execution?.label||
    (focus.status==='planned'?'Ez az előkészített csapat. A folyamat az Indítás gombbal indítható.':atelierStatus(focus,live));
  card.append(el('p','',String(explanation).slice(0,450)),el('p','atelier-flow-total',live?'A jelölések a mentett feladatok állapotát mutatják.':'A csapat még nem fut; kattints egy ügynökre a beállításaihoz.'));
  card.append(button(focus.job?'Feladat megtekintése':'Ügynök beállításai',()=>atelierOpenNode(focus),'secondary'));section.append(card);
  const assistant=button('',()=>{$('guardianTrigger').click();$('commandInput').focus();},'atelier-assistant-link');
  assistant.setAttribute('aria-label','Beszélgetés megnyitása a fő asszisztenssel a folyamatról');
  const icon=el('img');icon.src=AtelierArt.root+'agent-goblin.png';icon.alt='';
  assistant.append(icon,el('span','','Kérdezz a folyamatról vagy adj utasítást…'),el('span','assistant-link-arrow','↗'));
  section.append(assistant);
  return section;
};

const renderAutomationsBeforeAtelier=renderAutomations;
renderAutomations=function() {
  renderAutomationsBeforeAtelier();
  const pane=$('automationDetail'),head=pane.querySelector('.automation-detail-head'),actions=pane.querySelector('.automation-actions');
  if(head&&actions){const bar=el('div','atelier-automation-toolbar');head.before(bar);bar.append(head,actions);}
  const automation=automationData?.automations.find(a=>a.id===automationSelected),overview=pane.querySelector('.automation-overview'),explanation=pane.querySelector('.automation-schedule-explanation'),flow=pane.querySelector('.atelier-flow');
  if(automation&&overview&&flow){
    const details=el('details','atelier-schedule-details');details.dataset.detailKey='atelier-schedule-'+automation.id;
    details.append(el('summary','','Feladat és időzítés'),overview);if(explanation)details.append(explanation);flow.after(details);
    const goal=el('span','atelier-daily-goal','Napi cél: '+automation.daily_goal+' · ma kész: '+automation.today.completed);
    pane.querySelector('.atelier-automation-toolbar')?.append(goal);
  }
  // Duplicated waiting descriptions remain on each actual stage instead of above the toolbar.
  for(const note of pane.querySelectorAll(':scope>.growth-note'))if(!note.querySelector('button'))note.remove();
  // Actual health/resume actions and errors remain present below the compact flow.
  const health=pane.querySelector('.automation-health');if(health)pane.append(health);
};

// Cosmetic wording only; event handlers and navigation identifiers remain unchanged.
const agentsNav=$('navAgents');
for(const n of [...agentsNav.childNodes])if(n.nodeType===Node.TEXT_NODE)n.textContent='Műhely';
document.body.classList.add('atelier-studio');
