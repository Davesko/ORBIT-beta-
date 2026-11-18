/* The mail in the main chat: the morning card, and the letters an answer points at. */
let briefSig='',briefHiddenId=null;
function resetBriefForNewChat(){briefSig='';briefHiddenId=null;$('commandBriefing')?.remove();}
function openMailById(id,account){mailOpenId=id;if(account)mailAccount=account;switchApp('email');}
function replyInMail(e){if(e.account)mailAccount=e.account;mailCompose({title:'Válasz',to:e.sender,subject:mailReplySubject(e.subject),body:e.draft,reply_to:e.id});}
function briefAgo(days){return days===0?'ma':days===1?'tegnap':days+' napja';}
function briefRender(b){const sig=JSON.stringify(b||null);if(sig===briefSig)return;briefSig=sig;$('commandBriefing')?.remove();if(!b||b.id&&b.id===briefHiddenId)return;
 if(!b.items&&!b.pending)return;
 const card=el('section','brief-card');card.id='commandBriefing';card.setAttribute('aria-label','Teendők a leveleid alapján');const head=el('div','brief-head');head.append(el('strong','','✉ Teendők a leveleid alapján'));
 if(b.id){const x=el('button','brief-close','×');x.setAttribute('aria-label','Elrejtés ebben a chatben');x.onclick=()=>{briefHiddenId=b.id;card.remove();};head.append(x);}card.append(head);
 if(!b.items){card.append(el('p','hint','Átnézem a leveleidet…'));$('commandScroll').prepend(card);return;}
 if(b.summary)card.append(el('p','brief-summary',b.summary));
 if(!b.items.length)card.append(el('p','hint','Nincs olyan levél, ami most rád vár.'));
 for(const it of b.items){const row=el('div','brief-item'),text=el('div','brief-text');const top=el('div','brief-top');top.append(el('span','brief-kind brief-'+it.kind,it.kind==='forgotten'?'Elfelejtett':'Teendő'),el('strong','',it.task));text.append(top);if(it.why)text.append(el('small','',it.why));text.append(el('small','',(it.sender_name||it.sender)+' · '+it.subject+' · '+briefAgo(it.days)));
  const acts=el('div','brief-acts');acts.append(button('Megnyitás',async()=>openMailById(it.email,it.account),'secondary'),button('Kész',async()=>{await call('project_app',{op:'briefing_done',args:{email:it.email}});row.remove();},'secondary'));row.append(text,acts);card.append(row);}
 $('commandScroll').prepend(card);}
function mailCards(list){const box=el('div','mail-cards');for(const e of list){const card=el('div','mail-card');const top=el('div','mail-card-top'),info=el('div');info.append(el('strong','',e.subject||'(nincs tárgy)'),el('small','',(e.sender_name||e.sender)+' · '+mailDate(e.date)));top.append(info);const acts=el('div','brief-acts');acts.append(button('Megnyitás',async()=>openMailById(e.id,e.account),'secondary'));if(e.draft&&!e.replied)acts.append(button('Szerkesztés és küldés',async()=>replyInMail(e),'primary'));top.append(acts);card.append(top);if(e.draft&&!e.replied)card.append(Object.assign(el('div','mail-card-draft'),{textContent:e.draft}));box.append(card);}return box;}
