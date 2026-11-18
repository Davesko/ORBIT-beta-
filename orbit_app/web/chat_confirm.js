/* Main chat: show how ORBIT understood a video request, with one-click stop or modify.
   Production still starts automatically; this only makes the interpretation visible. */
(()=>{
 const isUrl=q=>/^https?:\/\//i.test(q||'');
 function chips(actions){
  const out=[],start=actions.find(a=>a.type==='start_shorts');if(!start)return null;
  const style=actions.find(a=>a.type==='short_style_save')?.settings||{};
  const q=String(start.query||'');
  if(Array.isArray(start.sources)&&start.sources.length>1){out.push(start.sources.length+' videó összevágása');if(q&&!isUrl(q))out.push('kérés: '+q.slice(0,60));}
  else if(isUrl(q))out.push('forrás: YouTube-link');
  else{
   let topic=q.replace(/\b(latest stream|\d{4} stream|best moments|funny moments|highlights)\b/gi,'').replace(/\s+/g,' ').trim();
   out.push('téma: '+(topic||q).slice(0,50));
   if(/latest stream/i.test(q))out.push('friss stream');
   const year=q.match(/\b(20\d{2}) stream\b/i);if(year)out.push(year[1]+'-es stream');
   if(/best moments/i.test(q))out.push('best moments');else if(/funny moments/i.test(q))out.push('vicces pillanatok');else if(/highlights/i.test(q))out.push('kiemelt pillanatok');
  }
  if(style.min_seconds&&style.max_seconds)out.push(style.min_seconds+'–'+style.max_seconds+' mp'+(style.length_policy==='strict'?' · pontos':''));
  if(style.language)out.push(style.language==='hu'?'magyar':'angol');
  if(style.publish_to_youtube===true)out.push('feltöltés: be');else if(style.publish_to_youtube===false)out.push('feltöltés: ki');
  if(start.source_mode==='topic')out.push('témakeresés');
  const project=(state?.projects||[]).find(p=>p.id===start.project)?.name;
  return {chips:out,project:start.project,projectName:project};
 }
 const baseDraw=drawCommandTurn;
 drawCommandTurn=function(turn,...context){
  const group=baseDraw(turn,...context),info=turn.actions?.length?chips(turn.actions):null;
  if(!info)return group;
  const reply=group.querySelector('.command-turn.assistant');if(!reply)return group;
  const running=(turn.linked_jobs||[]).filter(j=>['queued','running'].includes(j.status));
  const card=el('div','understood-card');
  card.append(el('span','understood-title','Így értettem'+(info.projectName?' · '+info.projectName:'')));
  const row=el('div','understood-chips');for(const c of info.chips)row.append(el('span','understood-chip',c));card.append(row);
  const stop=async()=>{for(const j of running)await call('job_cancel',{id:j.id,requestProject:info.project});};
  const actions=el('div','understood-actions');
  if(running.length)actions.append(button('■ Leállítás',async()=>{await stop();toast('A gyártás leállt.');await pollCommand();},'secondary'));
  actions.append(button('✎ Módosítom',async()=>{if(running.length)await stop();const input=$('commandInput');input.value=turn.prompt;input.focus();input.setSelectionRange(input.value.length,input.value.length);toast(running.length?'Leállítottam. Javítsd a kérést, majd küldd újra.':'Javítsd a kérést, majd küldd újra.');await pollCommand();},'secondary'));
  card.append(actions);
  const plan=reply.querySelector('.command-plan');reply.insertBefore(card,plan||reply.querySelector('.inline-media-grid')||reply.querySelector('.linked-production,.error-text')||null);
  return group;
 };
})();
